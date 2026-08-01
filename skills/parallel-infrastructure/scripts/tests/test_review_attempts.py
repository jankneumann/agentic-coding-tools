"""Characterization tests for the review-attempt core contract."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review_attempts import (  # noqa: E402
    run_vendor_recovery,
    sanitize_diagnostic,
    select_replacement_vendor,
    validate_review_attempt_chain,
)
from review_result_policy import is_quorum_eligible, quorum_summary  # noqa: E402


def _attempt(
    index: int,
    *,
    vendor: str = "alpha",
    model: str = "primary",
    reason: str = "initial",
    terminal: bool = False,
    success: bool = False,
    error_class: str | None = "invalid_output",
) -> dict[str, object]:
    return {
        "attempt_index": index,
        "vendor": vendor,
        "transport": "cli",
        "reason": reason,
        "terminal": terminal,
        "success": success,
        "elapsed_seconds": 0.1,
        "parser_stage": "schema" if success else "json",
        "validation_status": "schema_valid" if success else "invalid",
        "error_class": None if success else error_class,
        "error_detail": None if success else "malformed result",
        "stdout_excerpt": None,
        "stderr_excerpt": None,
        "diagnostics_truncated": False,
        "resolved_execution": {
            "model": model,
            "requested_thinking": None,
            "applied_thinking": None,
            "thinking_translation": "not_requested",
            "fallback_reason": None,
        },
    }


def _chain(attempts: list[dict[str, object]]) -> dict[str, object]:
    terminal = attempts[-1]
    success = bool(terminal["success"])
    return {
        "logical_request_id": "round-1-alpha",
        "requested_vendor": "alpha",
        "requested_routing": {"archetype": "reviewer", "tier": "premium", "phase": "review"},
        "deadline_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
        "budget": {"corrective_max": 1, "replacement_max": 1, "fallback_models": ["fallback"]},
        "attempts": attempts,
        "terminal_outcome": "success" if success else "invalid_output_exhausted",
        "terminal_vendor": terminal["vendor"] if success else "alpha",
        "quorum_eligible": success,
    }


def test_invalid_output_uses_one_corrective_then_fallback() -> None:
    outcomes = iter([
        {"validation_status": "invalid", "error_detail": "not json", "stdout": "not json"},
        {"validation_status": "invalid", "error_detail": "still not json"},
        {"validation_status": "schema_valid", "findings": []},
    ])

    result = run_vendor_recovery(
        logical_request_id="round-1-alpha",
        vendor="alpha",
        primary_model="primary",
        fallback_models=["fallback", "fallback"],
        invoke=lambda *_args: next(outcomes),
        timeout_seconds=60,
    )

    assert [a["reason"] for a in result["attempts"]] == [
        "initial", "corrective_redispatch", "model_fallback",
    ]
    assert [a["resolved_execution"]["model"] for a in result["attempts"]] == [
        "primary", "primary", "fallback",
    ]
    assert result["terminal_outcome"] == "success"
    assert is_quorum_eligible(result)


def test_capacity_skips_corrective_and_auth_is_terminal() -> None:
    capacity = iter([
        {"error_class": "capacity_exhausted", "error_detail": "full"},
        {"validation_status": "schema_valid", "findings": []},
    ])
    result = run_vendor_recovery(
        logical_request_id="capacity", vendor="alpha", primary_model="primary",
        fallback_models=["fallback"], invoke=lambda *_args: next(capacity), timeout_seconds=60,
    )
    assert [a["reason"] for a in result["attempts"]] == ["initial", "model_fallback"]

    auth = run_vendor_recovery(
        logical_request_id="auth", vendor="alpha", primary_model="primary",
        fallback_models=["fallback"],
        invoke=lambda *_args: {"error_class": "auth", "error_detail": "expired"}, timeout_seconds=60,
    )
    assert len(auth["attempts"]) == 1
    assert auth["terminal_outcome"] == "auth"


def test_validator_fails_closed_for_bad_indexes_and_after_success() -> None:
    bad = _chain([_attempt(2, terminal=True)])
    with pytest.raises(ValueError, match="indexes"):
        validate_review_attempt_chain(bad)

    success = _attempt(1, terminal=False, success=True, error_class=None)
    trailing = _attempt(2, terminal=True)
    with pytest.raises(ValueError, match="success"):
        validate_review_attempt_chain(_chain([success, trailing]))


def test_quorum_requires_valid_terminal_routing_but_accepts_empty_findings() -> None:
    valid = _chain([_attempt(1, terminal=True, success=True, error_class=None)])
    assert is_quorum_eligible(valid)
    invalid = dict(valid, terminal_vendor="other")
    assert not is_quorum_eligible(invalid)
    assert quorum_summary([valid, invalid], minimum_required=1) == {
        "requested": 2, "received": 1, "minimum_required": 1, "met": True,
    }


def test_replacement_is_config_ordered_and_never_already_dispatched() -> None:
    assert select_replacement_vendor(
        ["alpha", "beta", "gamma"], dispatched_vendors={"alpha", "beta"}
    ) == "gamma"
    assert select_replacement_vendor(["alpha", "beta"], dispatched_vendors={"alpha", "beta"}) is None


def test_success_after_logical_deadline_is_terminal_timeout() -> None:
    calls = 0

    def now() -> float:
        nonlocal calls
        calls += 1
        return 0.0 if calls <= 3 else 2.0

    result = run_vendor_recovery(
        logical_request_id="timeout", vendor="alpha", primary_model="primary",
        fallback_models=[], timeout_seconds=1,
        invoke=lambda *_args: {"validation_status": "schema_valid", "findings": []},
        now=now,
    )

    assert result["terminal_outcome"] == "timeout"
    assert result["quorum_eligible"] is False


def test_diagnostics_redact_and_bound_sensitive_output() -> None:
    text, truncated = sanitize_diagnostic("token=sk-super-secret Bearer abcdefghijklmnop", limit=20)
    assert "super-secret" not in text
    assert "abcdefghijklmnop" not in text
    assert truncated
