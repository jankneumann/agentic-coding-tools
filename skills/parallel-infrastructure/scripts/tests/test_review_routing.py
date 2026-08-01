"""Characterization tests for config-driven reviewer routing."""

from __future__ import annotations

from review_routing import RoutingContext, resolve_review_routing


def _resolved(phase: str | None, vendor: str) -> RoutingContext:
    return RoutingContext(
        archetype="reviewer",
        tier="premium",
        phase=phase,
        model=f"{vendor}-premium",
        thinking="high",
        source="coordinator",
    )


def test_explicit_routing_wins_over_phase_mapping() -> None:
    explicit = RoutingContext(
        archetype="reviewer", tier="standard", phase="PLAN_REVIEW",
        model="explicit-model", thinking=None, source="explicit",
    )

    result = resolve_review_routing(
        vendor="pi", dispatch_mode="review", phase="PLAN_REVIEW",
        explicit=explicit, resolver=_resolved,
    )

    assert result is explicit


def test_review_mode_without_phase_uses_reviewer_default() -> None:
    result = resolve_review_routing(
        vendor="pi", dispatch_mode="review", resolver=_resolved,
    )

    assert result.archetype == "reviewer"
    assert result.tier == "premium"
    assert result.model == "pi-premium"
    assert result.phase is None


def test_quick_mode_keeps_static_routing() -> None:
    result = resolve_review_routing(
        vendor="pi", dispatch_mode="quick", resolver=_resolved,
    )

    assert result is None


def test_resolution_failure_records_static_fallback() -> None:
    def unavailable(_phase: str | None, _vendor: str) -> RoutingContext:
        raise RuntimeError("coordinator unavailable")

    result = resolve_review_routing(
        vendor="pi", dispatch_mode="review", resolver=unavailable,
    )

    assert result is not None
    assert result.model is None
    assert result.archetype is None
    assert result.fallback_reason == "reviewer_resolution_unavailable"
