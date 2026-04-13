"""Vendor scheduling policy engine for roadmap execution.

Evaluates what action to take when a vendor hits limits (rate, budget, time).
Supports wait, switch, and fail-closed actions with cascading failover
and structured decision logging.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from models import Policy, PolicyAction  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class VendorLimit:
    """Describes a vendor limit that has been hit."""

    vendor: str
    reason: str
    reset_at: str | None = None  # ISO datetime when limit resets


@dataclass
class PolicyDecision:
    """Result of a policy evaluation."""

    action: str  # "wait", "switch", "fail_closed"
    reason: str
    from_vendor: str
    to_vendor: str | None = None
    expected_wait_seconds: int | None = None
    expected_cost_delta_usd: float | None = None


# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------

def evaluate_policy(
    policy: Policy,
    vendor_limit: VendorLimit,
    available_vendors: list[str],
    switch_attempts: int,
) -> PolicyDecision:
    """Evaluate what action to take given a vendor limit event.

    Parameters
    ----------
    policy:
        The roadmap-level policy configuration.
    vendor_limit:
        The limit event that triggered evaluation.
    available_vendors:
        List of vendor names that could serve as alternatives.
        Should NOT include the limited vendor.
    switch_attempts:
        How many times we've already switched vendors for this item.

    Returns
    -------
    PolicyDecision with one of:
    - action="wait": Wait for the vendor limit to reset.
    - action="switch": Switch to an alternate vendor.
    - action="fail_closed": No viable action; item cannot proceed.
    """
    from_vendor = vendor_limit.vendor

    # Filter out the limited vendor from available list
    alternates = [v for v in available_vendors if v != from_vendor]

    # Check if we've exhausted switch attempts
    if switch_attempts >= policy.max_switch_attempts_per_item:
        logger.info(
            "policy.fail_closed: switch_attempts=%d >= max=%d for vendor=%s",
            switch_attempts, policy.max_switch_attempts_per_item, from_vendor,
        )
        return PolicyDecision(
            action="fail_closed",
            reason=(
                f"Exceeded max switch attempts ({switch_attempts}"
                f"/{policy.max_switch_attempts_per_item})"
            ),
            from_vendor=from_vendor,
        )

    # Evaluate based on default_action policy
    if policy.default_action == PolicyAction.WAIT:
        return _evaluate_wait(policy, vendor_limit, from_vendor)

    if policy.default_action == PolicyAction.SWITCH:
        return _evaluate_switch(
            policy, vendor_limit, from_vendor, alternates, switch_attempts,
        )

    # Unknown policy action — fail safe
    return PolicyDecision(
        action="fail_closed",
        reason=f"Unknown policy action: {policy.default_action}",
        from_vendor=from_vendor,
    )


def _evaluate_wait(
    policy: Policy,
    vendor_limit: VendorLimit,
    from_vendor: str,
) -> PolicyDecision:
    """Produce a wait decision with estimated resume time."""
    wait_seconds = _estimate_wait_seconds(vendor_limit.reset_at)

    logger.info(
        "policy.wait: vendor=%s reason=%s wait_seconds=%s",
        from_vendor, vendor_limit.reason, wait_seconds,
    )

    return PolicyDecision(
        action="wait",
        reason=f"Waiting for {from_vendor} limit reset: {vendor_limit.reason}",
        from_vendor=from_vendor,
        expected_wait_seconds=wait_seconds,
    )


def _evaluate_switch(
    policy: Policy,
    vendor_limit: VendorLimit,
    from_vendor: str,
    alternates: list[str],
    switch_attempts: int,
) -> PolicyDecision:
    """Produce a switch or fail_closed decision."""
    if not alternates:
        logger.info(
            "policy.fail_closed: no alternates for vendor=%s", from_vendor,
        )
        return PolicyDecision(
            action="fail_closed",
            reason=f"No alternate vendors available (limited: {from_vendor})",
            from_vendor=from_vendor,
        )

    # Pick preferred vendor if available, otherwise first alternate
    to_vendor = alternates[0]
    if policy.preferred_vendor and policy.preferred_vendor in alternates:
        to_vendor = policy.preferred_vendor

    # Estimate cost delta (placeholder — real implementation would query
    # vendor pricing APIs)
    estimated_cost_delta = _estimate_cost_delta(from_vendor, to_vendor)

    # Check cost ceiling
    if (
        policy.cost_ceiling_usd is not None
        and estimated_cost_delta is not None
        and estimated_cost_delta > policy.cost_ceiling_usd
    ):
        logger.info(
            "policy.fail_closed: cost_delta=%.2f > ceiling=%.2f",
            estimated_cost_delta, policy.cost_ceiling_usd,
        )
        return PolicyDecision(
            action="fail_closed",
            reason=(
                f"Switch cost ${estimated_cost_delta:.2f} exceeds ceiling "
                f"${policy.cost_ceiling_usd:.2f}"
            ),
            from_vendor=from_vendor,
            to_vendor=to_vendor,
            expected_cost_delta_usd=estimated_cost_delta,
        )

    logger.info(
        "policy.switch: %s -> %s (attempt %d/%d, cost_delta=%s)",
        from_vendor, to_vendor, switch_attempts + 1,
        policy.max_switch_attempts_per_item, estimated_cost_delta,
    )

    return PolicyDecision(
        action="switch",
        reason=f"Switching from {from_vendor} to {to_vendor}: {vendor_limit.reason}",
        from_vendor=from_vendor,
        to_vendor=to_vendor,
        expected_cost_delta_usd=estimated_cost_delta,
    )


# ---------------------------------------------------------------------------
# Estimation helpers
# ---------------------------------------------------------------------------

def _estimate_wait_seconds(reset_at: str | None) -> int | None:
    """Estimate seconds until a limit resets from an ISO timestamp."""
    if reset_at is None:
        return None
    try:
        reset_time = datetime.fromisoformat(reset_at)
        if reset_time.tzinfo is None:
            reset_time = reset_time.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = (reset_time - now).total_seconds()
        return max(0, int(delta))
    except (ValueError, TypeError):
        return None


def _estimate_cost_delta(from_vendor: str, to_vendor: str) -> float | None:
    """Estimate cost difference when switching vendors.

    Returns a positive number if to_vendor is more expensive,
    negative if cheaper, None if unknown.

    This is a stub — real implementations would query vendor pricing
    APIs or use cached rate cards.
    """
    # Placeholder cost tiers (relative $/1K tokens, normalized)
    _COST_TIERS: dict[str, float] = {
        "claude": 1.0,
        "codex": 0.8,
        "gemini": 0.6,
        "openai": 1.2,
    }
    from_cost = _COST_TIERS.get(from_vendor)
    to_cost = _COST_TIERS.get(to_vendor)
    if from_cost is not None and to_cost is not None:
        return round(to_cost - from_cost, 2)
    return None
