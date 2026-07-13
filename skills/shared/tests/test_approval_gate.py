"""Tests for skills.shared.approval_gate.

Covers all four trust-posture dispositions end to end with a deterministic fake
clock and a fake coordinator client — no real sleeping, no real network:

- auto            → PROCEED + audit
- notify resolved → APPROVED (proceed) and REJECTED (block)
- notify timeout  → default_action proceed AND default_action block
- notify expired  → server-side expiry maps onto default_action
- block           → parks (BLOCKED), never hangs
- coordinator unreachable at each notify step (file / notify / poll) → BLOCKED
- audit recorded on every one of those paths
- the production BridgeCoordinatorClient / BridgeAuditSink wiring (monkeypatched
  transport, so no dead code)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared import approval_gate as ag
from shared.approval_gate import (
    ApprovalGate,
    CoordinatorUnavailable,
    Outcome,
    Resolution,
)
from shared.trust_posture import (
    DefaultAction,
    Disposition,
    Gate,
    GateDisposition,
    TrustPosture,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #

class FakeClock:
    """Monotonic clock advanced only by ``sleep`` — fully deterministic."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeCoordinator:
    """Scriptable coordinator client.

    ``statuses`` is the sequence returned by successive ``check_approval`` calls; the
    last value repeats. ``raise_on`` names a step whose call raises
    CoordinatorUnavailable. ``notify_return`` / ``notify_raises`` control notifications.
    """

    def __init__(
        self,
        *,
        statuses: list[str] | None = None,
        raise_on: str | None = None,
        notify_return: bool = True,
        request_id: str = "appr-123",
    ) -> None:
        self.statuses = list(statuses or [])
        self.raise_on = raise_on
        self.notify_return = notify_return
        self.request_id = request_id
        self.calls: list[str] = []
        self.request_payload: dict | None = None
        self.notifications: list[dict] = []
        self._poll_index = 0

    def request_approval(self, *, operation, resource, context, timeout_seconds) -> str:
        self.calls.append("request_approval")
        if self.raise_on == "request":
            raise CoordinatorUnavailable("filing failed")
        self.request_payload = {
            "operation": operation,
            "resource": resource,
            "context": context,
            "timeout_seconds": timeout_seconds,
        }
        return self.request_id

    def push_notification(self, *, subject, body, approval_id) -> bool:
        self.calls.append("push_notification")
        if self.raise_on == "notify":
            raise CoordinatorUnavailable("notify failed")
        self.notifications.append(
            {"subject": subject, "body": body, "approval_id": approval_id}
        )
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
    """Audit sink that captures every record; optionally simulates failure."""

    def __init__(self, *, ok: bool = True, raises: bool = False) -> None:
        self.ok = ok
        self.raises = raises
        self.records: list[dict] = []

    def record(self, record: dict) -> bool:
        self.records.append(record)
        if self.raises:
            raise RuntimeError("audit boom")
        return self.ok


# --------------------------------------------------------------------------- #
# Posture helpers
# --------------------------------------------------------------------------- #

def posture_with(gate: Gate, gd: GateDisposition, *, present: bool = True) -> TrustPosture:
    return TrustPosture(gates={gate: gd}, present=present)


def loader_returning(posture: TrustPosture):
    def _load(repo_root=None, *, path=None):
        return posture
    return _load


def make_gate(
    *,
    posture: TrustPosture,
    coordinator: FakeCoordinator | None = None,
    audit: RecordingAudit | None = None,
    clock: FakeClock | None = None,
    poll_interval: float = 5.0,
) -> tuple[ApprovalGate, FakeCoordinator, RecordingAudit, FakeClock]:
    coordinator = coordinator or FakeCoordinator()
    audit = audit or RecordingAudit()
    clock = clock or FakeClock()
    gate = ApprovalGate(
        coordinator=coordinator,
        audit=audit,
        agent_id="test-agent",
        poll_interval_seconds=poll_interval,
        clock=clock.time,
        sleep=clock.sleep,
        posture_loader=loader_returning(posture),
    )
    return gate, coordinator, audit, clock


NOTIFY_PROCEED = GateDisposition(
    disposition=Disposition.NOTIFY_WITH_TIMEOUT,
    timeout_seconds=30,
    default_action=DefaultAction.PROCEED,
)
NOTIFY_BLOCK = GateDisposition(
    disposition=Disposition.NOTIFY_WITH_TIMEOUT,
    timeout_seconds=30,
    default_action=DefaultAction.BLOCK,
)


# --------------------------------------------------------------------------- #
# auto
# --------------------------------------------------------------------------- #

def test_auto_proceeds_and_audits() -> None:
    posture = posture_with(Gate.MERGE, GateDisposition(disposition=Disposition.AUTO))
    gate, coord, audit, _ = make_gate(posture=posture)

    decision = gate.evaluate(Gate.MERGE)

    assert decision.proceed
    assert decision.outcome is Outcome.PROCEED
    assert decision.resolution is Resolution.AUTO
    assert decision.disposition is Disposition.AUTO
    assert decision.approval_id is None
    # auto must not touch the coordinator at all
    assert coord.calls == []
    # audit written with the authorizing disposition
    assert len(audit.records) == 1
    rec = audit.records[0]
    assert rec["outcome"] == "proceed"
    assert rec["resolution"] == "auto"
    assert rec["authorizing_disposition"] == "auto"
    assert rec["operation"] == ag.AUDIT_OPERATION
    assert rec["agent_id"] == "test-agent"


# --------------------------------------------------------------------------- #
# block
# --------------------------------------------------------------------------- #

def test_block_parks_and_audits_without_hanging() -> None:
    posture = posture_with(Gate.MERGE, GateDisposition(disposition=Disposition.BLOCK))
    gate, coord, audit, clock = make_gate(posture=posture)

    decision = gate.evaluate(Gate.MERGE)

    assert decision.blocked
    assert decision.resolution is Resolution.POSTURE_BLOCK
    assert decision.disposition is Disposition.BLOCK
    assert coord.calls == []          # never contacts coordinator
    assert clock.sleeps == []          # never sleeps → never hangs
    assert audit.records[0]["resolution"] == "posture_block"


def test_absent_posture_defaults_to_block() -> None:
    # Absent-file posture: no gates, present=False; disposition_for → BLOCK.
    posture = TrustPosture(gates={}, present=False)
    gate, _, audit, _ = make_gate(posture=posture)

    decision = gate.evaluate(Gate.PROPOSAL_APPROVAL)

    assert decision.blocked
    assert decision.resolution is Resolution.POSTURE_BLOCK
    assert decision.posture_present is False
    assert audit.records[0]["posture_present"] is False


# --------------------------------------------------------------------------- #
# notify_with_timeout — human resolves
# --------------------------------------------------------------------------- #

def test_notify_resolved_approved() -> None:
    posture = posture_with(Gate.PROPOSAL_APPROVAL, NOTIFY_BLOCK)
    coord = FakeCoordinator(statuses=["pending", "approved"])
    gate, coord, audit, clock = make_gate(posture=posture, coordinator=coord)

    decision = gate.evaluate(Gate.PROPOSAL_APPROVAL, {"change_id": "add-foo"})

    assert decision.proceed
    assert decision.resolution is Resolution.APPROVED
    assert decision.approval_id == "appr-123"
    # filed, notified, polled twice
    assert coord.calls == [
        "request_approval",
        "push_notification",
        "check_approval",
        "check_approval",
    ]
    assert coord.request_payload["operation"] == "gate:proposal_approval"
    assert coord.request_payload["context"] == {"change_id": "add-foo"}
    assert len(coord.notifications) == 1
    assert audit.records[0]["resolution"] == "approved"
    assert audit.records[0]["approval_id"] == "appr-123"


def test_notify_resolved_rejected() -> None:
    posture = posture_with(Gate.PROPOSAL_APPROVAL, NOTIFY_PROCEED)
    coord = FakeCoordinator(statuses=["denied"])
    gate, coord, audit, clock = make_gate(posture=posture, coordinator=coord)

    decision = gate.evaluate(Gate.PROPOSAL_APPROVAL)

    assert decision.blocked
    assert decision.resolution is Resolution.REJECTED
    assert audit.records[0]["outcome"] == "blocked"
    assert audit.records[0]["resolution"] == "rejected"


# --------------------------------------------------------------------------- #
# notify_with_timeout — timeout → default action
# --------------------------------------------------------------------------- #

def test_notify_timeout_default_proceed() -> None:
    posture = posture_with(Gate.PR_CREATION, NOTIFY_PROCEED)
    coord = FakeCoordinator(statuses=["pending"])  # never resolves
    gate, coord, audit, clock = make_gate(posture=posture, coordinator=coord, poll_interval=5.0)

    decision = gate.evaluate(Gate.PR_CREATION)

    assert decision.proceed
    assert decision.resolution is Resolution.TIMEOUT_PROCEED
    assert decision.default_action is DefaultAction.PROCEED
    # 30s timeout / 5s poll → advanced to (or past) the deadline via sleeps
    assert sum(clock.sleeps) >= 30
    assert audit.records[0]["resolution"] == "timeout_default_proceed"
    assert audit.records[0]["default_action"] == "proceed"


def test_notify_timeout_default_block() -> None:
    posture = posture_with(Gate.ESCALATE_RESUME, NOTIFY_BLOCK)
    coord = FakeCoordinator(statuses=["pending"])
    gate, coord, audit, clock = make_gate(posture=posture, coordinator=coord)

    decision = gate.evaluate(Gate.ESCALATE_RESUME)

    assert decision.blocked
    assert decision.resolution is Resolution.TIMEOUT_BLOCK
    assert decision.default_action is DefaultAction.BLOCK
    assert audit.records[0]["resolution"] == "timeout_default_block"
    assert audit.records[0]["default_action"] == "block"


def test_notify_server_expired_maps_to_default() -> None:
    posture = posture_with(Gate.MERGE, NOTIFY_BLOCK)
    coord = FakeCoordinator(statuses=["expired"])
    gate, coord, audit, clock = make_gate(posture=posture, coordinator=coord)

    decision = gate.evaluate(Gate.MERGE)

    assert decision.blocked
    assert decision.resolution is Resolution.TIMEOUT_BLOCK
    # resolved on first poll, so no full-timeout sleeping needed
    assert coord.calls.count("check_approval") == 1


def test_notify_soft_notification_failure_is_nonfatal() -> None:
    # push_notification returns False (no channel) but the approval still resolves.
    posture = posture_with(Gate.MERGE, NOTIFY_BLOCK)
    coord = FakeCoordinator(statuses=["approved"], notify_return=False)
    gate, coord, audit, clock = make_gate(posture=posture, coordinator=coord)

    decision = gate.evaluate(Gate.MERGE)

    assert decision.proceed
    assert decision.resolution is Resolution.APPROVED


# --------------------------------------------------------------------------- #
# coordinator unreachable → fail closed to block (at each step) + audited
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raise_on", ["request", "notify", "check"])
def test_coordinator_unreachable_degrades_to_block(raise_on: str) -> None:
    posture = posture_with(Gate.PROPOSAL_APPROVAL, NOTIFY_PROCEED)
    coord = FakeCoordinator(statuses=["pending"], raise_on=raise_on)
    gate, coord, audit, clock = make_gate(posture=posture, coordinator=coord)

    decision = gate.evaluate(Gate.PROPOSAL_APPROVAL)

    # fail CLOSED regardless of the notify gate's default_action=proceed
    assert decision.blocked
    assert decision.resolution is Resolution.COORDINATOR_UNREACHABLE
    assert clock.sleeps == []  # degrade immediately, never hang
    # audit still written, carrying the authorizing disposition
    assert len(audit.records) == 1
    assert audit.records[0]["resolution"] == "coordinator_unreachable"
    assert audit.records[0]["authorizing_disposition"] == "notify_with_timeout"


def test_unreachable_on_check_preserves_approval_id() -> None:
    posture = posture_with(Gate.MERGE, NOTIFY_PROCEED)
    coord = FakeCoordinator(statuses=["pending"], raise_on="check")
    gate, coord, audit, _ = make_gate(posture=posture, coordinator=coord)

    decision = gate.evaluate(Gate.MERGE)

    assert decision.blocked
    assert decision.approval_id == "appr-123"  # filed before the poll failed


# --------------------------------------------------------------------------- #
# audit-in-every-path guarantee + audit robustness
# --------------------------------------------------------------------------- #

def test_audit_written_in_every_disposition_path() -> None:
    cases = [
        (GateDisposition(disposition=Disposition.AUTO), FakeCoordinator()),
        (GateDisposition(disposition=Disposition.BLOCK), FakeCoordinator()),
        (NOTIFY_PROCEED, FakeCoordinator(statuses=["approved"])),
        (NOTIFY_BLOCK, FakeCoordinator(statuses=["denied"])),
        (NOTIFY_PROCEED, FakeCoordinator(statuses=["pending"])),          # timeout
        (NOTIFY_BLOCK, FakeCoordinator(statuses=["pending"], raise_on="request")),
    ]
    for gd, coord in cases:
        posture = posture_with(Gate.MERGE, gd)
        gate, _, audit, _ = make_gate(posture=posture, coordinator=coord)
        gate.evaluate(Gate.MERGE)
        assert len(audit.records) == 1, gd
        assert audit.records[0]["authorizing_disposition"] == gd.disposition.value


def test_audit_sink_failure_does_not_crash_gate() -> None:
    posture = posture_with(Gate.MERGE, GateDisposition(disposition=Disposition.AUTO))
    audit = RecordingAudit(raises=True)
    gate, _, _, _ = make_gate(posture=posture, audit=audit)

    # gate still returns a decision even though the sink raised
    decision = gate.evaluate(Gate.MERGE)
    assert decision.proceed
    assert len(audit.records) == 1  # the attempt happened


# --------------------------------------------------------------------------- #
# production wiring (bridge-backed defaults) — exercised via monkeypatched transport
# --------------------------------------------------------------------------- #

class FakeBridge:
    """Stand-in for the coordination_bridge module."""

    def __init__(self, responses: dict[tuple[str, str], dict]) -> None:
        self._responses = responses
        self.remembered: list[dict] = []

    def _resolve_http_url(self, http_url):
        return http_url or "http://localhost:8081"

    def _resolve_api_key(self, api_key):
        return api_key or "key"

    def _http_request(self, *, method, path, http_url, api_key, payload=None, timeout=1.5):
        key = (method.upper(), path.split("?")[0])
        # match /approvals/<id> generically
        if key not in self._responses and path.startswith("/approvals/"):
            key = ("GET", "/approvals/{id}")
        return self._responses[key]

    def try_remember(self, **kwargs):
        self.remembered.append(kwargs)
        return {"status": "ok"}


def test_bridge_coordinator_client_end_to_end(monkeypatch) -> None:
    responses = {
        ("POST", "/approvals/request"): {
            "status_code": 200,
            "data": {"request_id": "R1", "status": "pending"},
            "error": None,
        },
        ("POST", "/notifications/test"): {
            "status_code": 200,
            "data": {"success": True, "sent": True},
            "error": None,
        },
        ("GET", "/approvals/{id}"): {
            "status_code": 200,
            "data": {"status": "approved"},
            "error": None,
        },
    }
    fake_bridge = FakeBridge(responses)
    monkeypatch.setattr(ag, "_import_bridge", lambda: fake_bridge)

    client = ag.BridgeCoordinatorClient(agent_id="a1")
    rid = client.request_approval(
        operation="gate:merge", resource=None, context={}, timeout_seconds=10
    )
    assert rid == "R1"
    # The diagnostic notify endpoint never confirms approval delivery (fail closed).
    assert client.push_notification(subject="s", body="b", approval_id="R1") is False
    assert client.check_approval("R1") == "approved"


def test_bridge_coordinator_client_transport_error_raises(monkeypatch) -> None:
    responses = {
        ("POST", "/approvals/request"): {
            "status_code": None,
            "data": None,
            "error": "connection refused",
        },
    }
    monkeypatch.setattr(ag, "_import_bridge", lambda: FakeBridge(responses))
    client = ag.BridgeCoordinatorClient()
    with pytest.raises(CoordinatorUnavailable):
        client.request_approval(
            operation="gate:merge", resource=None, context={}, timeout_seconds=10
        )


@pytest.mark.parametrize("status", [500, 503, None])
def test_push_notification_transport_down_raises(monkeypatch, status) -> None:
    # A 5xx / no-response means the transport is genuinely down → fail closed (raise).
    responses = {
        ("POST", "/notifications/test"): {"status_code": status, "data": {}, "error": None},
    }
    monkeypatch.setattr(ag, "_import_bridge", lambda: FakeBridge(responses))
    client = ag.BridgeCoordinatorClient()
    with pytest.raises(CoordinatorUnavailable):
        client.push_notification(subject="s", body="b", approval_id="R1")


@pytest.mark.parametrize(
    "status,data",
    [
        (200, {"success": True, "sent": True}),   # diagnostic endpoint "sent" ≠ approval delivered
        (200, {"success": True, "sent": False}),
        (200, {}),
        (401, {}),
        (404, {}),
        (429, {}),
    ],
)
def test_push_notification_never_reports_delivery_via_diagnostic_endpoint(
    monkeypatch, status, data
) -> None:
    # /notifications/test is a diagnostic endpoint that ignores the approval details,
    # so the bridge client NEVER reports delivery from it (returns False). This keeps a
    # default_action=proceed gate failing closed on timeout until a real approval-
    # notification channel exists. (Transport-down 5xx still raises — tested separately.)
    responses = {
        ("POST", "/notifications/test"): {"status_code": status, "data": data, "error": None},
    }
    monkeypatch.setattr(ag, "_import_bridge", lambda: FakeBridge(responses))
    client = ag.BridgeCoordinatorClient()
    assert client.push_notification(subject="s", body="b", approval_id="R1") is False


def test_notify_timeout_proceed_fails_closed_when_undelivered() -> None:
    # Security: a default_action=proceed gate that times out MUST NOT proceed if the
    # notification was never delivered (no human could have vetoed the unattended action).
    posture = posture_with(Gate.MERGE, NOTIFY_PROCEED)
    coord = FakeCoordinator(statuses=["pending", "pending"], notify_return=False)
    gate, coord, audit, clock = make_gate(posture=posture, coordinator=coord)

    decision = gate.evaluate(Gate.MERGE)

    assert not decision.proceed
    assert decision.resolution is Resolution.TIMEOUT_BLOCK
    assert "push_notification" in coord.calls


def test_notify_timeout_proceed_applies_when_delivered() -> None:
    # Control: with the notification delivered, default_action=proceed still proceeds.
    posture = posture_with(Gate.MERGE, NOTIFY_PROCEED)
    coord = FakeCoordinator(statuses=["pending", "pending"], notify_return=True)
    gate, coord, audit, clock = make_gate(posture=posture, coordinator=coord)

    decision = gate.evaluate(Gate.MERGE)

    assert decision.proceed
    assert decision.resolution is Resolution.TIMEOUT_PROCEED


def test_bridge_audit_sink_records_to_memory(monkeypatch) -> None:
    fake_bridge = FakeBridge({})
    monkeypatch.setattr(ag, "_import_bridge", lambda: fake_bridge)
    sink = ag.BridgeAuditSink(agent_id="a1")

    ok = sink.record(
        {
            "gate": "merge",
            "reason": "auto",
            "outcome": "proceed",
            "authorizing_disposition": "auto",
            "resolution": "auto",
        }
    )
    assert ok is True
    assert fake_bridge.remembered[0]["event_type"] == "approval_gate_decision"
    assert "approval_gate" in fake_bridge.remembered[0]["tags"]


def test_build_default_gate_wires_bridge_defaults() -> None:
    gate = ag.build_default_gate(agent_id="a1")
    assert isinstance(gate.coordinator, ag.BridgeCoordinatorClient)
    assert isinstance(gate.audit, ag.BridgeAuditSink)
    assert gate.agent_id == "a1"
