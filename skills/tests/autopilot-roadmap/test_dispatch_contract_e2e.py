"""End-to-end dispatch contract: prepare -> child_start -> loop state ->
emit-result -> apply, for every terminal and parked shape (dispatch-contract
acceptance outcomes 2, 4, 5).

The child worktree is a real git repository under the supervisor's managed
root; the child side runs the real `runner.py` CLI in it, reading only its
launch marker; the supervisor side is the real `ExecutionAdapter` and gate
router. Only the capability probe, the coordinator transport and the audit
sink are faked.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from models import Effort, ItemStatus, Roadmap, RoadmapItem

_REPO_ROOT = Path(__file__).resolve().parents[3]
for _sub in ("supervise/scripts", "autopilot/scripts"):
    _path = str(_REPO_ROOT / "skills" / _sub)
    if _path not in sys.path:
        sys.path.append(_path)

import autopilot  # noqa: E402
import gate_router  # noqa: E402
import runner  # noqa: E402
from checkpoint import CheckpointManager  # noqa: E402
from execution import ExecutionAdapter  # noqa: E402
from shared import dispatch_contract  # noqa: E402
from shared.approval_gate import ApprovalGate  # noqa: E402
from shared.trust_posture import Gate  # noqa: E402

_CHANGE = "change-alpha"
_BRANCH = f"openspec/{_CHANGE}"
_HOST = "host-a"


def _git(cwd: Path, *argv: str) -> str:
    return subprocess.run(["git", *argv], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _probe(_repo: Path) -> tuple[int, str]:
    return 2, json.dumps(
        {
            "modes": {
                "review": {"verified": ["claude_code"], "unverified": [{"vendor": "codex", "reason": "cli_not_found"}]},
                "alternative": {"verified": ["claude_code"], "unverified": []},
                "quick": {"verified": ["claude_code"], "unverified": []},
            },
            "probe_command": "review_dispatcher.py --check-vendors --json",
            "quorum_policy": {
                "environment": "host",
                "min_quorum": {"PLAN_REVIEW": 2, "IMPL_REVIEW": 2, "VAL_REVIEW": 2},
                "policy_id": None,
                "sunset": None,
            },
        }
    )


class _Audit:
    def record(self, _record: dict[str, Any]) -> bool:
        return True


@pytest.fixture()
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    repo = tmp_path / "repo"
    schemas = repo / "openspec" / "schemas"
    schemas.mkdir(parents=True)
    for name in (
        "roadmap.schema.json",
        "checkpoint.schema.json",
        "supervisor-record.schema.json",
        "supervisor-record-mirror.schema.json",
    ):
        shutil.copy2(_REPO_ROOT / "openspec" / "schemas" / name, schemas / name)
    workspace = repo / "openspec" / "roadmaps" / "alpha"
    workspace.mkdir(parents=True)
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="alpha",
        source_proposal="proposal.md",
        items=[RoadmapItem("ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S, change_id=_CHANGE)],
    )
    (workspace / "roadmap.yaml").write_text(yaml.safe_dump(roadmap.to_dict(), sort_keys=False))

    managed = repo / ".git-worktrees"
    child = managed / _CHANGE
    child.mkdir(parents=True)
    _git(child, "init", "-q", "-b", _BRANCH)
    _git(child, "config", "user.email", "test@example.invalid")
    _git(child, "config", "user.name", "test")
    (child / ".gitignore").write_text(".supervised-dispatch/\n")
    autopilot.save_state(
        autopilot.LoopState(change_id=_CHANGE, current_phase="INIT"),
        child / "openspec" / "changes" / _CHANGE / "loop-state.json",
    )
    _git(child, "add", "-A")
    _git(child, "commit", "-q", "-m", "init")

    adapter = ExecutionAdapter(
        managed_worktree_root=managed,
        repo_root=repo,
        host_id=_HOST,
        branch_resolver=lambda path: _git(path, "rev-parse", "--abbrev-ref", "HEAD"),
        commit_resolver=lambda path: _git(path, "rev-parse", "HEAD"),
        liveness_probe=lambda _handle: "live",
        host_entry=lambda _change, _request: "entered",
        profile_probe=_probe,
    )
    approved = gate_router.answer(
        Gate.ROADMAP_APPROVAL, workspace=workspace, repo_root=repo, approved=True, note="e2e"
    )
    return {
        "repo": repo,
        "workspace": workspace,
        "child": child,
        "adapter": adapter,
        "roadmap_ref": f"gate-decision:{approved.record['decision_id']}",
        "monkeypatch": monkeypatch,
    }


def _launch(world: dict[str, Any], request: dict[str, Any], *, owner: str) -> None:
    adapter, workspace = world["adapter"], world["workspace"]
    generation = request["lease_generation"]
    adapter.child_start(
        workspace, dispatch_id=request["dispatch_id"], launch_token=request["launch_token"],
        lease_generation=generation, owner_nonce=owner,
    )
    adapter.acknowledge(workspace, dispatch_id=request["dispatch_id"], lease_generation=generation, handle=f"task-{generation}")
    adapter.enter(workspace, dispatch_id=request["dispatch_id"], lease_generation=generation, owner_nonce=owner)


def _prepare(world: dict[str, Any]) -> dict[str, Any]:
    prepared = world["adapter"].prepare(
        world["workspace"],
        repo_root=world["repo"],
        isolation_resolver=lambda _item: {
            "mode": "managed_worktree",
            "worktree_path": str(world["child"]),
            "branch": _BRANCH,
        },
        roadmap_approval_ref=world["roadmap_ref"],
    )
    request = prepared["requests"][0]
    assert dispatch_contract.validate_request(request) == request
    return request


def _child_commits_state(world: dict[str, Any], **fields: Any) -> None:
    child = world["child"]
    path = child / "openspec" / "changes" / _CHANGE / "loop-state.json"
    state = autopilot.load_state(path)
    for key, value in fields.items():
        setattr(state, key, value)
    autopilot.save_state(state, path)
    _git(child, "add", "openspec")
    _git(child, "commit", "-q", "-m", "loop state")


def _child_emits(world: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """The worker protocol: emit-result, commit the file, return its path."""
    child = world["child"]
    world["monkeypatch"].chdir(child)
    rc = runner.main(
        [
            "emit-result", _CHANGE,
            "--dispatch-id", request["dispatch_id"],
            "--generation", str(request["lease_generation"]),
            "--attempt", str(request["attempt"]),
        ]
    )
    assert rc == 0
    rel = dispatch_contract.result_relpath(_CHANGE, request["dispatch_id"], request["lease_generation"])
    _git(child, "add", rel)
    _git(child, "commit", "-q", "-m", "dispatch result")
    world["monkeypatch"].chdir(world["repo"])
    return json.loads((child / rel).read_text())


def _apply(world: dict[str, Any], request: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return world["adapter"].apply(
        world["workspace"],
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[result],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=world["repo"],
    )


def _attempt(world: dict[str, Any]) -> dict[str, Any]:
    return CheckpointManager(world["workspace"]).load().dispatch_attempts[0]


_GATES = [g.value for g in Gate if g is not Gate.ROADMAP_APPROVAL]
_SHAPES = [
    ("done-passed", {"current_phase": "DONE", "goal_gate": {"verdict": "passed"}, "last_handoff_id": "h-1", "handoff_ids": ["h-1"]}, "success", "completed"),
    ("done-abandoned", {"current_phase": "DONE", "goal_gate": {"verdict": "abandoned"}}, "failed:abandoned", "failed"),
    ("done-refused", {"current_phase": "DONE", "goal_gate": {"verdict": "refused"}, "last_handoff_id": "h-1"}, "failed:goal_gate_unverified", "failed"),
    ("escalate", {"current_phase": "ESCALATE", "previous_phase": "PLAN_REVIEW", "escalation_reason": "max_iter"}, "parked", "parked"),
    *[
        (f"pending-{gate}", {"current_phase": "PLAN", "pending_gate": {"gate": gate, "prompt": "Approve?"}}, "parked", "parked")
        for gate in _GATES
    ],
    (
        "park-permission",
        {"current_phase": "IMPLEMENT", "park": {
            "kind": "permission_blocked", "tool": "Bash", "rule": "Bash(env *)",
            "classifier_reason": "reads credentials", "command": "env", "reason": "denied"}},
        "parked", "parked",
    ),
    (
        "park-capability",
        {"current_phase": "PLAN_REVIEW", "park": {
            "kind": "capability_unavailable", "phase": "PLAN_REVIEW", "missing_lanes": ["codex"], "reason": "quorum"}},
        "parked", "parked",
    ),
]


@pytest.mark.parametrize(("name", "fields", "outcome", "status"), _SHAPES, ids=[s[0] for s in _SHAPES])
def test_every_shape_round_trips_through_emit_result_and_apply(
    world: dict[str, Any], name: str, fields: dict[str, Any], outcome: str, status: str
) -> None:
    request = _prepare(world)
    _launch(world, request, owner="owner-nonce-0000000001")
    _child_commits_state(world, **fields)

    result = _child_emits(world, request)
    assert dispatch_contract.validate_result(result) == result
    assert result["outcome"] == outcome
    assert result["worktree_ref"] == request["isolation"]["worktree_ref"]
    assert result["host_id"] == _HOST

    applied = _apply(world, request, result)

    assert _attempt(world)["status"] == status
    if outcome == "success":
        assert applied["completed_item_ids"] == ["ri-01"]
    elif outcome == "parked":
        assert applied["parked_item_ids"] == ["ri-01"]
    else:
        assert applied["failed_item_ids"] == ["ri-01"]


def _router_gate(repo: Path) -> ApprovalGate:
    return ApprovalGate(coordinator=object(), audit=_Audit(), repo_root=str(repo))


def _posture(root: Path, **gates: str) -> None:
    doc = {"schema_version": 1, "gates": {k: {"disposition": v} for k, v in gates.items()}}
    (root / "TRUST_POSTURE.md").write_text("---\n" + yaml.safe_dump(doc) + "---\n")


def _park_on_proposal_approval(world: dict[str, Any]) -> dict[str, Any]:
    request = _prepare(world)
    _launch(world, request, owner="owner-nonce-0000000001")
    _child_commits_state(
        world,
        current_phase="PLAN",
        pending_gate={
            "schema_version": 1, "change_id": _CHANGE, "gate": "proposal_approval", "phase": "PLAN",
            "requested_at": "2026-10-09T00:00:00+00:00", "prompt": "Approve?",
            "edge": {"outcome": "created", "target": "PLAN_ITERATE"},
            "posture": {"disposition": "block", "posture_present": True},
        },
    )
    _apply(world, request, _child_emits(world, request))
    return request


def test_a_posture_flip_resumes_the_child_which_leaves_plan(world: dict[str, Any]) -> None:
    repo, workspace, adapter = world["repo"], world["workspace"], world["adapter"]
    _posture(repo, proposal_approval="block")
    _park_on_proposal_approval(world)
    blocked = gate_router.resolve_parked(
        _attempt(world), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )
    assert blocked.outcome == "blocked"

    _posture(repo, proposal_approval="auto")
    _posture(world["child"], proposal_approval="auto")
    resolved = gate_router.resolve_parked(
        _attempt(world), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )
    assert resolved.outcome == "proceed"
    resumed = resolved.resume_result
    assert resumed["gate_answer"] == {
        "gate": "proposal_approval",
        "decision": "approved",
        "approval_ref": resumed["continuation"]["approval_ref"],
        "provenance": resolved.routed.record["provenance"],
    }

    # The child's next generation: its marker carries the typed answer.
    _launch(world, resumed, owner="owner-nonce-0000000002")
    world["monkeypatch"].chdir(world["child"])
    rc = runner.main(
        ["gate-answer", _CHANGE, "--gate", "proposal_approval", "--decision", "approved",
         "--approval-ref", resumed["gate_answer"]["approval_ref"]]
    )
    world["monkeypatch"].chdir(repo)
    assert rc == 0
    state = json.loads((world["child"] / "openspec" / "changes" / _CHANGE / "loop-state.json").read_text())
    assert state["pending_gate"] is None
    assert state["current_phase"] == "PLAN_ITERATE"
    assert state["gate_decisions"][-1]["provenance"]["source"] == "posture"


def test_a_human_rejection_survives_the_posture_flip(world: dict[str, Any]) -> None:
    repo, workspace, adapter = world["repo"], world["workspace"], world["adapter"]
    _posture(repo, proposal_approval="block")
    request = _park_on_proposal_approval(world)
    gate_router.resolve_parked(
        _attempt(world), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )
    gate_router.answer(
        "proposal_approval", workspace=workspace, repo_root=repo, approved=False,
        context={"dispatch_id": request["dispatch_id"], "change_id": _CHANGE, "verb": "resume"},
    )
    _posture(repo, proposal_approval="auto")

    resolution = gate_router.resolve_parked(
        _attempt(world), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )

    assert resolution.outcome == "blocked"
    assert resolution.routed.record["provenance"]["source"] == "human"
    assert _attempt(world)["status"] == "parked"


def _mirror_fingerprint_entries(repo: Path) -> list[dict[str, Any]]:
    from cycle_state import _extract_supervisor_record

    record = _extract_supervisor_record(gate_router._read_current_mirror(repo)) or {}
    return [e for e in record.get("pending_gates", []) if e.get("dedupe_fingerprint")]


@pytest.mark.parametrize(
    "park",
    [
        {"kind": "permission_blocked", "tool": "Bash", "rule": "Bash(env *)",
         "classifier_reason": "reads credentials", "command": 'curl -H "Authorization: Bearer abc123def"',
         "reason": "denied"},
        {"kind": "capability_unavailable", "phase": "PLAN_REVIEW", "missing_lanes": ["codex"], "reason": "quorum"},
    ],
    ids=["permission_blocked", "capability_unavailable"],
)
def test_a_capability_park_is_one_operator_escalation_that_resumes_the_child(
    world: dict[str, Any], park: dict[str, Any]
) -> None:
    repo, workspace, adapter = world["repo"], world["workspace"], world["adapter"]
    _posture(repo, escalate_resume="block")
    request = _prepare(world)
    _launch(world, request, owner="owner-nonce-0000000001")
    _child_commits_state(world, current_phase="IMPLEMENT", park=dict(park))
    applied = _apply(world, request, _child_emits(world, request))

    route = applied["escalation_route"]
    assert [entry["outcome"] for entry in route] == ["blocked"]
    entries = _mirror_fingerprint_entries(repo)
    assert len(entries) == 1
    assert [item["dispatch_id"] for item in entries[0]["dispatch_ids"]] == [request["dispatch_id"]]
    assert "abc123" not in json.dumps(CheckpointManager(workspace).load().gate_decisions)

    answered = gate_router.answer_escalation(
        entries[0]["dedupe_fingerprint"], workspace=workspace, repo_root=repo, approved=True, adapter=adapter,
    )
    assert len(answered["resumed"]) == 1
    resumed = answered["resumed"][0]
    assert resumed["continuation"]["kind"] == park["kind"]
    assert resumed["gate_answer"]["gate"] == "escalate_resume"

    # The child clears its park with the supervisor's answer.
    _launch(world, resumed, owner="owner-nonce-0000000002")
    world["monkeypatch"].chdir(world["child"])
    assert runner.main(
        ["gate-answer", _CHANGE, "--gate", "escalate_resume", "--decision", "approved",
         "--approval-ref", resumed["gate_answer"]["approval_ref"]]
    ) == 0
    world["monkeypatch"].chdir(repo)
    state = json.loads((world["child"] / "openspec" / "changes" / _CHANGE / "loop-state.json").read_text())
    assert state["park"] is None


# --------------------------------------------------------------------------- #
# Scoped auto end to end (acceptance outcome 8)
# --------------------------------------------------------------------------- #


def _child_gate_check(world: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """`runner.py gate-check --gate proposal_approval` in the child worktree,
    through the real default gate whose marker seam reads that worktree."""
    def build(change_id: str, repo_root: Path) -> ApprovalGate:
        return ApprovalGate(
            coordinator=object(), audit=_Audit(), repo_root=str(repo_root),
            marker_reader=autopilot.launch_marker_reader(change_id, repo_root),
        )

    world["monkeypatch"].setattr(autopilot, "_build_gate_evaluator", build)
    world["monkeypatch"].chdir(world["child"])
    rc = runner.main(["gate-check", _CHANGE, "--gate", "proposal_approval"])
    world["monkeypatch"].chdir(world["repo"])
    state = json.loads((world["child"] / "openspec" / "changes" / _CHANGE / "loop-state.json").read_text())
    return rc, state


def test_a_dispatched_child_with_a_marker_ref_takes_scoped_auto(world: dict[str, Any]) -> None:
    _posture(world["repo"], proposal_approval="auto")
    _posture(world["child"], proposal_approval="auto")
    request = _prepare(world)
    _launch(world, request, owner="owner-nonce-0000000001")
    _child_commits_state(world, current_phase="PLAN")

    rc, state = _child_gate_check(world)

    assert rc == runner.EXIT_NO_PENDING_GATE
    record = state["gate_decisions"][-1]
    assert record["outcome"] == "proceed"
    assert record["scope"] == "roadmap_approval"


def test_a_standalone_run_blocks_with_scope_unscoped(world: dict[str, Any]) -> None:
    _posture(world["child"], proposal_approval="auto")
    _child_commits_state(world, current_phase="PLAN")
    assert not (world["child"] / ".supervised-dispatch").exists()

    rc, state = _child_gate_check(world)

    assert rc == 0
    record = state["gate_decisions"][-1]
    assert record["outcome"] == "blocked"
    assert record["scope"] == "unscoped"
    assert state["pending_gate"]["gate"] == "proposal_approval"
