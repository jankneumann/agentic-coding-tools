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
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_archetypes_config()
    yield
    reset_archetypes_config()


def test_default_provider_model_map_includes_first_class_providers() -> None:
    assert set(DEFAULT_PROVIDER_MODEL_MAP["providers"]) >= {
        "claude_code",
        "codex",
        "gemini",
    }
    for provider in ("claude_code", "codex", "gemini"):
        assert set(DEFAULT_PROVIDER_MODEL_MAP["providers"][provider]) == {
            "premium",
            "standard",
            "economy",
        }


def test_legacy_claude_alias_resolves_to_codex_model() -> None:
    model = resolve_provider_model("opus", provider="codex")

    assert model == "gpt-5.5"
    assert model not in {"opus", "sonnet", "haiku"}


def test_legacy_claude_alias_resolves_to_latest_gemini_model() -> None:
    model = resolve_provider_model("sonnet", provider="gemini")

    assert model == "gemini-3-flash-preview"
    assert model not in {"opus", "sonnet", "haiku"}


def test_unknown_non_claude_mapping_raises_structured_error() -> None:
    with pytest.raises(ProviderModelMappingError) as exc_info:
        resolve_provider_model("opus", provider="codex", model_map={
            "schema_version": 1,
            "tiers": ["premium", "standard", "economy"],
            "providers": {
                "codex": {
                    "standard": "gpt-5.4",
                    "economy": "gpt-5.4-mini",
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


def test_resolve_model_maps_escalated_tier_for_gemini_provider() -> None:
    archetype = ArchetypeConfig(
        name="implementer",
        model="standard",
        system_prompt="You are a focused implementer.",
        escalation=EscalationConfig(escalate_to="premium", loc_threshold=100),
    )

    model, reasons = resolve_model(
        archetype,
        {"loc_estimate": 250},
        provider="gemini",
        return_reasons=True,
    )

    assert model == "gemini-3.1-pro-preview"
    assert any("loc_estimate" in reason for reason in reasons)


def test_resolve_archetype_for_phase_accepts_provider(tmp_path: Path) -> None:
    config = tmp_path / "archetypes.yaml"
    config.write_text(textwrap.dedent("""\
        schema_version: 2
        archetypes:
          architect:
            model: premium
            system_prompt: "You are a software architect."
          runner:
            model: economy
            system_prompt: "Execute and report."
        phase_mapping:
          PLAN: {archetype: architect}
          INIT: {archetype: runner}
    """))
    load_archetypes_config(config)

    resolved = resolve_archetype_for_phase("PLAN", {}, provider="codex")

    assert resolved.archetype == "architect"
    assert resolved.model == "gpt-5.5"
