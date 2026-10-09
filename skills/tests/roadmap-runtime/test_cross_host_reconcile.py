"""Cross-host reconcile (dispatch-contract Host-Portable Attempt Isolation, D7;
acceptance outcome 7).

A checkpoint committed on host A is reconciled by host B: a matching worktree is
rebound (same generation), a missing one is reinitialized (prepared / pre-go),
a diverged one is refused, and a post-go attempt of unknown liveness stays
subject to quarantine.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from models import Effort, ItemStatus, Roadmap, RoadmapItem

_REPO_ROOT = Path(__file__).resolve().parents[3]
for _sub in ("supervise/scripts", "autopilot-roadmap/scripts"):
    _path = str(_REPO_ROOT / "skills" / _sub)
    if _path not in sys.path:
        sys.path.append(_path)

import gate_router  # noqa: E402
from checkpoint import CheckpointManager  # noqa: E402
from execution import ExecutionAdapter, ExecutionStateError  # noqa: E402
from shared.trust_posture import Gate  # noqa: E402

_CHANGE = "change-alpha"
_BRANCH = f"openspec/{_CHANGE}"


def _probe(_repo: Path) -> tuple[int, str]:
    return 0, json.dumps(
        {
            "modes": {m: {"verified": ["claude_code", "codex"], "unverified": []} for m in ("review", "alternative", "quick")},
            "probe_command": "review_dispatcher.py --check-vendors --json",
            "quorum_policy": {"environment": "host", "min_quorum": {"PLAN_REVIEW": 2, "IMPL_REVIEW": 2, "VAL_REVIEW": 2}, "policy_id": None, "sunset": None},
        }
    )


class _Clock:
    def __init__(self) -> None:
        from datetime import datetime, timezone

        self.now = datetime(2026, 10, 9, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def _adapter(managed: Path, repo: Path, host: str, **overrides: Any) -> ExecutionAdapter:
    kwargs: dict[str, Any] = dict(
        managed_worktree_root=managed,
        repo_root=repo,
        host_id=host,
        clock=_Clock(),
        branch_resolver=lambda _path: _BRANCH,
        commit_resolver=lambda _path: "a" * 40,
        liveness_probe=lambda _handle: "live",
        host_entry=lambda *_a: "entered",
        profile_probe=_probe,
        ancestry_check=lambda _worktree, _commit: True,
        worktree_creator=lambda *_a: pytest.fail("no worktree may be created"),
    )
    kwargs.update(overrides)
    return ExecutionAdapter(**kwargs)


def _loop_state(worktree: Path, **fields: Any) -> Path:
    path = worktree / "openspec" / "changes" / _CHANGE / "loop-state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {"schema_version": 6, "change_id": _CHANGE, "current_phase": "PLAN", "handoff_ids": [],
             "last_handoff_id": None, "pending_gate": None}
    state.update(fields)
    path.write_text(json.dumps(state) + "\n")
    return path


@pytest.fixture()
def host_a(tmp_path: Path) -> dict[str, Any]:
    repo = tmp_path / "repo"
    schemas = repo / "openspec" / "schemas"
    schemas.mkdir(parents=True)
    for name in ("roadmap.schema.json", "checkpoint.schema.json",
                 "supervisor-record.schema.json", "supervisor-record-mirror.schema.json"):
        shutil.copy2(_REPO_ROOT / "openspec" / "schemas" / name, schemas / name)
    workspace = repo / "roadmap"
    workspace.mkdir()
    roadmap = Roadmap(schema_version=1, roadmap_id="alpha", source_proposal="p.md",
                      items=[RoadmapItem("ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S, change_id=_CHANGE)])
    (workspace / "roadmap.yaml").write_text(yaml.safe_dump(roadmap.to_dict(), sort_keys=False))
    managed_a = tmp_path / "host-a-worktrees"
    worktree_a = managed_a / _CHANGE
    (worktree_a / ".git").mkdir(parents=True)
    _loop_state(worktree_a)
    adapter = _adapter(managed_a, repo, "host-a")
    ref = gate_router.answer(Gate.ROADMAP_APPROVAL, workspace=workspace, repo_root=repo, approved=True)
    request = adapter.prepare(
        workspace, repo_root=repo,
        isolation_resolver=lambda _item: {"mode": "managed_worktree", "worktree_path": str(worktree_a), "branch": _BRANCH},
        roadmap_approval_ref=f"gate-decision:{ref.record['decision_id']}",
    )["requests"][0]
    return {"repo": repo, "workspace": workspace, "adapter": adapter, "request": request,
            "worktree_a": worktree_a, "tmp": tmp_path}


def _launch(world: dict[str, Any]) -> None:
    adapter, workspace, request = world["adapter"], world["workspace"], world["request"]
    adapter.child_start(workspace, dispatch_id=request["dispatch_id"], launch_token=request["launch_token"],
                        lease_generation=1, owner_nonce="owner-nonce-0000000001")
    adapter.acknowledge(workspace, dispatch_id=request["dispatch_id"], lease_generation=1, handle="task-a")
    adapter.enter(workspace, dispatch_id=request["dispatch_id"], lease_generation=1, owner_nonce="owner-nonce-0000000001")


def _park(world: dict[str, Any]) -> str:
    _launch(world)
    path = _loop_state(world["worktree_a"], pending_gate={"gate": "pr_creation"})
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    request = world["request"]
    world["adapter"].apply(
        world["workspace"], batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[{
            "schema_version": 2, "dispatch_id": request["dispatch_id"], "change_id": _CHANGE,
            "attempt": 1, "lease_generation": 1, "outcome": "parked",
            "worktree_ref": request["isolation"]["worktree_ref"], "branch": _BRANCH, "host_id": "host-a",
            "degradations": [],
            "parked": {"kind": "pending_gate", "gate": "pr_creation", "reason": "approval"},
            "evidence": {"loop_state_path": f"openspec/changes/{_CHANGE}/loop-state.json",
                         "commit": "a" * 40, "loop_state_digest": digest},
        }],
        dispatch_fn=lambda _i, _p, context: context["dispatch_result"],
        repo_root=world["repo"],
    )
    return digest


def _attempt(world: dict[str, Any]) -> dict[str, Any]:
    return CheckpointManager(world["workspace"]).load().dispatch_attempts[0]


def _host_b_with_worktree(world: dict[str, Any], **overrides: Any) -> tuple[ExecutionAdapter, Path]:
    managed_b = world["tmp"] / "host-b-worktrees"
    shutil.copytree(world["worktree_a"], managed_b / _CHANGE)
    return _adapter(managed_b, world["repo"], "host-b", **overrides), managed_b


def test_another_host_rebinds_a_matching_worktree(host_a: dict[str, Any]) -> None:
    _park(host_a)
    before = _attempt(host_a)
    adapter_b, _managed_b = _host_b_with_worktree(host_a)

    adapter_b.reconcile(host_a["workspace"], dispatch_id=host_a["request"]["dispatch_id"])

    after = _attempt(host_a)
    assert after["lease_generation"] == before["lease_generation"]
    assert after["isolation"]["host_id"] == "host-b"
    assert after["launch_history"][-1]["state"] == "rebound"
    assert after["launch_history"][-1]["host_id"] == "host-b"
    assert after["status"] == "parked"


def test_rebind_refuses_a_diverged_worktree(host_a: dict[str, Any]) -> None:
    _park(host_a)
    before = _attempt(host_a)
    adapter_b, _ = _host_b_with_worktree(host_a, ancestry_check=lambda _w, _c: False)

    report = adapter_b.reconcile(host_a["workspace"], dispatch_id=host_a["request"]["dispatch_id"])

    assert report["state"] == "rebind_refused:evidence_mismatch"
    assert _attempt(host_a) == before


def test_rebind_refuses_a_loop_state_digest_mismatch(host_a: dict[str, Any]) -> None:
    _park(host_a)
    adapter_b, managed_b = _host_b_with_worktree(host_a)
    _loop_state(managed_b / _CHANGE, current_phase="IMPLEMENT")

    report = adapter_b.reconcile(host_a["workspace"], dispatch_id=host_a["request"]["dispatch_id"])

    assert report["state"] == "rebind_refused:evidence_mismatch"
    assert _attempt(host_a)["isolation"]["host_id"] == "host-a"


def test_another_host_reinitializes_a_prepared_attempt_without_a_worktree(host_a: dict[str, Any]) -> None:
    created: list[Path] = []

    def create(_repo: Path, managed: Path, change_id: str, branch: str) -> Path:
        assert branch == _BRANCH
        target = managed / change_id
        (target / ".git").mkdir(parents=True)
        created.append(target)
        return target

    managed_b = host_a["tmp"] / "host-b-worktrees"
    managed_b.mkdir()
    adapter_b = _adapter(managed_b, host_a["repo"], "host-b", worktree_creator=create)
    before = _attempt(host_a)

    adapter_b.reconcile(host_a["workspace"], dispatch_id=host_a["request"]["dispatch_id"])

    after = _attempt(host_a)
    assert created == [managed_b / _CHANGE]
    assert after["lease_generation"] == before["lease_generation"] + 1
    assert after["launch_digest"] != before["launch_digest"]
    assert after["isolation"] == {"mode": "managed_worktree", "worktree_ref": _CHANGE, "branch": _BRANCH, "host_id": "host-b"}
    # Host B can launch it: reissue mints its token, the old one is revoked.
    reissued = adapter_b.reissue(host_a["workspace"], dispatch_id=host_a["request"]["dispatch_id"])
    with pytest.raises(ExecutionStateError, match="launch token mismatch"):
        adapter_b.child_start(host_a["workspace"], dispatch_id=reissued["dispatch_id"],
                              launch_token=host_a["request"]["launch_token"], lease_generation=2,
                              owner_nonce="owner-nonce-0000000002")
    claimed = adapter_b.child_start(host_a["workspace"], dispatch_id=reissued["dispatch_id"],
                                    launch_token=reissued["launch_token"], lease_generation=2,
                                    owner_nonce="owner-nonce-0000000002")
    assert claimed["status"] == "claimed"


def test_an_unexpired_pre_go_claim_on_another_host_is_not_taken_over(host_a: dict[str, Any]) -> None:
    """D6/D7: reinitializing a claimed attempt is a takeover, allowed only once
    its pre-go lease expired (the same rule child_start and reissue apply)."""
    request = host_a["request"]
    host_a["adapter"].child_start(host_a["workspace"], dispatch_id=request["dispatch_id"],
                                  launch_token=request["launch_token"], lease_generation=1,
                                  owner_nonce="owner-nonce-0000000001", lease_seconds=60)
    before = _attempt(host_a)
    managed_b = host_a["tmp"] / "host-b-worktrees"
    managed_b.mkdir()
    adapter_b = _adapter(managed_b, host_a["repo"], "host-b")  # creating a worktree fails the test

    adapter_b.reconcile(host_a["workspace"], dispatch_id=request["dispatch_id"])

    assert _attempt(host_a) == before


def test_an_expired_pre_go_claim_on_another_host_is_reinitialized(host_a: dict[str, Any]) -> None:
    from datetime import timedelta

    request = host_a["request"]
    host_a["adapter"].child_start(host_a["workspace"], dispatch_id=request["dispatch_id"],
                                  launch_token=request["launch_token"], lease_generation=1,
                                  owner_nonce="owner-nonce-0000000001", lease_seconds=60)
    managed_b = host_a["tmp"] / "host-b-worktrees"
    managed_b.mkdir()

    def create(_repo: Path, managed: Path, change_id: str, _branch: str) -> Path:
        (managed / change_id / ".git").mkdir(parents=True)
        return managed / change_id

    clock = _Clock()
    clock.now += timedelta(seconds=61)
    adapter_b = _adapter(managed_b, host_a["repo"], "host-b", worktree_creator=create, clock=clock)

    adapter_b.reconcile(host_a["workspace"], dispatch_id=request["dispatch_id"])

    after = _attempt(host_a)
    assert after["status"] == "prepared"
    assert after["lease_generation"] == 2
    assert after["isolation"]["host_id"] == "host-b"


def test_a_post_go_attempt_of_unknown_liveness_is_quarantined_not_rebound(host_a: dict[str, Any]) -> None:
    _launch(host_a)
    managed_b = host_a["tmp"] / "host-b-worktrees"
    managed_b.mkdir()
    adapter_b = _adapter(managed_b, host_a["repo"], "host-b", liveness_probe=lambda _h: "unknown")

    reconciled = adapter_b.reconcile(host_a["workspace"], dispatch_id=host_a["request"]["dispatch_id"])

    assert reconciled["status"] == "quarantined"
    assert list(managed_b.iterdir()) == []
