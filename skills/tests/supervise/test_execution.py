"""TDD lifecycle coverage for the leased supervised-execution host adapter."""

from __future__ import annotations

import ast
import fcntl
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

_SKILLS = Path(__file__).resolve().parents[2]
_RUNTIME_SCRIPTS = _SKILLS / "roadmap-runtime" / "scripts"
_SCRIPTS = _SKILLS / "supervise" / "scripts"
for script_dir in (_RUNTIME_SCRIPTS, _SCRIPTS):
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

from models import Effort, ItemStatus, Roadmap, RoadmapItem  # noqa: E402
import execution  # noqa: E402
import gate_router  # noqa: E402
from execution import ExecutionAdapter, ExecutionStateError  # noqa: E402
from shared.approval_gate import ApprovalDecision, ApprovalGate, Outcome, Resolution  # noqa: E402
from shared.trust_posture import (  # noqa: E402
    Disposition,
    Gate,
    GateDisposition,
    TrustPosture,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = Path(__file__).parent / "fixtures" / "execution" / "lifecycle"


class FakeClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)



def _profile_probe(_repo_root: Path) -> tuple[int, str]:
    """The supervisor's capability probe, faked (dispatch-contract D10): two
    verified review lanes and the default quorum."""
    return 0, json.dumps(
        {
            "modes": {
                "review": {"verified": ["claude_code", "codex"], "unverified": []},
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

def _write_work_packages(repo: Path, change_id: str) -> None:
    package = {
        "package_id": f"wp-{change_id}",
        "task_type": "implementation",
        "description": f"Fixture for {change_id}",
        "depends_on": [],
        "priority": 1,
        "locks": {"files": [], "keys": [f"feature:{change_id}:fixture"]},
        "scope": {"write_allow": [f"src/{change_id}/**"], "read_allow": ["**"]},
        "worktree": {"name": change_id},
        "timeout_minutes": 10,
        "retry_budget": 0,
        "min_trust_level": 0,
        "verification": {
            "tier_required": "C",
            "steps": [
                {
                    "name": "fixture",
                    "kind": "command",
                    "command": "true",
                    "evidence": {"artifacts": [], "result_keys": ["fixture"]},
                }
            ],
        },
        "outputs": {"result_keys": ["fixture"]},
    }
    document = {
        "schema_version": 1,
        "feature": {"id": change_id, "plan_revision": 1},
        "contracts": {
            "revision": 1,
            "openapi": {
                "primary": "contracts/openapi.yaml",
                "files": ["contracts/openapi.yaml"],
            },
        },
        "packages": [package],
    }
    path = repo / "openspec" / "changes" / change_id / "work-packages.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False))


#: The roots of the most recent fixture workspace: requests carry only a
#: host-portable worktree_ref (dispatch-contract D7), resolved here by `_wt`.
_ROOTS: dict[str, Path] = {}


def _wt(request: dict[str, Any]) -> Path:
    """The absolute worktree of a request's portable isolation, in this test host."""
    isolation = request["isolation"]
    base = _ROOTS["managed"] if isolation["mode"] == "managed_worktree" else _ROOTS["repo"]
    return base / isolation["worktree_ref"]


def _workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    schema_root = repo / "openspec" / "schemas"
    schema_root.mkdir(parents=True)
    for schema_name in (
        "roadmap.schema.json",
        "checkpoint.schema.json",
        "supervisor-record.schema.json",
        "supervisor-record-mirror.schema.json",
    ):
        (schema_root / schema_name).write_text(
            (_REPO_ROOT / "openspec" / "schemas" / schema_name).read_text()
        )
    workspace = repo / "roadmap"
    workspace.mkdir()
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="roadmap-host-adapter",
        source_proposal="proposal.md",
        items=[
            RoadmapItem(
                "ri-01",
                "Alpha",
                ItemStatus.APPROVED,
                1,
                Effort.S,
                change_id="change-alpha",
            )
        ],
    )
    (workspace / "roadmap.yaml").write_text(
        yaml.safe_dump(roadmap.to_dict(), sort_keys=False)
    )
    _write_work_packages(repo, "change-alpha")
    managed_root = repo / ".git-worktrees"
    _ROOTS.update(managed=managed_root.resolve(), repo=repo.resolve())
    worktree = managed_root / "change-alpha"
    (worktree / ".git").mkdir(parents=True)
    loop_state = worktree / "openspec" / "changes" / "change-alpha" / "loop-state.json"
    loop_state.parent.mkdir(parents=True, exist_ok=True)
    loop_state.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "change_id": "change-alpha",
                "current_phase": "INIT",
                "handoff_ids": [],
                "last_handoff_id": None,
                "pending_gate": None,
            }
        )
        + "\n"
    )
    return repo, workspace, managed_root


def _use_linked_worktree_layout(managed_root: Path) -> Path:
    worktree = managed_root / "change-alpha"
    git_entry = worktree / ".git"
    shutil.rmtree(git_entry)
    git_entry.write_text("gitdir: /tmp/fake-linked-worktree-gitdir\n")
    loop_state = worktree / "openspec" / "changes" / "change-alpha" / "loop-state.json"
    loop_state.parent.mkdir(parents=True, exist_ok=True)
    loop_state.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "change_id": "change-alpha",
                "current_phase": "DONE",
                "goal_gate": {"verdict": "passed"},
                "last_handoff_id": "handoff-alpha-001",
                "handoff_ids": ["handoff-alpha-001"],
            }
        )
        + "\n"
    )
    return loop_state


def _adapter(
    managed_root: Path,
    clock: FakeClock,
    *,
    liveness: str = "live",
    host_calls: list[tuple[str, dict[str, Any]]] | None = None,
) -> ExecutionAdapter:
    calls = host_calls if host_calls is not None else []
    return ExecutionAdapter(
        profile_probe=_profile_probe,
        managed_worktree_root=managed_root,
        repo_root=managed_root.parent,
        clock=clock,
        branch_resolver=lambda _: "openspec/change-alpha",
        commit_resolver=lambda _: "a" * 40,
        liveness_probe=lambda _: liveness,
        host_entry=lambda change_id, request: calls.append((change_id, request)) or "entered",
    )


class _RecordingAudit:
    def record(self, _record: dict[str, Any]) -> bool:
        return True


def _escalation_service(disposition: Disposition) -> ApprovalGate:
    posture = TrustPosture(
        gates={Gate.ESCALATE_RESUME: GateDisposition(disposition)},
        present=True,
    )
    return ApprovalGate(
        coordinator=object(),
        audit=_RecordingAudit(),
        posture_loader=lambda repo_root=None, path=None: posture,
    )


def _isolation(managed_root: Path) -> dict[str, str]:
    return {
        "mode": "managed_worktree",
        "worktree_path": str(managed_root / "change-alpha"),
        "branch": "openspec/change-alpha",
    }


def approve_roadmap(workspace: Path, repo: Path, *, note: str = "test fixture") -> str:
    """Console-approve `roadmap_approval` for the fixture roadmap and return the
    resulting `gate-decision:<id>` reference, for tests that need a valid
    `roadmap_approval_ref` to pass to `ExecutionAdapter.prepare`."""
    routed = gate_router.answer(
        Gate.ROADMAP_APPROVAL, workspace=workspace, repo_root=repo, approved=True, note=note
    )
    return f"gate-decision:{routed.record['decision_id']}"


def approve_parked(
    workspace: Path, repo: Path, attempt: dict[str, Any], *, gate: str = "pr_creation"
) -> str:
    """Append a `proceed` gate-decision record for a parked child's own gate,
    correlated to its `dispatch_id`, and return the resulting `approval_ref`,
    for tests exercising the lease/generation state machine directly (not
    through `resolve_parked`, so no prior parked router record exists for
    `gate_router.answer` to require)."""
    from shared.approval_gate import (
        ApprovalDecision,
        Disposition as _ApprovalDisposition,
        Outcome as _ApprovalOutcome,
        Resolution as _ApprovalResolution,
        build_gate_decision_record,
    )

    import uuid as _uuid

    gate_enum = gate if isinstance(gate, Gate) else Gate(gate)
    decision = ApprovalDecision(
        gate=gate_enum,
        outcome=_ApprovalOutcome.PROCEED,
        resolution=_ApprovalResolution.AUTO,
        disposition=_ApprovalDisposition.AUTO,
        reason=f"gate {gate_enum.value!r} auto-approved by test fixture",
        posture_present=True,
    )
    record = build_gate_decision_record(
        decision,
        phase="SUPERVISE",
        extra={
            "decision_id": str(_uuid.uuid4()),
            "source": "supervise",
            "verb": "resume",
            "roadmap_id": "roadmap-host-adapter",
            "dispatch_id": attempt["dispatch_id"],
            "change_id": attempt.get("change_id"),
        },
    )
    # No repo_root: matches execution.py's own _load_attempt, which loads
    # unvalidated (checkpoint.schema.json disallows the delegated-dispatch
    # `resume_hint` field the parked fixture legitimately carries -- a
    # pre-existing schema/fixture mismatch outside ri-04's scope; validating
    # here would fail on state execution.py itself never validates).
    manager = gate_router.CheckpointManager(workspace)
    checkpoint = manager.load() if manager.exists() else manager.create(
        gate_router.load_roadmap(workspace / "roadmap.yaml", repo)
    )
    manager.record_gate_decision(checkpoint, record)
    return f"gate-decision:{record['decision_id']}"


def _prepare(
    adapter: ExecutionAdapter,
    workspace: Path,
    repo: Path,
    managed_root: Path,
    *,
    context: dict[str, Any] | None = None,
    roadmap_approval_ref: str | None = None,
) -> dict[str, Any]:
    return adapter.prepare(
        workspace,
        repo_root=repo,
        isolation_resolver=lambda _: _isolation(managed_root),
        roadmap_approval_ref=roadmap_approval_ref or approve_roadmap(workspace, repo),
        context=context,
    )


def _attempt(workspace: Path) -> dict[str, Any]:
    checkpoint = json.loads((workspace / "checkpoint.json").read_text())
    return checkpoint["dispatch_attempts"][0]


def _result(name: str, request: dict[str, Any]) -> dict[str, Any]:
    value = json.loads((_FIXTURES / name).read_text())
    # The lifecycle fixtures are version-1 documents; build the version-2
    # result emit-result produces (dispatch-contract D1, D7).
    value.pop("worktree_path", None)
    value.update(
        schema_version=2,
        dispatch_id=request["dispatch_id"],
        change_id=request["change_id"],
        attempt=request["attempt"],
        lease_generation=request["lease_generation"],
        worktree_ref=request["isolation"]["worktree_ref"],
        branch=request["isolation"]["branch"],
        host_id=request["isolation"]["host_id"],
        degradations=[],
    )
    loop_state_path = (
        _wt(request)
        / "openspec"
        / "changes"
        / request["change_id"]
        / "loop-state.json"
    )
    if value["outcome"] == "success":
        loop_state = {
            "schema_version": 5,
            "change_id": request["change_id"],
            "current_phase": "DONE",
            "goal_gate": {"verdict": "passed"},
            "handoff_ids": [value["handoff_id"]],
            "last_handoff_id": value["handoff_id"],
            "pending_gate": None,
        }
    else:
        loop_state = {
            "schema_version": 5,
            "change_id": request["change_id"],
            "current_phase": "VALIDATE",
            "handoff_ids": [],
            "last_handoff_id": None,
            "pending_gate": {"gate": value["parked"].get("gate")},
        }
    loop_state_path.write_text(json.dumps(loop_state) + "\n")
    value["evidence"] = {
        "loop_state_path": f"openspec/changes/{request['change_id']}/loop-state.json",
        "commit": "a" * 40,
        "loop_state_digest": hashlib.sha256(loop_state_path.read_bytes()).hexdigest(),
    }
    return value


def _launch(
    adapter: ExecutionAdapter,
    workspace: Path,
    request: dict[str, Any],
    *,
    owner: str = "owner-nonce-0001",
) -> None:
    adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=request["lease_generation"],
        owner_nonce=owner,
    )
    adapter.acknowledge(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=request["lease_generation"],
        handle="task-alpha-001",
    )
    adapter.enter(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=request["lease_generation"],
        owner_nonce=owner,
    )


def test_lifecycle_fixtures_are_schema_valid() -> None:
    schema_root = (
        _REPO_ROOT
        / "openspec"
        / "contracts"
        / "roadmap-orchestration"
        / "schemas"
    )
    result_validator = Draft202012Validator(
        json.loads((schema_root / "supervised-dispatch-result.schema.json").read_text()),
        format_checker=FormatChecker(),
    )
    context_validator = Draft202012Validator(
        json.loads((schema_root / "bounded-dispatch-context.schema.json").read_text()),
        format_checker=FormatChecker(),
    )

    assert list(result_validator.iter_errors(json.loads((_FIXTURES / "success-result.json").read_text()))) == []
    assert list(result_validator.iter_errors(json.loads((_FIXTURES / "parked-result.json").read_text()))) == []
    assert list(context_validator.iter_errors(json.loads((_FIXTURES / "router-context.json").read_text()))) == []


def test_prepare_sanitizes_router_context_before_checkpoint_persistence(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    clock = FakeClock()
    context = json.loads((_FIXTURES / "router-context.json").read_text())

    prepared = _prepare(_adapter(managed_root, clock), workspace, repo, managed_root, context=context)

    assert prepared["requests"][0]["context"] == context
    assert _attempt(workspace)["context"] == context


@pytest.mark.parametrize(
    "unsafe",
    [
        {"routing": {"metadata": {"Api_Token": "nope"}}},
        {"a": {"b": {"c": {"d": {"too_deep": True}}}}},
        {"routing": {"raw-response": "SENTINEL_DO_NOT_PERSIST"}},
        {"items": list(range(65))},
        {f"key-{index}": index for index in range(33)},
        {"value": "x" * 4097},
        {f"field-{index}": "x" * 3500 for index in range(5)},
    ],
)
def test_prepare_rejects_unsafe_nested_context_before_any_checkpoint_write(
    tmp_path: Path,
    unsafe: dict[str, Any],
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)

    with pytest.raises(ValueError, match="dispatch context"):
        # Context validation is the cheapest, first-run check inside prepare() --
        # it must reject before the approval-ref check ever touches the
        # checkpoint, so a placeholder ref (never resolved) proves that.
        _prepare(
            _adapter(managed_root, FakeClock()), workspace, repo, managed_root, context=unsafe,
            roadmap_approval_ref="gate-decision:00000000-0000-0000-0000-000000000000",
        )

    assert not (workspace / "checkpoint.json").exists()


def test_prepare_rejects_missing_approval_ref_without_creating_checkpoint(tmp_path: Path) -> None:
    """A checkpoint that has never been saved has no gate_decisions, so an
    approval_ref can never resolve against it -- require_approval_ref must
    refuse before prepare() bootstraps checkpoint.json, not after."""
    repo, workspace, managed_root = _workspace(tmp_path)

    with pytest.raises(gate_router.ApprovalRefError):
        _prepare(
            _adapter(managed_root, FakeClock()), workspace, repo, managed_root,
            roadmap_approval_ref="gate-decision:00000000-0000-0000-0000-000000000000",
        )

    assert not (workspace / "checkpoint.json").exists()


def test_prepare_rejects_managed_isolation_before_launch_or_attempt_persistence(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    outside = repo / "outside"
    outside.mkdir()
    adapter = _adapter(managed_root, FakeClock())

    prepared = adapter.prepare(
        workspace,
        repo_root=repo,
        isolation_resolver=lambda _: {
            "mode": "managed_worktree",
            "worktree_path": str(outside),
            "branch": "openspec/change-alpha",
        },
        roadmap_approval_ref=approve_roadmap(workspace, repo),
    )

    assert prepared["requests"] == []
    assert prepared["failures"] == [
        {"item_id": "ri-01", "reason": "isolation_resolution_failed:ValueError"}
    ]
    assert json.loads((workspace / "checkpoint.json").read_text()).get(
        "dispatch_attempts", []
    ) == []


def test_prepare_rejects_exact_managed_branch_mismatch(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = ExecutionAdapter(
        profile_probe=_profile_probe,
        managed_worktree_root=managed_root,
        clock=FakeClock(),
        branch_resolver=lambda _: "openspec/wrong-change",
        commit_resolver=lambda _: "a" * 40,
        liveness_probe=lambda _: "live",
        host_entry=lambda *_: pytest.fail("host entry must not run"),
    )

    prepared = _prepare(adapter, workspace, repo, managed_root)

    assert prepared["requests"] == []
    assert prepared["failures"] == [
        {"item_id": "ri-01", "reason": "isolation_resolution_failed:ValueError"}
    ]
    assert _attempt_count(workspace) == 0


def _attempt_count(workspace: Path) -> int:
    path = workspace / "checkpoint.json"
    return len(json.loads(path.read_text()).get("dispatch_attempts", [])) if path.exists() else 0


def test_child_start_waits_for_durable_ack_and_go_before_host_entry(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    clock = FakeClock()
    host_calls: list[tuple[str, dict[str, Any]]] = []
    adapter = _adapter(managed_root, clock, host_calls=host_calls)
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]

    claimed = adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
    )
    assert claimed["status"] == "claimed"
    assert claimed["launch_gate"]["state"] == "waiting_ack"
    assert Path(_wt(request), request["launch_marker_path"]).exists()
    with pytest.raises(ValueError, match="go has not been released"):
        adapter.enter(
            workspace,
            dispatch_id=request["dispatch_id"],
            lease_generation=1,
            owner_nonce="owner-nonce-0001",
        )
    assert host_calls == []

    acknowledged = adapter.acknowledge(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=1,
        handle="task-alpha-001",
    )
    assert acknowledged["status"] == "acknowledged"
    assert acknowledged["launch_gate"]["state"] == "go_released"
    entered = adapter.enter(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
    )
    assert entered["status"] == "launched"
    assert entered["launch_gate"]["state"] == "entered"
    assert [change_id for change_id, _ in host_calls] == ["change-alpha"]


def test_marker_collision_refuses_duplicate_owner_without_state_change(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    marker = Path(_wt(request), request["launch_marker_path"])
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("other-owner\n")

    with pytest.raises(FileExistsError):
        adapter.child_start(
            workspace,
            dispatch_id=request["dispatch_id"],
            launch_token=request["launch_token"],
            lease_generation=1,
            owner_nonce="owner-nonce-0001",
        )

    assert _attempt(workspace)["status"] == "prepared"


def test_child_start_supports_real_linked_worktree_gitfile(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    _use_linked_worktree_layout(managed_root)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]

    claimed = adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
    )

    marker = Path(_wt(request), request["launch_marker_path"])
    assert claimed["status"] == "claimed"
    assert not request["launch_marker_path"].startswith(".git/")
    assert marker.is_file()


def test_child_start_rejects_unbounded_owner_nonce_before_persistence(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]

    with pytest.raises(ValueError, match="owner nonce"):
        adapter.child_start(
            workspace,
            dispatch_id=request["dispatch_id"],
            launch_token=request["launch_token"],
            lease_generation=1,
            owner_nonce="x" * 257,
        )

    assert _attempt(workspace)["status"] == "prepared"


def test_enter_revalidates_managed_branch_before_host_entry(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    host_calls: list[tuple[str, dict[str, Any]]] = []
    branch = {"value": "openspec/change-alpha"}
    adapter = ExecutionAdapter(
        profile_probe=_profile_probe,
        managed_worktree_root=managed_root,
        clock=FakeClock(),
        branch_resolver=lambda _: branch["value"],
        commit_resolver=lambda _: "a" * 40,
        liveness_probe=lambda _: "live",
        host_entry=lambda change_id, request: host_calls.append((change_id, request)),
    )
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
    )
    adapter.acknowledge(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=1,
        handle="task-alpha-001",
    )
    branch["value"] = "openspec/wrong-change"

    with pytest.raises(ValueError, match="branch"):
        adapter.enter(
            workspace,
            dispatch_id=request["dispatch_id"],
            lease_generation=1,
            owner_nonce="owner-nonce-0001",
        )

    assert host_calls == []
    assert _attempt(workspace)["status"] == "acknowledged"


def test_waiting_heartbeat_is_child_owned_and_generation_bound(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    clock = FakeClock()
    adapter = _adapter(managed_root, clock)
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
    )
    before = _attempt(workspace)["lease"]["heartbeat_at"]
    clock.advance(10)

    updated = adapter.heartbeat_waiting(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
    )
    assert updated["lease"]["heartbeat_at"] != before
    with pytest.raises(ValueError, match="lease owner"):
        adapter.heartbeat_waiting(
            workspace,
            dispatch_id=request["dispatch_id"],
            lease_generation=1,
            owner_nonce="owner-nonce-other",
        )



def test_waiting_heartbeat_and_acknowledgement_serialize_checkpoint_mutations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
    )

    original_save = execution.CheckpointManager.save
    heartbeat_at_save = threading.Event()
    acknowledge_at_save = threading.Event()
    release_heartbeat = threading.Event()
    errors: list[BaseException] = []

    def delayed_save(manager: Any, checkpoint: Any) -> None:
        if threading.current_thread().name == "heartbeat-writer":
            heartbeat_at_save.set()
            assert release_heartbeat.wait(timeout=5)
        elif threading.current_thread().name == "acknowledgement-writer":
            acknowledge_at_save.set()
        original_save(manager, checkpoint)

    monkeypatch.setattr(execution.CheckpointManager, "save", delayed_save)

    def heartbeat() -> None:
        try:
            adapter.heartbeat_waiting(
                workspace,
                dispatch_id=request["dispatch_id"],
                lease_generation=1,
                owner_nonce="owner-nonce-0001",
            )
        except BaseException as error:  # pragma: no cover - surfaced below
            errors.append(error)

    def acknowledge() -> None:
        try:
            adapter.acknowledge(
                workspace,
                dispatch_id=request["dispatch_id"],
                lease_generation=1,
                handle="task-alpha-001",
            )
        except BaseException as error:  # pragma: no cover - surfaced below
            errors.append(error)

    heartbeat_thread = threading.Thread(target=heartbeat, name="heartbeat-writer")
    acknowledge_thread = threading.Thread(
        target=acknowledge,
        name="acknowledgement-writer",
    )
    heartbeat_thread.start()
    assert heartbeat_at_save.wait(timeout=5)
    acknowledge_thread.start()
    serialized = not acknowledge_at_save.wait(timeout=0.2)
    release_heartbeat.set()
    heartbeat_thread.join(timeout=5)
    acknowledge_thread.join(timeout=5)

    assert serialized, "acknowledgement raced a waiting-heartbeat checkpoint write"
    assert not errors
    assert _attempt(workspace)["status"] == "acknowledged"


def test_hard_termination_before_claim_persistence_cannot_orphan_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    marker = Path(_wt(request), request["launch_marker_path"])

    def terminate_before_persistence(*_args: Any, **_kwargs: Any) -> None:
        raise SystemExit("simulated hard termination")

    monkeypatch.setattr(
        execution.CheckpointManager,
        "save",
        terminate_before_persistence,
    )

    with pytest.raises(SystemExit, match="simulated hard termination"):
        adapter.child_start(
            workspace,
            dispatch_id=request["dispatch_id"],
            launch_token=request["launch_token"],
            lease_generation=1,
            owner_nonce="owner-nonce-0001",
        )

    assert not marker.exists()
    assert _attempt(workspace)["status"] == "prepared"


def test_expired_pre_go_claim_allows_generation_cas_takeover(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    clock = FakeClock()
    adapter = _adapter(managed_root, clock)
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
        lease_seconds=5,
    )
    clock.advance(6)

    reclaimed = adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=1,
        owner_nonce="owner-nonce-0002",
    )

    assert reclaimed["lease_generation"] == 2
    assert reclaimed["lease"]["generation"] == 2
    assert reclaimed["lease"]["owner_nonce"] == "owner-nonce-0002"
    assert [entry["state"] for entry in reclaimed["launch_history"][-2:]] == [
        "stale_takeover",
        "claimed",
    ]
    with pytest.raises(ValueError, match="generation"):
        adapter.acknowledge(
            workspace,
            dispatch_id=request["dispatch_id"],
            lease_generation=1,
            handle="stale-task",
        )
    adapter.acknowledge(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=2,
        handle="task-alpha-002",
    )
    with pytest.raises(ValueError, match="generation"):
        adapter.enter(
            workspace,
            dispatch_id=request["dispatch_id"],
            lease_generation=1,
            owner_nonce="owner-nonce-0001",
        )


def test_harness_provided_isolation_preserves_exact_external_path_and_branch(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    harness_path = repo / "harness-checkout"
    (harness_path / ".git" / "autopilot").mkdir(parents=True)
    adapter = ExecutionAdapter(
        profile_probe=_profile_probe,
        managed_worktree_root=managed_root,
        clock=FakeClock(),
        branch_resolver=lambda path: "harness/session-123"
        if path == harness_path.resolve()
        else "unexpected",
        commit_resolver=lambda _: "a" * 40,
        liveness_probe=lambda _: "live",
        host_entry=lambda *_: "entered",
    )

    prepared = adapter.prepare(
        workspace,
        repo_root=repo,
        isolation_resolver=lambda _: {
            "mode": "harness_provided",
            "worktree_path": str(harness_path),
            "branch": "harness/session-123",
        },
        roadmap_approval_ref=approve_roadmap(workspace, repo),
    )

    assert prepared["requests"][0]["isolation"] == {
        "mode": "harness_provided",
        "worktree_ref": "harness-checkout",
        "branch": "harness/session-123",
        "host_id": adapter.host_id,
    }


def test_positive_live_reconciliation_preserves_generation_and_owner(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock(), liveness="live")
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    before = _attempt(workspace)

    reconciled = adapter.reconcile(workspace, dispatch_id=request["dispatch_id"])

    assert reconciled == before
    assert reconciled["lease_generation"] == 1
    assert reconciled["lease"]["owner_nonce"] == "owner-nonce-0001"


def test_unknown_post_go_liveness_quarantines_and_never_resumes(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock(), liveness="unknown")
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)

    reconciled = adapter.reconcile(workspace, dispatch_id=request["dispatch_id"])

    assert reconciled["status"] == "quarantined"
    assert reconciled["lease"]["state"] == "uncertain"
    with pytest.raises(ValueError, match="quarantined"):
        adapter.resume(
            workspace,
            dispatch_id=request["dispatch_id"],
            approval_ref="approval-001",
            kind="pending_gate",
        )


def test_only_positive_task_death_allows_post_go_generation_takeover(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    clock = FakeClock()
    adapter = _adapter(managed_root, clock, liveness="dead")
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)

    reclaimed = adapter.reconcile(workspace, dispatch_id=request["dispatch_id"])

    assert reclaimed["status"] == "prepared"
    assert reclaimed["lease_generation"] == 2
    # The dead generation's token is revoked (D6); reissue mints the next one.
    with pytest.raises(execution.ExecutionStateError, match="launch token mismatch"):
        adapter.child_start(
            workspace,
            dispatch_id=request["dispatch_id"],
            launch_token=request["launch_token"],
            lease_generation=2,
            owner_nonce="owner-nonce-0002",
        )
    reissued = adapter.reissue(workspace, dispatch_id=request["dispatch_id"])
    assert reissued["lease_generation"] == 2
    restarted = adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=reissued["launch_token"],
        lease_generation=2,
        owner_nonce="owner-nonce-0002",
    )
    assert restarted["status"] == "claimed"


def test_parked_attempt_releases_lease_and_authorized_resume_increments_generation(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("parked-result.json", request)

    applied = adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[result],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    assert applied["parked_item_ids"] == ["ri-01"]
    assert _attempt(workspace)["lease"]["state"] == "released"

    ref = approve_parked(workspace, repo, _attempt(workspace), gate="pr_creation")
    resumed = adapter.resume(
        workspace,
        dispatch_id=request["dispatch_id"],
        approval_ref=ref,
        kind="pending_gate",
    )
    assert resumed["dispatch_id"] == request["dispatch_id"]
    assert resumed["attempt"] == request["attempt"]
    # D6: a token is minted per launch generation.
    assert resumed["launch_token"] != request["launch_token"]
    assert _attempt(workspace)["launch_digest"] == (
        "sha256:" + hashlib.sha256(resumed["launch_token"].encode()).hexdigest()
    )
    assert resumed["lease_generation"] == 2
    assert resumed["continuation"] == {
        "kind": "pending_gate",
        "approval_ref": ref,
    }
    with pytest.raises(ValueError, match="not parked"):
        adapter.resume(
            workspace,
            dispatch_id=request["dispatch_id"],
            approval_ref=ref,
            kind="pending_gate",
        )


def test_resumed_parked_generation_runs_normal_ack_go_with_exact_continuation(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    host_calls: list[tuple[str, dict[str, Any]]] = []
    adapter = _adapter(managed_root, FakeClock(), host_calls=host_calls)
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    parked = _result("parked-result.json", request)
    adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[parked],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    resumed = adapter.resume(
        workspace,
        dispatch_id=request["dispatch_id"],
        approval_ref=approve_parked(workspace, repo, _attempt(workspace), gate="pr_creation"),
        kind="pending_gate",
    )

    claimed = adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=resumed["launch_token"],
        lease_generation=2,
        owner_nonce="owner-nonce-0002",
    )
    assert claimed["status"] == "claimed"
    adapter.acknowledge(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=2,
        handle="task-alpha-002",
    )
    entered = adapter.enter(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=2,
        owner_nonce="owner-nonce-0002",
    )

    assert entered["status"] == "launched"
    assert host_calls[-1][1]["continuation"] == resumed["continuation"]
    with pytest.raises(ValueError):
        adapter.enter(
            workspace,
            dispatch_id=request["dispatch_id"],
            lease_generation=1,
            owner_nonce="owner-nonce-0001",
        )
    marker = Path(_wt(request), request["launch_marker_path"])
    marker_record = json.loads(marker.read_text())
    assert marker_record["generation"] == 2
    assert marker_record["owner_nonce"] == "owner-nonce-0002"


def test_resumed_parked_generation_accepts_fresh_success_result(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    parked = _result("parked-result.json", request)
    adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[parked],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    resumed = adapter.resume(
        workspace,
        dispatch_id=request["dispatch_id"],
        approval_ref=approve_parked(
            workspace, repo, _attempt(workspace), gate="pr_creation"
        ),
        kind="pending_gate",
    )
    _launch(adapter, workspace, resumed, owner="owner-nonce-0002")
    succeeded = _result("success-result.json", resumed)

    applied = adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[succeeded],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )

    assert applied["completed_item_ids"] == ["ri-01"]
    assert _attempt(workspace)["outcome"] == "success"


def test_apply_replaces_legacy_parked_journal_after_resume(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    parked = _result("parked-result.json", request)
    adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[parked],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    legacy_journal = _attempt(workspace)["application_journal"]
    resumed = adapter.resume(
        workspace,
        dispatch_id=request["dispatch_id"],
        approval_ref=approve_parked(
            workspace, repo, _attempt(workspace), gate="pr_creation"
        ),
        kind="pending_gate",
    )
    checkpoint_path = workspace / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint["dispatch_attempts"][0]["application_journal"] = legacy_journal
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    _launch(adapter, workspace, resumed, owner="owner-nonce-0002")
    succeeded = _result("success-result.json", resumed)

    applied = adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[succeeded],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )

    assert applied["completed_item_ids"] == ["ri-01"]
    assert _attempt(workspace)["application_journal"]["result"] == succeeded


def test_pre_go_stale_takeover_preserves_parked_continuation(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    clock = FakeClock()
    host_calls: list[tuple[str, dict[str, Any]]] = []
    adapter = _adapter(managed_root, clock, host_calls=host_calls)
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[_result("parked-result.json", request)],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    resumed = adapter.resume(
        workspace,
        dispatch_id=request["dispatch_id"],
        approval_ref=approve_parked(workspace, repo, _attempt(workspace), gate="pr_creation"),
        kind="pending_gate",
    )
    adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=resumed["launch_token"],
        lease_generation=2,
        owner_nonce="owner-nonce-0002",
        lease_seconds=5,
    )
    clock.advance(6)

    reclaimed = adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=resumed["launch_token"],
        lease_generation=2,
        owner_nonce="owner-nonce-0003",
    )
    adapter.acknowledge(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=reclaimed["lease_generation"],
        handle="task-alpha-003",
    )
    adapter.enter(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=reclaimed["lease_generation"],
        owner_nonce="owner-nonce-0003",
    )

    assert host_calls[-1][1]["continuation"] == resumed["continuation"]


def test_failed_child_start_never_creates_an_orphan_marker(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    marker = Path(_wt(request), request["launch_marker_path"])

    with pytest.raises(ValueError, match="owner nonce"):
        adapter.child_start(
            workspace,
            dispatch_id=request["dispatch_id"],
            launch_token=request["launch_token"],
            lease_generation=1,
            owner_nonce="short",
        )

    assert not marker.exists()
    assert _attempt(workspace)["status"] == "prepared"


def test_apply_rejects_stale_unbound_loop_state_evidence(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    loop_state = (
        _wt(request)
        / result["evidence"]["loop_state_path"]
    )
    loop_state.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "change_id": request["change_id"],
                "current_phase": "INIT",
                "handoff_ids": [],
                "last_handoff_id": None,
            }
        )
        + "\n"
    )
    result["evidence"]["loop_state_digest"] = hashlib.sha256(
        loop_state.read_bytes()
    ).hexdigest()
    calls: list[str] = []

    with pytest.raises(ValueError, match="loop-state"):
        adapter.apply(
            workspace,
            batch_id=request["dispatch_id"].split(":", 1)[0],
            results=[result],
            dispatch_fn=lambda item, _phase, _context: calls.append(item) or "success",
            repo_root=repo,
        )

    assert calls == []
    assert _attempt(workspace)["status"] == "launched"


def test_apply_accepts_real_autopilot_loop_state_in_linked_worktree(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    loop_state = _use_linked_worktree_layout(managed_root)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    result["evidence"] = {
        "loop_state_path": "openspec/changes/change-alpha/loop-state.json",
        "commit": "a" * 40,
        "loop_state_digest": hashlib.sha256(loop_state.read_bytes()).hexdigest(),
    }

    applied = adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[result],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )

    assert applied["completed_item_ids"] == ["ri-01"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda result: result.update(worktree_ref="other"), "worktree"),
        (lambda result: result.update(branch="openspec/other"), "branch"),
        (
            lambda result: result["evidence"].update(loop_state_path="../outside.json"),
            "loop-state containment|loop_state_path",
        ),
        (
            lambda result: result["evidence"].update(loop_state_digest="0" * 64),
            "loop-state digest",
        ),
    ],
)
def test_apply_rejects_exact_isolation_and_loop_state_evidence_before_callback(
    tmp_path: Path,
    mutation: Any,
    message: str,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    mutation(result)
    calls: list[str] = []

    with pytest.raises(ValueError, match=message):
        adapter.apply(
            workspace,
            batch_id=request["dispatch_id"].split(":", 1)[0],
            results=[result],
            dispatch_fn=lambda item, _phase, _context: calls.append(item) or "success",
            repo_root=repo,
        )

    assert calls == []
    assert _attempt(workspace)["status"] == "launched"


def test_apply_rejects_noncanonical_inside_worktree_evidence_before_callback(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    other = (
        _wt(request)
        / "openspec"
        / "changes"
        / "change-alpha"
        / "other.json"
    )
    other.write_text('{"status":"other"}\n')
    result["evidence"]["loop_state_path"] = (
        "openspec/changes/change-alpha/other.json"
    )
    calls: list[str] = []

    with pytest.raises(ValueError, match="exact loop-state path"):
        adapter.apply(
            workspace,
            batch_id=request["dispatch_id"].split(":", 1)[0],
            results=[result],
            dispatch_fn=lambda item, _phase, _context: calls.append(item) or "success",
            repo_root=repo,
        )

    assert calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gate", 7),
        ("deadline", "not-a-date-time"),
        ("resume_hint", 7),
    ],
)
def test_invalid_optional_parked_fields_never_reach_temp_result_file(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    observed: list[Path] = []
    adapter = ExecutionAdapter(
        profile_probe=_profile_probe,
        managed_worktree_root=managed_root,
        clock=FakeClock(),
        branch_resolver=lambda _: "openspec/change-alpha",
        commit_resolver=lambda _: "a" * 40,
        liveness_probe=lambda _: "live",
        host_entry=lambda *_: "entered",
        result_file_observer=observed.append,
    )
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("parked-result.json", request)
    result["parked"][field] = value

    with pytest.raises(ValueError, match="schema-valid"):
        adapter.apply(
            workspace,
            batch_id=request["dispatch_id"].split(":", 1)[0],
            results=[result],
            dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
            repo_root=repo,
        )

    assert observed == []
    assert _attempt(workspace)["status"] == "launched"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda result: result.update(schema_version=True),
        lambda result: result.update(outcome="failed:boom", worktree_ref=7),
        lambda result: result.update(outcome="vendor_limit:test:busy", branch=""),
    ],
)
def test_invalid_result_scalar_types_never_reach_temp_result_file(
    tmp_path: Path,
    mutation: Any,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    observed: list[Path] = []
    adapter = ExecutionAdapter(
        profile_probe=_profile_probe,
        managed_worktree_root=managed_root,
        clock=FakeClock(),
        branch_resolver=lambda _: "openspec/change-alpha",
        commit_resolver=lambda _: "a" * 40,
        liveness_probe=lambda _: "live",
        host_entry=lambda *_: "entered",
        result_file_observer=observed.append,
    )
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    mutation(result)

    with pytest.raises(ValueError, match="schema-valid"):
        adapter.apply(
            workspace,
            batch_id=request["dispatch_id"].split(":", 1)[0],
            results=[result],
            dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
            repo_root=repo,
        )

    assert observed == []
    assert _attempt(workspace)["status"] == "launched"


def test_apply_rejects_symlinked_loop_state_escape_before_callback(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    worktree = _wt(request)
    outside = repo / "outside-loop-state.json"
    outside.write_text('{"status":"outside"}\n')
    link = worktree / result["evidence"]["loop_state_path"]
    link.unlink()
    link.symlink_to(outside)
    calls: list[str] = []

    with pytest.raises(ValueError, match="loop-state containment"):
        adapter.apply(
            workspace,
            batch_id=request["dispatch_id"].split(":", 1)[0],
            results=[result],
            dispatch_fn=lambda item, _phase, _context: calls.append(item) or "success",
            repo_root=repo,
        )

    assert calls == []
    assert _attempt(workspace)["status"] == "launched"


def test_apply_accepts_exact_digest_and_uses_bounded_temp_result_only(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    loop_state = _wt(request) / result["evidence"][
        "loop_state_path"
    ]
    result["evidence"]["loop_state_digest"] = hashlib.sha256(loop_state.read_bytes()).hexdigest()

    applied = adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[result],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )

    assert applied["completed_item_ids"] == ["ri-01"]
    durable = json.dumps(json.loads((workspace / "checkpoint.json").read_text()))
    assert "transcript" not in durable.lower()


def test_apply_releases_workspace_lock_for_callback_and_replan_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="roadmap-host-adapter",
        source_proposal="proposal.md",
        items=[
            RoadmapItem(
                "ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S,
                change_id="change-alpha",
            ),
            RoadmapItem(
                "ri-02", "Dependent", ItemStatus.APPROVED, 2, Effort.S,
                depends_on=["ri-01"],
            ),
        ],
    )
    (workspace / "roadmap.yaml").write_text(yaml.safe_dump(roadmap.to_dict(), sort_keys=False))
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)

    def assert_workspace_unlocked() -> None:
        identity = hashlib.sha256(str(workspace.resolve()).encode()).hexdigest()
        lock_path = (
            Path(tempfile.gettempdir()) / "roadmap-checkpoint-locks" / f"{identity}.lock"
        )
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(descriptor)

    observations: list[str] = []

    def dispatch(_item: str, _phase: str, _context: dict[str, Any]) -> dict[str, Any]:
        assert_workspace_unlocked()
        observations.append("callback")
        return {"outcome": "failed:needs redesign", "replan": True}

    class ReplanGate:
        def evaluate(self, gate: Gate, _context: dict[str, Any]) -> ApprovalDecision:
            assert gate is Gate.REPLAN_REQUIRED
            assert_workspace_unlocked()
            observations.append("replan_gate")
            return ApprovalDecision(
                gate=gate,
                outcome=Outcome.BLOCKED,
                resolution=Resolution.POSTURE_BLOCK,
                disposition=Disposition.BLOCK,
                reason="fixture blocks replan",
                posture_present=True,
            )

    monkeypatch.setitem(
        execution.apply_delegated_batch.__globals__, "_build_default_gate_evaluator", ReplanGate
    )
    result = {
        "schema_version": 1,
        "dispatch_id": request["dispatch_id"],
        "change_id": request["change_id"],
        "attempt": request["attempt"],
        "lease_generation": request["lease_generation"],
        "outcome": "failed:needs redesign",
        "replan": True,
    }
    applied = adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[result],
        dispatch_fn=dispatch,
        repo_root=repo,
    )

    assert observations == ["callback", "replan_gate"]
    assert applied["failed_item_ids"] == ["ri-01"]
    assert len(applied["gate_decisions"]) == 1
    checkpoint = json.loads((workspace / "checkpoint.json").read_text())
    assert applied["gate_decisions"][0] in checkpoint["gate_decisions"]
    statuses = {
        item["item_id"]: item["status"]
        for item in yaml.safe_load((workspace / "roadmap.yaml").read_text())["items"]
    }
    assert statuses["ri-02"] == "replan_required"


def test_adapter_source_has_no_model_provider_or_network_boundary() -> None:
    source = (_SCRIPTS / "execution.py").read_text()
    tree = ast.parse(source)
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint({"anthropic", "openai", "google", "litellm", "httpx", "requests"})


def test_route_parked_escalations_rejects_partial_batch_before_gate_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    calls: list[str] = []

    monkeypatch.setattr(
        gate_router,
        "resolve_parked",
        lambda *_args, **_kwargs: calls.append("evaluated"),
    )

    with pytest.raises(ExecutionStateError, match="fully effects-applied"):
        adapter.route_parked_escalations(
            workspace, batch_id=request["dispatch_id"].split(":", 1)[0], repo_root=repo
        )

    assert calls == []


def _fully_applied_policy_pause(
    tmp_path: Path,
) -> tuple[Path, Path, ExecutionAdapter, dict[str, Any], str]:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    batch_id = request["dispatch_id"].split(":", 1)[0]
    adapter.apply(
        workspace,
        batch_id=batch_id,
        results=[_result("parked-result.json", request)],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    manager = execution.CheckpointManager(workspace)
    checkpoint = manager.load()
    # D3: a policy_pause carries gate null or escalate_resume.
    checkpoint.dispatch_attempts[0]["parked"].update(kind="policy_pause", gate=None)
    manager.save(checkpoint)
    return repo, workspace, adapter, request, batch_id


def _escalation_decisions(workspace: Path) -> list[dict[str, Any]]:
    checkpoint = json.loads((workspace / "checkpoint.json").read_text(encoding="utf-8"))
    return [
        record
        for record in checkpoint.get("gate_decisions", [])
        if record.get("gate") == Gate.ESCALATE_RESUME.value
    ]


def test_route_parked_escalations_returns_exact_proceed_resolution_once(
    tmp_path: Path,
) -> None:
    repo, workspace, adapter, request, batch_id = _fully_applied_policy_pause(tmp_path)

    result = adapter.route_parked_escalations(
        workspace, batch_id=batch_id, repo_root=repo,
        evaluator=_escalation_service(Disposition.AUTO),
    )

    assert result == [{
        "dispatch_id": request["dispatch_id"],
        "outcome": "proceed",
        "decided_lease_generation": 1,
        "resumed_lease_generation": 2,
    }]
    assert len(_escalation_decisions(workspace)) == 1
    resumed = _attempt(workspace)
    assert resumed["status"] == "prepared"
    assert resumed["lease_generation"] == 2
    assert "application_journal" not in resumed


def test_route_parked_escalations_returns_exact_blocked_resolution_once(
    tmp_path: Path,
) -> None:
    repo, workspace, adapter, request, batch_id = _fully_applied_policy_pause(tmp_path)

    result = adapter.route_parked_escalations(
        workspace, batch_id=batch_id, repo_root=repo,
        evaluator=_escalation_service(Disposition.BLOCK),
    )

    decisions = _escalation_decisions(workspace)
    mirror = json.loads(
        (repo / "openspec" / "supervise" / "supervisor-record.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(decisions) == 1
    assert result == [{
        "dispatch_id": request["dispatch_id"],
        "outcome": "blocked",
        "decided_lease_generation": 1,
        "pending_gate": mirror["pending_gates"][0],
    }]
    assert _attempt(workspace)["status"] == "parked"


def test_route_parked_escalations_retry_reports_durable_already_routed_state(
    tmp_path: Path,
) -> None:
    repo, workspace, adapter, request, batch_id = _fully_applied_policy_pause(tmp_path)
    adapter.route_parked_escalations(
        workspace, batch_id=batch_id, repo_root=repo,
        evaluator=_escalation_service(Disposition.AUTO),
    )

    retried = adapter.route_parked_escalations(
        workspace, batch_id=batch_id, repo_root=repo,
        evaluator=_escalation_service(Disposition.AUTO),
    )

    assert retried == [{
        "dispatch_id": request["dispatch_id"],
        "outcome": "already_routed",
        "decided_lease_generation": 1,
        "resumed_lease_generation": 2,
    }]
    assert len(_escalation_decisions(workspace)) == 1


def test_atomic_escalation_resume_publishes_decision_and_generation_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[_result("parked-result.json", request)],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    manager = execution.CheckpointManager(workspace)
    checkpoint = manager.load()
    attempt = checkpoint.dispatch_attempts[0]
    attempt["parked"].update(kind="policy_pause", gate=None)  # D3: gate null or escalate_resume
    manager.save(checkpoint)
    record = {
        "decision_id": "11111111-2222-4333-8444-555555555555",
        "gate": "escalate_resume",
        "outcome": "proceed",
        "resolution": "auto",
        "disposition": "auto",
        "reason": "approved",
        "posture_present": True,
        "recorded_at": "2026-09-01T00:00:00+00:00",
        "roadmap_id": "roadmap-host-adapter",
        "dispatch_id": request["dispatch_id"],
        "lease_generation": 1,
    }
    saved: list[dict[str, Any]] = []
    original_save = execution.CheckpointManager.save

    def capture_save(self: Any, value: Any) -> None:
        original_save(self, value)
        saved.append(json.loads(self.checkpoint_path.read_text()))

    monkeypatch.setattr(execution.CheckpointManager, "save", capture_save)
    adapter.resume_with_gate_decision(
        workspace,
        dispatch_id=request["dispatch_id"],
        approval_ref="gate-decision:11111111-2222-4333-8444-555555555555",
        kind="policy_pause",
        record=record,
    )

    assert len(saved) == 1
    persisted = saved[0]
    assert persisted["gate_decisions"][-1] == record
    resumed = persisted["dispatch_attempts"][0]
    assert resumed["status"] == "prepared"
    assert resumed["lease_generation"] == 2
    assert "application_journal" not in resumed


def test_stale_atomic_escalation_candidate_does_not_append_a_decision(
    tmp_path: Path
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[_result("parked-result.json", request)],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    manager = execution.CheckpointManager(workspace)
    checkpoint = manager.load()
    attempt = checkpoint.dispatch_attempts[0]
    attempt.update(
        status="prepared",
        lease_generation=2,
        continuation={"kind": "policy_pause", "approval_ref": "gate-decision:00000000-0000-4000-8000-000000000000"},
    )
    for field in (
        "lease", "launch_evidence", "launch_gate", "parked", "outcome",
        "resolved_at", "handoff_id", "application_journal",
    ):
        attempt.pop(field, None)
    manager.save(checkpoint)
    record = {
        "decision_id": "11111111-2222-4333-8444-555555555555",
        "gate": "escalate_resume",
        "outcome": "proceed",
        "resolution": "auto",
        "disposition": "auto",
        "reason": "approved",
        "posture_present": True,
        "recorded_at": "2026-09-01T00:00:00+00:00",
        "roadmap_id": "roadmap-host-adapter",
        "dispatch_id": request["dispatch_id"],
        "lease_generation": 1,
    }

    with pytest.raises(ExecutionStateError, match="stale or mismatched"):
        adapter.resume_with_gate_decision(
            workspace,
            dispatch_id=request["dispatch_id"],
            approval_ref="gate-decision:11111111-2222-4333-8444-555555555555",
            kind="policy_pause",
            record=record,
        )

    assert all(record.get("decision_id") != "11111111-2222-4333-8444-555555555555" for record in manager.load().gate_decisions)


# --------------------------------------------------------------------------- #
# dispatch-contract: launch digests, reissue, execution profile, new parks
# --------------------------------------------------------------------------- #


def test_child_start_rejects_a_wrong_token_without_touching_the_checkpoint(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    before = (workspace / "checkpoint.json").read_bytes()

    with pytest.raises(ExecutionStateError, match="launch token mismatch"):
        adapter.child_start(
            workspace,
            dispatch_id=request["dispatch_id"],
            launch_token=request["launch_token"] + "-wrong",
            lease_generation=1,
            owner_nonce="owner-nonce-0001",
        )
    assert (workspace / "checkpoint.json").read_bytes() == before


def test_no_raw_token_is_persisted_and_each_request_hashes_to_its_digest(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    text = (workspace / "checkpoint.json").read_text()
    assert "launch_token" not in text and request["launch_token"] not in text
    assert _attempt(workspace)["launch_digest"] == (
        "sha256:" + hashlib.sha256(request["launch_token"].encode()).hexdigest()
    )


def test_resume_rotates_the_token_and_revokes_the_previous_one(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[_result("parked-result.json", request)],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    resumed = adapter.resume(
        workspace,
        dispatch_id=request["dispatch_id"],
        approval_ref=approve_parked(workspace, repo, _attempt(workspace), gate="pr_creation"),
        kind="pending_gate",
    )
    assert resumed["launch_token"] != request["launch_token"]
    assert resumed["gate_answer"]["gate"] == "pr_creation"
    assert resumed["gate_answer"]["decision"] == "approved"
    with pytest.raises(ExecutionStateError, match="launch token mismatch"):
        adapter.child_start(
            workspace,
            dispatch_id=request["dispatch_id"],
            launch_token=request["launch_token"],
            lease_generation=2,
            owner_nonce="owner-nonce-0002",
        )


def test_reissue_is_refused_after_go(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    before = _attempt(workspace)

    with pytest.raises(ExecutionStateError, match="reissue"):
        adapter.reissue(workspace, dispatch_id=request["dispatch_id"])
    after = _attempt(workspace)
    assert after["launch_digest"] == before["launch_digest"]
    assert after["lease_generation"] == before["lease_generation"]


def test_reissue_of_a_prepared_attempt_rearms_the_same_generation(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]

    reissued = adapter.reissue(workspace, dispatch_id=request["dispatch_id"])

    assert reissued["lease_generation"] == 1
    assert reissued["launch_token"] != request["launch_token"]
    with pytest.raises(ExecutionStateError, match="launch token mismatch"):
        adapter.child_start(
            workspace, dispatch_id=request["dispatch_id"], launch_token=request["launch_token"],
            lease_generation=1, owner_nonce="owner-nonce-0001",
        )


def test_a_marker_carries_the_supervisor_view_but_no_token(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    adapter.child_start(
        workspace, dispatch_id=request["dispatch_id"], launch_token=request["launch_token"],
        lease_generation=1, owner_nonce="owner-nonce-0001",
    )
    marker = json.loads(Path(_wt(request), request["launch_marker_path"]).read_text())
    assert request["launch_token"] not in json.dumps(marker)
    assert marker["roadmap_approval_ref"] == request["roadmap_approval_ref"]
    assert marker["execution_profile"] == request["execution_profile"]
    assert marker["review_requirements"] == request["review_requirements"]
    assert len(marker["posture_digest"]) == 64
    assert marker["isolation"] == request["isolation"]


def test_request_carries_a_resolved_profile(tmp_path: Path) -> None:
    from shared import dispatch_contract

    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    assert dispatch_contract.validate_request(request)["schema_version"] == 2
    assert request["execution_profile"]["lanes"]["review"]
    assert request["execution_profile"]["probe_command"]
    assert set(request["review_requirements"]["min_quorum"]) == {"PLAN_REVIEW", "IMPL_REVIEW", "VAL_REVIEW"}


def test_router_context_overrides_the_review_quorum(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(
        adapter, workspace, repo, managed_root, context={"review_min_quorum": 3}
    )["requests"][0]
    assert request["review_requirements"]["min_quorum"]["PLAN_REVIEW"] == 3
    assert "review_min_quorum" not in request["context"]


@pytest.mark.parametrize(
    "stdout, message",
    [("not json at all", "not JSON"), (json.dumps({"error": "roster unreadable", "modes": {}}), "roster unreadable")],
)
def test_profile_resolution_failure_blocks_launch(tmp_path: Path, stdout: str, message: str) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    adapter.profile_probe = lambda _repo: (2, stdout)
    ref = approve_roadmap(workspace, repo)
    before = json.loads((workspace / "checkpoint.json").read_text()).get("dispatch_attempts", [])

    with pytest.raises(ValueError, match=message):
        _prepare(adapter, workspace, repo, managed_root, roadmap_approval_ref=ref)
    assert json.loads((workspace / "checkpoint.json").read_text()).get("dispatch_attempts", []) == before


def test_below_quorum_availability_still_launches_with_an_honest_profile(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    adapter.profile_probe = lambda _repo: (
        2,
        json.dumps(
            {
                "modes": {
                    "review": {
                        "verified": ["claude_code"],
                        "unverified": [{"vendor": "codex", "reason": "cli_not_found"}],
                    }
                },
                "probe_command": "review_dispatcher.py --check-vendors --json",
            }
        ),
    )
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    assert request["execution_profile"]["lanes"]["review"] == ["claude_code"]
    assert request["review_requirements"]["counting_lanes"] == ["claude_code", "codex"]
    assert request["review_requirements"]["min_quorum"]["PLAN_REVIEW"] == 2


def _capability_parked(tmp_path: Path) -> tuple[Path, Path, ExecutionAdapter, dict[str, Any]]:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("parked-result.json", request)
    result["parked"] = {
        "kind": "capability_unavailable",
        "gate": None,
        "phase": "PLAN_REVIEW",
        "missing_lanes": ["codex"],
        "reason": "quorum 2 unmet",
    }
    loop_state = _wt(request) / "openspec" / "changes" / "change-alpha" / "loop-state.json"
    state = json.loads(loop_state.read_text())
    state.update(pending_gate=None, park=dict(result["parked"]))
    loop_state.write_text(json.dumps(state) + "\n")
    result["evidence"]["loop_state_digest"] = hashlib.sha256(loop_state.read_bytes()).hexdigest()
    adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[result],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    return repo, workspace, adapter, request


def _escalate_record(attempt: dict[str, Any], *, fingerprint: str | None) -> dict[str, Any]:
    import uuid as _uuid

    record = {
        "decision_id": str(_uuid.uuid4()),
        "gate": "escalate_resume",
        "outcome": "proceed",
        "resolution": "console_approved",
        "disposition": "block",
        "reason": "operator fixed the lane",
        "posture_present": True,
        "recorded_at": "2026-10-09T00:00:00+00:00",
        "roadmap_id": "roadmap-host-adapter",
        "dispatch_id": attempt["dispatch_id"],
        "lease_generation": attempt["lease_generation"],
        "provenance": {"source": "human", "approval_ref": None},
    }
    if fingerprint is not None:
        record["dedupe_fingerprint"] = fingerprint
    return record


def test_resume_accepts_a_capability_park_only_with_its_fingerprint(tmp_path: Path) -> None:
    from shared import dispatch_contract

    repo, workspace, adapter, request = _capability_parked(tmp_path)
    attempt = _attempt(workspace)
    assert attempt["status"] == "parked"
    manager = execution.CheckpointManager(workspace)
    wrong = _escalate_record(attempt, fingerprint="0" * 64)
    right = _escalate_record(attempt, fingerprint=dispatch_contract.dedupe_fingerprint(attempt["parked"]))
    checkpoint = manager.load()
    checkpoint.gate_decisions.extend([wrong, right])
    manager.save(checkpoint)

    with pytest.raises(ValueError, match="fingerprint"):
        adapter.resume(
            workspace, dispatch_id=request["dispatch_id"],
            approval_ref=f"gate-decision:{wrong['decision_id']}", kind="capability_unavailable",
        )
    resumed = adapter.resume(
        workspace, dispatch_id=request["dispatch_id"],
        approval_ref=f"gate-decision:{right['decision_id']}", kind="capability_unavailable",
    )
    assert resumed["continuation"]["kind"] == "capability_unavailable"
    assert resumed["gate_answer"]["gate"] == "escalate_resume"
    assert resumed["lease_generation"] == 2


def test_apply_persists_degradations_on_the_attempt(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    degradation = {"code": "single_vendor_review", "phase": "PLAN_REVIEW", "detail": "codex not dispatchable"}
    result["degradations"] = [degradation]

    applied = adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[result],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )

    assert applied["degradations"] == {request["dispatch_id"]: [degradation]}
    assert _attempt(workspace)["degradations"] == [degradation]


# --------------------------------------------------------------------------- #
# Typed gate answers with provenance (D5) and one escalation per park (D9)
# --------------------------------------------------------------------------- #


def _write_repo_posture(repo: Path, **gates: str) -> str:
    from shared.trust_posture import load_posture, posture_digest

    doc = {"schema_version": 1, "gates": {k: {"disposition": v} for k, v in gates.items()}}
    (repo / "TRUST_POSTURE.md").write_text("---\n" + yaml.safe_dump(doc) + "---\n\n# body\n")
    return posture_digest(load_posture(repo))


def _router_gate(repo: Path) -> ApprovalGate:
    return ApprovalGate(coordinator=object(), audit=_RecordingAudit(), repo_root=str(repo))


def _parked_on(tmp_path: Path, gate: str) -> tuple[Path, Path, ExecutionAdapter, dict[str, Any]]:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("parked-result.json", request)
    result["parked"]["gate"] = gate
    loop_state = _wt(request) / "openspec" / "changes" / "change-alpha" / "loop-state.json"
    state = json.loads(loop_state.read_text())
    state["pending_gate"] = {"gate": gate}
    loop_state.write_text(json.dumps(state) + "\n")
    result["evidence"]["loop_state_digest"] = hashlib.sha256(loop_state.read_bytes()).hexdigest()
    adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[result],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    return repo, workspace, adapter, request


def test_a_posture_derived_block_clears_after_a_posture_change(tmp_path: Path) -> None:
    repo, workspace, adapter, request = _parked_on(tmp_path, "proposal_approval")
    first_digest = _write_repo_posture(repo, proposal_approval="block")
    blocked = gate_router.resolve_parked(
        _attempt(workspace), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )
    assert blocked.outcome == "blocked"
    assert blocked.routed.record["provenance"] == {"source": "posture", "posture_digest": first_digest}

    second_digest = _write_repo_posture(repo, proposal_approval="auto")
    resolved = gate_router.resolve_parked(
        _attempt(workspace), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )

    assert resolved.outcome == "proceed"
    assert resolved.routed.record["provenance"] == {"source": "posture", "posture_digest": second_digest}
    # D8: the attempt's verified roadmap_approval_ref scoped the auto.
    assert resolved.routed.record["scope"] == "roadmap_approval"
    assert resolved.resume_result["gate_answer"]["decision"] == "approved"
    assert resolved.resume_result["gate_answer"]["provenance"]["source"] == "posture"


def test_an_unchanged_posture_reuses_the_prior_block(tmp_path: Path) -> None:
    repo, workspace, adapter, _request = _parked_on(tmp_path, "pr_creation")
    _write_repo_posture(repo, pr_creation="block")
    first = gate_router.resolve_parked(
        _attempt(workspace), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )
    count = len(execution.CheckpointManager(workspace).load().gate_decisions)
    (repo / "TRUST_POSTURE.md").write_text(
        (repo / "TRUST_POSTURE.md").read_text() + "\nA prose-only edit.\n"
    )
    second = gate_router.resolve_parked(
        _attempt(workspace), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )
    assert second.routed.reused is True
    assert second.routed.record["decision_id"] == first.routed.record["decision_id"]
    assert len(execution.CheckpointManager(workspace).load().gate_decisions) == count


def test_a_human_rejection_survives_a_posture_change(tmp_path: Path) -> None:
    repo, workspace, adapter, request = _parked_on(tmp_path, "pr_creation")
    _write_repo_posture(repo, pr_creation="block")
    gate_router.resolve_parked(
        _attempt(workspace), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )
    rejected = gate_router.answer(
        "pr_creation", workspace=workspace, repo_root=repo, approved=False,
        context={"dispatch_id": request["dispatch_id"], "change_id": "change-alpha", "verb": "resume"},
    )
    assert rejected.record["provenance"]["source"] == "human"
    count = len(execution.CheckpointManager(workspace).load().gate_decisions)
    _write_repo_posture(repo, pr_creation="auto")

    resolution = gate_router.resolve_parked(
        _attempt(workspace), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )

    assert resolution.outcome == "blocked"
    assert resolution.routed.record["decision_id"] == rejected.record["decision_id"]
    assert len(execution.CheckpointManager(workspace).load().gate_decisions) == count
    assert _attempt(workspace)["status"] == "parked"


def _clone_parked(workspace: Path, parks: list[dict[str, Any]]) -> list[str]:
    """Replace the parked attempt with one parked copy per payload (same
    isolation; distinct dispatch ids), each a schema-valid parked attempt."""
    manager = execution.CheckpointManager(workspace)
    checkpoint = manager.load()
    base = checkpoint.dispatch_attempts[0]
    attempts, ids = [], []
    for index, park in enumerate(parks, start=1):
        clone = json.loads(json.dumps(base))
        clone["dispatch_id"] = f"{base['dispatch_id'].rsplit(':', 1)[0]}:attempt-{index}"
        clone["attempt"] = index
        clone["parked"] = dict(park)
        clone.pop("application_journal", None)
        attempts.append(clone)
        ids.append(clone["dispatch_id"])
    checkpoint.dispatch_attempts = attempts
    manager.save(checkpoint)
    return ids


_BLOCKED = {
    "kind": "permission_blocked",
    "gate": None,
    "tool": "Bash",
    "rule": "Bash(env *)",
    "classifier_reason": "reads credentials",
    "reason": "permission denied",
}


def _mirror_entries(repo: Path) -> list[dict[str, Any]]:
    record = gate_router._read_current_mirror(repo) or {}
    from cycle_state import _extract_supervisor_record

    return (_extract_supervisor_record(record) or {}).get("pending_gates", [])


def test_three_workers_blocked_on_one_rule_produce_one_escalation(tmp_path: Path) -> None:
    repo, workspace, adapter, _request = _parked_on(tmp_path, "pr_creation")
    _write_repo_posture(repo, escalate_resume="block")
    ids = _clone_parked(
        workspace,
        [dict(_BLOCKED, command=f"env | grep KEY_{n}") for n in range(3)],
    )
    for attempt in execution.CheckpointManager(workspace).load().dispatch_attempts:
        gate_router.resolve_parked(
            attempt, workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
        )

    entries = [e for e in _mirror_entries(repo) if e.get("dedupe_fingerprint")]
    assert len(entries) == 1
    assert [item["dispatch_id"] for item in entries[0]["dispatch_ids"]] == ids

    # One answer resumes every listed attempt, each through its own CAS.
    answered = gate_router.answer_escalation(
        entries[0]["dedupe_fingerprint"], workspace=workspace, repo_root=repo, approved=True, adapter=adapter,
    )
    assert sorted(r["dispatch_id"] for r in answered["resumed"]) == ids
    assert answered["skipped"] == []
    records = answered["records"]
    assert len({r["decision_id"] for r in records}) == 3
    assert {r["dedupe_fingerprint"] for r in records} == {entries[0]["dedupe_fingerprint"]}
    assert all(a["status"] == "prepared" and a["lease_generation"] == 2
               for a in execution.CheckpointManager(workspace).load().dispatch_attempts)
    assert [e for e in _mirror_entries(repo) if e.get("dedupe_fingerprint")] == []


def test_an_attempt_whose_generation_moved_is_skipped_and_reported(tmp_path: Path) -> None:
    repo, workspace, adapter, _request = _parked_on(tmp_path, "pr_creation")
    _write_repo_posture(repo, escalate_resume="block")
    ids = _clone_parked(workspace, [dict(_BLOCKED), dict(_BLOCKED)])
    for attempt in execution.CheckpointManager(workspace).load().dispatch_attempts:
        gate_router.resolve_parked(
            attempt, workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
        )
    fingerprint = [e for e in _mirror_entries(repo) if e.get("dedupe_fingerprint")][0]["dedupe_fingerprint"]
    manager = execution.CheckpointManager(workspace)
    checkpoint = manager.load()
    moved = checkpoint.dispatch_attempts[1]
    for key in ("lease", "launch_evidence", "launch_gate"):
        moved[key]["generation"] = 5
    moved["lease_generation"] = 5
    manager.save(checkpoint)

    answered = gate_router.answer_escalation(
        fingerprint, workspace=workspace, repo_root=repo, approved=True, adapter=adapter
    )

    assert [r["dispatch_id"] for r in answered["resumed"]] == [ids[0]]
    assert [s["dispatch_id"] for s in answered["skipped"]] == [ids[1]]


def _park_late_member(workspace: Path, park: dict[str, Any]) -> str:
    """Append one more parked attempt on ``park`` after a subject was recorded."""
    manager = execution.CheckpointManager(workspace)
    checkpoint = manager.load()
    clone = json.loads(json.dumps(checkpoint.dispatch_attempts[0]))
    clone["dispatch_id"] = f"{clone['dispatch_id'].rsplit(':', 1)[0]}:attempt-9"
    clone["attempt"] = 9
    clone["status"] = "parked"
    clone["parked"] = dict(park)
    clone.pop("application_journal", None)
    checkpoint.dispatch_attempts.append(clone)
    manager.save(checkpoint)
    return clone["dispatch_id"]


def _status(workspace: Path, dispatch_id: str) -> str:
    attempts = execution.CheckpointManager(workspace).load().dispatch_attempts
    return next(a["status"] for a in attempts if a["dispatch_id"] == dispatch_id)


def _durable_subject_ids(workspace: Path, fingerprint: str) -> list[str]:
    subjects = [
        r for r in execution.CheckpointManager(workspace).load().gate_decisions
        if r.get("dedupe_fingerprint") == fingerprint and "dispatch_ids" in r and r.get("outcome") == "blocked"
    ]
    latest = max(subjects, key=lambda r: str(r.get("recorded_at") or ""))
    return [item["dispatch_id"] for item in latest["dispatch_ids"]]


def test_a_member_that_parks_after_the_subject_is_not_resumed_by_its_answer(tmp_path: Path) -> None:
    """Provenance (D9): an answer authorizes only the dispatches its durable
    subject listed. A member that parked on the fingerprint later stays parked
    until it is re-projected as a subject of its own, awaiting an answer."""
    repo, workspace, adapter, _request = _parked_on(tmp_path, "pr_creation")
    _write_repo_posture(repo, escalate_resume="block")
    [first] = _clone_parked(workspace, [dict(_BLOCKED)])
    gate_router.resolve_parked(
        execution.CheckpointManager(workspace).load().dispatch_attempts[0],
        workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo),
    )
    fingerprint = [e for e in _mirror_entries(repo) if e.get("dedupe_fingerprint")][0]["dedupe_fingerprint"]
    late = _park_late_member(workspace, _BLOCKED)

    answered = gate_router.answer_escalation(
        fingerprint, workspace=workspace, repo_root=repo, approved=True, adapter=adapter
    )

    assert [r["dispatch_id"] for r in answered["resumed"]] == [first]
    assert [r["dispatch_id"] for r in answered["records"]] == [first]
    assert _status(workspace, late) == "parked"

    late_attempt = next(
        a for a in execution.CheckpointManager(workspace).load().dispatch_attempts if a["dispatch_id"] == late
    )
    resolution = gate_router.resolve_parked(
        late_attempt, workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )

    assert resolution.outcome == "blocked"
    entries = [e for e in _mirror_entries(repo) if e.get("dedupe_fingerprint") == fingerprint]
    assert [[item["dispatch_id"] for item in e["dispatch_ids"]] for e in entries] == [[late]]
    assert _durable_subject_ids(workspace, fingerprint) == [late]
    assert _status(workspace, late) == "parked"


def test_a_member_joining_a_human_rejection_is_persisted_before_it_can_be_approved(tmp_path: Path) -> None:
    """D5 + D9: a member joining a human-rejected subject extends the durable
    subject and its projection (the rejection stays in force); an approval
    given before that re-projection does not resume it."""
    repo, workspace, adapter, _request = _parked_on(tmp_path, "pr_creation")
    _write_repo_posture(repo, escalate_resume="block")
    [first] = _clone_parked(workspace, [dict(_BLOCKED)])
    gate_router.resolve_parked(
        execution.CheckpointManager(workspace).load().dispatch_attempts[0],
        workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo),
    )
    fingerprint = [e for e in _mirror_entries(repo) if e.get("dedupe_fingerprint")][0]["dedupe_fingerprint"]
    gate_router.answer_escalation(fingerprint, workspace=workspace, repo_root=repo, approved=False, adapter=adapter)
    late = _park_late_member(workspace, _BLOCKED)
    late_attempt = next(
        a for a in execution.CheckpointManager(workspace).load().dispatch_attempts if a["dispatch_id"] == late
    )

    resolution = gate_router.resolve_parked(
        late_attempt, workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )

    assert resolution.outcome == "blocked"
    assert resolution.routed.record["provenance"]["source"] == "human"
    assert _durable_subject_ids(workspace, fingerprint) == sorted([first, late])
    entries = [e for e in _mirror_entries(repo) if e.get("dedupe_fingerprint") == fingerprint]
    assert [sorted(item["dispatch_id"] for item in e["dispatch_ids"]) for e in entries] == [sorted([first, late])]
    # Re-resolving with an unchanged membership adds no further subject record.
    count = len(execution.CheckpointManager(workspace).load().gate_decisions)
    gate_router.resolve_parked(
        late_attempt, workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )
    assert len(execution.CheckpointManager(workspace).load().gate_decisions) == count

    answered = gate_router.answer_escalation(
        fingerprint, workspace=workspace, repo_root=repo, approved=True, adapter=adapter
    )
    assert sorted(r["dispatch_id"] for r in answered["resumed"]) == sorted([first, late])


def test_a_human_rejection_answered_before_re_projection_leaves_the_late_member_parked(
    tmp_path: Path,
) -> None:
    repo, workspace, adapter, _request = _parked_on(tmp_path, "pr_creation")
    _write_repo_posture(repo, escalate_resume="block")
    [first] = _clone_parked(workspace, [dict(_BLOCKED)])
    gate_router.resolve_parked(
        execution.CheckpointManager(workspace).load().dispatch_attempts[0],
        workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo),
    )
    fingerprint = [e for e in _mirror_entries(repo) if e.get("dedupe_fingerprint")][0]["dedupe_fingerprint"]
    gate_router.answer_escalation(fingerprint, workspace=workspace, repo_root=repo, approved=False, adapter=adapter)
    late = _park_late_member(workspace, _BLOCKED)

    answered = gate_router.answer_escalation(
        fingerprint, workspace=workspace, repo_root=repo, approved=True, adapter=adapter
    )

    assert [r["dispatch_id"] for r in answered["resumed"]] == [first]
    assert _status(workspace, late) == "parked"


def test_different_missing_lanes_are_separate_escalations(tmp_path: Path) -> None:
    repo, workspace, adapter, _request = _parked_on(tmp_path, "pr_creation")
    _write_repo_posture(repo, escalate_resume="block")
    base = {"kind": "capability_unavailable", "gate": None, "phase": "PLAN_REVIEW", "reason": "quorum unmet"}
    _clone_parked(workspace, [dict(base, missing_lanes=["codex"]), dict(base, missing_lanes=["codex", "gemini"])])
    for attempt in execution.CheckpointManager(workspace).load().dispatch_attempts:
        gate_router.resolve_parked(
            attempt, workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
        )
    assert len([e for e in _mirror_entries(repo) if e.get("dedupe_fingerprint")]) == 2


def test_a_secret_in_the_blocked_command_is_redacted(tmp_path: Path) -> None:
    repo, workspace, adapter, _request = _parked_on(tmp_path, "pr_creation")
    _write_repo_posture(repo, escalate_resume="block")
    _clone_parked(workspace, [dict(_BLOCKED, command='curl -H "Authorization: Bearer abc123..."')])
    attempt = execution.CheckpointManager(workspace).load().dispatch_attempts[0]
    resolution = gate_router.resolve_parked(
        attempt, workspace=workspace, repo_root=repo, adapter=adapter, evaluator=_router_gate(repo)
    )
    commands = resolution.routed.record["parked_commands"]
    assert commands and "abc123" not in commands[0] and "[REDACTED:" in commands[0]
