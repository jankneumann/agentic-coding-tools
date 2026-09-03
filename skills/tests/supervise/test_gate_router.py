"""Tests for skills/supervise/scripts/gate_router.py (ri-04, D2-D7).

Spec: openspec/changes/route-supervise-gates-through-the-approval-gate-service/
      specs/supervise/spec.md, Requirement "Supervise Gate Routing".
Design decisions: D2, D3, D4, D5, D6, D7.
"""
from __future__ import annotations

import ast
import json
import shutil
import sys
from datetime import timedelta
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SUPERVISE_SCRIPTS = _REPO_ROOT / "skills" / "supervise" / "scripts"
_SCHEMAS = _REPO_ROOT / "openspec" / "schemas"
if str(_SUPERVISE_SCRIPTS) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(_SUPERVISE_SCRIPTS))

import cycle_state  # noqa: E402
import gate_router  # noqa: E402

_SKILLS_ROOT = _REPO_ROOT / "skills"
if str(_SKILLS_ROOT) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(_SKILLS_ROOT))

from shared.approval_gate import (  # noqa: E402
    ApprovalGate,
    CoordinatorUnavailable,
    Outcome,
    Resolution,
)
from shared.trust_posture import Disposition, Gate, GateDisposition, TrustPosture  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures + test doubles
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
        source = _SCHEMAS / name
        if source.exists():
            shutil.copy2(source, target / name)


def _item(item_id: str, **kw) -> dict:
    d = {
        "item_id": item_id,
        "title": "Item",
        "status": "approved",
        "priority": 1,
        "effort": "M",
        "depends_on": kw.pop("depends_on", []),
        "acceptance_outcomes": ["done"],
    }
    d.update(kw)
    return d


def _write_roadmap(repo: Path, roadmap_id: str, items: list[dict]) -> Path:
    d = repo / "openspec" / "roadmaps" / roadmap_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "roadmap.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "roadmap_id": roadmap_id,
                "source_proposal": f"docs/proposals/{roadmap_id}.md",
                "status": "planning",
                "items": items,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return d


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _install_schemas(r)
    return r


@pytest.fixture
def workspace(repo: Path) -> Path:
    return _write_roadmap(repo, "alpha", [_item("ri-01", change_id="demo-change")])


class FakeCoordinator:
    """Minimal scriptable coordinator client (mirrors shared/tests/test_approval_gate.py)."""

    def __init__(self, *, statuses=None, raise_on=None, notify_return=False, request_id="appr-1"):
        self.statuses = list(statuses or [])
        self.raise_on = raise_on
        self.notify_return = notify_return
        self.request_id = request_id
        self.calls: list[str] = []
        self._poll_index = 0

    def request_approval(self, *, operation, resource, context, timeout_seconds) -> str:
        self.calls.append("request_approval")
        if self.raise_on == "request":
            raise CoordinatorUnavailable("filing failed")
        return self.request_id

    def push_notification(self, *, subject, body, approval_id) -> bool:
        self.calls.append("push_notification")
        if self.raise_on == "notify":
            raise CoordinatorUnavailable("notify failed")
        return self.notify_return

    def check_approval(self, approval_id: str) -> str:
        self.calls.append("check_approval")
        if self.raise_on == "check":
            raise CoordinatorUnavailable("poll failed")
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


def make_service(posture: TrustPosture, *, coordinator=None, poll_interval: float = 1.0) -> ApprovalGate:
    clock = FakeClock()
    return ApprovalGate(
        coordinator=coordinator or FakeCoordinator(),
        audit=RecordingAudit(),
        agent_id="supervise",
        poll_interval_seconds=poll_interval,
        clock=clock.time,
        sleep=clock.sleep,
        posture_loader=lambda repo_root=None, path=None: posture,
    )


def posture_with(gate: Gate, gd: GateDisposition, *, present: bool = True) -> TrustPosture:
    return TrustPosture(gates={gate: gd}, present=present)


from shared.trust_posture import DefaultAction  # noqa: E402

NOTIFY_BLOCK = GateDisposition(
    disposition=Disposition.NOTIFY_WITH_TIMEOUT, timeout_seconds=30, default_action=DefaultAction.BLOCK
)


def read_checkpoint_json(workspace: Path) -> dict:
    return json.loads((workspace / "checkpoint.json").read_text(encoding="utf-8"))


def read_mirror(repo: Path) -> dict:
    return json.loads((repo / cycle_state.MIRROR_PATH).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# .1 auto posture
# --------------------------------------------------------------------------- #


class TestAutoPosture:
    def test_auto_records_proceed_with_correlation_ids_and_upserts_standing_decision(
        self, repo: Path, workspace: Path
    ) -> None:
        service = make_service(posture_with(Gate.ROADMAP_APPROVAL, GateDisposition(Disposition.AUTO)))

        routed = gate_router.evaluate(
            Gate.ROADMAP_APPROVAL, {"verb": "cycle"}, workspace=workspace, repo_root=repo, evaluator=service
        )

        assert routed.decision.proceed
        assert routed.record["gate"] == "roadmap_approval"
        assert routed.record["source"] == "supervise"
        assert routed.record["verb"] == "cycle"
        assert routed.record["roadmap_id"] == "alpha"
        assert routed.record["decision_id"]
        assert routed.record["roadmap_fingerprint"]

        on_disk = read_checkpoint_json(workspace)
        assert len(on_disk["gate_decisions"]) == 1
        assert on_disk["gate_decisions"][0]["decision_id"] == routed.record["decision_id"]

        mirror = read_mirror(repo)
        assert mirror["pending_gates"] == []
        assert mirror["standing_decisions"][0]["decision"] == "roadmap_approval:proceed"
        assert mirror["standing_decisions"][0]["scope"] == "alpha"


# --------------------------------------------------------------------------- #
# .2 block posture parks for a console answer
# --------------------------------------------------------------------------- #


class TestBlockPosture:
    def test_block_records_posture_block_and_projects_pending_gate(
        self, repo: Path, workspace: Path
    ) -> None:
        service = make_service(posture_with(Gate.ROADMAP_APPROVAL, GateDisposition(Disposition.BLOCK)))

        routed = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service)

        assert routed.decision.blocked
        assert routed.decision.resolution is Resolution.POSTURE_BLOCK

        mirror = read_mirror(repo)
        assert len(mirror["pending_gates"]) == 1
        entry = mirror["pending_gates"][0]
        assert entry["gate"] == "roadmap_approval"
        assert entry["change_id"] == "demo-change"
        assert entry["source"] == "supervise"
        assert entry["decision_id"] == routed.record["decision_id"]
        assert entry["deadline"]

    def test_console_answer_originates_a_roadmap_approval_record_and_mirrors_standing_decision(
        self, repo: Path, workspace: Path
    ) -> None:
        routed = gate_router.answer(
            Gate.ROADMAP_APPROVAL, workspace=workspace, repo_root=repo, approved=True, note="direct invocation",
        )

        assert routed.decision.resolution is Resolution.CONSOLE_APPROVED
        assert routed.decision.proceed
        assert routed.record["note"] == "direct invocation"

        mirror = read_mirror(repo)
        assert mirror["pending_gates"] == []
        assert mirror["standing_decisions"][0]["decision"] == "roadmap_approval:proceed"

    def test_console_answer_for_unparked_non_roadmap_gate_is_refused(
        self, repo: Path, workspace: Path
    ) -> None:
        with pytest.raises(gate_router.GateRefusalError):
            gate_router.answer(
                Gate.PR_CREATION, workspace=workspace, repo_root=repo, approved=True, note=None,
                context={"dispatch_id": "d-1", "change_id": "demo-change"},
            )
        on_disk = read_checkpoint_json(workspace)
        assert on_disk.get("gate_decisions", []) == []


# --------------------------------------------------------------------------- #
# .3 notify posture waits + late answer honoured without re-filing
# --------------------------------------------------------------------------- #


class TestNotifyPosture:
    def test_timeout_default_block_then_late_check_filed_approval_proceeds_without_refiling(
        self, repo: Path, workspace: Path
    ) -> None:
        coord = FakeCoordinator(statuses=["pending"], notify_return=False)
        service = make_service(posture_with(Gate.ROADMAP_APPROVAL, NOTIFY_BLOCK), coordinator=coord)

        first = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service)

        assert first.decision.resolution is Resolution.TIMEOUT_BLOCK
        assert first.decision.notified is False
        assert first.record["approval_id"] == "appr-1"
        first_calls = list(coord.calls)
        assert first_calls.count("request_approval") == 1

        mirror = read_mirror(repo)
        assert len(mirror["pending_gates"]) == 1

        # Operator later approves in the coordinator; a fresh gate-check runs.
        coord2 = FakeCoordinator(statuses=["approved"])
        service2 = make_service(posture_with(Gate.ROADMAP_APPROVAL, NOTIFY_BLOCK), coordinator=coord2)
        second = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service2)

        assert second.decision.proceed
        assert second.decision.resolution is Resolution.APPROVED
        # Never re-files or re-notifies — only polls the existing approval.
        assert coord2.calls == ["check_approval"]

        on_disk = read_checkpoint_json(workspace)
        assert len(on_disk["gate_decisions"]) == 2

        mirror2 = read_mirror(repo)
        assert mirror2["pending_gates"] == []
        assert mirror2["standing_decisions"][0]["decision"] == "roadmap_approval:proceed"

    def test_still_pending_resurfaces_same_entry_and_files_nothing(
        self, repo: Path, workspace: Path
    ) -> None:
        coord = FakeCoordinator(statuses=["pending"], notify_return=False)
        service = make_service(posture_with(Gate.ROADMAP_APPROVAL, NOTIFY_BLOCK), coordinator=coord)
        first = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service)
        mirror_before = read_mirror(repo)

        coord2 = FakeCoordinator(statuses=["pending"])
        service2 = make_service(posture_with(Gate.ROADMAP_APPROVAL, NOTIFY_BLOCK), coordinator=coord2)
        second = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service2)

        assert second.reused is True
        assert second.record["decision_id"] == first.record["decision_id"]
        assert coord2.calls == ["check_approval"]
        on_disk = read_checkpoint_json(workspace)
        assert len(on_disk["gate_decisions"]) == 1
        mirror_after = read_mirror(repo)
        assert mirror_after["pending_gates"] == mirror_before["pending_gates"]


# --------------------------------------------------------------------------- #
# .4 ask once — reused until the DAG fingerprint changes
# --------------------------------------------------------------------------- #


class TestAskOnce:
    def test_proceed_is_reused_across_a_completion_only_change(self, repo: Path, workspace: Path) -> None:
        service = make_service(posture_with(Gate.ROADMAP_APPROVAL, GateDisposition(Disposition.AUTO)))
        first = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service)

        _write_roadmap(repo, "alpha", [_item("ri-01", change_id="demo-change", status="completed")])
        service2 = make_service(posture_with(Gate.ROADMAP_APPROVAL, GateDisposition(Disposition.AUTO)))
        second = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service2)

        assert second.reused is True
        assert second.record["decision_id"] == first.record["decision_id"]
        on_disk = read_checkpoint_json(workspace)
        assert len(on_disk["gate_decisions"]) == 1

    def test_superseded_item_changes_the_fingerprint_and_forces_reevaluation(
        self, repo: Path, workspace: Path
    ) -> None:
        service = make_service(posture_with(Gate.ROADMAP_APPROVAL, GateDisposition(Disposition.AUTO)))
        first = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service)

        _write_roadmap(repo, "alpha", [_item("ri-01", change_id="demo-change", status="superseded")])
        service2 = make_service(posture_with(Gate.ROADMAP_APPROVAL, GateDisposition(Disposition.AUTO)))
        second = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service2)

        assert second.reused is False
        assert second.record["decision_id"] != first.record["decision_id"]
        on_disk = read_checkpoint_json(workspace)
        assert len(on_disk["gate_decisions"]) == 2

    def test_external_dependency_edge_change_moves_the_fingerprint(self, repo: Path) -> None:
        base = [_item("ri-01", change_id="demo-change")]
        workspace = _write_roadmap(repo, "alpha", base)
        roadmap_a = cycle_state.load_all_roadmaps(repo)["alpha"]
        fp_before = gate_router.roadmap_fingerprint(roadmap_a)

        with_external = [_item("ri-01", change_id="demo-change", external_depends_on=["beta:ri-02"])]
        _write_roadmap(repo, "alpha", with_external)
        roadmap_b = cycle_state.load_all_roadmaps(repo)["alpha"]
        fp_after = gate_router.roadmap_fingerprint(roadmap_b)

        assert fp_before != fp_after


# --------------------------------------------------------------------------- #
# .9 posture flip unparks a child gate; policy_pause maps to escalate_resume
# --------------------------------------------------------------------------- #


class TestResolveParked:
    def _attempt(self, **overrides) -> dict:
        attempt = {
            "dispatch_id": "d-1",
            "change_id": "demo-change",
            "item_id": "ri-01",
            "parked": {"kind": "pending_gate", "gate": "pr_creation", "reason": "awaiting approval"},
        }
        attempt.update(overrides)
        return attempt

    class FakeAdapter:
        def __init__(self) -> None:
            self.resumed = []

        def resume(self, workspace, *, dispatch_id, approval_ref, kind):
            self.resumed.append((dispatch_id, approval_ref, kind))
            return {"resumed": True, "approval_ref": approval_ref}

    def test_blocked_deadline_is_requested_at_plus_timeout_when_an_approval_was_filed(
        self, repo: Path, workspace: Path
    ) -> None:
        adapter = self.FakeAdapter()
        coord = FakeCoordinator(statuses=["pending"], notify_return=False)
        service = make_service(posture_with(Gate.PR_CREATION, NOTIFY_BLOCK), coordinator=coord)

        resolution = gate_router.resolve_parked(
            self._attempt(), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=service
        )

        assert resolution.outcome == "blocked"
        assert resolution.pending_gate_entry["approval_id"] == "appr-1"
        requested = gate_router._parse_iso(resolution.pending_gate_entry["requested_at"])
        deadline = gate_router._parse_iso(resolution.pending_gate_entry["deadline"])
        assert deadline - requested == timedelta(seconds=30)

    def test_blocked_deadline_is_requested_at_plus_seven_days_when_no_approval_was_filed(
        self, repo: Path, workspace: Path
    ) -> None:
        adapter = self.FakeAdapter()
        service = make_service(posture_with(Gate.PR_CREATION, GateDisposition(Disposition.BLOCK)))

        resolution = gate_router.resolve_parked(
            self._attempt(), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=service
        )

        assert resolution.outcome == "blocked"
        assert resolution.pending_gate_entry["approval_id"] is None
        requested = gate_router._parse_iso(resolution.pending_gate_entry["requested_at"])
        deadline = gate_router._parse_iso(resolution.pending_gate_entry["deadline"])
        assert deadline - requested == gate_router.DEFAULT_BLOCK_HORIZON

    def test_a_prior_router_record_for_the_same_dispatch_id_is_reused_without_reevaluating(
        self, repo: Path, workspace: Path
    ) -> None:
        adapter = self.FakeAdapter()
        service = make_service(posture_with(Gate.PR_CREATION, GateDisposition(Disposition.AUTO)))
        first = gate_router.resolve_parked(
            self._attempt(), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=service
        )
        assert first.outcome == "proceed"
        assert len(adapter.resumed) == 1

        # A second resolution attempt for the SAME dispatch_id (e.g. a retried
        # reconciliation pass) must reuse the recorded decision rather than
        # calling the evaluator or the adapter again.
        service2 = make_service(posture_with(Gate.PR_CREATION, GateDisposition(Disposition.AUTO)))
        second = gate_router.resolve_parked(
            self._attempt(), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=service2
        )

        assert second.outcome == "proceed"
        assert second.routed.reused is True
        assert second.routed.record["decision_id"] == first.routed.record["decision_id"]
        assert len(adapter.resumed) == 2  # resume() is still called each time; only evaluation is deduped
        on_disk = read_checkpoint_json(workspace)
        assert len(on_disk["gate_decisions"]) == 1

    def test_a_prior_blocked_record_for_the_same_dispatch_id_is_resurfaced_not_refiled(
        self, repo: Path, workspace: Path
    ) -> None:
        adapter = self.FakeAdapter()
        service = make_service(posture_with(Gate.PR_CREATION, GateDisposition(Disposition.BLOCK)))
        first = gate_router.resolve_parked(
            self._attempt(), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=service
        )
        assert first.outcome == "blocked"

        service2 = make_service(posture_with(Gate.PR_CREATION, GateDisposition(Disposition.BLOCK)))
        second = gate_router.resolve_parked(
            self._attempt(), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=service2
        )

        assert second.outcome == "blocked"
        assert second.routed.reused is True
        assert second.pending_gate_entry["decision_id"] == first.pending_gate_entry["decision_id"]
        on_disk = read_checkpoint_json(workspace)
        assert len(on_disk["gate_decisions"]) == 1

    def test_pending_gate_unparks_after_a_posture_flip_to_auto(self, repo: Path, workspace: Path) -> None:
        adapter = self.FakeAdapter()
        service = make_service(posture_with(Gate.PR_CREATION, GateDisposition(Disposition.AUTO)))

        resolution = gate_router.resolve_parked(
            self._attempt(), workspace=workspace, repo_root=repo, adapter=adapter, evaluator=service
        )

        assert resolution.outcome == "proceed"
        assert resolution.routed.decision.resolution is Resolution.AUTO
        assert len(adapter.resumed) == 1
        dispatch_id, approval_ref, kind = adapter.resumed[0]
        assert dispatch_id == "d-1"
        assert kind == "pending_gate"
        assert approval_ref == f"gate-decision:{resolution.routed.record['decision_id']}"

    def test_policy_pause_evaluates_escalate_resume_not_a_new_gate(self, repo: Path, workspace: Path) -> None:
        adapter = self.FakeAdapter()
        service = make_service(posture_with(Gate.ESCALATE_RESUME, GateDisposition(Disposition.BLOCK)))

        resolution = gate_router.resolve_parked(
            self._attempt(parked={"kind": "policy_pause", "reason": "stuck"}),
            workspace=workspace, repo_root=repo, adapter=adapter, evaluator=service,
        )

        assert resolution.outcome == "blocked"
        assert resolution.routed.record["gate"] == "escalate_resume"
        assert resolution.pending_gate_entry["gate"] == "escalate_resume"
        assert adapter.resumed == []

    def test_unknown_parked_gate_raises_without_recording(self, repo: Path, workspace: Path) -> None:
        adapter = self.FakeAdapter()
        with pytest.raises(gate_router.GateRefusalError):
            gate_router.resolve_parked(
                self._attempt(parked={"kind": "pending_gate", "gate": "not_a_real_gate"}),
                workspace=workspace, repo_root=repo, adapter=adapter,
            )
        on_disk = read_checkpoint_json(workspace) if (workspace / "checkpoint.json").exists() else {"gate_decisions": []}
        assert on_disk.get("gate_decisions", []) == []


# --------------------------------------------------------------------------- #
# require_approval_ref (D3)
# --------------------------------------------------------------------------- #


class TestRequireApprovalRef:
    def test_resolves_a_proceed_roadmap_approval_record(self, repo: Path, workspace: Path) -> None:
        service = make_service(posture_with(Gate.ROADMAP_APPROVAL, GateDisposition(Disposition.AUTO)))
        routed = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service)
        ref = f"gate-decision:{routed.record['decision_id']}"

        manager = gate_router.CheckpointManager(workspace, repo)
        checkpoint = manager.load()
        roadmap = gate_router.load_roadmap(workspace / "roadmap.yaml", repo)

        record = gate_router.require_approval_ref(
            checkpoint, ref, gate=Gate.ROADMAP_APPROVAL, roadmap_id="alpha", roadmap=roadmap
        )
        assert record["decision_id"] == routed.record["decision_id"]

    def test_rejects_a_stale_fingerprint(self, repo: Path, workspace: Path) -> None:
        service = make_service(posture_with(Gate.ROADMAP_APPROVAL, GateDisposition(Disposition.AUTO)))
        routed = gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service)
        ref = f"gate-decision:{routed.record['decision_id']}"

        _write_roadmap(repo, "alpha", [_item("ri-01", change_id="demo-change", status="superseded")])
        manager = gate_router.CheckpointManager(workspace, repo)
        checkpoint = manager.load()
        roadmap = gate_router.load_roadmap(workspace / "roadmap.yaml", repo)

        with pytest.raises(gate_router.ApprovalRefError):
            gate_router.require_approval_ref(
                checkpoint, ref, gate=Gate.ROADMAP_APPROVAL, roadmap_id="alpha", roadmap=roadmap
            )

    def test_rejects_an_unresolvable_ref(self, repo: Path, workspace: Path) -> None:
        manager = gate_router.CheckpointManager(workspace, repo)
        manager.create(gate_router.load_roadmap(workspace / "roadmap.yaml", repo))
        checkpoint = manager.load()
        roadmap = gate_router.load_roadmap(workspace / "roadmap.yaml", repo)

        with pytest.raises(gate_router.ApprovalRefError):
            gate_router.require_approval_ref(
                checkpoint, "gate-decision:does-not-exist", gate=Gate.ROADMAP_APPROVAL,
                roadmap_id="alpha", roadmap=roadmap,
            )

    def test_roadmap_approval_requires_a_roadmap_argument(self, repo: Path, workspace: Path) -> None:
        manager = gate_router.CheckpointManager(workspace, repo)
        manager.create(gate_router.load_roadmap(workspace / "roadmap.yaml", repo))
        checkpoint = manager.load()

        with pytest.raises(gate_router.ApprovalRefError):
            gate_router.require_approval_ref(
                checkpoint, "gate-decision:whatever", gate=Gate.ROADMAP_APPROVAL, roadmap_id="alpha"
            )


# --------------------------------------------------------------------------- #
# gate_log (D6)
# --------------------------------------------------------------------------- #


class TestGateLog:
    def test_empty_workspace_reports_empty_rather_than_failing(self, repo: Path, workspace: Path) -> None:
        assert gate_router.gate_log(workspace, repo) == []

    def test_one_record_per_evaluate_none_for_reuse(self, repo: Path, workspace: Path) -> None:
        service = make_service(posture_with(Gate.ROADMAP_APPROVAL, GateDisposition(Disposition.AUTO)))
        gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service)
        service2 = make_service(posture_with(Gate.ROADMAP_APPROVAL, GateDisposition(Disposition.AUTO)))
        gate_router.evaluate(Gate.ROADMAP_APPROVAL, {}, workspace=workspace, repo_root=repo, evaluator=service2)

        log = gate_router.gate_log(workspace, repo)
        assert len(log) == 1
        assert log[0]["origin"] == "checkpoint"


# --------------------------------------------------------------------------- #
# Router is the only seam (D2) — AST scan
# --------------------------------------------------------------------------- #


def test_only_gate_router_imports_approval_gate() -> None:
    forbidden_names = {"ApprovalGate", "build_default_gate"}
    forbidden_attrs = {"check_filed"}
    for path in sorted(_SUPERVISE_SCRIPTS.glob("*.py")):
        if path.name == "gate_router.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        imported = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert not (forbidden_names & (names | imported)), f"{path} references {forbidden_names & (names | imported)}"
        assert not (forbidden_attrs & attrs), f"{path} calls .check_filed(...)"


def test_no_supervise_script_imports_autopilot() -> None:
    for path in sorted(_SUPERVISE_SCRIPTS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(alias.name == "autopilot" for alias in node.names), path
            if isinstance(node, ast.ImportFrom):
                assert node.module != "autopilot", path
