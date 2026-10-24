"""Capability probes must detect a route without running its handler.

``detect_coordination()`` runs on every session start. A probe body that passes
request validation executes the endpoint for real: ``{}`` to ``/work/claim``
claims the next pending task of any type (including cross-host review passes)
and strands it with the probing agent. Mutating probes therefore have to send a
body the coordinator rejects with 422, which ``_probe_capability`` reads as
"route exists".

The models below mirror ``agent-coordinator/src/coordination_api.py``. The
coordinator side pins the ``/work/claim`` contract in
``test_claim_work_empty_body_claims_any_task_type`` and
``test_claim_work_rejects_bridge_capability_probe_body``.
"""

from __future__ import annotations

from typing import Any

import coordination_bridge as bridge
import pytest
from pydantic import BaseModel, ValidationError


class WorkClaimRequest(BaseModel):
    agent_id: str | None = None
    agent_type: str | None = None
    task_types: list[str] | None = None


class LockAcquireRequest(BaseModel):
    file_path: str
    agent_id: str | None = None
    agent_type: str | None = None
    session_id: str | None = None


class HandoffWriteRequest(BaseModel):
    agent_id: str | None = None
    agent_type: str | None = None
    session_id: str | None = None
    summary: str


class MemoryQueryRequest(BaseModel):
    agent_id: str
    tags: list[str] | None = None
    event_type: str | None = None
    limit: int = 10


class GuardrailsCheckRequest(BaseModel):
    operation_text: str
    file_paths: list[str] | None = None


_MUTATING_PROBE_MODELS: dict[str, tuple[str, type[BaseModel]]] = {
    "CAN_LOCK": ("/locks/acquire", LockAcquireRequest),
    "CAN_QUEUE_WORK": ("/work/claim", WorkClaimRequest),
    "CAN_HANDOFF": ("/handoffs/write", HandoffWriteRequest),
    "CAN_MEMORY": ("/memory/query", MemoryQueryRequest),
    "CAN_GUARDRAILS": ("/guardrails/check", GuardrailsCheckRequest),
}


def test_empty_body_is_a_valid_claim() -> None:
    """Why the work probe cannot send ``{}``: it validates as a claim of any type."""
    claim = WorkClaimRequest.model_validate({})
    assert claim.task_types is None


@pytest.mark.parametrize("flag", sorted(_MUTATING_PROBE_MODELS))
def test_mutating_probe_body_fails_request_validation(flag: str) -> None:
    path, model = _MUTATING_PROBE_MODELS[flag]
    probes = bridge._CAPABILITY_PROBES[flag]

    assert [probe[:2] for probe in probes] == [("POST", path)]
    for _method, _path, payload in probes:
        with pytest.raises(ValidationError):
            model.model_validate(payload)


def test_queue_work_probe_cannot_validate_as_a_claim() -> None:
    [(_method, path, payload)] = bridge._CAPABILITY_PROBES["CAN_QUEUE_WORK"]

    assert path == "/work/claim"
    assert payload != {}
    with pytest.raises(ValidationError):
        WorkClaimRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (422, True),
        (200, True),
        (405, True),
        (404, False),
        (401, False),
        (403, False),
        (500, False),
        (None, False),
    ],
)
def test_probe_capability_status_mapping(
    monkeypatch: pytest.MonkeyPatch, status_code: int | None, expected: bool
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"status_code": status_code, "data": None}

    monkeypatch.setattr(bridge, "_http_request", fake_http_request)

    result = bridge._probe_capability(
        probes=bridge._CAPABILITY_PROBES["CAN_QUEUE_WORK"],
        http_url="https://coordinator.invalid",
        api_key="key",
    )

    assert result is expected
    assert calls[0]["payload"] == {"task_types": "not-a-list"}
