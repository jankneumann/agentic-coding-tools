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
    AgentClaimant,
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
# Claimability — a rostered role nobody can claim (issue #390)
# =============================================================================


class TestClaimability:
    """A roster entry that exists and names real vendors can still be dead.

    ``claim_task`` filters on the *agent's own* declared archetypes, so a role
    no registered agent declares is unclaimable: its tasks sit pending with no
    error and no rejection. Existence checks cannot see that; this one can.
    """

    _KNOWN_ARCHETYPES = {"supervisor": False, "architect": True, "implementer": True}
    _KNOWN_VENDORS = {"claude_code", "codex", "grok"}

    def _validate(self, manifest, agents):
        return manifest.validate_against(
            known_archetypes=self._KNOWN_ARCHETYPES,
            known_vendors=self._KNOWN_VENDORS,
            agents=agents,
        )

    def test_fully_staffed_roster_passes(self, valid_crew_data):
        manifest = CrewManifest.from_dict(valid_crew_data)
        agents = [
            AgentClaimant("claude-local", "claude_code", ("supervisor", "architect")),
            AgentClaimant("grok-local", "grok", ("implementer",)),
        ]
        assert self._validate(manifest, agents) == []

    def test_undeclared_archetype_is_flagged(self, valid_crew_data):
        """The #390 shape: the role exists, the vendor is real, nobody declares it."""
        manifest = CrewManifest.from_dict(valid_crew_data)
        agents = [
            AgentClaimant("claude-local", "claude_code", ("architect", "implementer")),
            AgentClaimant("grok-local", "grok", ("implementer",)),
        ]
        errors = self._validate(manifest, agents)
        assert any(
            "supervisor" in e and "unclaimable" in e and "do not declare it" in e
            for e in errors
        ), errors

    def test_wrong_vendor_declaring_it_does_not_count(self, valid_crew_data):
        """Declaring the archetype is not enough — the roster gates the vendor.

        ``supervisor`` is rostered to claude_code only. A grok agent declaring
        it would never be routed the work, so the role is still dead.
        """
        manifest = CrewManifest.from_dict(valid_crew_data)
        agents = [
            AgentClaimant("claude-local", "claude_code", ("architect",)),
            AgentClaimant("grok-local", "grok", ("supervisor", "implementer")),
        ]
        errors = self._validate(manifest, agents)
        assert any("supervisor" in e and "unclaimable" in e for e in errors), errors

    def test_no_agent_of_an_eligible_vendor_is_flagged_distinctly(
        self, valid_crew_data
    ):
        """An empty vendor pool gets its own diagnosis, not 'do not declare it'.

        ``supervisor`` is rostered to claude_code alone; with no claude_code
        agent registered at all, the fix is a different one (register an agent
        / widen the pool) than for a vendor that is present but silent.
        """
        manifest = CrewManifest.from_dict(valid_crew_data)
        agents = [AgentClaimant("grok-local", "grok", ("implementer",))]
        errors = self._validate(manifest, agents)
        supervisor = [e for e in errors if "supervisor" in e]
        assert supervisor, errors
        assert all("no registered agent" in e for e in supervisor), supervisor

    def test_agent_with_no_declared_archetypes_is_a_wildcard(self, valid_crew_data):
        """Empty ``archetypes`` means 'claims anything', matching claim_task.

        The SQL admits the task when ``p_agent_archetypes IS NULL``; reading an
        empty list as 'claims nothing' here would report roles that are in fact
        perfectly claimable.
        """
        manifest = CrewManifest.from_dict(valid_crew_data)
        agents = [
            AgentClaimant("legacy-claude", "claude_code", ()),
            AgentClaimant("legacy-grok", "grok", ()),
        ]
        assert self._validate(manifest, agents) == []

    def test_check_is_skipped_when_agents_not_supplied(self, valid_crew_data):
        """Structure-only callers keep their existing behaviour."""
        manifest = CrewManifest.from_dict(valid_crew_data)
        errors = manifest.validate_against(
            known_archetypes=self._KNOWN_ARCHETYPES,
            known_vendors=self._KNOWN_VENDORS,
        )
        assert errors == []

    def test_error_names_both_remedies(self, valid_crew_data):
        manifest = CrewManifest.from_dict(valid_crew_data)
        agents = [AgentClaimant("grok-local", "grok", ("implementer",))]
        errors = [e for e in self._validate(manifest, agents) if "supervisor" in e]
        assert errors
        assert "agents.yaml" in errors[0] and "teams.yaml" in errors[0]


class TestAgentClaimant:
    def test_declared_archetype_can_be_claimed(self):
        agent = AgentClaimant("a", "codex", ("implementer", "reviewer"))
        assert agent.can_claim("implementer")
        assert not agent.can_claim("validator")

    def test_empty_archetypes_claims_anything(self):
        agent = AgentClaimant("a", "codex")
        assert agent.can_claim("validator")
        assert agent.can_claim("anything-at-all")


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

    def test_cached_manifest_is_still_cross_validated_on_demand(
        self, tmp_path, valid_crew_data
    ):
        """An early ``cross_validate=False`` load must not disable the guard.

        Cross-validation used to run only on the call that populated the
        singleton. So one ``get_crew_manifest(path, cross_validate=False)``
        cached an unchecked manifest, and every later default call returned it
        while believing it had been validated — the fail-loud guarantee
        silently disabled for the life of the process. Here the manifest names
        an archetype that does not exist in archetypes.yaml: the unchecked load
        must succeed, and the next checked load must raise.
        """
        bad = dict(valid_crew_data)
        bad["roster"] = [
            {"archetype": "supervisor", "vendors": ["claude_code"]},
            {"archetype": "not-a-real-archetype", "vendors": ["claude_code"]},
        ]
        path = tmp_path / "teams.yaml"
        with open(path, "w") as f:
            yaml.dump(bad, f)

        # Structural load only — deliberately skips the roster cross-check.
        assert get_crew_manifest(path, cross_validate=False).crew == "test-crew"

        with pytest.raises(ValueError, match="cross-validation failed"):
            get_crew_manifest()

    def test_failed_cross_validation_is_not_cached(self, tmp_path, valid_crew_data):
        """A manifest that failed validation must not be handed out later."""
        bad = dict(valid_crew_data)
        bad["roster"] = [
            {"archetype": "supervisor", "vendors": ["claude_code"]},
            {"archetype": "not-a-real-archetype", "vendors": ["claude_code"]},
        ]
        path = tmp_path / "teams.yaml"
        with open(path, "w") as f:
            yaml.dump(bad, f)

        with pytest.raises(ValueError):
            get_crew_manifest(path)
        # A retry must re-raise rather than return the rejected object.
        with pytest.raises(ValueError):
            get_crew_manifest(path)


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

    def test_every_rostered_role_is_claimable_by_a_registered_agent(self):
        """No shipped roster entry may be dead on arrival (issue #390).

        Roles and vendors are read from the live teams.yaml/agents.yaml — never
        spelled out here — so adding a roster entry without staffing it fails
        this test rather than silently producing an unclaimable archetype.
        """
        from src.agents_config import (
            get_agents_config,
            reset_agents_config,
            reset_archetypes_config,
        )

        reset_crew_manifest()
        reset_archetypes_config()
        reset_agents_config()
        try:
            manifest = get_crew_manifest(cross_validate=False)
            agents = [
                AgentClaimant(e.name, e.type, tuple(e.archetypes))
                for e in get_agents_config()
            ]
            unstaffed = {
                role.archetype
                for role in manifest.roster
                if not any(
                    a.vendor in role.vendors and a.can_claim(role.archetype)
                    for a in agents
                )
            }
            assert unstaffed == set(), (
                f"rostered but unclaimable: {sorted(unstaffed)} — tasks "
                f"requiring these would sit pending forever"
            )
        finally:
            reset_crew_manifest()
            reset_archetypes_config()
            reset_agents_config()


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
