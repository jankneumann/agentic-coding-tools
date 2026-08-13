"""Tests for the crew manifest module (repurposed from team composition).

The crew manifest (``teams.yaml``) declares the supervisor archetype at the
crew's apex, the archetype roster, and which vendors may fill each role. The
reader (``src/teams.py``) validates structure and cross-checks references
against the live ``archetypes.yaml`` roster + provider map.
"""

from pathlib import Path

import pytest
import yaml
from jsonschema import ValidationError

from src.teams import (
    CrewManifest,
    RoleAssignment,
    get_crew_manifest,
    reset_crew_manifest,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def valid_crew_data():
    """A valid crew manifest dictionary."""
    return {
        "schema_version": 1,
        "crew": "test-crew",
        "supervisor": "supervisor",
        "roster": [
            {"archetype": "supervisor", "vendors": ["claude_code"]},
            {"archetype": "architect", "vendors": ["claude_code", "codex"]},
            {"archetype": "implementer", "vendors": ["claude_code", "grok"]},
        ],
    }


@pytest.fixture
def valid_crew_yaml(tmp_path, valid_crew_data):
    """Write a valid crew manifest YAML file and return its path."""
    path = tmp_path / "teams.yaml"
    with open(path, "w") as f:
        yaml.dump(valid_crew_data, f)
    return path


@pytest.fixture(autouse=True)
def _reset_global():
    """Reset the global crew manifest after each test."""
    yield
    reset_crew_manifest()


# =============================================================================
# Loading
# =============================================================================


class TestCrewManifestLoading:
    def test_from_dict_valid(self, valid_crew_data):
        manifest = CrewManifest.from_dict(valid_crew_data)

        assert manifest.crew == "test-crew"
        assert manifest.supervisor == "supervisor"
        assert len(manifest.roster) == 3
        assert manifest.roster[0].archetype == "supervisor"
        assert manifest.roster[1].vendors == ["claude_code", "codex"]

    def test_from_file_valid(self, valid_crew_yaml):
        manifest = CrewManifest.from_file(valid_crew_yaml)

        assert manifest.crew == "test-crew"
        assert len(manifest.roster) == 3

    def test_from_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            CrewManifest.from_file(Path("/nonexistent/teams.yaml"))

    def test_from_file_empty(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("")

        with pytest.raises(ValueError, match="Empty crew manifest file"):
            CrewManifest.from_file(path)


# =============================================================================
# Schema Validation
# =============================================================================


class TestSchemaValidation:
    def test_missing_crew_field(self):
        data = {
            "supervisor": "supervisor",
            "roster": [{"archetype": "supervisor", "vendors": ["claude_code"]}],
        }
        with pytest.raises(ValidationError, match="'crew' is a required property"):
            CrewManifest.from_dict(data)

    def test_missing_supervisor_field(self):
        data = {
            "crew": "test-crew",
            "roster": [{"archetype": "supervisor", "vendors": ["claude_code"]}],
        }
        with pytest.raises(
            ValidationError, match="'supervisor' is a required property"
        ):
            CrewManifest.from_dict(data)

    def test_missing_roster_field(self):
        data = {"crew": "test-crew", "supervisor": "supervisor"}
        with pytest.raises(ValidationError, match="'roster' is a required property"):
            CrewManifest.from_dict(data)

    def test_empty_roster_rejected(self):
        data = {"crew": "test-crew", "supervisor": "supervisor", "roster": []}
        with pytest.raises(ValidationError):
            CrewManifest.from_dict(data)

    def test_roster_entry_requires_vendors(self):
        data = {
            "crew": "test-crew",
            "supervisor": "supervisor",
            "roster": [{"archetype": "supervisor"}],
        }
        with pytest.raises(ValidationError, match="'vendors' is a required property"):
            CrewManifest.from_dict(data)

    def test_roster_entry_empty_vendors_rejected(self):
        data = {
            "crew": "test-crew",
            "supervisor": "supervisor",
            "roster": [{"archetype": "supervisor", "vendors": []}],
        }
        with pytest.raises(ValidationError):
            CrewManifest.from_dict(data)

    def test_additional_properties_rejected(self):
        data = {
            "crew": "test-crew",
            "supervisor": "supervisor",
            "roster": [{"archetype": "supervisor", "vendors": ["claude_code"]}],
            "extra_field": "not allowed",
        }
        with pytest.raises(ValidationError, match="Additional properties"):
            CrewManifest.from_dict(data)


# =============================================================================
# Semantic Validation
# =============================================================================


class TestSemanticValidation:
    def test_duplicate_roster_archetype_rejected(self):
        data = {
            "crew": "test-crew",
            "supervisor": "supervisor",
            "roster": [
                {"archetype": "supervisor", "vendors": ["claude_code"]},
                {"archetype": "implementer", "vendors": ["codex"]},
                {"archetype": "implementer", "vendors": ["grok"]},
            ],
        }
        with pytest.raises(
            ValueError, match="Duplicate roster archetype: 'implementer'"
        ):
            CrewManifest.from_dict(data)

    def test_supervisor_must_be_in_roster(self):
        data = {
            "crew": "test-crew",
            "supervisor": "supervisor",
            "roster": [{"archetype": "implementer", "vendors": ["codex"]}],
        }
        with pytest.raises(
            ValueError, match="Supervisor archetype 'supervisor' is not in the roster"
        ):
            CrewManifest.from_dict(data)


# =============================================================================
# Cross-Validation against archetypes / providers
# =============================================================================


class TestCrossValidation:
    def test_valid_manifest_cross_validates_clean(self, valid_crew_data):
        manifest = CrewManifest.from_dict(valid_crew_data)
        errors = manifest.validate_against(
            known_archetypes={
                "supervisor": False,
                "architect": True,
                "implementer": True,
            },
            known_vendors={"claude_code", "codex", "grok"},
        )
        assert errors == []

    def test_unknown_archetype_flagged(self, valid_crew_data):
        manifest = CrewManifest.from_dict(valid_crew_data)
        errors = manifest.validate_against(
            known_archetypes={"supervisor": False, "architect": True},
            known_vendors={"claude_code", "codex", "grok"},
        )
        assert any("implementer" in e and "not defined" in e for e in errors)

    def test_unknown_vendor_flagged(self, valid_crew_data):
        manifest = CrewManifest.from_dict(valid_crew_data)
        errors = manifest.validate_against(
            known_archetypes={
                "supervisor": False,
                "architect": True,
                "implementer": True,
            },
            known_vendors={"claude_code"},  # codex + grok now "unknown"
        )
        assert any("unknown" in e and "vendors" in e for e in errors)

    def test_write_capable_supervisor_flagged(self, valid_crew_data):
        manifest = CrewManifest.from_dict(valid_crew_data)
        errors = manifest.validate_against(
            known_archetypes={
                "supervisor": True,  # invalid: supervisor must be read-only
                "architect": True,
                "implementer": True,
            },
            known_vendors={"claude_code", "codex", "grok"},
        )
        assert any(
            "supervisor" in e.lower() and "write_capable: false" in e for e in errors
        )


# =============================================================================
# Lookup
# =============================================================================


class TestRosterLookup:
    def test_get_role_found(self, valid_crew_data):
        manifest = CrewManifest.from_dict(valid_crew_data)
        role = manifest.get_role("architect")
        assert role is not None
        assert role.vendors == ["claude_code", "codex"]

    def test_get_role_not_found(self, valid_crew_data):
        manifest = CrewManifest.from_dict(valid_crew_data)
        assert manifest.get_role("nonexistent") is None

    def test_vendors_for_found(self, valid_crew_data):
        manifest = CrewManifest.from_dict(valid_crew_data)
        assert manifest.vendors_for("implementer") == ["claude_code", "grok"]

    def test_vendors_for_not_found(self, valid_crew_data):
        manifest = CrewManifest.from_dict(valid_crew_data)
        assert manifest.vendors_for("nonexistent") == []


# =============================================================================
# Global Singleton
# =============================================================================


class TestGlobalSingleton:
    def test_get_crew_manifest_loads_from_file(self, valid_crew_yaml):
        manifest = get_crew_manifest(valid_crew_yaml, cross_validate=False)
        assert manifest.crew == "test-crew"
        assert len(manifest.roster) == 3

    def test_get_crew_manifest_returns_same_instance(self, valid_crew_yaml):
        m1 = get_crew_manifest(valid_crew_yaml, cross_validate=False)
        m2 = get_crew_manifest()
        assert m1 is m2

    def test_reset_crew_manifest(self, valid_crew_yaml):
        m1 = get_crew_manifest(valid_crew_yaml, cross_validate=False)
        reset_crew_manifest()
        m2 = get_crew_manifest(valid_crew_yaml, cross_validate=False)
        assert m1 is not m2
        assert m1.crew == m2.crew


# =============================================================================
# Real manifest — the shipped teams.yaml cross-validates against archetypes.yaml
# =============================================================================


class TestRealManifest:
    def test_shipped_manifest_cross_validates(self):
        """The real teams.yaml must be consistent with the real archetypes.yaml.

        This is the wiring guard: every roster archetype exists, every vendor is
        a real provider, and the supervisor is read-only.
        """
        from src.agents_config import reset_archetypes_config

        reset_crew_manifest()
        reset_archetypes_config()
        try:
            manifest = get_crew_manifest()  # cross_validate=True by default
            assert manifest.supervisor == "supervisor"
            assert manifest.get_role("supervisor") is not None
        finally:
            reset_crew_manifest()
            reset_archetypes_config()


# =============================================================================
# RoleAssignment dataclass
# =============================================================================


class TestRoleAssignment:
    def test_fields(self):
        role = RoleAssignment(archetype="implementer", vendors=["claude_code", "codex"])
        assert role.archetype == "implementer"
        assert role.vendors == ["claude_code", "codex"]

    def test_equality(self):
        a = RoleAssignment(archetype="reviewer", vendors=["grok"])
        b = RoleAssignment(archetype="reviewer", vendors=["grok"])
        assert a == b
