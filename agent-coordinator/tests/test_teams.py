"""Tests for the declarative team composition module."""

from pathlib import Path

import pytest
import yaml
from jsonschema import ValidationError

from src.teams import (
    AgentDefinition,
    TeamsConfig,
    get_teams_config,
    reset_teams_config,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def valid_team_data():
    """A valid team configuration dictionary."""
    return {
        "team": "test-team",
        "agents": [
            {
                "name": "lead",
                "role": "coordinator",
                "capabilities": ["planning", "review", "orchestration"],
                "description": "Decomposes tasks and coordinates workers",
            },
            {
                "name": "implementer",
                "role": "worker",
                "capabilities": ["coding", "testing"],
                "description": "Implements features from proposals",
            },
            {
                "name": "reviewer",
                "role": "reviewer",
                "capabilities": ["review", "security-analysis"],
                "description": "Reviews PRs and checks for security issues",
            },
        ],
    }


@pytest.fixture
def valid_team_yaml(tmp_path, valid_team_data):
    """Write a valid team YAML file and return its path."""
    path = tmp_path / "teams.yaml"
    with open(path, "w") as f:
        yaml.dump(valid_team_data, f)
    return path


@pytest.fixture(autouse=True)
def _reset_global():
    """Reset the global teams config after each test."""
    yield
    reset_teams_config()


# =============================================================================
# TeamsConfig Loading
# =============================================================================


class TestTeamsConfigLoading:
    """Tests for loading team configurations."""

    def test_from_dict_valid(self, valid_team_data):
        """Test creating TeamsConfig from a valid dictionary."""
        config = TeamsConfig.from_dict(valid_team_data)

        assert config.team == "test-team"
        assert len(config.agents) == 3
        assert config.agents[0].name == "lead"
        assert config.agents[0].role == "coordinator"
        assert config.agents[0].capabilities == ["planning", "review", "orchestration"]
        assert config.agents[0].description == "Decomposes tasks and coordinates workers"

    def test_from_file_valid(self, valid_team_yaml):
        """Test loading TeamsConfig from a valid YAML file."""
        config = TeamsConfig.from_file(valid_team_yaml)

        assert config.team == "test-team"
        assert len(config.agents) == 3

    def test_from_file_not_found(self):
        """Test loading from a nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            TeamsConfig.from_file(Path("/nonexistent/teams.yaml"))

    def test_from_file_empty(self, tmp_path):
        """Test loading from an empty YAML file raises ValueError."""
        path = tmp_path / "empty.yaml"
        path.write_text("")

        with pytest.raises(ValueError, match="Empty YAML file"):
            TeamsConfig.from_file(path)


# =============================================================================
# Schema Validation
# =============================================================================


class TestSchemaValidation:
    """Tests for JSON Schema validation of team configs."""

    def test_missing_team_field(self):
        """Test that missing 'team' field fails validation."""
        data = {
            "agents": [
                {
                    "name": "lead",
                    "role": "coordinator",
                    "capabilities": ["planning"],
                    "description": "The lead",
                }
            ]
        }

        with pytest.raises(ValidationError, match="'team' is a required property"):
            TeamsConfig.from_dict(data)

    def test_missing_agents_field(self):
        """Test that missing 'agents' field fails validation."""
        data = {"team": "test-team"}

        with pytest.raises(ValidationError, match="'agents' is a required property"):
            TeamsConfig.from_dict(data)

    def test_empty_agents_list(self):
        """Test that an empty agents list fails validation."""
        data = {"team": "test-team", "agents": []}

        with pytest.raises(ValidationError):
            TeamsConfig.from_dict(data)

    def test_missing_agent_name(self):
        """Test that a missing agent name fails validation."""
        data = {
            "team": "test-team",
            "agents": [
                {
                    "role": "worker",
                    "capabilities": ["coding"],
                    "description": "A worker",
                }
            ],
        }

        with pytest.raises(ValidationError, match="'name' is a required property"):
            TeamsConfig.from_dict(data)

    def test_missing_agent_role(self):
        """Test that a missing agent role fails validation."""
        data = {
            "team": "test-team",
            "agents": [
                {
                    "name": "worker1",
                    "capabilities": ["coding"],
                    "description": "A worker",
                }
            ],
        }

        with pytest.raises(ValidationError, match="'role' is a required property"):
            TeamsConfig.from_dict(data)

    def test_missing_agent_capabilities(self):
        """Test that missing agent capabilities fails validation."""
        data = {
            "team": "test-team",
            "agents": [
                {
                    "name": "worker1",
                    "role": "worker",
                    "description": "A worker",
                }
            ],
        }

        with pytest.raises(ValidationError, match="'capabilities' is a required property"):
            TeamsConfig.from_dict(data)

    def test_missing_agent_description(self):
        """Test that missing agent description fails validation."""
        data = {
            "team": "test-team",
            "agents": [
                {
                    "name": "worker1",
                    "role": "worker",
                    "capabilities": ["coding"],
                }
            ],
        }

        with pytest.raises(ValidationError, match="'description' is a required property"):
            TeamsConfig.from_dict(data)

    def test_invalid_role_value(self):
        """Test that an invalid role value fails validation."""
        data = {
            "team": "test-team",
            "agents": [
                {
                    "name": "worker1",
                    "role": "manager",
                    "capabilities": ["coding"],
                    "description": "A manager",
                }
            ],
        }

        with pytest.raises(ValidationError, match="'manager' is not one of"):
            TeamsConfig.from_dict(data)

    def test_empty_team_name(self):
        """Test that an empty team name fails validation."""
        data = {
            "team": "",
            "agents": [
                {
                    "name": "lead",
                    "role": "coordinator",
                    "capabilities": ["planning"],
                    "description": "The lead",
                }
            ],
        }

        with pytest.raises(ValidationError):
            TeamsConfig.from_dict(data)

    def test_additional_properties_rejected(self):
        """Test that extra properties at the top level are rejected."""
        data = {
            "team": "test-team",
            "extra_field": "not allowed",
            "agents": [
                {
                    "name": "lead",
                    "role": "coordinator",
                    "capabilities": ["planning"],
                    "description": "The lead",
                }
            ],
        }

        with pytest.raises(ValidationError, match="Additional properties"):
            TeamsConfig.from_dict(data)


# =============================================================================
# Semantic Validation
# =============================================================================


class TestSemanticValidation:
    """Tests for semantic validation beyond JSON Schema."""

    def test_duplicate_agent_names(self):
        """Test that duplicate agent names are rejected."""
        data = {
            "team": "test-team",
            "agents": [
                {
                    "name": "worker",
                    "role": "worker",
                    "capabilities": ["coding"],
                    "description": "First worker",
                },
                {
                    "name": "worker",
                    "role": "worker",
                    "capabilities": ["testing"],
                    "description": "Second worker",
                },
            ],
        }

        with pytest.raises(ValueError, match="Duplicate agent name: 'worker'"):
            TeamsConfig.from_dict(data)

    def test_unique_agent_names_pass(self, valid_team_data):
        """Test that unique agent names pass validation."""
        config = TeamsConfig.from_dict(valid_team_data)
        assert config.validate() == []

    def test_validate_returns_all_errors(self):
        """Test that validate() collects all errors, not just the first."""
        config = TeamsConfig(
            team="test-team",
            agents=[
                AgentDefinition(
                    name="dup",
                    role="worker",
                    capabilities=["coding"],
                    description="First",
                ),
                AgentDefinition(
                    name="dup",
                    role="worker",
                    capabilities=["testing"],
                    description="Second",
                ),
                AgentDefinition(
                    name="dup",
                    role="reviewer",
                    capabilities=["review"],
                    description="Third",
                ),
            ],
        )

        errors = config.validate()
        # "dup" appears 3 times, so it's flagged as duplicate on 2nd and 3rd occurrence
        assert len(errors) == 2
        assert all("Duplicate agent name: 'dup'" in e for e in errors)


# =============================================================================
# Agent Lookup
# =============================================================================


class TestAgentLookup:
    """Tests for agent lookup methods."""

    def test_get_agent_by_name_found(self, valid_team_data):
        """Test getting an agent by name when it exists."""
        config = TeamsConfig.from_dict(valid_team_data)

        agent = config.get_agent("lead")
        assert agent is not None
        assert agent.name == "lead"
        assert agent.role == "coordinator"

    def test_get_agent_by_name_not_found(self, valid_team_data):
        """Test getting an agent by name when it does not exist."""
        config = TeamsConfig.from_dict(valid_team_data)

        agent = config.get_agent("nonexistent")
        assert agent is None

    def test_get_agents_with_capability_found(self, valid_team_data):
        """Test filtering agents by capability."""
        config = TeamsConfig.from_dict(valid_team_data)

        agents = config.get_agents_with_capability("review")
        assert len(agents) == 2
        names = {a.name for a in agents}
        assert names == {"lead", "reviewer"}

    def test_get_agents_with_capability_none_found(self, valid_team_data):
        """Test filtering by a capability no agent has."""
        config = TeamsConfig.from_dict(valid_team_data)

        agents = config.get_agents_with_capability("deployment")
        assert agents == []

    def test_get_agents_with_capability_single_match(self, valid_team_data):
        """Test filtering by a capability only one agent has."""
        config = TeamsConfig.from_dict(valid_team_data)

        agents = config.get_agents_with_capability("coding")
        assert len(agents) == 1
        assert agents[0].name == "implementer"

    def test_get_agents_with_capability_security_analysis(self, valid_team_data):
        """Test filtering by security-analysis capability."""
        config = TeamsConfig.from_dict(valid_team_data)

        agents = config.get_agents_with_capability("security-analysis")
        assert len(agents) == 1
        assert agents[0].name == "reviewer"


# =============================================================================
# Global Singleton
# =============================================================================


class TestGlobalSingleton:
    """Tests for the global teams config singleton."""

    def test_get_teams_config_loads_from_file(self, valid_team_yaml):
        """Test that get_teams_config loads from a file path."""
        config = get_teams_config(valid_team_yaml)

        assert config.team == "test-team"
        assert len(config.agents) == 3

    def test_get_teams_config_returns_same_instance(self, valid_team_yaml):
        """Test that get_teams_config returns the same instance on repeated calls."""
        config1 = get_teams_config(valid_team_yaml)
        config2 = get_teams_config()

        assert config1 is config2

    def test_reset_teams_config(self, valid_team_yaml):
        """Test that reset_teams_config clears the singleton."""
        config1 = get_teams_config(valid_team_yaml)
        reset_teams_config()
        config2 = get_teams_config(valid_team_yaml)

        assert config1 is not config2
        assert config1.team == config2.team


# =============================================================================
# AgentDefinition Dataclass
# =============================================================================


class TestAgentDefinition:
    """Tests for the AgentDefinition dataclass."""

    def test_agent_definition_fields(self):
        """Test that AgentDefinition stores all fields correctly."""
        agent = AgentDefinition(
            name="test-agent",
            role="worker",
            capabilities=["coding", "testing"],
            description="A test agent",
        )

        assert agent.name == "test-agent"
        assert agent.role == "worker"
        assert agent.capabilities == ["coding", "testing"]
        assert agent.description == "A test agent"

    def test_agent_definition_equality(self):
        """Test that AgentDefinition supports equality comparison."""
        agent1 = AgentDefinition(
            name="agent",
            role="worker",
            capabilities=["coding"],
            description="An agent",
        )
        agent2 = AgentDefinition(
            name="agent",
            role="worker",
            capabilities=["coding"],
            description="An agent",
        )

        assert agent1 == agent2
