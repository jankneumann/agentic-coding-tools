"""Bound-key identity retry for the memory endpoints of coordination_bridge.

A key bound to an identity refuses any other ``agent_id``. Before the retry,
``try_remember`` / ``try_recall`` surfaced that refusal as a failure, which
silently dropped every approval-gate audit record (its sink writes as
"approval-gate"). The memory helpers now share the lock helpers' rule: send
the caller's identity first, and retry once with it blanked only when the
server refuses it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Make the bridge importable without needing an editable install.
_BRIDGE_DIR = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

import coordination_bridge  # noqa: E402


def _state() -> dict[str, Any]:
    return {
        "status": "ok",
        "COORDINATOR_AVAILABLE": True,
        "COORDINATION_TRANSPORT": "http",
        "http_url": "http://coord.example",
        "CAN_LOCK": False,
        "CAN_QUEUE_WORK": False,
        "CAN_HANDOFF": False,
        "CAN_MEMORY": True,
        "CAN_GUARDRAILS": False,
        "CAN_FEATURE_REGISTRY": False,
        "CAN_MERGE_QUEUE": False,
        "CAN_ISSUES": False,
        "CAN_CODE_SEARCH": False,
    }


def _refusal() -> dict[str, Any]:
    return {
        "status_code": 403,
        "data": {"detail": "API key is not permitted to act as requested agent_id"},
        "error": "forbidden",
    }


def _ok() -> dict[str, Any]:
    return {"status_code": 200, "data": {"success": True}, "error": None}


def _capture_bridge(
    monkeypatch: pytest.MonkeyPatch, responses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []
    queue = list(responses)
    monkeypatch.setattr(coordination_bridge, "detect_coordination", lambda **_: _state())
    monkeypatch.setattr(
        coordination_bridge,
        "_http_request",
        lambda **kwargs: (captured.append(kwargs) or queue.pop(0)),
    )
    return captured


def test_try_remember_retries_without_identity_when_the_key_is_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The approval-gate audit sink writes as "approval-gate"; a bound key
    refused that and every gate decision went unaudited."""
    captured = _capture_bridge(monkeypatch, [_refusal(), _ok()])

    result = coordination_bridge.try_remember(
        agent_id="approval-gate",
        event_type="approval_gate_decision",
        summary="s",
        details={"agent_id": "approval-gate"},
        api_key="bound-key-xyz",
    )

    assert result["status"] == "ok"
    assert [c["payload"]["agent_id"] for c in captured] == ["approval-gate", ""]
    # The logical actor survives the retry in ``details``.
    assert captured[1]["payload"]["details"] == {"agent_id": "approval-gate"}


def test_try_remember_keeps_caller_identity_for_an_unbound_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a refusal the caller's identity is the memory's author."""
    captured = _capture_bridge(monkeypatch, [_ok()])

    coordination_bridge.try_remember(
        agent_id="claude-code-1", event_type="e", summary="s", api_key="k"
    )

    assert len(captured) == 1
    assert captured[0]["payload"]["agent_id"] == "claude-code-1"


def test_try_recall_retries_without_identity_when_the_key_is_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_bridge(monkeypatch, [_refusal(), _ok()])

    coordination_bridge.try_recall(agent_id="approval-gate", api_key="bound-key-xyz")

    assert [c["payload"]["agent_id"] for c in captured] == ["approval-gate", ""]


def test_try_remember_does_not_retry_an_unrelated_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the identity refusal means "you are bound"; other 403s are real."""
    denied = {
        "status_code": 403,
        "data": {"detail": "agent is not permitted to store memory"},
        "error": "forbidden",
    }
    captured = _capture_bridge(monkeypatch, [denied])

    result = coordination_bridge.try_remember(
        agent_id="a", event_type="e", summary="s", api_key="k"
    )

    assert len(captured) == 1
    assert result["status"] != "ok"


def test_try_recall_keeps_caller_identity_for_an_unbound_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unbound key never refuses, so recall stays scoped to the caller."""
    captured = _capture_bridge(monkeypatch, [_ok()])

    coordination_bridge.try_recall(agent_id="claude-code-1", api_key="k")

    assert len(captured) == 1
    assert captured[0]["payload"]["agent_id"] == "claude-code-1"


def test_try_recall_does_not_retry_an_unrelated_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied = {
        "status_code": 403,
        "data": {"detail": "agent is not permitted to query memory"},
        "error": "forbidden",
    }
    captured = _capture_bridge(monkeypatch, [denied])

    result = coordination_bridge.try_recall(agent_id="a", api_key="k")

    assert len(captured) == 1
    assert result["status"] != "ok"
