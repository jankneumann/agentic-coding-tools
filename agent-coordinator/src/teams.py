"""Declarative team composition for Agent Coordinator.

Loads team definitions from YAML files, validates them against a JSON Schema,
and provides query methods for agent lookup by name or capability.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import validate

# Valid agent roles
VALID_ROLES = {"coordinator", "worker", "reviewer"}

# JSON Schema for team definition validation
TEAMS_SCHEMA = {
    "$schema": "https://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["team", "agents"],
    "properties": {
        "team": {"type": "string", "minLength": 1},
        "agents": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "role", "capabilities", "description"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "role": {"type": "string", "enum": list(VALID_ROLES)},
                    "capabilities": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "description": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


@dataclass
class AgentDefinition:
    """Definition of an agent within a team."""

    name: str
    role: str
    capabilities: list[str]
    description: str


@dataclass
class TeamsConfig:
    """Team composition configuration.

    Loads team definitions from YAML, validates structure and semantics,
    and provides lookup methods for agents.
    """

    team: str
    agents: list[AgentDefinition]

    @classmethod
    def from_file(cls, path: Path) -> "TeamsConfig":
        """Load and validate from a YAML file.

        Args:
            path: Path to the YAML team definition file.

        Returns:
            A validated TeamsConfig instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the file is not valid YAML.
            jsonschema.ValidationError: If the data fails schema validation.
            ValueError: If semantic validation fails (e.g. duplicate agent names).
        """
        with open(path) as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ValueError("Empty YAML file")

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "TeamsConfig":
        """Create from a dictionary (after validation).

        Args:
            data: Dictionary matching the TEAMS_SCHEMA structure.

        Returns:
            A validated TeamsConfig instance.

        Raises:
            jsonschema.ValidationError: If the data fails schema validation.
            ValueError: If semantic validation fails (e.g. duplicate agent names).
        """
        # Schema validation
        validate(instance=data, schema=TEAMS_SCHEMA)

        # Build the config
        agents = [
            AgentDefinition(
                name=agent_data["name"],
                role=agent_data["role"],
                capabilities=agent_data["capabilities"],
                description=agent_data["description"],
            )
            for agent_data in data["agents"]
        ]

        config = cls(team=data["team"], agents=agents)

        # Semantic validation
        errors = config.validate()
        if errors:
            raise ValueError(f"Team config validation failed: {'; '.join(errors)}")

        return config

    def get_agent(self, name: str) -> AgentDefinition | None:
        """Get agent definition by name.

        Args:
            name: The agent name to look up.

        Returns:
            The AgentDefinition if found, None otherwise.
        """
        for agent in self.agents:
            if agent.name == name:
                return agent
        return None

    def get_agents_with_capability(self, capability: str) -> list[AgentDefinition]:
        """Get agents that have a specific capability.

        Args:
            capability: The capability to filter by.

        Returns:
            List of agents that have the specified capability.
        """
        return [agent for agent in self.agents if capability in agent.capabilities]

    def validate(self) -> list[str]:
        """Validate the config, returning list of error messages.

        Checks semantic constraints that JSON Schema cannot express,
        such as agent name uniqueness within the team.

        Returns:
            List of error message strings. Empty if valid.
        """
        errors: list[str] = []

        # Check for duplicate agent names
        names = [agent.name for agent in self.agents]
        seen: set[str] = set()
        for name in names:
            if name in seen:
                errors.append(f"Duplicate agent name: '{name}'")
            seen.add(name)

        return errors


# Global config instance
_teams_config: TeamsConfig | None = None


def get_teams_config(path: Path | None = None) -> TeamsConfig:
    """Get the global teams configuration.

    Loads from the specified path on first call, or from `teams.yaml`
    in the agent-coordinator directory if no path is given.

    Args:
        path: Optional path to the teams YAML file.

    Returns:
        The global TeamsConfig instance.
    """
    global _teams_config
    if _teams_config is None:
        if path is None:
            path = Path(__file__).parent.parent / "teams.yaml"
        _teams_config = TeamsConfig.from_file(path)
    return _teams_config


def reset_teams_config() -> None:
    """Reset the global teams config. Useful for testing."""
    global _teams_config
    _teams_config = None
