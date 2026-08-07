"""Characterization tests for config-driven reviewer routing."""

from __future__ import annotations

from types import SimpleNamespace

from review_routing import (
    RoutingContext,
    _local_routing,
    default_reviewer_resolver,
    resolve_review_routing,
    translate_thinking,
)


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


def test_default_resolver_falls_back_without_a_public_coordinator(monkeypatch) -> None:
    def unavailable(_phase: str | None, _vendor: str) -> RoutingContext:
        raise RuntimeError("coordinator unavailable")

    monkeypatch.setattr("review_routing.default_reviewer_resolver", unavailable)
    result = resolve_review_routing(vendor="codex", dispatch_mode="review")

    assert result is not None
    assert result.archetype is None
    assert result.model is None
    assert result.source == "static"
    assert result.fallback_reason == "reviewer_resolution_unavailable"


def test_public_local_resolver_preserves_archetype_tier_and_provider_model() -> None:
    result = _local_routing("IMPL_REVIEW", "pi")
    assert result.source == "coordinator_local"
    assert result.archetype == "reviewer"
    assert result.tier == "premium"
    assert result.model == "qwen/qwen3-coder-plus"


def test_http_resolver_derives_missing_canonical_tier(monkeypatch) -> None:
    bridge = SimpleNamespace(
        try_resolve_archetype_for_phase=lambda *_args, **_kwargs: {
            "archetype": "reviewer",
            "model": "gpt-test",
            "thinking": "high",
        },
    )
    spec = SimpleNamespace(
        name="test_coordination_bridge",
        loader=SimpleNamespace(exec_module=lambda _module: None),
    )
    monkeypatch.setattr("review_routing.importlib.util.spec_from_file_location", lambda *_args: spec)
    monkeypatch.setattr("review_routing.importlib.util.module_from_spec", lambda _spec: bridge)

    result = default_reviewer_resolver("IMPL_REVIEW", "codex")

    assert result.archetype == "reviewer"
    assert result.tier == "premium"
    assert result.source == "coordinator_http"
    assert result.fallback_reason == "tier_derived_from_archetype"


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


def test_thinking_translation_is_configured_or_explicitly_unsupported() -> None:
    assert translate_thinking("high", "--reasoning-effort", {"high": "high"}) == (
        "--reasoning-effort", "high", "applied",
    )
    assert translate_thinking("high", "", {}) == (None, None, "unsupported")
