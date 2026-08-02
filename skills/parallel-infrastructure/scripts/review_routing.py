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


def _load_local_resolver() -> object:
    """Load the coordinator's public resolver from a source checkout."""
    for parent in Path(__file__).resolve().parents:
        coordinator = parent / "agent-coordinator"
        if (coordinator / "src" / "agents_config.py").is_file():
            if str(coordinator) not in sys.path:
                sys.path.insert(0, str(coordinator))
            from src import agents_config
            return agents_config
    raise RuntimeError("local coordinator resolver is unavailable")


def _local_routing(phase: str | None, vendor: str) -> RoutingContext:
    module = _load_local_resolver()
    resolved = module.resolve_archetype_for_phase(phase or "IMPL_REVIEW", {}, provider=vendor)
    tier = None
    archetype = module.get_archetype(resolved.archetype)
    if archetype is not None and archetype.model in module.ALL_MODEL_TIERS:
        tier = archetype.model
    return RoutingContext(
        archetype=resolved.archetype,
        tier=tier,
        phase=phase,
        model=resolved.model,
        thinking=resolved.thinking,
        source="coordinator_local",
    )


def default_reviewer_resolver(phase: str | None, vendor: str) -> RoutingContext:
    """Resolve routing through the coordinator's portable public bridge.

    Skills are installed without the coordinator source tree, so importing
    ``src.agents_config`` here created a source-checkout-only dependency.
    The bridge is copied with skills and degrades to the static adapter model
    when the coordinator is not reachable.
    """
    bridge_path = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts" / "coordination_bridge.py"
    try:
        spec = importlib.util.spec_from_file_location("coordination_bridge", bridge_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("coordinator bridge is unavailable")
        bridge = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = bridge
        spec.loader.exec_module(bridge)
        resolved = bridge.try_resolve_archetype_for_phase(phase or "IMPL_REVIEW", {}, provider=vendor)
        if isinstance(resolved, dict):
            return RoutingContext(
                archetype=resolved.get("archetype") if isinstance(resolved.get("archetype"), str) else None,
                tier=resolved.get("tier") if isinstance(resolved.get("tier"), str) else None,
                phase=phase,
                model=resolved.get("model") if isinstance(resolved.get("model"), str) else None,
                thinking=resolved.get("thinking") if isinstance(resolved.get("thinking"), str) else None,
                source="coordinator_http",
            )
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    return _local_routing(phase, vendor)


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
    except (ImportError, KeyError, OSError, RuntimeError, ValueError):
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
