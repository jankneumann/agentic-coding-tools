"""Tests for archetype configuration loading, prompt composition, and escalation.

Spec scenarios:
- agent-archetypes.1 (archetype definition schema)
- agent-archetypes.2 (predefined archetypes)
- agent-archetypes.4 (complexity-based escalation)

Design decisions: D1 (configuration not code), D2 (composition not replacement),
D3 (escalation at dispatch time), D5 (graceful degradation)
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.agents_config import (
    ArchetypeConfig,
    EscalationConfig,
    compose_prompt,
    get_archetype,
    load_archetypes_config,
    reset_archetypes_config,
    resolve_model,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """Reset the global archetypes cache before each test."""
    reset_archetypes_config()
    yield  # type: ignore[misc]
    reset_archetypes_config()


@pytest.fixture
def valid_archetypes_yaml(tmp_path: Path) -> Path:
    """Create a minimal valid archetypes.yaml."""
    content = textwrap.dedent("""\
        schema_version: 1

        archetypes:
          architect:
            model: opus
            system_prompt: "You are a software architect."
          analyst:
            model: sonnet
            system_prompt: "You are a codebase analyst."
          implementer:
            model: sonnet
            system_prompt: "You are a focused implementer."
            escalation:
              escalate_to: opus
              max_write_dirs: 3
              max_dependencies: 2
              loc_threshold: 100
          reviewer:
            model: opus
            system_prompt: "You are a code reviewer."
          runner:
            model: haiku
            system_prompt: "Execute the requested command and report results."
          documenter:
            model: sonnet
            system_prompt: "You are a documentation writer."
    """)
    p = tmp_path / "archetypes.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def invalid_archetypes_yaml(tmp_path: Path) -> Path:
    """Create an archetypes.yaml missing required 'model' field."""
    content = textwrap.dedent("""\
        schema_version: 1

        archetypes:
          broken:
            system_prompt: "Missing model field."
    """)
    p = tmp_path / "archetypes.yaml"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Task 2.0.1: ArchetypeConfig loading and validation
# ---------------------------------------------------------------------------

class TestArchetypeLoading:
    """Spec: agent-archetypes.1 — archetype definition schema."""

    def test_valid_archetype_loads_successfully(
        self, valid_archetypes_yaml: Path,
    ) -> None:
        """WHEN archetypes.yaml has valid content THEN all archetypes load."""
        archetypes = load_archetypes_config(path=valid_archetypes_yaml)

        assert "implementer" in archetypes
        impl = archetypes["implementer"]
        assert isinstance(impl, ArchetypeConfig)
        assert impl.name == "implementer"
        assert impl.model == "sonnet"
        assert impl.system_prompt == "You are a focused implementer."
        assert impl.escalation is not None
        assert impl.escalation.escalate_to == "opus"
        assert impl.escalation.loc_threshold == 100

    def test_all_six_predefined_archetypes_load(
        self, valid_archetypes_yaml: Path,
    ) -> None:
        """All 6 predefined archetypes must be present."""
        archetypes = load_archetypes_config(path=valid_archetypes_yaml)
        expected = {"architect", "analyst", "implementer", "reviewer", "runner", "documenter"}
        assert set(archetypes.keys()) == expected

    def test_invalid_archetype_rejected(
        self, invalid_archetypes_yaml: Path,
    ) -> None:
        """WHEN model field is missing THEN ValidationError is raised."""
        from jsonschema import ValidationError

        with pytest.raises(ValidationError, match="model"):
            load_archetypes_config(path=invalid_archetypes_yaml)

    def test_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """WHEN archetypes.yaml doesn't exist THEN return empty dict (D5)."""
        missing = tmp_path / "nonexistent.yaml"
        archetypes = load_archetypes_config(path=missing)
        assert archetypes == {}

    def test_get_archetype_returns_none_for_unknown(
        self, valid_archetypes_yaml: Path,
    ) -> None:
        """WHEN unknown archetype referenced THEN get_archetype returns None."""
        load_archetypes_config(path=valid_archetypes_yaml)
        result = get_archetype("nonexistent")
        assert result is None

    def test_get_archetype_returns_config_for_known(
        self, valid_archetypes_yaml: Path,
    ) -> None:
        """WHEN known archetype referenced THEN get_archetype returns it."""
        load_archetypes_config(path=valid_archetypes_yaml)
        result = get_archetype("architect")
        assert result is not None
        assert result.model == "opus"

    def test_caching_avoids_reload(
        self, valid_archetypes_yaml: Path,
    ) -> None:
        """Config is loaded once and cached (singleton pattern)."""
        a1 = load_archetypes_config(path=valid_archetypes_yaml)
        # Modify file — cached version should be returned
        valid_archetypes_yaml.write_text("schema_version: 1\narchetypes: {}")
        a2 = load_archetypes_config(path=valid_archetypes_yaml)
        assert a1 is a2  # Same object reference = cached

    def test_archetype_name_validation(self, tmp_path: Path) -> None:
        """Archetype names must match ^[a-z][a-z0-9_-]{0,31}$."""
        from jsonschema import ValidationError

        content = textwrap.dedent("""\
            schema_version: 1
            archetypes:
              INVALID_NAME:
                model: sonnet
                system_prompt: "Bad name."
        """)
        p = tmp_path / "archetypes.yaml"
        p.write_text(content)
        with pytest.raises(ValidationError, match="INVALID_NAME"):
            load_archetypes_config(path=p)


# ---------------------------------------------------------------------------
# Task 2.0.2: System prompt composition
# ---------------------------------------------------------------------------

class TestPromptComposition:
    """Spec: agent-archetypes.2 — predefined archetypes.
    Design: D2 — composition not replacement."""

    def test_compose_prepends_system_prompt(self) -> None:
        """Archetype system_prompt is prepended with separator."""
        archetype = ArchetypeConfig(
            name="implementer",
            model="sonnet",
            system_prompt="You are a focused implementer.",
        )
        result = compose_prompt(archetype, "Fix the bug in users.py")
        assert result.startswith("You are a focused implementer.")
        assert "\n\n---\n\n" in result
        assert result.endswith("Fix the bug in users.py")

    def test_compose_with_empty_system_prompt(self) -> None:
        """Empty system_prompt returns just the task prompt."""
        archetype = ArchetypeConfig(
            name="test",
            model="sonnet",
            system_prompt="",
        )
        result = compose_prompt(archetype, "Do something")
        assert result == "Do something"

    def test_architect_prompt_contains_keyword(
        self, valid_archetypes_yaml: Path,
    ) -> None:
        """Scenario: Architect system prompt SHALL contain 'software architect'."""
        archetypes = load_archetypes_config(path=valid_archetypes_yaml)
        assert "software architect" in archetypes["architect"].system_prompt.lower()

    def test_runner_prompt_contains_keywords(
        self, valid_archetypes_yaml: Path,
    ) -> None:
        """Scenario: Runner system prompt SHALL contain 'execute' and 'report'."""
        archetypes = load_archetypes_config(path=valid_archetypes_yaml)
        prompt = archetypes["runner"].system_prompt.lower()
        assert "execute" in prompt
        assert "report" in prompt


# ---------------------------------------------------------------------------
# Task 2.0.3: Complexity-based escalation
# ---------------------------------------------------------------------------

class TestEscalation:
    """Spec: agent-archetypes.4 — complexity-based escalation.
    Design: D3 — escalation at dispatch time."""

    @pytest.fixture
    def implementer(self) -> ArchetypeConfig:
        return ArchetypeConfig(
            name="implementer",
            model="sonnet",
            system_prompt="You are a focused implementer.",
            escalation=EscalationConfig(
                escalate_to="opus",
                max_write_dirs=3,
                max_dependencies=2,
                loc_threshold=100,
            ),
        )

    @pytest.fixture
    def architect(self) -> ArchetypeConfig:
        """Architect has no escalation (always opus)."""
        return ArchetypeConfig(
            name="architect",
            model="opus",
            system_prompt="You are a software architect.",
        )

    def test_no_escalation_returns_base_model(
        self, architect: ArchetypeConfig,
    ) -> None:
        """Archetype without escalation returns its base model."""
        result = resolve_model(architect, {})
        assert result == "opus"

    def test_simple_package_stays_on_sonnet(
        self, implementer: ArchetypeConfig,
    ) -> None:
        """WHEN write_allow has 1 file, no deps THEN stays on sonnet."""
        pkg = {
            "write_allow": ["src/api/users.py"],
            "dependencies": [],
            "loc_estimate": 50,
        }
        result = resolve_model(implementer, pkg)
        assert result == "sonnet"

    def test_large_scope_triggers_escalation(
        self, implementer: ArchetypeConfig,
    ) -> None:
        """WHEN write_allow spans >3 dirs THEN escalate to opus."""
        pkg = {
            "write_allow": [
                "src/api/**", "src/models/**",
                "src/services/**", "tests/**",
            ],
            "dependencies": [],
            "loc_estimate": 50,
        }
        model, reasons = resolve_model(implementer, pkg, return_reasons=True)
        assert model == "opus"
        assert any("write_allow" in r for r in reasons)

    def test_cross_module_deps_trigger_escalation(
        self, implementer: ArchetypeConfig,
    ) -> None:
        """WHEN depends_on has >2 packages THEN escalate to opus."""
        pkg = {
            "write_allow": ["src/api/**"],
            "dependencies": ["wp-a", "wp-b", "wp-c"],
            "loc_estimate": 50,
        }
        model, reasons = resolve_model(implementer, pkg, return_reasons=True)
        assert model == "opus"
        assert any("depends on" in r for r in reasons)

    def test_high_loc_triggers_escalation(
        self, implementer: ArchetypeConfig,
    ) -> None:
        """WHEN loc_estimate exceeds threshold (100) THEN escalate to opus."""
        pkg = {
            "write_allow": ["src/api/**"],
            "dependencies": [],
            "loc_estimate": 150,
        }
        model, reasons = resolve_model(implementer, pkg, return_reasons=True)
        assert model == "opus"
        assert any("loc_estimate" in r for r in reasons)

    def test_explicit_complexity_flag_triggers_escalation(
        self, implementer: ArchetypeConfig,
    ) -> None:
        """WHEN complexity: high THEN escalate regardless of scope."""
        pkg = {
            "write_allow": ["src/api/tiny.py"],
            "dependencies": [],
            "loc_estimate": 10,
            "complexity": "high",
        }
        model, reasons = resolve_model(implementer, pkg, return_reasons=True)
        assert model == "opus"
        assert any("complexity" in r for r in reasons)

    def test_multiple_triggers_all_logged(
        self, implementer: ArchetypeConfig,
    ) -> None:
        """Multiple escalation triggers should all appear in reasons."""
        pkg = {
            "write_allow": [
                "src/api/**", "src/models/**",
                "src/services/**", "tests/**",
            ],
            "dependencies": ["wp-a", "wp-b", "wp-c"],
            "loc_estimate": 200,
            "complexity": "high",
        }
        model, reasons = resolve_model(implementer, pkg, return_reasons=True)
        assert model == "opus"
        assert len(reasons) == 4

    def test_escalation_retains_system_prompt(
        self, implementer: ArchetypeConfig,
    ) -> None:
        """Escalation changes model but NOT system prompt (still implementer)."""
        pkg = {
            "write_allow": [
                "src/api/**", "src/models/**",
                "src/services/**", "tests/**",
            ],
            "dependencies": [],
            "loc_estimate": 50,
        }
        model, _ = resolve_model(implementer, pkg, return_reasons=True)
        assert model == "opus"
        # System prompt unchanged — compose_prompt still uses implementer prompt
        composed = compose_prompt(implementer, "task")
        assert "focused implementer" in composed

    def test_missing_package_metadata_no_crash(
        self, implementer: ArchetypeConfig,
    ) -> None:
        """Empty metadata dict should not crash — just returns base model."""
        result = resolve_model(implementer, {})
        assert result == "sonnet"
