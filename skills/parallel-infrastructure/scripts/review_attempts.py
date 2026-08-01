"""Transport-neutral, bounded review-attempt recovery helpers."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any


MAX_DIAGNOSTIC_CHARS = 4096
_SECRET_PATTERNS = (
    re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def sanitize_diagnostic(text: object, *, limit: int = MAX_DIAGNOSTIC_CHARS) -> tuple[str | None, bool]:
    """Redact secret-like tokens and bound text before it reaches an artifact."""
    if text is None:
        return None, False
    value = str(text)
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    truncated = len(value) > limit
    if truncated:
        value = value[:limit]
    return value, truncated


def _execution(model: str | None, *, fallback_reason: str | None = None) -> dict[str, object]:
    return {
        "model": model,
        "requested_thinking": None,
        "applied_thinking": None,
        "thinking_translation": "not_requested",
        "fallback_reason": fallback_reason,
    }


def _attempt_record(
    *, index: int, vendor: str, model: str | None, reason: str, response: Mapping[str, Any],
    elapsed: float, fallback_reason: str | None = None,
) -> dict[str, object]:
    validation_status = str(response.get("validation_status", "not_reached"))
    success = validation_status == "schema_valid"
    error_class = None if success else str(response.get("error_class") or "invalid_output")
    error_detail = None if success else str(response.get("error_detail") or "review output did not validate")
    stdout, stdout_truncated = sanitize_diagnostic(response.get("stdout"))
    stderr, stderr_truncated = sanitize_diagnostic(response.get("stderr"))
    return {
        "attempt_index": index,
        "vendor": vendor,
        "transport": str(response.get("transport", "cli")),
        "reason": reason,
        "terminal": False,
        "success": success,
        "elapsed_seconds": max(0.0, elapsed),
        "parser_stage": "schema" if success else response.get("parser_stage", "json" if validation_status == "invalid" else None),
        "validation_status": validation_status,
        "error_class": error_class,
        "error_detail": error_detail,
        "stdout_excerpt": stdout,
        "stderr_excerpt": stderr,
        "diagnostics_truncated": stdout_truncated or stderr_truncated,
        "resolved_execution": _execution(model, fallback_reason=fallback_reason),
    }


def validate_review_attempt_chain(chain: Mapping[str, Any]) -> None:
    """Validate application invariants that the JSON contract cannot express."""
    attempts = chain.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError("attempts must contain at least one attempt")
    requested_vendor = chain.get("requested_vendor")
    if not isinstance(requested_vendor, str) or not requested_vendor:
        raise ValueError("requested_vendor is required")
    indexes = [attempt.get("attempt_index") if isinstance(attempt, Mapping) else None for attempt in attempts]
    if indexes != list(range(1, len(attempts) + 1)):
        raise ValueError("attempt indexes must be unique and monotonically increasing from one")
    if attempts[0].get("reason") != "initial" or attempts[0].get("vendor") != requested_vendor:
        raise ValueError("initial attempt must use requested vendor")
    terminals = [attempt for attempt in attempts if attempt.get("terminal") is True]
    if len(terminals) != 1 or terminals[0] is not attempts[-1]:
        raise ValueError("exactly one terminal attempt is required and it must be last")
    if any(attempt.get("success") is True for attempt in attempts[:-1]):
        raise ValueError("no attempt may follow a success")
    reasons = [attempt.get("reason") for attempt in attempts]
    if reasons.count("corrective_redispatch") > 1 or reasons.count("replacement_vendor") > 1:
        raise ValueError("corrective and replacement attempts are each bounded to one")
    budget = chain.get("budget")
    if not isinstance(budget, Mapping):
        raise ValueError("budget is required")
    fallbacks = budget.get("fallback_models", [])
    if not isinstance(fallbacks, list) or len(fallbacks) != len(set(fallbacks)):
        raise ValueError("fallback_models must be a deduplicated list")
    initial_model = _model_of(attempts[0])
    replacement_seen = False
    fallback_models_used: set[str] = set()
    for attempt in attempts:
        reason = attempt.get("reason")
        vendor = attempt.get("vendor")
        model = _model_of(attempt)
        if not isinstance(vendor, str) or not vendor:
            raise ValueError("every attempt needs a vendor")
        if reason == "corrective_redispatch" and (vendor != requested_vendor or model != initial_model):
            raise ValueError("corrective redispatch must repeat the requested vendor and initial model")
        if reason == "model_fallback":
            if replacement_seen or vendor != requested_vendor or model not in fallbacks or model in fallback_models_used:
                raise ValueError("model fallback must be a configured, unique primary-vendor fallback")
            fallback_models_used.add(str(model))
        elif reason == "replacement_vendor":
            if replacement_seen or vendor == requested_vendor:
                raise ValueError("replacement vendor transition is illegal")
            replacement_seen = True
        elif replacement_seen and vendor != requested_vendor:
            raise ValueError("replacement chains are not permitted in the core logical chain")
    terminal = terminals[0]
    success = terminal.get("success") is True
    if chain.get("terminal_outcome") == "success":
        if not success or chain.get("quorum_eligible") is not True:
            raise ValueError("successful chains require a successful eligible terminal attempt")
        if chain.get("terminal_vendor") != terminal.get("vendor") or not _model_of(terminal):
            raise ValueError("successful terminal provenance is invalid")
    elif success or chain.get("quorum_eligible") is True:
        raise ValueError("failed chains cannot be successful or quorum eligible")


def _model_of(attempt: Mapping[str, Any]) -> str | None:
    execution = attempt.get("resolved_execution")
    if not isinstance(execution, Mapping):
        return None
    model = execution.get("model")
    return model if isinstance(model, str) and model else None


def select_replacement_vendor(
    configured_vendors: Iterable[str], *, dispatched_vendors: set[str], eligible: Callable[[str], bool] | None = None,
) -> str | None:
    """Choose the first configured, not-yet-dispatched eligible vendor."""
    predicate = eligible or (lambda _vendor: True)
    return next((vendor for vendor in configured_vendors if vendor not in dispatched_vendors and predicate(vendor)), None)


def run_vendor_recovery(
    *, logical_request_id: str, vendor: str, primary_model: str, fallback_models: Iterable[str],
    invoke: Callable[[str, str, float, str], Mapping[str, Any]], timeout_seconds: float,
    requested_routing: Mapping[str, object] | None = None,
    now: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    """Execute the bounded primary/corrective/fallback state machine.

    ``invoke`` receives only the remaining monotonic budget, allowing every
    adapter to use this implementation without importing subprocess details.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    ordered_fallbacks = list(dict.fromkeys(model for model in fallback_models if model != primary_model))
    deadline = now() + timeout_seconds
    attempts: list[dict[str, object]] = []

    def invoke_one(model: str, reason: str, fallback_reason: str | None = None) -> dict[str, object]:
        remaining = deadline - now()
        if remaining <= 0:
            response: Mapping[str, Any] = {"error_class": "timeout", "error_detail": "logical vendor deadline exhausted"}
        else:
            started = now()
            response = invoke(vendor, model, remaining, reason)
            elapsed = now() - started
            if now() >= deadline:
                response = {
                    "error_class": "timeout",
                    "error_detail": "logical vendor deadline exhausted during invocation",
                }
            record = _attempt_record(index=len(attempts) + 1, vendor=vendor, model=model, reason=reason, response=response, elapsed=elapsed, fallback_reason=fallback_reason)
            attempts.append(record)
            return record
        record = _attempt_record(index=len(attempts) + 1, vendor=vendor, model=model, reason=reason, response=response, elapsed=0.0, fallback_reason=fallback_reason)
        attempts.append(record)
        return record

    initial = invoke_one(primary_model, "initial")
    if not initial["success"] and initial["error_class"] == "invalid_output":
        corrective = invoke_one(primary_model, "corrective_redispatch")
        if corrective["success"]:
            initial = corrective
        else:
            initial = corrective
    if not initial["success"] and initial["error_class"] in {"invalid_output", "capacity_exhausted"}:
        for fallback in ordered_fallbacks:
            attempted = invoke_one(fallback, "model_fallback", fallback_reason=str(initial["error_class"]))
            initial = attempted
            if attempted["success"] or attempted["error_class"] == "auth":
                break
    terminal = attempts[-1]
    terminal["terminal"] = True
    success = terminal["success"] is True
    error_class = terminal["error_class"]
    outcome = "success" if success else str(error_class or "unknown")
    if outcome == "invalid_output":
        outcome = "invalid_output_exhausted"
    result: dict[str, object] = {
        "logical_request_id": logical_request_id,
        "requested_vendor": vendor,
        "requested_routing": dict(requested_routing or {"archetype": None, "tier": None, "phase": None}),
        "deadline_at": (datetime.now(timezone.utc) + timedelta(seconds=max(0.0, deadline - now()))).isoformat(),
        "budget": {"corrective_max": 1, "replacement_max": 1, "fallback_models": ordered_fallbacks},
        "attempts": attempts,
        "terminal_outcome": outcome,
        "terminal_vendor": vendor,
        "quorum_eligible": success,
    }
    validate_review_attempt_chain(result)
    return result
