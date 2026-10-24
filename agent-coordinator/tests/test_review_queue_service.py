"""ReviewQueueService parameter mapping onto the migration-046 RPCs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

import src.audit
from src.config import reset_config
from src.review_queue import (
    LaneResultIn,
    ReviewJobRequest,
    ReviewQueueService,
)

_HEAD = "c" * 40
_BASE = "d" * 40


class FakeDb:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def rpc(self, fn: str, params: dict[str, Any]) -> Any:
        self.calls.append((fn, params))
        return self.result


@pytest.fixture()
def audit(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    service = AsyncMock()
    monkeypatch.setattr(src.audit, "_audit_service", service)
    return service


async def test_submit_maps_the_request_and_audits(audit: AsyncMock) -> None:
    db = FakeDb({"success": True, "created": True, "job": {"job_id": "j1"}})
    request = ReviewJobRequest(
        repo="acme/widgets",
        pr=3,
        head_sha=_HEAD,
        base_sha=_BASE,
        deadline=datetime(2026, 11, 1, 12, tzinfo=UTC),
    )

    result = await ReviewQueueService(db).submit_job(request, "review-producer")  # type: ignore[arg-type]

    assert result["created"] is True
    fn, params = db.calls[0]
    assert fn == "submit_review_job"
    assert params == {
        "p_repo": "acme/widgets",
        "p_pr": 3,
        "p_head_sha": _HEAD,
        "p_base_sha": _BASE,
        "p_submitted_by": "review-producer",
        "p_round": None,
        "p_lanes_required": 2,
        "p_risk": "medium",
        "p_deadline": "2026-11-01T12:00:00+00:00",
    }
    logged = audit.log_operation.await_args.kwargs
    assert logged["operation"] == "review_submit"
    assert logged["result"]["job_id"] == "j1"
    assert logged["success"] is True


async def test_record_lanes_sends_lane_dicts_and_the_pass_budget(
    audit: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVIEW_MAX_PASSES", "5")
    reset_config()
    db = FakeDb({"success": False, "reason": "stale_pass"})
    lanes = [LaneResultIn(vendor="codex", verified=True, findings=[{"description": "x"}])]

    result = await ReviewQueueService(db).record_lanes("t1", "agent-a", lanes)  # type: ignore[arg-type]

    assert result["reason"] == "stale_pass"
    fn, params = db.calls[0]
    assert fn == "record_review_lanes"
    assert params["p_max_passes"] == 5
    assert params["p_lanes"] == [
        {
            "vendor": "codex",
            "verified": True,
            "verdict": None,
            "model": None,
            "findings": [{"description": "x"}],
            "error": None,
        }
    ]
    logged = audit.log_operation.await_args.kwargs
    assert logged["parameters"]["lanes"] == [("codex", True)]
    assert logged["success"] is False


async def test_publication_calls_map_their_arguments() -> None:
    db = FakeDb({"claimed": True})
    service = ReviewQueueService(db)  # type: ignore[arg-type]

    await service.get_round("acme/widgets", 3, _HEAD)
    await service.claim_publication("j1")
    await service.finish_publication("j1", review_id=42)

    assert db.calls == [
        (
            "get_review_round",
            {"p_repo": "acme/widgets", "p_pr": 3, "p_head_sha": _HEAD, "p_round": None},
        ),
        ("claim_review_publication", {"p_job_id": "j1"}),
        ("finish_review_publication", {"p_job_id": "j1", "p_review_id": 42, "p_error": None}),
    ]


async def test_a_non_object_rpc_result_is_an_error() -> None:
    with pytest.raises(RuntimeError, match="get_review_round returned list"):
        await ReviewQueueService(FakeDb([])).get_round("acme/widgets", 3, _HEAD)  # type: ignore[arg-type]
