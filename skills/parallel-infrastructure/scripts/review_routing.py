"""Pure reviewer-routing and thinking-translation helpers.

The dispatcher owns transport execution.  This module owns the small policy
boundary that decides whether a review should use an explicitly resolved
archetype or retain the legacy static vendor configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
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
    """Resolve routing through the coordinator's portable public bridge.

    Skills are installed without the coordinator source tree, so importing
    ``src.agents_config`` here created a source-checkout-only dependency.
    The bridge is copied with skills and degrades to the static adapter model
    when the coordinator is not reachable.
    """
    bridge_path = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts" / "coordination_bridge.py"
    spec = importlib.util.spec_from_file_location("coordination_bridge", bridge_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("coordinator bridge is unavailable")
    bridge = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = bridge
    spec.loader.exec_module(bridge)
    resolved = bridge.try_resolve_archetype_for_phase(phase or "IMPL_REVIEW", {}, provider=vendor)
    if not isinstance(resolved, dict):
        raise RuntimeError("reviewer resolution is unavailable")
    return RoutingContext(
        archetype=resolved.get("archetype") if isinstance(resolved.get("archetype"), str) else None,
        tier=None,
        phase=phase,
        model=resolved.get("model") if isinstance(resolved.get("model"), str) else None,
        thinking=resolved.get("thinking") if isinstance(resolved.get("thinking"), str) else None,
        source="coordinator_http",
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
