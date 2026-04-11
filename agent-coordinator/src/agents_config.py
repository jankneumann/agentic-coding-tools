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
# Archetype name pattern (shared between schema and runtime validation)
# ---------------------------------------------------------------------------

ARCHETYPE_NAME_PATTERN = r"^[a-z][a-z0-9_-]{0,31}$"

# ---------------------------------------------------------------------------
# JSON Schema for archetypes.yaml validation
# ---------------------------------------------------------------------------

ARCHETYPES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["schema_version", "archetypes"],
    "properties": {
        "schema_version": {"type": "integer", "const": 1},
        "archetypes": {
            "type": "object",
            "minProperties": 1,
            "propertyNames": {
                "type": "string",
                "pattern": ARCHETYPE_NAME_PATTERN,
            },
            "additionalProperties": {
                "type": "object",
                "required": ["model", "system_prompt"],
                "properties": {
                    "model": {
                        "type": "string",
                        "enum": ["opus", "sonnet", "haiku"],
                    },
                    "system_prompt": {"type": "string"},
                    "escalation": {
                        "type": ["object", "null"],
                        "properties": {
                            "escalate_to": {
                                "type": "string",
                                "enum": ["opus", "sonnet", "haiku"],
                            },
                            "max_write_dirs": {
                                "type": "integer",
                                "minimum": 1,
                            },
                            "max_dependencies": {
                                "type": "integer",
                                "minimum": 1,
                            },
                            "loc_threshold": {
                                "type": "integer",
                                "minimum": 1,
                            },
                        },
                        "required": ["escalate_to"],
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
                    "archetypes": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": ARCHETYPE_NAME_PATTERN,
                        },
                    },
                    "sdk": {
                        "type": "object",
                        "required": ["package", "model"],
                        "properties": {
                            "package": {"type": "string", "minLength": 1},
                            "method": {"type": "string", "minLength": 1},
                            "model": {"type": "string", "minLength": 1},
                            "model_fallbacks": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "api_key_env": {"type": "string", "minLength": 1},
                            "max_tokens": {"type": "integer", "minimum": 1},
                        },
                        "additionalProperties": False,
                    },
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
                                        "async": {"type": "boolean"},
                                        "poll": {
                                            "type": "object",
                                            "required": [
                                                "command_template",
                                                "task_id_pattern",
                                                "success_pattern",
                                            ],
                                            "properties": {
                                                "command_template": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                                "task_id_pattern": {"type": "string"},
                                                "success_pattern": {"type": "string"},
                                                "failure_pattern": {"type": "string"},
                                                "interval_seconds": {"type": "integer"},
                                                "timeout_seconds": {"type": "integer"},
                                            },
                                            "additionalProperties": False,
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
                            "prompt_via_stdin": {"type": "boolean"},
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
class PollConfig:
    """Polling configuration for async dispatch modes.

    The dispatcher extracts a task ID from the dispatch command's output
    using ``task_id_pattern``, substitutes it into ``command_template``,
    and polls until ``success_pattern`` or ``failure_pattern`` matches
    or ``timeout_seconds`` is reached.
    """

    command_template: list[str]
    task_id_pattern: str
    success_pattern: str
    failure_pattern: str = "failed|error"
    interval_seconds: int = 30
    timeout_seconds: int = 600


@dataclass
class ModeConfig:
    """CLI args for a single dispatch mode."""

    args: list[str]
    async_dispatch: bool = False
    poll: PollConfig | None = None


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
    prompt_via_stdin: bool = False


@dataclass
class SdkConfig:
    """SDK dispatch configuration for an agent.

    Parsed from the optional ``sdk`` section of an agent entry in
    ``agents.yaml``.  Enables direct API dispatch via vendor Python SDKs
    as a fallback when the vendor's CLI is not installed.
    """

    package: str
    model: str
    method: str = "messages.create"
    model_fallbacks: list[str] = field(default_factory=list)
    api_key_env: str = ""
    max_tokens: int = 16384


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
    archetypes: list[str] = field(default_factory=list)
    cli: CliConfig | None = None
    sdk: SdkConfig | None = None


# ---------------------------------------------------------------------------
# Archetype data classes
# ---------------------------------------------------------------------------

@dataclass
class EscalationConfig:
    """Complexity-based escalation rules for an archetype.

    All thresholds are configurable in ``archetypes.yaml`` — no
    hardcoded values.  See design decision D1.
    """

    escalate_to: str
    max_write_dirs: int | None = None
    max_dependencies: int | None = None
    loc_threshold: int | None = None


@dataclass
class ArchetypeConfig:
    """A named agent archetype from ``archetypes.yaml``.

    Bundles model preference, system prompt, and optional complexity
    escalation rules.
    """

    name: str
    model: str
    system_prompt: str
    escalation: EscalationConfig | None = None


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
            def _parse_mode(mode_data: dict[str, Any]) -> ModeConfig:
                poll_config: PollConfig | None = None
                raw_poll = mode_data.get("poll")
                if raw_poll:
                    poll_config = PollConfig(
                        command_template=raw_poll["command_template"],
                        task_id_pattern=raw_poll["task_id_pattern"],
                        success_pattern=raw_poll["success_pattern"],
                        failure_pattern=raw_poll.get(
                            "failure_pattern", "failed|error",
                        ),
                        interval_seconds=raw_poll.get(
                            "interval_seconds", 30,
                        ),
                        timeout_seconds=raw_poll.get(
                            "timeout_seconds", 600,
                        ),
                    )
                return ModeConfig(
                    args=mode_data["args"],
                    async_dispatch=mode_data.get("async", False),
                    poll=poll_config,
                )

            cli_config = CliConfig(
                command=raw_cli["command"],
                dispatch_modes={
                    mode_name: _parse_mode(mode_data)
                    for mode_name, mode_data in raw_cli["dispatch_modes"].items()
                },
                model_flag=raw_cli["model_flag"],
                model=raw_cli.get("model"),
                model_fallbacks=raw_cli.get("model_fallbacks", []),
                prompt_via_stdin=raw_cli.get("prompt_via_stdin", False),
            )

        sdk_config: SdkConfig | None = None
        raw_sdk = agent_data.get("sdk")
        if raw_sdk:
            sdk_config = SdkConfig(
                package=raw_sdk["package"],
                model=raw_sdk["model"],
                method=raw_sdk.get("method", "messages.create"),
                model_fallbacks=raw_sdk.get("model_fallbacks", []),
                api_key_env=raw_sdk.get("api_key_env", ""),
                max_tokens=raw_sdk.get("max_tokens", 16384),
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
                archetypes=agent_data.get("archetypes", []),
                api_key=resolved_key,
                openbao_role_id=agent_data.get("openbao_role_id"),
                cli=cli_config,
                sdk=sdk_config,
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
# Dispatch config helpers
# ---------------------------------------------------------------------------

def get_dispatch_configs(
    agents: list[AgentEntry] | None = None,
) -> dict[str, Any]:
    """Return dispatch configs for agents with a ``cli`` or ``sdk`` section.

    Shared serialization logic used by both MCP and HTTP endpoints.
    Returns a dict with ``agents`` key containing a list of agent
    dispatch config dicts.
    """
    if agents is None:
        agents = get_agents_config()

    agents_out: list[dict[str, Any]] = []
    for entry in agents:
        if entry.cli is None and entry.sdk is None:
            continue
        sdk_out: dict[str, Any] | None = None
        if entry.sdk:
            sdk_out = {
                "package": entry.sdk.package,
                "model": entry.sdk.model,
                "method": entry.sdk.method,
                "model_fallbacks": entry.sdk.model_fallbacks,
                "api_key_env": entry.sdk.api_key_env,
                "max_tokens": entry.sdk.max_tokens,
            }
        cli_out: dict[str, Any] | None = None
        if entry.cli:
            cli_out = {
                "command": entry.cli.command,
                "dispatch_modes": {
                    name: {
                        "args": mc.args,
                        "async": mc.async_dispatch,
                        **({"poll": {
                            "command_template": mc.poll.command_template,
                            "task_id_pattern": mc.poll.task_id_pattern,
                            "success_pattern": mc.poll.success_pattern,
                            "failure_pattern": mc.poll.failure_pattern,
                            "interval_seconds": mc.poll.interval_seconds,
                            "timeout_seconds": mc.poll.timeout_seconds,
                        }} if mc.poll else {}),
                    }
                    for name, mc in entry.cli.dispatch_modes.items()
                },
                "model_flag": entry.cli.model_flag,
                "model": entry.cli.model,
                "model_fallbacks": entry.cli.model_fallbacks,
                "prompt_via_stdin": entry.cli.prompt_via_stdin,
            }
        agents_out.append({
            "agent_id": entry.name,
            "type": entry.type,
            "transport": entry.transport,
            "openbao_role_id": entry.openbao_role_id,
            "cli": cli_out,
            "sdk": sdk_out,
        })

    return {"agents": agents_out}


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


# ---------------------------------------------------------------------------
# Archetype loading + helpers
# ---------------------------------------------------------------------------

def _default_archetypes_path() -> Path:
    return Path(__file__).resolve().parent.parent / "archetypes.yaml"


def load_archetypes_config(
    path: Path | None = None,
) -> dict[str, ArchetypeConfig]:
    """Load and validate ``archetypes.yaml``.

    Returns a dict mapping archetype names to :class:`ArchetypeConfig`.
    Uses the global cache — subsequent calls return the same dict.

    If the file does not exist, returns an empty dict and logs a warning
    (design decision D5: graceful degradation).
    """
    global _archetypes
    if _archetypes is not None:
        return _archetypes

    if path is None:
        path = _default_archetypes_path()

    if not path.exists():
        logger.warning("archetypes.yaml not found at %s — falling back to ambient model", path)
        _archetypes = {}
        return _archetypes

    with open(path) as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        raise ValueError("Empty archetypes.yaml file")

    validate(instance=raw, schema=ARCHETYPES_SCHEMA)

    result: dict[str, ArchetypeConfig] = {}
    for name, data in raw["archetypes"].items():
        esc_config: EscalationConfig | None = None
        raw_esc = data.get("escalation")
        if raw_esc:
            esc_config = EscalationConfig(
                escalate_to=raw_esc["escalate_to"],
                max_write_dirs=raw_esc.get("max_write_dirs"),
                max_dependencies=raw_esc.get("max_dependencies"),
                loc_threshold=raw_esc.get("loc_threshold"),
            )
        result[name] = ArchetypeConfig(
            name=name,
            model=data["model"],
            system_prompt=data["system_prompt"],
            escalation=esc_config,
        )

    _archetypes = result
    return _archetypes


_archetypes: dict[str, ArchetypeConfig] | None = None


def get_archetype(name: str) -> ArchetypeConfig | None:
    """Look up an archetype by name from the cached config.

    Returns ``None`` if the archetype is unknown or config hasn't been loaded.
    """
    if _archetypes is None:
        logger.warning("Archetypes not loaded — call load_archetypes_config() first")
        return None
    archetype = _archetypes.get(name)
    if archetype is None:
        logger.warning("Unknown archetype '%s' — falling back to ambient model", name)
    return archetype


def reset_archetypes_config() -> None:
    """Reset the global archetypes config cache (for testing)."""
    global _archetypes
    _archetypes = None


# ---------------------------------------------------------------------------
# Prompt composition (D2: composition, not replacement)
# ---------------------------------------------------------------------------

def compose_prompt(archetype: ArchetypeConfig, task_prompt: str) -> str:
    """Compose an archetype's system prompt with a task-specific prompt.

    Prepends the archetype system prompt with a ``---`` separator, per
    design decision D2.  If the archetype has no system prompt, returns
    the task prompt unchanged.
    """
    if not archetype.system_prompt:
        return task_prompt
    return f"{archetype.system_prompt}\n\n---\n\n{task_prompt}"


# ---------------------------------------------------------------------------
# Complexity-based escalation (D3: at dispatch time)
# ---------------------------------------------------------------------------

def _unique_dir_prefixes(write_allow: list[str]) -> int:
    """Count unique directory prefixes in write_allow globs.

    Extracts the directory portion of each glob (stripping wildcards
    and filenames) and counts distinct paths.  For example,
    ``["src/api/**", "src/models/**", "tests/**"]`` yields 3 prefixes.
    """
    dirs: set[str] = set()
    for glob_pattern in write_allow:
        path = glob_pattern.replace("\\", "/")
        # Strip trailing wildcards and filename patterns
        parts = path.split("/")
        # Keep only directory-like components (no wildcards)
        dir_parts = [p for p in parts if "*" not in p and "?" not in p]
        if dir_parts:
            dirs.add("/".join(dir_parts))
    return len(dirs)


def resolve_model(
    archetype: ArchetypeConfig,
    package_metadata: dict[str, Any],
    *,
    return_reasons: bool = False,
) -> str | tuple[str, list[str]]:
    """Resolve the effective model for a work package.

    Checks escalation rules from the archetype config against package
    metadata.  All thresholds come from ``archetypes.yaml`` — no
    hardcoded values (design decision D1).

    Args:
        archetype: The archetype configuration.
        package_metadata: Dict with optional keys: ``write_allow``,
            ``dependencies``, ``loc_estimate``, ``complexity``.
        return_reasons: If True, return a tuple of (model, reasons).

    Returns:
        The resolved model string, or (model, reasons) if *return_reasons*.
    """
    if not archetype.escalation:
        return (archetype.model, []) if return_reasons else archetype.model

    rules = archetype.escalation
    reasons: list[str] = []

    write_allow = package_metadata.get("write_allow", [])
    if rules.max_write_dirs and _unique_dir_prefixes(write_allow) > rules.max_write_dirs:
        reasons.append(f"write_allow spans >{rules.max_write_dirs} directories")

    dependencies = package_metadata.get("dependencies", [])
    if rules.max_dependencies and len(dependencies) > rules.max_dependencies:
        reasons.append(f"depends on >{rules.max_dependencies} packages")

    loc_estimate = package_metadata.get("loc_estimate", 0) or 0
    if rules.loc_threshold and loc_estimate > rules.loc_threshold:
        reasons.append(f"loc_estimate >{rules.loc_threshold}")

    if package_metadata.get("complexity") == "high":
        reasons.append("explicit complexity: high flag")

    if reasons:
        escalated_model = rules.escalate_to
        logger.info(
            "Escalating %s to %s: %s",
            archetype.name, escalated_model, ", ".join(reasons),
        )
        return (escalated_model, reasons) if return_reasons else escalated_model

    return (archetype.model, []) if return_reasons else archetype.model
