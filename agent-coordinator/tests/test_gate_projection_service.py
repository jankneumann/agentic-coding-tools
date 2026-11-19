"""Gate projection: configuration and service behaviour.

The service is exercised against a hand-written fake database and a fake
approval service, so each test states exactly which rows exist and can count
the reads the listing makes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from src.approval import ApprovalRequest
from src.config import GateProjectionConfig, get_config, reset_config
from src.gate_projection import (
    GateDecisionRequest,
    GateNotDecidableError,
    GateNotFoundError,
    GateProjectionService,
    GateSnapshotRequest,
    ProjectNotEnrolledError,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_config_defaults_to_no_enrolled_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GATE_PROJECTION_PROJECTS", raising=False)
    monkeypatch.delenv("GATE_PROJECTION_STALE_SECONDS", raising=False)

    config = GateProjectionConfig.from_env()

    assert config.projects == frozenset()
    assert config.stale_seconds == 86400


def test_config_reads_a_comma_separated_enrolment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATE_PROJECTION_PROJECTS", " acme/api , acme/web,, ")
    monkeypatch.setenv("GATE_PROJECTION_STALE_SECONDS", "600")

    config = GateProjectionConfig.from_env()

    assert config.projects == frozenset({"acme/api", "acme/web"})
    assert config.stale_seconds == 600


def test_config_stale_window_is_at_least_one_second(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATE_PROJECTION_STALE_SECONDS", "0")

    assert GateProjectionConfig.from_env().stale_seconds == 1


def test_config_is_attached_to_the_coordinator_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATE_PROJECTION_PROJECTS", "acme/api")
    reset_config()
    try:
        assert get_config().gate_projection.projects == frozenset({"acme/api"})
    finally:
        reset_config()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
APPROVAL_A = "11111111-1111-4111-8111-111111111111"
APPROVAL_B = "22222222-2222-4222-8222-222222222222"
TABLE = "gate_projection_snapshots"


class FakeDb:
    """In-memory stand-in for the snapshot table that records every call."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, Any]] = []
        self.fail_next_insert = False

    async def query(
        self, table: str, query_params: str | None = None, select: str = "*"
    ) -> list[dict[str, Any]]:
        assert table == TABLE
        self.calls.append(("query", query_params))
        if query_params is None:
            return [dict(r) for r in self.rows.values()]
        assert query_params.startswith("project=eq.")
        row = self.rows.get(query_params.removeprefix("project=eq."))
        return [dict(row)] if row else []

    async def insert(
        self, table: str, data: dict[str, Any], return_data: bool = True
    ) -> dict[str, Any]:
        assert table == TABLE
        self.calls.append(("insert", data["project"]))
        if self.fail_next_insert:
            # Another writer inserted the row between our update and insert.
            self.fail_next_insert = False
            self.rows[data["project"]] = {**data, "digest": "theirs"}
            raise RuntimeError("duplicate key value violates unique constraint")
        self.rows[data["project"]] = dict(data)
        return data

    async def update(
        self,
        table: str,
        match: dict[str, Any],
        data: dict[str, Any],
        return_data: bool = True,
    ) -> list[dict[str, Any]]:
        assert table == TABLE
        self.calls.append(("update", match["project"]))
        if match["project"] not in self.rows:
            return []
        self.rows[match["project"]].update(data)
        return [dict(self.rows[match["project"]])]

    async def delete(self, table: str, match: dict[str, Any]) -> None:
        assert table == TABLE
        self.calls.append(("delete", match["project"]))
        self.rows.pop(match["project"], None)

    @property
    def writes(self) -> list[tuple[str, Any]]:
        return [c for c in self.calls if c[0] != "query"]


class FakeApprovals:
    """Approval service double holding requests by id and counting reads."""

    def __init__(self, *requests: ApprovalRequest) -> None:
        self.requests = {r.id: r for r in requests}
        self.reads: list[str] = []
        self.decisions: list[dict[str, Any]] = []

    async def list_pending(
        self, agent_id: str | None = None, limit: int = 50
    ) -> list[ApprovalRequest]:
        self.reads.append("list_pending")
        return [r for r in self.requests.values() if r.status == "pending"][:limit]

    async def get_requests(self, request_ids: Any) -> list[ApprovalRequest]:
        self.reads.append("get_requests")
        return [self.requests[i] for i in request_ids if i in self.requests]

    async def decide_request(
        self,
        request_id: str,
        decision: str,
        *,
        decided_by: str | None = None,
        reason: str | None = None,
    ) -> ApprovalRequest | None:
        request = self.requests.get(request_id)
        if request is None or request.status != "pending":
            return None
        self.decisions.append(
            {
                "request_id": request_id,
                "decision": decision,
                "decided_by": decided_by,
                "reason": reason,
            }
        )
        request.status = decision
        request.decided_by = decided_by
        request.reason = reason
        return request


def _approval(
    request_id: str,
    *,
    status: str = "pending",
    operation: str = "gate:merge",
    resource: str | None = "acme/api#12",
    expires_in: timedelta = timedelta(hours=2),
) -> ApprovalRequest:
    return ApprovalRequest(
        id=request_id,
        agent_id="agent-1",
        agent_type="claude_code",
        operation=operation,
        resource=resource,
        context={},
        status=status,
        decided_by=None,
        decided_at=None,
        reason=None,
        expires_at=NOW + expires_in,
        created_at=NOW - timedelta(minutes=5),
    )


def _gate(gate_id: str = "a" * 16, **overrides: Any) -> dict[str, Any]:
    gate: dict[str, Any] = {
        "gate_id": gate_id,
        "gate": "merge",
        "source": "checkpoint",
        "subject": "ri-03 add-thing",
        "deadline": "2026-11-20T00:00:00+00:00",
        "answer_hint": "cycle_state.py gate-answer --roadmap r --gate merge",
        "roadmap_id": "r",
        "item_id": "ri-03",
    }
    gate.update(overrides)
    return gate


def _snapshot(
    project: str = "acme/api",
    gates: list[dict[str, Any]] | None = None,
    source_errors: list[dict[str, str]] | None = None,
) -> GateSnapshotRequest:
    return GateSnapshotRequest.model_validate(
        {
            "project": project,
            "collected_at": "2026-11-19T11:59:00+00:00",
            "gates": [_gate()] if gates is None else gates,
            "source_errors": source_errors or [],
        }
    )


def _service(
    db: FakeDb,
    approvals: FakeApprovals | None = None,
    *,
    projects: tuple[str, ...] = ("acme/api", "acme/web"),
    stale_seconds: int = 3600,
    now: datetime = NOW,
) -> GateProjectionService:
    return GateProjectionService(
        db=db,  # type: ignore[arg-type]
        approvals=approvals or FakeApprovals(),  # type: ignore[arg-type]
        config=GateProjectionConfig(
            projects=frozenset(projects), stale_seconds=stale_seconds
        ),
        now=lambda: now,
    )


def _project(listing: dict[str, Any], name: str) -> dict[str, Any]:
    return next(p for p in listing["projects"] if p["project"] == name)


# --- Requirement: Gate Projection Snapshot ---------------------------------


async def test_a_snapshot_replaces_the_earlier_one() -> None:
    db = FakeDb()
    service = _service(db)

    await service.replace_snapshot(
        _snapshot(gates=[_gate("a" * 16), _gate("b" * 16)])
    )
    result = await service.replace_snapshot(_snapshot(gates=[_gate("c" * 16)]))

    assert result["success"] is True
    assert result["gate_count"] == 1
    assert list(db.rows) == ["acme/api"]
    listing = await service.list_pending()
    assert [g["gate_id"] for g in listing["gates"]] == ["c" * 16]


async def test_a_project_that_is_not_enrolled_is_refused() -> None:
    db = FakeDb()
    service = _service(db)

    with pytest.raises(ProjectNotEnrolledError):
        await service.replace_snapshot(_snapshot(project="other/repo"))

    assert db.calls == []


async def test_rebuilding_after_deletion_yields_the_same_set() -> None:
    db = FakeDb()
    service = _service(db)
    snapshot = _snapshot(gates=[_gate("a" * 16), _gate("b" * 16)])

    first = await service.replace_snapshot(snapshot)
    before = (await service.list_pending())["gates"]
    deleted = await service.delete_snapshot("acme/api")
    again = await service.delete_snapshot("acme/api")
    second = await service.replace_snapshot(snapshot)
    after = (await service.list_pending())["gates"]

    assert deleted == {"success": True, "project": "acme/api", "deleted": True}
    assert again["deleted"] is False
    assert after == before
    assert second["digest"] == first["digest"]


async def test_deleting_a_snapshot_of_an_unenrolled_project_is_refused() -> None:
    db = FakeDb()
    service = _service(db)

    with pytest.raises(ProjectNotEnrolledError):
        await service.delete_snapshot("other/repo")

    assert db.calls == []


def test_an_oversized_snapshot_is_refused() -> None:
    gates = [_gate(f"{i:016x}") for i in range(501)]

    with pytest.raises(ValidationError):
        _snapshot(gates=gates)


def test_a_snapshot_gate_must_carry_a_wellformed_id_and_source() -> None:
    with pytest.raises(ValidationError):
        _snapshot(gates=[_gate("not-a-gate-id")])
    with pytest.raises(ValidationError):
        _snapshot(gates=[_gate(source="approval_service")])
    with pytest.raises(ValidationError):
        _snapshot(project="not a project")


async def test_a_concurrent_first_push_falls_back_to_an_update() -> None:
    db = FakeDb()
    db.fail_next_insert = True
    service = _service(db)

    result = await service.replace_snapshot(_snapshot())

    assert [c[0] for c in db.writes] == ["update", "insert", "update"]
    assert db.rows["acme/api"]["digest"] == result["digest"]


# --- Requirement: Cross-Project Pending Gate Listing -----------------------


async def test_gates_of_two_projects_are_listed_together() -> None:
    db = FakeDb()
    service = _service(db)
    await service.replace_snapshot(_snapshot("acme/api", [_gate("a" * 16)]))
    await service.replace_snapshot(
        _snapshot("acme/web", [_gate("b" * 16, gate="plan_approval")])
    )

    listing = await service.list_pending()

    assert [(g["project"], g["gate"]) for g in listing["gates"]] == [
        ("acme/api", "merge"),
        ("acme/web", "plan_approval"),
    ]
    for gate in listing["gates"]:
        assert {"project", "gate", "subject", "options", "deadline"} <= gate.keys()
        assert gate["project_status"] == "ok"
    assert [p["status"] for p in listing["projects"]] == ["ok", "ok"]
    assert listing["generated_at"] == NOW.isoformat()


async def test_an_enrolled_project_with_no_snapshot_is_degraded() -> None:
    db = FakeDb()
    service = _service(db)
    await service.replace_snapshot(_snapshot("acme/api"))

    listing = await service.list_pending()

    web = _project(listing, "acme/web")
    assert web["status"] == "degraded"
    assert web["reason"] == "no_snapshot"
    assert web["gate_count"] == 0
    assert web["received_at"] is None


async def test_a_stale_snapshot_is_degraded_and_still_listed() -> None:
    db = FakeDb()
    await _service(db).replace_snapshot(_snapshot("acme/api"))
    later = _service(db, now=NOW + timedelta(seconds=3601))

    listing = await later.list_pending()

    api = _project(listing, "acme/api")
    assert (api["status"], api["reason"]) == ("degraded", "stale")
    assert [g["project_status"] for g in listing["gates"]] == ["degraded"]


async def test_a_snapshot_inside_the_window_is_not_stale() -> None:
    db = FakeDb()
    await _service(db).replace_snapshot(_snapshot("acme/api"))
    later = _service(db, now=NOW + timedelta(seconds=3600))

    api = _project(await later.list_pending(), "acme/api")

    assert (api["status"], api["reason"]) == ("ok", None)


async def test_staleness_uses_the_coordinator_clock_not_the_collector_clock() -> None:
    db = FakeDb()
    service = _service(db)
    snapshot = GateSnapshotRequest.model_validate(
        {
            "project": "acme/api",
            "collected_at": "2020-01-01T00:00:00+00:00",
            "gates": [],
        }
    )
    await service.replace_snapshot(snapshot)

    api = _project(await service.list_pending(), "acme/api")

    assert api["status"] == "ok"
    assert api["collected_at"] == "2020-01-01T00:00:00+00:00"
    assert api["received_at"] == NOW.isoformat()


async def test_source_errors_degrade_a_project() -> None:
    db = FakeDb()
    service = _service(db)
    errors = [{"path": "openspec/roadmaps/r/checkpoint.json", "error": "bad JSON"}]
    await service.replace_snapshot(_snapshot("acme/api", source_errors=errors))

    listing = await service.list_pending()

    api = _project(listing, "acme/api")
    assert (api["status"], api["reason"]) == ("degraded", "source_errors")
    assert api["source_errors"] == errors
    assert len(listing["gates"]) == 1


async def test_no_enrolment_means_an_empty_listing() -> None:
    db = FakeDb()
    db.rows["acme/api"] = {"project": "acme/api"}
    approvals = FakeApprovals(_approval(APPROVAL_A))
    service = _service(db, approvals, projects=())

    listing = await service.list_pending()

    assert listing["gates"] == []
    assert listing["projects"] == []
    assert db.calls == []
    assert approvals.reads == []


async def test_a_row_of_a_project_no_longer_enrolled_is_ignored_and_kept() -> None:
    db = FakeDb()
    await _service(db).replace_snapshot(_snapshot("acme/web"))
    narrowed = _service(db, projects=("acme/api",))

    listing = await narrowed.list_pending()

    assert listing["gates"] == []
    assert [p["project"] for p in listing["projects"]] == ["acme/api"]
    assert "acme/web" in db.rows


async def test_a_gate_with_a_pending_approval_takes_the_approvals_deadline() -> None:
    db = FakeDb()
    approvals = FakeApprovals(_approval(APPROVAL_A))
    service = _service(db, approvals)
    await service.replace_snapshot(
        _snapshot(gates=[_gate(approval_id=APPROVAL_A.upper())])
    )

    (gate,) = (await service.list_pending())["gates"]

    assert gate["decision_route"] == "approval_service"
    assert gate["options"] == ["approved", "denied"]
    assert gate["deadline"] == (NOW + timedelta(hours=2)).isoformat()
    assert gate["approval_id"] == APPROVAL_A


async def test_a_gate_whose_approval_is_already_decided_is_not_listed() -> None:
    db = FakeDb()
    approvals = FakeApprovals(
        _approval(APPROVAL_A, status="approved"),
        _approval(APPROVAL_B, status="expired"),
    )
    service = _service(db, approvals)
    await service.replace_snapshot(
        _snapshot(
            gates=[
                _gate("a" * 16, approval_id=APPROVAL_A),
                _gate("b" * 16, approval_id=APPROVAL_B),
                _gate("c" * 16),
            ]
        )
    )

    listing = await service.list_pending()

    assert [g["gate_id"] for g in listing["gates"]] == ["c" * 16]
    api = _project(listing, "acme/api")
    assert api["decided_awaiting_sync"] == 2
    assert api["gate_count"] == 1


async def test_a_gate_with_no_approval_is_routed_to_the_repository() -> None:
    db = FakeDb()
    service = _service(db)
    await service.replace_snapshot(_snapshot())

    (gate,) = (await service.list_pending())["gates"]

    assert gate["decision_route"] == "repository"
    assert gate["options"] == ["approved", "rejected"]
    assert gate["deadline"] == "2026-11-20T00:00:00+00:00"
    assert gate["answer_hint"].startswith("cycle_state.py gate-answer")
    assert gate["approval_id"] is None


@pytest.mark.parametrize("approval_id", ["not-a-uuid", APPROVAL_B])
async def test_an_approval_id_that_names_no_request_routes_to_the_repository(
    approval_id: str,
) -> None:
    db = FakeDb()
    service = _service(db, FakeApprovals())
    await service.replace_snapshot(_snapshot(gates=[_gate(approval_id=approval_id)]))

    listing = await service.list_pending()

    assert [g["decision_route"] for g in listing["gates"]] == ["repository"]
    assert _project(listing, "acme/api")["decided_awaiting_sync"] == 0


async def test_an_approval_request_no_snapshot_references_is_listed() -> None:
    db = FakeDb()
    approvals = FakeApprovals(
        _approval(APPROVAL_A), _approval(APPROVAL_B, operation="deploy", resource=None)
    )
    service = _service(db, approvals)
    await service.replace_snapshot(
        _snapshot(gates=[_gate(approval_id=APPROVAL_A)])
    )

    listing = await service.list_pending()

    assert len(listing["gates"]) == 2
    orphan = listing["gates"][-1]
    assert orphan["project"] is None
    assert orphan["project_status"] is None
    assert orphan["source"] == "approval_service"
    assert orphan["gate_id"] is None
    assert orphan["gate"] == "deploy"
    assert orphan["subject"] == "deploy"
    assert orphan["decision_route"] == "approval_service"
    assert orphan["approval_id"] == APPROVAL_B
    assert APPROVAL_B in orphan["answer_hint"]


async def test_an_unreferenced_gate_approval_drops_the_gate_prefix() -> None:
    db = FakeDb()
    service = _service(db, FakeApprovals(_approval(APPROVAL_A)))

    (orphan,) = (await service.list_pending())["gates"]

    assert orphan["gate"] == "merge"
    assert orphan["subject"] == "acme/api#12"


async def test_the_listing_reads_do_not_grow_with_the_number_of_gates() -> None:
    db = FakeDb()
    approvals = FakeApprovals(
        _approval(APPROVAL_A), _approval(APPROVAL_B, status="denied")
    )
    service = _service(db, approvals)
    gates = [_gate(f"{i:016x}", approval_id=APPROVAL_B) for i in range(40)]
    gates += [_gate(f"{i:016x}", approval_id=APPROVAL_A) for i in range(40, 80)]
    await service.replace_snapshot(_snapshot("acme/api", gates))
    await service.replace_snapshot(_snapshot("acme/web", [_gate("f" * 16)]))
    db.calls.clear()

    await service.list_pending()

    assert db.calls == [("query", None)]
    assert approvals.reads == ["list_pending", "get_requests"]


async def test_the_decided_lookup_is_skipped_when_nothing_needs_it() -> None:
    db = FakeDb()
    approvals = FakeApprovals(_approval(APPROVAL_A))
    service = _service(db, approvals)
    await service.replace_snapshot(
        _snapshot(gates=[_gate("a" * 16, approval_id=APPROVAL_A), _gate("b" * 16)])
    )

    await service.list_pending()

    assert approvals.reads == ["list_pending"]


async def test_a_payload_stored_as_text_is_still_read() -> None:
    db = FakeDb()
    service = _service(db)
    await service.replace_snapshot(_snapshot())
    row = db.rows["acme/api"]
    row["payload"] = json.dumps(row["payload"])
    row["received_at"] = NOW

    listing = await service.list_pending()

    assert len(listing["gates"]) == 1
    assert _project(listing, "acme/api")["received_at"] == NOW.isoformat()


# --- Requirement: Gate Decision Through the Approval Service ---------------


def _decision(**overrides: Any) -> GateDecisionRequest:
    body: dict[str, Any] = {
        "project": "acme/api",
        "gate_id": "a" * 16,
        "decision": "approved",
        "reason": "looks right",
    }
    body.update(overrides)
    return GateDecisionRequest.model_validate(body)


async def test_a_decision_reaches_the_approval_request() -> None:
    db = FakeDb()
    approvals = FakeApprovals(_approval(APPROVAL_A))
    service = _service(db, approvals)
    await service.replace_snapshot(_snapshot(gates=[_gate(approval_id=APPROVAL_A)]))
    stored = json.dumps(db.rows["acme/api"], sort_keys=True, default=str)
    db.calls.clear()

    result = await service.decide(_decision(), decided_by="operator-1")

    assert approvals.decisions == [
        {
            "request_id": APPROVAL_A,
            "decision": "approved",
            "decided_by": "operator-1",
            "reason": "looks right",
        }
    ]
    assert result["success"] is True
    assert result["approval"] == {"request_id": APPROVAL_A, "status": "approved"}
    assert db.writes == []
    assert json.dumps(db.rows["acme/api"], sort_keys=True, default=str) == stored


async def test_a_repository_routed_gate_is_refused_with_its_answer_hint() -> None:
    db = FakeDb()
    approvals = FakeApprovals()
    service = _service(db, approvals)
    await service.replace_snapshot(_snapshot())

    with pytest.raises(GateNotDecidableError) as raised:
        await service.decide(_decision(), decided_by="operator-1")

    assert raised.value.reason == "no_approval_request"
    assert raised.value.answer_hint == (
        "cycle_state.py gate-answer --roadmap r --gate merge"
    )
    assert approvals.decisions == []


async def test_a_gate_whose_approval_is_no_longer_pending_is_refused() -> None:
    db = FakeDb()
    approvals = FakeApprovals(_approval(APPROVAL_A, status="denied"))
    service = _service(db, approvals)
    await service.replace_snapshot(_snapshot(gates=[_gate(approval_id=APPROVAL_A)]))

    with pytest.raises(GateNotDecidableError) as raised:
        await service.decide(_decision(), decided_by="operator-1")

    assert raised.value.reason == "approval_not_pending"


async def test_an_unknown_gate_is_not_found() -> None:
    db = FakeDb()
    service = _service(db)
    await service.replace_snapshot(_snapshot())

    with pytest.raises(GateNotFoundError):
        await service.decide(_decision(gate_id="b" * 16), decided_by="operator-1")
    with pytest.raises(GateNotFoundError):
        await service.decide(_decision(project="acme/web"), decided_by="operator-1")


async def test_a_decision_for_an_unenrolled_project_is_refused() -> None:
    db = FakeDb()
    service = _service(db)

    with pytest.raises(ProjectNotEnrolledError):
        await service.decide(_decision(project="other/repo"), decided_by="operator-1")

    assert db.calls == []


def test_an_invalid_decision_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _decision(decision="rejected")
    with pytest.raises(ValidationError):
        _decision(gate_id="nope")
