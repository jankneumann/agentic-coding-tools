from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.agents_config import (
    DEFAULT_PROVIDER_MODEL_MAP,
    ArchetypeConfig,
    EscalationConfig,
    ProviderModelMappingError,
    load_archetypes_config,
    reset_archetypes_config,
    resolve_archetype_for_phase,
    resolve_model,
    resolve_provider_model,
    resolve_provider_model_spec,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_archetypes_config()
    yield
    reset_archetypes_config()


# Tests derive expected models from the configured map — never from literals —
# so tuning tier entries (model or thinking level) does not invalidate tests.

def _entry(provider: str, tier: str) -> dict | str:
    return DEFAULT_PROVIDER_MODEL_MAP["providers"][provider][tier]


def _entry_model(provider: str, tier: str) -> str:
    entry = _entry(provider, tier)
    return entry["model"] if isinstance(entry, dict) else entry


def _entry_thinking(provider: str, tier: str) -> str | None:
    entry = _entry(provider, tier)
    return entry.get("thinking") if isinstance(entry, dict) else None


def test_default_provider_model_map_includes_first_class_providers() -> None:
    assert set(DEFAULT_PROVIDER_MODEL_MAP["providers"]) >= {
        "claude_code",
        "codex",
        "antigravity",
    }
    # Base tiers are required on every provider; frontier is optional.
    for provider in ("claude_code", "codex", "antigravity"):
        assert set(DEFAULT_PROVIDER_MODEL_MAP["providers"][provider]) >= {
            "premium",
            "standard",
            "economy",
        }
    # Structural expectations only — which providers carry a frontier slot.
    assert "frontier" in DEFAULT_PROVIDER_MODEL_MAP["providers"]["claude_code"]
    assert "frontier" in DEFAULT_PROVIDER_MODEL_MAP["providers"]["codex"]
    assert "frontier" not in DEFAULT_PROVIDER_MODEL_MAP["providers"]["antigravity"]


def test_frontier_tier_resolves_for_providers_that_define_it() -> None:
    for provider in ("claude_code", "codex"):
        assert resolve_provider_model("frontier", provider=provider) == _entry_model(
            provider, "frontier"
        )


def test_frontier_tier_falls_back_to_premium_when_unmapped() -> None:
    model = resolve_provider_model("frontier", provider="antigravity")

    assert model == _entry_model("antigravity", "premium")


def test_frontier_fallback_raises_when_premium_also_missing() -> None:
    with pytest.raises(ProviderModelMappingError):
        resolve_provider_model("frontier", provider="codex", model_map={
            "schema_version": 2,
            "tiers": ["premium", "standard", "economy"],
            "providers": {
                "codex": {
                    "standard": "some-standard-model",
                    "economy": "some-economy-model",
                },
            },
        })


def test_spec_resolution_carries_thinking_level() -> None:
    for provider, tier in (("codex", "frontier"), ("codex", "premium")):
        spec = resolve_provider_model_spec(tier, provider=provider)

        assert spec.model == _entry_model(provider, tier)
        assert spec.thinking == _entry_thinking(provider, tier)


def test_same_model_in_two_tiers_is_distinguished_by_thinking() -> None:
    """Thinking level is part of the model definition (cost per successful
    task): the same model id may serve two tiers at different thinking."""
    frontier = resolve_provider_model_spec("frontier", provider="codex")
    premium = resolve_provider_model_spec("premium", provider="codex")

    if frontier.model == premium.model:
        assert frontier.thinking != premium.thinking


def test_string_tier_entries_have_no_thinking_level() -> None:
    spec = resolve_provider_model_spec("standard", provider="claude_code")

    assert spec.model == _entry_model("claude_code", "standard")
    assert spec.thinking is None


def test_legacy_claude_alias_resolves_to_codex_model() -> None:
    model = resolve_provider_model("opus", provider="codex")

    assert model == _entry_model("codex", "premium")
    assert model not in {"opus", "sonnet", "haiku"}


def test_legacy_claude_alias_resolves_to_latest_antigravity_model() -> None:
    model = resolve_provider_model("sonnet", provider="antigravity")

    assert model == _entry_model("antigravity", "standard")
    assert model not in {"opus", "sonnet", "haiku"}


def test_unknown_non_claude_mapping_raises_structured_error() -> None:
    with pytest.raises(ProviderModelMappingError) as exc_info:
        resolve_provider_model("opus", provider="codex", model_map={
            "schema_version": 1,
            "tiers": ["premium", "standard", "economy"],
            "providers": {
                "codex": {
                    "standard": "some-standard-model",
                    "economy": "some-economy-model",
                },
            },
        })

    assert exc_info.value.provider == "codex"
    assert "premium" in str(exc_info.value)


def test_resolve_model_remains_backward_compatible_without_provider() -> None:
    archetype = ArchetypeConfig(
        name="architect",
        model="opus",
        system_prompt="You are a software architect.",
    )

    assert resolve_model(archetype, {}) == "opus"


def test_resolve_model_maps_escalated_tier_for_antigravity_provider() -> None:
    archetype = ArchetypeConfig(
        name="implementer",
        model="standard",
        system_prompt="You are a focused implementer.",
        escalation=EscalationConfig(escalate_to="premium", loc_threshold=100),
    )

    model, reasons = resolve_model(
        archetype,
        {"loc_estimate": 250},
        provider="antigravity",
        return_reasons=True,
    )

    assert model == _entry_model("antigravity", "premium")
    assert any("loc_estimate" in reason for reason in reasons)


def test_resolve_archetype_for_phase_accepts_provider(tmp_path: Path) -> None:
    config = tmp_path / "archetypes.yaml"
    config.write_text(textwrap.dedent("""\
        schema_version: 2
        archetypes:
          architect:
            model: premium
            write_capable: true
            system_prompt: "You are a software architect."
          runner:
            model: economy
            write_capable: false
            system_prompt: "Execute and report."
        phase_mapping:
          PLAN: {archetype: architect}
          INIT: {archetype: runner}
    """))
    load_archetypes_config(config)

    resolved = resolve_archetype_for_phase("PLAN", {}, provider="codex")

    assert resolved.archetype == "architect"
    assert resolved.model == _entry_model("codex", "premium")
    assert resolved.thinking == _entry_thinking("codex", "premium")
