"""Structural checks over the real ``agent-coordinator/archetypes.yaml``.

Spec: openspec/changes/fix-autopilot-archetype-and-apply-outcome/specs/
      skill-workflow/spec.md
      Requirement: "Archetypes Declare Write-Capability via a Structured Field"

These are CI guards (Task 6.1-6.3). They enforce that every write-capable
autopilot phase resolves to an archetype declaring ``write_capable: true`` via
the structured field — NO substring matching over ``system_prompt`` text.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from src.agents_config import (
    SUPERVISOR_ARCHETYPE,
    WRITE_CAPABLE_PHASES,
    get_archetype,
    load_archetypes_config,
    reset_archetypes_config,
    resolve_archetype_for_phase,
    resolve_model,
    resolve_provider_model_spec,
)

_ARCHETYPES_YAML = Path(__file__).resolve().parent.parent / "archetypes.yaml"


@pytest.fixture()
def _load_real_config() -> None:
    """Load the real archetypes.yaml into the module cache and reset after."""
    reset_archetypes_config()
    load_archetypes_config(_ARCHETYPES_YAML)
    yield
    reset_archetypes_config()


def _raw() -> dict:
    return yaml.safe_load(_ARCHETYPES_YAML.read_text())


# ---------------------------------------------------------------------------
# Task 6.2 — every archetype declares write_capable
# ---------------------------------------------------------------------------


def test_every_archetype_declares_write_capable() -> None:
    raw = _raw()
    missing = [
        name
        for name, data in raw["archetypes"].items()
        if "write_capable" not in data
    ]
    assert not missing, f"archetypes missing write_capable field: {missing}"


def test_write_capable_values_are_boolean() -> None:
    raw = _raw()
    non_bool = {
        name: data["write_capable"]
        for name, data in raw["archetypes"].items()
        if not isinstance(data.get("write_capable"), bool)
    }
    assert not non_bool, f"write_capable must be a bool: {non_bool}"


# ---------------------------------------------------------------------------
# Task 6.1 — every write-capable phase resolves to write_capable: true
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phase", sorted(WRITE_CAPABLE_PHASES))
def test_write_capable_phase_resolves_to_write_capable_archetype(
    phase: str, _load_real_config: None
) -> None:
    resolved = resolve_archetype_for_phase(phase, {})
    assert resolved.write_capable is True, (
        f"phase {phase} resolves to archetype {resolved.archetype!r} "
        f"with write_capable={resolved.write_capable}"
    )


def test_validate_maps_to_validator(_load_real_config: None) -> None:
    resolved = resolve_archetype_for_phase("VALIDATE", {})
    assert resolved.archetype == "validator"
    assert resolved.write_capable is True


def test_val_fix_maps_to_implementer(_load_real_config: None) -> None:
    resolved = resolve_archetype_for_phase("VAL_FIX", {})
    assert resolved.archetype == "implementer"
    assert resolved.write_capable is True


# ---------------------------------------------------------------------------
# Task 6.3 — validator prompt free of read-only-marker phrasing (secondary
# defense-in-depth guard; the structured field is the primary gate)
# ---------------------------------------------------------------------------


def test_validator_system_prompt_has_no_read_only_markers() -> None:
    raw = _raw()
    prompt = raw["archetypes"]["validator"]["system_prompt"].lower()
    forbidden = [
        "do not modify source code",
        "without making changes",
        "without modifying",
        "only synthesize",
    ]
    hits = [phrase for phrase in forbidden if phrase in prompt]
    assert not hits, f"validator system_prompt contains read-only markers: {hits}"


# ---------------------------------------------------------------------------
# Frontier tier — planning archetypes think at frontier, implementer does not
#
# Expectations are DERIVED from archetypes.yaml, never hardcoded: tuning a
# tier entry (model or thinking level) must not invalidate these tests.
# ---------------------------------------------------------------------------


def _alias(provider: str, tier: str) -> dict | str | None:
    return _raw()["model_aliases"][provider].get(tier)


def _alias_model(provider: str, tier: str) -> str:
    entry = _alias(provider, tier)
    assert entry is not None, f"{provider} defines no {tier} alias"
    return entry["model"] if isinstance(entry, dict) else entry


def _alias_thinking(provider: str, tier: str) -> str | None:
    entry = _alias(provider, tier)
    return entry.get("thinking") if isinstance(entry, dict) else None


def test_architect_resolves_frontier_per_provider(_load_real_config: None) -> None:
    aliases = _raw()["model_aliases"]

    for provider in aliases:
        resolved = resolve_archetype_for_phase("PLAN", {}, provider=provider)
        # Providers without a frontier alias gracefully fall back to premium.
        tier = "frontier" if "frontier" in aliases[provider] else "premium"

        assert resolved.archetype == "architect"
        assert resolved.model == _alias_model(provider, tier)
        assert resolved.thinking == _alias_thinking(provider, tier)


def test_implement_resolves_to_standard_not_frontier(_load_real_config: None) -> None:
    for provider in _raw()["model_aliases"]:
        resolved = resolve_archetype_for_phase("IMPLEMENT", {}, provider=provider)

        assert resolved.archetype == "implementer"
        assert resolved.model == _alias_model(provider, "standard")


# ---------------------------------------------------------------------------
# Supervisor archetype (ri-01): frontier tier, read-only, resolver rejects a
# write-capable supervisor. Expectations DERIVED from archetypes.yaml.
# ---------------------------------------------------------------------------


def test_supervisor_declared_frontier_and_read_only() -> None:
    """The shipped supervisor archetype is frontier + write_capable: false."""
    raw = _raw()
    assert SUPERVISOR_ARCHETYPE in raw["archetypes"], "supervisor archetype missing"
    supervisor = raw["archetypes"][SUPERVISOR_ARCHETYPE]
    assert supervisor["model"] == "frontier"
    assert supervisor["write_capable"] is False


def test_supervisor_resolves_frontier_write_capable_false(
    _load_real_config: None,
) -> None:
    """Resolving the supervisor archetype yields the frontier tier, read-only."""
    supervisor = get_archetype(SUPERVISOR_ARCHETYPE)
    assert supervisor is not None
    assert supervisor.write_capable is False
    # No provider: the logical tier passes through unchanged.
    assert resolve_model(supervisor, {}) == "frontier"


def test_supervisor_resolves_frontier_per_provider(_load_real_config: None) -> None:
    """Per provider, supervisor resolves to the frontier tier model (premium
    fallback for providers without a frontier alias)."""
    aliases = _raw()["model_aliases"]
    supervisor = get_archetype(SUPERVISOR_ARCHETYPE)
    assert supervisor is not None

    for provider in aliases:
        tier = "frontier" if "frontier" in aliases[provider] else "premium"
        spec = resolve_provider_model_spec(supervisor.model, provider=provider)
        assert spec.model == _alias_model(provider, tier)
        assert spec.thinking == _alias_thinking(provider, tier)


def test_resolver_rejects_write_capable_supervisor(tmp_path: Path) -> None:
    """The archetype resolver fails fast when supervisor is write_capable: true.

    Mirrors the D3 structured-field enforcement — a config that marks the
    supervisor write-capable is rejected at load time, not silently accepted.
    """
    content = textwrap.dedent(
        """\
        schema_version: 3
        archetypes:
          supervisor:
            write_capable: true
            model: frontier
            system_prompt: "Bad — supervisor must never be write-capable."
          implementer:
            write_capable: true
            model: standard
            system_prompt: "You are a focused implementer."
        """
    )
    p = tmp_path / "archetypes.yaml"
    p.write_text(content)

    reset_archetypes_config()
    try:
        with pytest.raises(ValueError, match="write_capable: false"):
            load_archetypes_config(path=p)
    finally:
        reset_archetypes_config()


def test_supervisor_not_write_capable_loads_clean(tmp_path: Path) -> None:
    """A read-only supervisor (write_capable: false) loads without error."""
    content = textwrap.dedent(
        """\
        schema_version: 3
        archetypes:
          supervisor:
            write_capable: false
            model: frontier
            system_prompt: "You are the supervisor. You delegate, never implement."
        """
    )
    p = tmp_path / "archetypes.yaml"
    p.write_text(content)

    reset_archetypes_config()
    try:
        archetypes = load_archetypes_config(path=p)
        assert archetypes[SUPERVISOR_ARCHETYPE].write_capable is False
        assert archetypes[SUPERVISOR_ARCHETYPE].model == "frontier"
    finally:
        reset_archetypes_config()
