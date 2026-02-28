"""Declarative agent configuration from ``agents.yaml``.

Loads agent definitions, validates against a JSON schema (following
``teams.py`` patterns), and provides helpers for API key identity
generation and MCP environment variable generation.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import validate

from src.profile_loader import _load_secrets, interpolate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON Schema for agents.yaml validation
# ---------------------------------------------------------------------------

VALID_TRANSPORTS = {"mcp", "http"}
VALID_CAPABILITIES = {
    "lock", "queue", "memory", "guardrails", "handoff", "discover", "audit",
}

AGENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["agents"],
    "properties": {
        "agents": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {
                "type": "object",
                "required": [
                    "type", "profile", "trust_level", "transport",
                    "capabilities", "description",
                ],
                "properties": {
                    "type": {"type": "string", "minLength": 1},
                    "profile": {"type": "string", "minLength": 1},
                    "trust_level": {"type": "integer", "minimum": 1, "maximum": 5},
                    "transport": {"type": "string", "enum": list(VALID_TRANSPORTS)},
                    "api_key": {"type": "string"},
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


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AgentEntry:
    """A single agent definition from ``agents.yaml``."""

    name: str
    type: str
    profile: str
    trust_level: int
    transport: str
    capabilities: list[str]
    description: str
    api_key: str | None = None


# ---------------------------------------------------------------------------
# Loading + validation
# ---------------------------------------------------------------------------

def _default_agents_path() -> Path:
    return Path(__file__).resolve().parent.parent / "agents.yaml"


def _default_secrets_path() -> Path:
    return Path(__file__).resolve().parent.parent / ".secrets.yaml"


def load_agents_config(
    path: Path | None = None,
    *,
    secrets_path: Path | None = None,
) -> list[AgentEntry]:
    """Load and validate ``agents.yaml``.

    Args:
        path: Path to agents YAML file.
        secrets_path: Path to ``.secrets.yaml`` for ``${VAR}`` interpolation
            in ``api_key`` fields.

    Returns:
        List of validated :class:`AgentEntry` objects.

    Raises:
        FileNotFoundError: If *path* does not exist.
        jsonschema.ValidationError: If the data fails schema validation.
        ValueError: On duplicate agent names.
    """
    if path is None:
        path = _default_agents_path()
    if secrets_path is None:
        secrets_path = _default_secrets_path()

    with open(path) as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        raise ValueError("Empty agents.yaml file")

    validate(instance=raw, schema=AGENTS_SCHEMA)

    secrets = _load_secrets(secrets_path)
    entries: list[AgentEntry] = []
    seen_names: set[str] = set()

    for name, agent_data in raw["agents"].items():
        if name in seen_names:
            raise ValueError(f"Duplicate agent name: '{name}'")
        seen_names.add(name)

        raw_key = agent_data.get("api_key")
        resolved_key: str | None = None
        if raw_key:
            resolved_key = interpolate(raw_key, secrets)
            # If interpolation left the ${VAR} literal, treat as unresolved.
            if resolved_key.startswith("${"):
                resolved_key = None

        entries.append(
            AgentEntry(
                name=name,
                type=agent_data["type"],
                profile=agent_data["profile"],
                trust_level=agent_data["trust_level"],
                transport=agent_data["transport"],
                capabilities=agent_data["capabilities"],
                description=agent_data["description"],
                api_key=resolved_key,
            )
        )

    return entries


# ---------------------------------------------------------------------------
# API key identity generation
# ---------------------------------------------------------------------------

def get_api_key_identities(
    agents: list[AgentEntry] | None = None,
) -> dict[str, dict[str, str]]:
    """Generate ``COORDINATION_API_KEY_IDENTITIES`` from HTTP agents.

    Returns:
        Dict mapping resolved API key values to
        ``{"agent_id": ..., "agent_type": ...}``.
    """
    if agents is None:
        agents = load_agents_config()

    identities: dict[str, dict[str, str]] = {}
    for agent in agents:
        if agent.transport == "http" and agent.api_key:
            identities[agent.api_key] = {
                "agent_id": agent.name,
                "agent_type": agent.type,
            }
    return identities


# ---------------------------------------------------------------------------
# MCP environment generation
# ---------------------------------------------------------------------------

def get_mcp_env(
    agent_id: str,
    agents: list[AgentEntry] | None = None,
) -> dict[str, str]:
    """Generate env vars for MCP server registration of *agent_id*.

    Returns:
        Dict of environment variables (``AGENT_ID``, ``AGENT_TYPE``, and
        database settings from the current environment).
    """
    if agents is None:
        agents = load_agents_config()

    agent = next((a for a in agents if a.name == agent_id), None)
    if agent is None:
        raise ValueError(f"Agent '{agent_id}' not found in agents.yaml")

    env: dict[str, str] = {
        "AGENT_ID": agent.name,
        "AGENT_TYPE": agent.type,
    }

    # Include database connection settings from the current environment.
    for key in ("DB_BACKEND", "POSTGRES_DSN", "POSTGRES_POOL_MIN", "POSTGRES_POOL_MAX"):
        val = os.environ.get(key)
        if val:
            env[key] = val

    return env


# ---------------------------------------------------------------------------
# Global config singleton (lazy)
# ---------------------------------------------------------------------------

_agents: list[AgentEntry] | None = None


def get_agents_config(path: Path | None = None) -> list[AgentEntry]:
    """Get the global agents configuration (lazy-loaded).

    Returns an empty list when ``agents.yaml`` does not exist (graceful
    fallback to env-var-based identity).
    """
    global _agents
    if _agents is None:
        try:
            _agents = load_agents_config(path)
        except FileNotFoundError:
            logger.debug("agents.yaml not found — falling back to env-var identity")
            _agents = []
    return _agents


def get_agent_config(agent_id: str) -> AgentEntry | None:
    """Look up a single agent by name."""
    for agent in get_agents_config():
        if agent.name == agent_id:
            return agent
    return None


def reset_agents_config() -> None:
    """Reset the global agents config (for testing)."""
    global _agents
    _agents = None
