"""Pure reviewer-routing and thinking-translation helpers.

The dispatcher owns transport execution.  This module owns the small policy
boundary that decides whether a review should use an explicitly resolved
archetype or retain the legacy static vendor configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class RoutingContext:
    """Requested logical routing and its resolved provider execution."""

    archetype: str | None
    tier: str | None
    phase: str | None
    model: str | None
    thinking: str | None
    source: str
    fallback_reason: str | None = None


Resolver = Callable[[str | None, str], RoutingContext]


def resolve_review_routing(
    *,
    vendor: str,
    dispatch_mode: str,
    explicit: RoutingContext | None = None,
    phase: str | None = None,
    resolver: Resolver | None = None,
) -> RoutingContext | None:
    """Resolve review routing with the documented conservative precedence.

    ``None`` means the caller must use its existing static vendor model.  This
    is intentional for quick-mode calls and for unavailable local/coordinator
    resolution; no static model is duplicated in this policy module.
    """
    if explicit is not None:
        return explicit
    if dispatch_mode != "review":
        return None
    if resolver is None:
        return RoutingContext(
            archetype=None,
            tier=None,
            phase=phase,
            model=None,
            thinking=None,
            source="static",
            fallback_reason="reviewer_resolution_unavailable",
        )
    try:
        return resolver(phase, vendor)
    except (KeyError, RuntimeError, ValueError):
        return RoutingContext(
            archetype=None,
            tier=None,
            phase=phase,
            model=None,
            thinking=None,
            source="static",
            fallback_reason="reviewer_resolution_unavailable",
        )


def translate_thinking(
    requested: str | None,
    flag: str,
    values: dict[str, str],
) -> tuple[str | None, str | None, str]:
    """Return configured CLI flag/value and an auditable translation status."""
    if requested is None:
        return None, None, "not_requested"
    applied = values.get(requested)
    if not flag or not applied:
        return None, None, "unsupported"
    return flag, applied, "applied"
