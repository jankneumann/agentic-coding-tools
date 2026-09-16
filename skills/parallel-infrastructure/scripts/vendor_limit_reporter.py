"""Best-effort exact-lane reporting for dispatcher-observed capacity limits."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)

_BRIDGE_SCRIPTS = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts"
if str(_BRIDGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_SCRIPTS))

from coordination_bridge import try_report_vendor_rate_limit  # noqa: E402

Reporter = Callable[[str, dict[str, Any]], dict[str, Any]]


def _error_class_value(result: Any) -> str | None:
    value = getattr(result, "error_class", None)
    return getattr(value, "value", value) if value is not None else None


def report_vendor_limit_result(
    result: Any,
    *,
    reporter: Reporter = try_report_vendor_rate_limit,
) -> dict[str, Any]:
    """Report one capacity result without ever deriving a lane from provider."""
    if _error_class_value(result) not in {"capacity", "capacity_exhausted"}:
        return {"status": "skipped", "reason": "not_capacity"}

    agent_id = getattr(result, "agent_id", None)
    if not isinstance(agent_id, str) or not agent_id.strip():
        logger.warning(
            "Skipping ambiguous provider-only capacity report for vendor=%s; "
            "an exact agent_id is required",
            getattr(result, "vendor", None),
        )
        return {"status": "skipped", "reason": "exact_agent_id_required"}

    model = getattr(result, "capacity_model", None)
    scope = getattr(result, "capacity_scope", None) or ("model" if model else "lane")
    payload: dict[str, Any] = {
        "observation_id": f"dispatch-{uuid4()}",
        "reason": str(getattr(result, "error", None) or "capacity_exhausted"),
        "scope": scope,
        "metadata": {"vendor": str(getattr(result, "vendor", ""))},
    }
    if model:
        payload["model"] = model
    reset_at = getattr(result, "capacity_reset_at", None)
    retry_after = getattr(result, "capacity_retry_after_seconds", None)
    if reset_at is not None:
        payload["reset_at"] = reset_at
    elif retry_after is not None:
        payload["retry_after_seconds"] = retry_after

    try:
        return reporter(agent_id, payload)
    except Exception as exc:  # noqa: BLE001 — reporting never masks dispatch
        logger.warning(
            "Vendor limit reporting failed for agent_id=%s: %s",
            agent_id,
            exc,
        )
        return {"status": "error", "reason": "report_failed", "error": str(exc)}
