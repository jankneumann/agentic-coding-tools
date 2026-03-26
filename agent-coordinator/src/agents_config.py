"""Declarative agent configuration from ``agents.yaml``.

Loads agent definitions, validates against a JSON schema (following
``teams.py`` patterns), and provides helpers for API key identity
generation and MCP environment variable generation.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import validate

from src.profile_loader import _INTERPOLATION_RE, _load_secrets_file, interpolate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON Schema for agents.yaml validation
# ---------------------------------------------------------------------------

VALID_TRANSPORTS = {"mcp", "http"}
VALID_ISOLATION_MODES = {"worktree", "sandbox", "none"}
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
                    "isolation": {
                        "type": "string",
                        "enum": sorted(VALID_ISOLATION_MODES),
                    },
                    "api_key": {"type": "string"},
                    "openbao_role_id": {"type": "string", "minLength": 1},
                    "capabilities": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "string",
                            "enum": sorted(VALID_CAPABILITIES),
                        },
                    },
                    "description": {"type": "string", "minLength": 1},
                    "cli": {
                        "type": "object",
                        "required": ["command", "dispatch_modes", "model_flag"],
                        "properties": {
                            "command": {"type": "string", "minLength": 1},
                            "dispatch_modes": {
                                "type": "object",
                                "minProperties": 1,
                                "additionalProperties": {
                                    "type": "object",
                                    "required": ["args"],
                                    "properties": {
                                        "args": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "minItems": 1,
                                        },
                                    },
                                    "additionalProperties": False,
                                },
                            },
                            "model_flag": {"type": "string", "minLength": 1},
                            "model": {"type": ["string", "null"]},
                            "model_fallbacks": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "additionalProperties": False,
                    },
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
class ModeConfig:
    """CLI args for a single dispatch mode."""

    args: list[str]


@dataclass
class CliConfig:
    """CLI dispatch configuration for an agent.

    Parsed from the ``cli`` section of an agent entry in ``agents.yaml``.
    """

    command: str
    dispatch_modes: dict[str, ModeConfig]
    model_flag: str
    model: str | None = None
    model_fallbacks: list[str] = field(default_factory=list)


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
    isolation: str = "none"
    api_key: str | None = None
    openbao_role_id: str | None = None
    cli: CliConfig | None = None


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

    secrets = _load_secrets_file(secrets_path)
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
            # Keep unresolved ${VAR} placeholders so that
            # _resolve_api_key_from_openbao() can extract the variable
            # name and fetch the secret from OpenBao at runtime.

        cli_config: CliConfig | None = None
        raw_cli = agent_data.get("cli")
        if raw_cli:
            cli_config = CliConfig(
                command=raw_cli["command"],
                dispatch_modes={
                    mode_name: ModeConfig(args=mode_data["args"])
                    for mode_name, mode_data in raw_cli["dispatch_modes"].items()
                },
                model_flag=raw_cli["model_flag"],
                model=raw_cli.get("model"),
                model_fallbacks=raw_cli.get("model_fallbacks", []),
            )

        entries.append(
            AgentEntry(
                name=name,
                type=agent_data["type"],
                profile=agent_data["profile"],
                trust_level=agent_data["trust_level"],
                transport=agent_data["transport"],
                capabilities=agent_data["capabilities"],
                description=agent_data["description"],
                isolation=agent_data.get("isolation", "none"),
                api_key=resolved_key,
                openbao_role_id=agent_data.get("openbao_role_id"),
                cli=cli_config,
            )
        )

    return entries


# ---------------------------------------------------------------------------
# API key identity generation
# ---------------------------------------------------------------------------

def _resolve_api_key_from_openbao(agent: AgentEntry) -> str | None:
    """Resolve an agent's API key from OpenBao using its AppRole.

    When the agent has an ``openbao_role_id`` and OpenBao is enabled,
    authenticates with the agent's AppRole and reads secrets. Falls back
    to the coordinator's shared token when no per-agent role is configured.
    """
    from src.config import OpenBaoConfig

    bao_config = OpenBaoConfig.from_env()
    if not bao_config.is_enabled():
        return None

    if not agent.openbao_role_id:
        # Use shared coordinator secrets — api_key already resolved from shared pool
        return agent.api_key

    try:
        import hvac

        # Authenticate with the agent's own AppRole, not the global coordinator token.
        # The agent's secret_id is expected in BAO_SECRET_ID (shared bootstrap secret)
        # while the role_id comes from the per-agent openbao_role_id field.
        client = hvac.Client(url=bao_config.addr, timeout=bao_config.timeout)
        client.auth.approle.login(
            role_id=agent.openbao_role_id,
            secret_id=bao_config.secret_id,
        )
        response = client.secrets.kv.v2.read_secret_version(
            path=bao_config.secret_path,
            mount_point=bao_config.mount_path,
        )
        data = response.get("data", {}).get("data", {})
        # Look for agent-specific key pattern or the interpolation source
        raw_key = agent.api_key
        if raw_key and _INTERPOLATION_RE.search(raw_key):
            var_name = _INTERPOLATION_RE.search(raw_key).group(1)  # type: ignore[union-attr]
            resolved = data.get(var_name)
            if isinstance(resolved, str) and resolved:
                return resolved
        return agent.api_key
    except Exception:  # noqa: BLE001
        logger.warning(
            "Failed to resolve API key from OpenBao for agent '%s' — "
            "falling back to static resolution",
            agent.name,
            exc_info=True,
        )
        return agent.api_key


def get_api_key_identities(
    agents: list[AgentEntry] | None = None,
) -> dict[str, dict[str, str]]:
    """Generate ``COORDINATION_API_KEY_IDENTITIES`` from HTTP agents.

    When OpenBao is enabled, attempts to resolve API keys from OpenBao
    for agents with ``openbao_role_id``. Falls back to static interpolation.

    Returns:
        Dict mapping resolved API key values to
        ``{"agent_id": ..., "agent_type": ...}``.
    """
    if agents is None:
        agents = load_agents_config()

    # Check if OpenBao is available for key resolution
    openbao_enabled = bool(os.environ.get("BAO_ADDR"))

    identities: dict[str, dict[str, str]] = {}
    for agent in agents:
        if agent.transport != "http":
            continue

        key = agent.api_key
        if openbao_enabled and agent.openbao_role_id:
            resolved = _resolve_api_key_from_openbao(agent)
            if resolved:
                key = resolved

        if not key:
            continue

        # Skip unresolved ${VAR} placeholders — they're not usable as
        # identity keys unless resolved via OpenBao above.
        if _INTERPOLATION_RE.search(key):
            continue

        if key in identities:
            existing = identities[key]["agent_id"]
            logger.warning(
                "Duplicate API key: agents '%s' and '%s' share the same key — "
                "'%s' will be used",
                existing,
                agent.name,
                agent.name,
            )
        identities[key] = {
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


# ---------------------------------------------------------------------------
# Isolation helpers
# ---------------------------------------------------------------------------

def get_agent_isolation(agent_type: str) -> str | None:
    """Return the isolation mode for *agent_type*, or ``None`` if not found.

    Searches through loaded agent entries and returns the ``isolation``
    field of the first agent whose ``type`` matches *agent_type*.
    """
    for agent in get_agents_config():
        if agent.type == agent_type:
            return agent.isolation
    return None
