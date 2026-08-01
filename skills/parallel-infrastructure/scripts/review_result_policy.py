"""Shared, fail-closed policy for logical review results.

This module deliberately accepts mappings rather than dispatcher-specific
dataclasses so CLI, SDK, async, checkpoints, and future result transports all
apply the same quorum rule.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    as_dict = getattr(value, "to_dict", None)
    if callable(as_dict):
        candidate = as_dict()
        return candidate if isinstance(candidate, Mapping) else None
    fields = getattr(value, "__dict__", None)
    return fields if isinstance(fields, Mapping) else None


def is_quorum_eligible(logical_result: object) -> bool:
    """Return whether a terminal logical result may contribute one vote.

    A malformed result is intentionally treated as ineligible, rather than
    leaking validation failures into callers deciding whether a round may
    converge.
    """
    result = _as_mapping(logical_result)
    if result is None or result.get("terminal_outcome") != "success":
        return False
    if result.get("quorum_eligible") is not True:
        return False
    terminal_vendor = result.get("terminal_vendor")
    if not isinstance(terminal_vendor, str) or not terminal_vendor:
        return False
    try:
        from review_attempts import validate_review_attempt_chain

        validate_review_attempt_chain(result)
    except (ImportError, TypeError, ValueError):
        return False
    attempts = result.get("attempts")
    if not isinstance(attempts, list):
        return False
    terminal = [attempt for attempt in attempts if isinstance(attempt, Mapping) and attempt.get("terminal")]
    if len(terminal) != 1:
        return False
    attempt = terminal[0]
    execution = attempt.get("resolved_execution")
    return (
        attempt.get("success") is True
        and attempt.get("vendor") == terminal_vendor
        and isinstance(execution, Mapping)
        and isinstance(execution.get("model"), str)
        and bool(execution["model"])
    )


def quorum_summary(
    logical_results: Iterable[object], *, minimum_required: int, requested: int | None = None
) -> dict[str, int | bool]:
    """Derive quorum from distinct eligible terminal vendors.

    ``requested`` is a logical-slot count, not a physical-attempt count.
    Supplying it lets a caller retain a transferred/cancelled replacement slot.
    """
    results = list(logical_results)
    eligible_vendors: set[str] = set()
    for result in results:
        if is_quorum_eligible(result):
            mapped = _as_mapping(result)
            assert mapped is not None
            eligible_vendors.add(str(mapped["terminal_vendor"]))
    requested_count = len(results) if requested is None else requested
    if requested_count < 0 or minimum_required < 0:
        raise ValueError("requested and minimum_required must be non-negative")
    received = len(eligible_vendors)
    return {
        "requested": requested_count,
        "received": received,
        "minimum_required": minimum_required,
        "met": received >= minimum_required and received <= requested_count,
    }
