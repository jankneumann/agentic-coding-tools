"""End-to-end evaluation-log coverage for the supervise gate router (ri-04, D2-D6).

Ties gate_router.py, ExecutionAdapter, and cycle_state.py's CLI together over
one flowing scenario: `cycle` (gate-check) -> `execute` (prepare) -> a parked
child -> a posture flip -> resume -> a second cycle that reuses the roadmap
approval and honours a late coordinator answer. Asserts the evaluation log
(gate-log) has exactly one record per real decision -- none for a reuse or a
re-surface -- and that every `approval_ref` used along the way resolves.

A second, focused test proves the `notified` / `default_action` distinguish-
ability contract grok's round-3 finding required (task 2.10's own note): a
genuine `default_action: block` timeout and an undelivered `proceed` forced
closed persist the *same* `default_action` value, so only `notified` tells
them apart.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SUPERVISE_SCRIPTS = _REPO_ROOT / "skills" / "supervise" / "scripts"
_RUNTIME_SCRIPTS = _REPO_ROOT / "skills" / "roadmap-runtime" / "scripts"
_SKILLS_ROOT = _REPO_ROOT / "skills"
for _dir in (_SUPERVISE_SCRIPTS, _RUNTIME_SCRIPTS, _SKILLS_ROOT):
    if str(_dir) not in sys.path:  # pragma: no cover - import wiring
        sys.path.insert(0, str(_dir))

import gate_router  # noqa: E402
from execution import ExecutionAdapter  # noqa: E402
from models import Effort, ItemStatus, Roadmap, RoadmapItem  # noqa: E402
from shared.approval_gate import (  # noqa: E402
    ApprovalGate,
    DefaultAction,
)
from shared.trust_posture import Disposition, Gate, GateDisposition, TrustPosture  # noqa: E402

_SCHEMAS = _REPO_ROOT / "openspec" / "schemas"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _install_schemas(repo: Path) -> None:
    target = repo / "openspec" / "schemas"
    target.mkdir(parents=True, exist_ok=True)
    for name in (
        "supervisor-record.schema.json",
        "supervisor-record-mirror.schema.json",
        "roadmap.schema.json",
        "checkpoint.schema.json",
    ):
        shutil.copy2(_SCHEMAS / name, target / name)


def _write_posture(repo: Path, **gates: dict) -> None:
    lines = ["---", "schema_version: 1", "gates:"]
    for gate, cfg in gates.items():
        lines.append(f"  {gate}:")
        for key, value in cfg.items():
            lines.append(f"    {key}: {value}")
    lines.append("---\n")
    (repo / "TRUST_POSTURE.md").write_text("\n".join(lines), encoding="utf-8")


def _write_work_packages(repo: Path, change_id: str) -> None:
    package = {
        "package_id": f"wp-{change_id}",
        "task_type": "implementation",
        "description": f"e2e fixture for {change_id}",
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
            "openapi": {"primary": "contracts/openapi.yaml", "files": ["contracts/openapi.yaml"]},
        },
        "packages": [package],
    }
    path = repo / "openspec" / "changes" / change_id / "work-packages.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False))


class FakeCoordinator:
    def __init__(self, *, statuses=None, notify_return: bool = False, request_id: str = "appr-e2e") -> None:
        self.statuses = list(statuses or [])
        self.notify_return = notify_return
        self.request_id = request_id
        self._poll_index = 0

    def request_approval(self, *, operation, resource, context, timeout_seconds) -> str:
        return self.request_id

    def push_notification(self, *, subject, body, approval_id) -> bool:
        return self.notify_return

    def check_approval(self, approval_id: str) -> str:
        if self._poll_index < len(self.statuses):
            status = self.statuses[self._poll_index]
        else:
            status = self.statuses[-1] if self.statuses else "pending"
        self._poll_index += 1
        return status


class RecordingAudit:
    def record(self, record: dict) -> bool:
        return True


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _service(repo: Path, *, coordinator=None, poll_interval: float = 1.0) -> ApprovalGate:
    clock = FakeClock()
    posture = _load_posture(repo)
    return ApprovalGate(
        coordinator=coordinator or FakeCoordinator(),
        audit=RecordingAudit(),
        agent_id="e2e",
        poll_interval_seconds=poll_interval,
        clock=clock.time,
        sleep=clock.sleep,
        posture_loader=lambda repo_root=None, path=None: posture,
    )


def _load_posture(repo: Path) -> TrustPosture:
    from shared.trust_posture import load_posture

    return load_posture(repo)


@pytest.fixture
def scenario(tmp_path: Path):
    """A roadmap `alpha` (one item, change `change-alpha`) plus a managed
    worktree root placed OUTSIDE the supervisor repo -- so `gate-log`'s child
    loop-state resolution exercises D6's attempt-resolved path (the recorded
    `isolation.worktree_path`), never the co-located-tmp-tree shortcut."""
    repo = tmp_path / "repo"
    _install_schemas(repo)
    roadmap_dir = repo / "openspec" / "roadmaps" / "alpha"
    roadmap_dir.mkdir(parents=True)
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="alpha",
        source_proposal="proposal.md",
        items=[RoadmapItem("ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S, change_id="change-alpha")],
    )
    (roadmap_dir / "roadmap.yaml").write_text(yaml.safe_dump(roadmap.to_dict(), sort_keys=False))
    _write_work_packages(repo, "change-alpha")

    # Deliberately NOT under repo/ -- a real managed worktree never is either;
    # this just makes "outside the supervisor repo root" unambiguous in the test.
    managed_root = tmp_path / "external-worktrees"
    worktree = managed_root / "change-alpha"
    (worktree / ".git").mkdir(parents=True)
    loop_state = worktree / "openspec" / "changes" / "change-alpha" / "loop-state.json"
    loop_state.parent.mkdir(parents=True)
    loop_state.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "change_id": "change-alpha",
                "current_phase": "INIT",
                "handoff_ids": [],
                "last_handoff_id": None,
                "pending_gate": None,
                "gate_decisions": [],
            }
        )
        + "\n"
    )
    return repo, roadmap_dir, managed_root


def _adapter(managed_root: Path) -> ExecutionAdapter:
    return ExecutionAdapter(
        managed_worktree_root=managed_root,
        branch_resolver=lambda _: "openspec/change-alpha",
        commit_resolver=lambda _: "a" * 40,
        liveness_probe=lambda _: "live",
        host_entry=lambda change_id, request: "entered",
    )


def _isolation(managed_root: Path) -> dict[str, str]:
    return {
        "mode": "managed_worktree",
        "worktree_path": str(managed_root / "change-alpha"),
        "branch": "openspec/change-alpha",
    }


def _result(request: dict[str, Any], *, gate: str = "pr_creation") -> dict[str, Any]:
    """Overwrite the child's loop-state.json to match the `parked` outcome and
    compute its digest fresh, matching `apply`'s exact-evidence check --
    mirrors test_execution.py's own `_result` helper."""
    import hashlib

    loop_state_path = (
        Path(request["isolation"]["worktree_path"]) / "openspec" / "changes" / "change-alpha" / "loop-state.json"
    )
    loop_state_path.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "change_id": "change-alpha",
                "current_phase": "VALIDATE",
                "handoff_ids": [],
                "last_handoff_id": None,
                "pending_gate": {"gate": gate},
                "gate_decisions": [],
            }
        )
        + "\n"
    )
    return {
        "schema_version": 1,
        "dispatch_id": request["dispatch_id"],
        "change_id": request["change_id"],
        "attempt": request["attempt"],
        "lease_generation": request["lease_generation"],
        "outcome": "parked",
        "worktree_path": request["isolation"]["worktree_path"],
        "branch": request["isolation"]["branch"],
        "parked": {"kind": "pending_gate", "reason": "operator approval required", "gate": gate},
        "evidence": {
            "loop_state_path": "openspec/changes/change-alpha/loop-state.json",
            "commit": "a" * 40,
            "loop_state_digest": hashlib.sha256(loop_state_path.read_bytes()).hexdigest(),
        },
    }


# --------------------------------------------------------------------------- #
# The flowing scenario
# --------------------------------------------------------------------------- #
def test_cycle_execute_parked_flip_resume_second_cycle_late_answer(scenario) -> None:
    repo, workspace, managed_root = scenario

    # --- cycle 1: roadmap_approval under notify_with_timeout, unanswered --- #
    coord1 = FakeCoordinator(statuses=["pending"], notify_return=False)
    _write_posture(
        repo,
        roadmap_approval={"disposition": "notify_with_timeout", "timeout_seconds": 30, "default_action": "block"},
        pr_creation={"disposition": "block"},
    )
    service1 = _service(repo, coordinator=coord1)
    first = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service1)
    assert first.decision.resolution.value == "timeout_default_block"
    assert first.decision.notified is False

    # --- cycle 2: SAME evaluation subject, but the coordinator now answers -- #
    # "reuses the roadmap approval" (same subject key) "and honours a late
    # coordinator answer" (check_filed, no re-filing).
    coord2 = FakeCoordinator(statuses=["approved"])
    service2 = _service(repo, coordinator=coord2)
    second = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service2)
    assert second.decision.proceed
    assert second.decision.resolution.value == "approved"
    roadmap_approval_ref = f"gate-decision:{second.record['decision_id']}"

    # A third gate-check with the SAME subject and an unchanged posture must
    # reuse the decision -- no new coordinator call, no new gate-log entry.
    service3 = _service(repo, coordinator=FakeCoordinator())
    third = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service3)
    assert third.reused is True
    assert third.record["decision_id"] == second.record["decision_id"]

    # --- execute: prepare with the roadmap_approval_ref cycle produced ----- #
    adapter = _adapter(managed_root)
    prepared = adapter.prepare(
        workspace,
        repo_root=repo,
        isolation_resolver=lambda _: _isolation(managed_root),
        roadmap_approval_ref=roadmap_approval_ref,
    )
    assert len(prepared["requests"]) == 1
    request = prepared["requests"][0]

    # child_start / acknowledge / enter -- the normal ack/go sequence.
    adapter.child_start(
        workspace, dispatch_id=request["dispatch_id"], launch_token=request["launch_token"],
        lease_generation=request["lease_generation"], owner_nonce="owner-nonce-0001",
    )
    adapter.acknowledge(workspace, dispatch_id=request["dispatch_id"], lease_generation=1, handle="task-0001")
    adapter.enter(workspace, dispatch_id=request["dispatch_id"], lease_generation=1, owner_nonce="owner-nonce-0001")

    # --- parked child: the dispatched item parks on pr_creation ------------ #
    applied = adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[_result(request)],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    assert applied["parked_item_ids"] == ["ri-01"]

    # --- posture flip: pr_creation now auto-resolves ------------------------ #
    _write_posture(
        repo,
        roadmap_approval={"disposition": "notify_with_timeout", "timeout_seconds": 30, "default_action": "block"},
        pr_creation={"disposition": "auto"},
    )

    # --- resume: resolve_parked unparks the child with no console answer --- #
    checkpoint_manager = gate_router.CheckpointManager(workspace, repo)
    checkpoint = checkpoint_manager.load()
    attempt = next(a for a in checkpoint.dispatch_attempts if a["dispatch_id"] == request["dispatch_id"])
    service4 = _service(repo, coordinator=FakeCoordinator())
    resolution = gate_router.resolve_parked(attempt, workspace=workspace, repo_root=repo, adapter=adapter, evaluator=service4)
    assert resolution.outcome == "proceed"
    assert resolution.routed.decision.resolution.value == "auto"

    # --- the log: one record per real decision, none for reuse/re-surface -- #
    log = gate_router.gate_log(workspace, repo)
    checkpoint_records = [r for r in log if r.get("origin") == "checkpoint"]
    # roadmap_approval: timeout_default_block (cycle 1) + approved (cycle 2) = 2.
    # cycle 3's reuse adds nothing. pr_creation: auto (resume) = 1. Total 3.
    assert len(checkpoint_records) == 3
    decision_ids = {r["decision_id"] for r in checkpoint_records}
    assert len(decision_ids) == 3  # every record distinct -- confirms no duplicate for the reuse

    # every approval_ref this scenario minted resolves.
    checkpoint = checkpoint_manager.load()
    roadmap = gate_router.load_roadmap(workspace / "roadmap.yaml", repo)
    resolved = gate_router.require_approval_ref(
        checkpoint, roadmap_approval_ref, gate=Gate.ROADMAP_APPROVAL, roadmap_id="alpha", roadmap=roadmap
    )
    assert resolved["decision_id"] == second.record["decision_id"]
    child_ref = f"gate-decision:{resolution.routed.record['decision_id']}"
    resolved_child = gate_router.require_approval_ref(
        checkpoint, child_ref, gate=Gate.PR_CREATION, dispatch_id=request["dispatch_id"]
    )
    assert resolved_child["decision_id"] == resolution.routed.record["decision_id"]

    # the child's loop-state.json was read from its OWN worktree, outside repo/.
    child_log_entries = [r for r in log if r.get("origin") == "change-alpha"]
    assert child_log_entries == []  # this fixture's child loop-state carries no gate_decisions of its own
    # (a non-empty loop-state.json outside repo/ was still readable without error --
    # proven by the absence of a `degraded: True` entry for "change-alpha" above.)
    assert not any(r.get("origin") == "change-alpha" and r.get("degraded") for r in log)


# --------------------------------------------------------------------------- #
# notified / default_action distinguishability (grok round-3 finding #43)
# --------------------------------------------------------------------------- #
def test_notified_distinguishes_genuine_block_timeout_from_undelivered_proceed() -> None:
    """Both scenarios below persist resolution=timeout_default_block and
    default_action=block (the posture's declared value, in the first case;
    _apply_default's fail-closed override, in the second) -- proving that
    field alone cannot tell them apart, and that `notified` can."""

    # Scenario A: posture genuinely says default_action: block. Delivered.
    coord_a = FakeCoordinator(statuses=["pending"], notify_return=True)
    posture_a = TrustPosture(
        gates={
            Gate.PR_CREATION: GateDisposition(
                Disposition.NOTIFY_WITH_TIMEOUT, timeout_seconds=10, default_action=DefaultAction.BLOCK
            )
        },
        present=True,
    )
    clock_a = FakeClock()
    service_a = ApprovalGate(
        coordinator=coord_a, audit=RecordingAudit(), agent_id="a",
        clock=clock_a.time, sleep=clock_a.sleep,
        posture_loader=lambda repo_root=None, path=None: posture_a,
    )
    decision_a = service_a.evaluate(Gate.PR_CREATION, {})

    # Scenario B: posture says default_action: proceed, but the notification
    # was never delivered -- _apply_default fails closed and overwrites
    # default_action to BLOCK, making it look identical to A.
    coord_b = FakeCoordinator(statuses=["pending"], notify_return=False)
    posture_b = TrustPosture(
        gates={
            Gate.PR_CREATION: GateDisposition(
                Disposition.NOTIFY_WITH_TIMEOUT, timeout_seconds=10, default_action=DefaultAction.PROCEED
            )
        },
        present=True,
    )
    clock_b = FakeClock()
    service_b = ApprovalGate(
        coordinator=coord_b, audit=RecordingAudit(), agent_id="b",
        clock=clock_b.time, sleep=clock_b.sleep,
        posture_loader=lambda repo_root=None, path=None: posture_b,
    )
    decision_b = service_b.evaluate(Gate.PR_CREATION, {})

    record_a = decision_a.to_audit_record()
    record_b = decision_b.to_audit_record()

    # The trap: resolution and default_action are IDENTICAL between the two.
    assert record_a["resolution"] == record_b["resolution"] == "timeout_default_block"
    assert record_a["default_action"] == record_b["default_action"] == "block"
    assert record_a["reason"] != record_b["reason"]  # the only textual tell -- must not be required
    # notified is the field that actually distinguishes them, round-tripped
    # onto the persisted record without needing to parse `reason`.
    assert record_a["notified"] is True
    assert record_b["notified"] is False
