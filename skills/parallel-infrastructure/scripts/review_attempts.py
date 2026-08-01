"""Transport-neutral, bounded review-attempt recovery helpers."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


MAX_DIAGNOSTIC_CHARS = 4096
_CHAIN_CONTRACT_FIELDS = (
    "logical_request_id", "requested_vendor", "requested_routing", "deadline_at", "budget",
    "attempts", "terminal_outcome", "terminal_vendor", "quorum_eligible",
)
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
    error_detail, error_detail_truncated = sanitize_diagnostic(
        None if success else response.get("error_detail") or "review output did not validate"
    )
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
        "diagnostics_truncated": error_detail_truncated or stdout_truncated or stderr_truncated,
        "resolved_execution": _execution(model, fallback_reason=fallback_reason),
    }


@lru_cache(maxsize=1)
def _review_attempt_validator() -> Draft202012Validator:
    """Load the frozen contract from either a source tree or installed skill copy."""
    relative_contract = Path(
        "openspec/changes/harden-review-consensus-and-recovery/contracts/review-attempt.schema.json"
    )
    contract_path = next(
        (parent / relative_contract for parent in Path(__file__).resolve().parents
         if (parent / relative_contract).is_file()),
        None,
    )
    if contract_path is None:
        raise ValueError("review attempt schema is unavailable")
    try:
        schema = json.loads(contract_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, ValueError) as exc:
        raise ValueError("review attempt schema is invalid") from exc
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_attempt_schema(chain: Mapping[str, Any]) -> None:
    """Fail closed before applying relational invariants to a chain."""
    # ReviewResult containers retain legacy fields alongside the contract.  The
    # schema intentionally validates the embedded logical-chain projection,
    # while remaining strict about every field inside that projection.
    contract_chain = {field: chain.get(field) for field in _CHAIN_CONTRACT_FIELDS}
    errors = sorted(
        _review_attempt_validator().iter_errors(contract_chain),
        key=lambda error: (tuple(map(str, error.absolute_path)), error.message),
    )
    if errors:
        # Do not interpolate invalid provider values: they can contain credentials.
        raise ValueError(f"review attempt chain fails schema validation: {errors[0].validator}")


def validate_review_attempt_chain(chain: Mapping[str, Any]) -> None:
    """Validate application invariants that the JSON contract cannot express."""
    _validate_attempt_schema(chain)
    attempts = chain.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError("attempts must contain at least one attempt")
    requested_vendor = chain.get("requested_vendor")
    if not isinstance(requested_vendor, str) or not requested_vendor:
        raise ValueError("requested_vendor is required")
    indexes = [attempt.get("attempt_index") for attempt in attempts]
    if indexes != list(range(1, len(attempts) + 1)):
        raise ValueError("attempt indexes must be unique and monotonically increasing from one")
    if attempts[0].get("reason") != "initial" or attempts[0].get("vendor") != requested_vendor:
        raise ValueError("initial attempt must use requested vendor")
    terminals = [attempt for attempt in attempts if attempt.get("terminal") is True]
    if len(terminals) != 1 or terminals[0] is not attempts[-1]:
        raise ValueError("exactly one terminal attempt is required and it must be last")
    if any(attempt.get("success") is True for attempt in attempts[:-1]):
        raise ValueError("no attempt may follow a success")
    budget = chain.get("budget")
    if not isinstance(budget, Mapping):
        raise ValueError("budget is required")
    fallbacks = budget.get("fallback_models", [])
    if not isinstance(fallbacks, list) or len(fallbacks) != len(set(fallbacks)):
        raise ValueError("fallback_models must be a deduplicated list")
    fallback_set = set(fallbacks)

    # The JSON Schema bounds counts but cannot associate transitions with the
    # active vendor.  This automaton keeps each vendor-local recovery chain in
    # its legal order: initial -> corrective? -> fallbacks* -> replacement?
    # -> corrective? -> fallbacks*.
    active_vendor = requested_vendor
    active_initial_model = _model_of(attempts[0])
    replacement_seen = False
    corrective_seen: dict[str, bool] = {active_vendor: False}
    fallback_models_used: dict[str, set[str]] = {active_vendor: set()}
    recoverable_errors = {"invalid_output", "capacity_exhausted"}
    for index, attempt in enumerate(attempts):
        reason = attempt.get("reason")
        vendor = attempt.get("vendor")
        model = _model_of(attempt)
        if index == 0:
            continue
        previous = attempts[index - 1]
        if previous.get("error_class") not in recoverable_errors:
            raise ValueError("only invalid-output or capacity failures may be retried")
        if reason == "replacement_vendor":
            if replacement_seen or vendor == requested_vendor or vendor == active_vendor:
                raise ValueError("replacement vendor transition is illegal")
            replacement_seen = True
            active_vendor = vendor
            active_initial_model = model
            corrective_seen[active_vendor] = False
            fallback_models_used[active_vendor] = set()
            continue
        if vendor != active_vendor:
            raise ValueError("replacement follow-up attempts must stay with the replacement vendor")
        if reason == "corrective_redispatch":
            if corrective_seen[active_vendor] or fallback_models_used[active_vendor]:
                raise ValueError("corrective redispatch must precede model fallbacks")
            if model != active_initial_model:
                raise ValueError("corrective redispatch must repeat the active vendor and initial model")
            corrective_seen[active_vendor] = True
        elif reason == "model_fallback":
            if model not in fallback_set or model == active_initial_model or model in fallback_models_used[active_vendor]:
                raise ValueError("model fallback must be a configured, unique active-vendor fallback")
            fallback_models_used[active_vendor].add(model)
        else:
            # The schema rejects this too; retain the explicit automaton guard.
            raise ValueError("attempt transition reason is illegal")
    terminal = terminals[0]
    success = terminal.get("success") is True
    if chain.get("terminal_outcome") == "success":
        if not success or chain.get("quorum_eligible") is not True:
            raise ValueError("successful chains require a successful eligible terminal attempt")
        if chain.get("terminal_vendor") != terminal.get("vendor") or not _model_of(terminal):
            raise ValueError("successful terminal provenance is invalid")
    else:
        if success or chain.get("quorum_eligible") is True:
            raise ValueError("failed chains cannot be successful or quorum eligible")
        expected_outcome = (
            "invalid_output_exhausted"
            if terminal.get("error_class") == "invalid_output"
            else terminal.get("error_class")
        )
        if chain.get("terminal_outcome") != expected_outcome:
            raise ValueError("terminal outcome must match the terminal error class")
    if chain.get("terminal_vendor") != terminal.get("vendor"):
        raise ValueError("terminal vendor must match the terminal attempt")


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


def _invoke_with_deadline(
    invoke: Callable[[str, str, float, str], Mapping[str, Any]], *, vendor: str,
    model: str, remaining: float, reason: str,
) -> Mapping[str, Any]:
    """Return at the deadline even when an adapter's synchronous call hangs.

    The worker is daemonized so a non-cooperative SDK or polling adapter cannot
    hold the recovery coordinator (or process shutdown) past its logical slot.
    Adapters still receive the remaining budget and should use it for their own
    request, poll, sleep, and retry timeouts.
    """
    response_queue: Queue[Mapping[str, Any]] = Queue(maxsize=1)

    def call() -> None:
        try:
            response = invoke(vendor, model, remaining, reason)
            response_queue.put(
                response if isinstance(response, Mapping) else {
                    "error_class": "configuration",
                    "error_detail": "review adapter returned a non-mapping response",
                }
            )
        except BaseException:
            # Never persist or print raw SDK exception text from this boundary.
            response_queue.put({
                "error_class": "transient",
                "error_detail": "review adapter invocation failed",
            })

    Thread(target=call, name="review-attempt-invoke", daemon=True).start()
    try:
        return response_queue.get(timeout=remaining)
    except Empty:
        return {
            "error_class": "timeout",
            "error_detail": "logical vendor deadline exhausted during invocation",
        }


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
            response = _invoke_with_deadline(
                invoke, vendor=vendor, model=model, remaining=remaining, reason=reason,
            )
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
