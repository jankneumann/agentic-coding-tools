"""Pure reviewer-routing and thinking-translation helpers.

The dispatcher owns transport execution.  This module owns the small policy
boundary that decides whether a review should use an explicitly resolved
archetype or retain the legacy static vendor configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
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


def default_reviewer_resolver(phase: str | None, vendor: str) -> RoutingContext:
    """Resolve local coordinator routing for ordinary review-mode callers."""
    coordinator_root = Path(__file__).resolve().parents[3] / "agent-coordinator"
    if str(coordinator_root) not in sys.path:
        sys.path.insert(0, str(coordinator_root))
    from src import agents_config

    agents_config.load_archetypes_config()
    if phase is not None:
        resolved = agents_config.resolve_archetype_for_phase(phase, {}, provider=vendor)
        return RoutingContext(
            archetype=resolved.archetype,
            tier=None,
            phase=phase,
            model=resolved.model,
            thinking=resolved.thinking,
            source="local_coordinator",
        )
    archetype = agents_config.get_archetype("reviewer")
    if archetype is None:
        raise RuntimeError("reviewer archetype is unavailable")
    model_spec = agents_config.resolve_provider_model_spec(archetype.model, provider=vendor)
    return RoutingContext(
        archetype=archetype.name,
        tier=archetype.model,
        phase=None,
        model=model_spec.model,
        thinking=model_spec.thinking,
        source="local_coordinator",
    )


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
    resolver = resolver or default_reviewer_resolver
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
