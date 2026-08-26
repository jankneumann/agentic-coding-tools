"""Declarative agent configuration from ``agents.yaml``.

Loads agent definitions, validates against a JSON schema (following
``teams.py`` patterns), and provides helpers for API key identity
generation and MCP environment variable generation.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from jsonschema import validate

from src.profile_loader import _INTERPOLATION_RE, _load_secrets_file, interpolate
from src.trust_levels import MAX_TRUST, MIN_TRUST, TrustLevel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.audit import AuditService
    from src.db import DatabaseClient

logger = logging.getLogger(__name__)

# Provider-specific model map. Archetypes can continue to use legacy Claude
# aliases or logical tiers; dispatch resolves them against this map only when a
# provider is selected.
MODEL_TIERS: tuple[str, ...] = ("premium", "standard", "economy")
# Optional tiers a provider MAY define. Resolution falls back to "premium"
# when a provider has no mapping for an optional tier, so archetypes can
# request frontier-class reasoning without every provider carrying one.
OPTIONAL_MODEL_TIERS: tuple[str, ...] = ("frontier",)
ALL_MODEL_TIERS: tuple[str, ...] = OPTIONAL_MODEL_TIERS + MODEL_TIERS
LEGACY_CLAUDE_ALIAS_TO_TIER: dict[str, str] = {
    "opus": "premium",
    "sonnet": "standard",
    "haiku": "economy",
}

# ---------------------------------------------------------------------------
# `local` provider (OpenSpec change add-local-model-provider-tier)
#
# The always-on host is bandwidth-bound, not capacity-bound, so its roster is
# selected by ARCHITECTURE (small-active-parameter MoE) rather than by what
# fits in memory. Roster entries rotate; the two rules below do not, which is
# why they live in code and are enforced at startup instead of in comments.
# ---------------------------------------------------------------------------
LOCAL_PROVIDER = "local"
# Tiers the local roster MUST define. Everything else degrades to the best
# tier it does define (agent-archetypes: "Local roster omits a tier").
LOCAL_REQUIRED_TIERS: tuple[str, ...] = ("standard", "economy")
# Archetypes whose output is cheap to discard or verified downstream. This is
# an allowlist, not a denylist: an archetype absent from it (architect,
# reviewer, gatekeeper, implementer, ...) MUST NOT resolve to `local` (D3).
LOCAL_TRUSTED_ARCHETYPES: frozenset[str] = frozenset({
    "runner",
    "analyst",
    "documenter",
    "validator",
})
# Host-class defaults used when archetypes.yaml omits `local_host_class`.
# GB10 (128 GB unified LPDDR5x @ ~273 GB/s): decode throughput tracks ACTIVE
# parameters, so a 30B-total/3B-active MoE runs ~9x faster than a dense 32B.
DEFAULT_LOCAL_HOST_CLASS: dict[str, Any] = {
    "name": "gb10",
    "active_params_ceiling_b": 12,
    "dense_params_limit_b": 30,
}
_REVIEWED_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Tier entries are either a bare model-id string or {"model": ..., "thinking": ...}.
# Thinking level is part of the model definition, not a dispatch afterthought:
# it shifts both cost and capability enough that a standard model at xhigh
# thinking can out-cost a premium model at medium. Cost-per-successful-task
# tuning happens by editing these entries — never by editing tests, which must
# derive expectations from this map / archetypes.yaml rather than literals.
DEFAULT_PROVIDER_MODEL_MAP: dict[str, Any] = {
    "schema_version": 2,
    "tiers": list(ALL_MODEL_TIERS),
    "providers": {
        "claude_code": {
            "frontier": "fable",
            "premium": "opus",
            "standard": "sonnet",
            "economy": "haiku",
        },
        "codex": {
            "frontier": {"model": "gpt-5.6-sol", "thinking": "xhigh"},
            "premium": {"model": "gpt-5.6-sol", "thinking": "medium"},
            "standard": "gpt-5.6-terra",
            "economy": "gpt-5.6-luna",
        },
        # Roster per contracts/roster.md; tier slugs resolved empirically in
        # Phase 1 (design.md § Empirical CLI findings, E1/E5/E8) and signed off
        # by the operator at checkpoint 1.4 (2026-07-23).
        "antigravity": {
            # agy `models` catalog (E1); one model across three effort levels.
            # Effort is baked into the slug suffix, not a separate flag.
            # `frontier` omitted — falls back to premium (operator, 2026-07-23).
            "premium": "gemini-3.6-flash-high",
            "standard": "gemini-3.6-flash-medium",
            "economy": "gemini-3.6-flash-low",
        },
        "grok": {
            # Single model `grok-4.5` (E5); tiers differ only by thinking budget,
            # translated to `--reasoning-effort` by the dispatching adapter.
            "premium": {"model": "grok-4.5", "thinking": "high"},
            "standard": {"model": "grok-4.5", "thinking": "medium"},
            "economy": {"model": "grok-4.5", "thinking": "low"},
        },
        "pi": {
            # OpenRouter `<publisher>/<model>` slugs (spec configuration.2).
            # The spec constrains slug *form*, not which model — the concrete
            # default lives here so it can move without a spec amendment
            # (switch-pi-standard-to-ox-alpha, superseding roadmap ri-01's
            # qwen/qwen3-coder pin). frontier is Kimi 3 (E8).
            #
            # `standard` is a STEALTH slug and is temporary by construction: it
            # stops resolving without notice when the cloak lifts. premium and
            # economy deliberately stay on stable published qwen3-coder slugs so
            # the tier ladder survives that retirement.
            "frontier": "moonshotai/kimi-k3",
            "premium": "qwen/qwen3-coder-plus",
            "standard": "stealth/ox-alpha",
            "economy": "qwen/qwen3-coder-flash",
        },
        # Always-on local host (GB10 class). This is the tier -> model-id view
        # of `model_aliases.local` in archetypes.yaml; the parameter metadata
        # and operator review date live there, where startup validation
        # enforces the MoE-first hardware rule (D4). `frontier`/`premium` are
        # deliberately omitted — they degrade to the best defined tier. Keep
        # both in sync; a test asserts the two rosters agree.
        "local": {
            "standard": "gpt-oss-120b",
            "economy": "qwen3-coder-30b-a3b",
        },
    },
}

# ---------------------------------------------------------------------------
# Archetype name pattern (shared between schema and runtime validation)
# ---------------------------------------------------------------------------

# The supervisor archetype is a read-only orchestrator: it decomposes work,
# delegates it to write-capable worker archetypes, and adjudicates gates. It
# MUST NOT be write-capable — every code change is dispatched, never made by
# the supervisor itself. The archetype resolver enforces this invariant at
# config-load time (fail-loud), mirroring the D3 structured-field enforcement
# that a write-capable phase must resolve to a write_capable archetype.
SUPERVISOR_ARCHETYPE: str = "supervisor"

ARCHETYPE_NAME_PATTERN = r"^[a-z][a-z0-9_-]{0,31}$"

# A tier entry: bare model-id string, or model paired with a thinking level.
# Thinking vocabularies are vendor-specific (Claude effort tiers, Codex
# model_reasoning_effort, grok thinking budgets), so the value is a free
# string — the dispatching adapter owns translation to CLI flags.
_TIER_VALUE_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {"type": "string", "minLength": 1},
        {
            "type": "object",
            "required": ["model"],
            "additionalProperties": False,
            "properties": {
                "model": {"type": "string", "minLength": 1},
                "thinking": {"type": "string", "minLength": 1},
            },
        },
    ],
}

# The `local` roster uses an extended entry form so the hardware-matching rule
# is machine-checkable (contracts/local-roster-entry.schema.json). Only `model`
# is required *here*; the remaining fields are checked by
# :func:`_validate_local_roster` so every violation surfaces as one structured
# LocalRosterConfigError naming the rule it broke, rather than a raw
# jsonschema error for some rules and a config error for others.
_LOCAL_TIER_VALUE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["model"],
    "additionalProperties": False,
    "properties": {
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "total_params_b": {"type": "number", "exclusiveMinimum": 0},
        "active_params_b": {"type": "number", "exclusiveMinimum": 0},
        "reviewed": {"type": "string", "minLength": 1},
    },
}

_LOCAL_ROSTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": list(LOCAL_REQUIRED_TIERS),
    "additionalProperties": False,
    "properties": dict.fromkeys(ALL_MODEL_TIERS, _LOCAL_TIER_VALUE_SCHEMA),
}

_LOCAL_HOST_CLASS_SCHEMA: dict[str, Any] = {
    "type": ["object", "null"],
    "required": ["name", "active_params_ceiling_b"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "active_params_ceiling_b": {"type": "number", "exclusiveMinimum": 0},
        "dense_params_limit_b": {"type": "number", "exclusiveMinimum": 0},
    },
}

# Autopilot phases that produce files, artifacts, or handoffs and therefore
# MUST resolve to a `write_capable: true` archetype (design D7 canonical list).
# State-only phases (INIT, SUBMIT_PR) and read-only judge phases (GATEKEEPER)
# are intentionally excluded. Keep this list in sync with the write-capable
# phase enumerations in skills/autopilot and design D7 when phases change.
WRITE_CAPABLE_PHASES: frozenset[str] = frozenset({
    "PLAN",
    "PLAN_ITERATE",
    "PLAN_REVIEW",
    "PLAN_FIX",
    "IMPLEMENT",
    "IMPL_ITERATE",
    "IMPL_REVIEW",
    "IMPL_FIX",
    "VALIDATE",
    "VAL_REVIEW",
    "VAL_FIX",
})

# Non-terminal autopilot phases that may be mapped to archetypes (per design D11).
# Terminal phases (DONE, ESCALATE, ERROR) are not mapped.
NON_TERMINAL_PHASES: tuple[str, ...] = (
    "INIT",
    "GATEKEEPER",
    "PLAN",
    "PLAN_ITERATE",
    "PLAN_REVIEW",
    "PLAN_FIX",
    "IMPLEMENT",
    "IMPL_ITERATE",
    "IMPL_REVIEW",
    "IMPL_FIX",
    "VALIDATE",
    "VAL_REVIEW",
    "VAL_FIX",
    "SUBMIT_PR",
)

# ---------------------------------------------------------------------------
# JSON Schema for archetypes.yaml validation
# ---------------------------------------------------------------------------

ARCHETYPES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["schema_version", "archetypes"],
    "properties": {
        # schema_version selects optional structure: v2 enables phase_mapping (OpenSpec
        # add-per-phase-archetype-resolution), v3 adds model_aliases / tier models. Note:
        # `write_capable` is REQUIRED on every archetype regardless of version (fail-loud,
        # design D3 — no implicit default). A pre-existing v1 file that omits it must add
        # `write_capable` on migration; the version does NOT grandfather the field away.
        "schema_version": {"type": "integer", "enum": [1, 2, 3]},
        # Host class of the machine serving the `local` provider. Optional:
        # absent means the GB10 defaults apply (DEFAULT_LOCAL_HOST_CLASS).
        "local_host_class": _LOCAL_HOST_CLASS_SCHEMA,
        "model_aliases": {
            "type": ["object", "null"],
            # `local` carries parameter metadata and may omit frontier/premium
            # (they degrade to its best defined tier); every other provider
            # keeps the bare-slug form with all base tiers required.
            "properties": {LOCAL_PROVIDER: _LOCAL_ROSTER_SCHEMA},
            "additionalProperties": {
                "type": "object",
                # Base tiers stay required; optional tiers (frontier) may be
                # omitted per provider — resolution falls back to premium.
                "required": list(MODEL_TIERS),
                "additionalProperties": False,
                "properties": {
                    "frontier": _TIER_VALUE_SCHEMA,
                    "premium": _TIER_VALUE_SCHEMA,
                    "standard": _TIER_VALUE_SCHEMA,
                    "economy": _TIER_VALUE_SCHEMA,
                },
            },
        },
        "archetypes": {
            "type": "object",
            "minProperties": 1,
            "propertyNames": {
                "type": "string",
                "pattern": ARCHETYPE_NAME_PATTERN,
            },
            "additionalProperties": {
                "type": "object",
                "required": ["model", "system_prompt", "write_capable"],
                "properties": {
                    "model": {
                        "type": "string",
                        "enum": [
                            "frontier", "premium", "standard", "economy",
                            "opus", "sonnet", "haiku",
                        ],
                    },
                    "system_prompt": {"type": "string"},
                    # Whether the archetype may write files / artifacts. Required
                    # on every archetype (design D3 / D3.1 — no implicit default;
                    # a missing field fails schema validation, i.e. fail-loud).
                    "write_capable": {"type": "boolean"},
                    "escalation": {
                        "type": ["object", "null"],
                        "properties": {
                            "escalate_to": {
                                "type": "string",
                                "enum": [
                                    "frontier", "premium", "standard", "economy",
                                    "opus", "sonnet", "haiku",
                                ],
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
        "phase_mapping": {
            "type": ["object", "null"],
            "propertyNames": {"enum": list(NON_TERMINAL_PHASES)},
            "additionalProperties": {
                "type": "object",
                "required": ["archetype"],
                "additionalProperties": False,
                "properties": {
                    "archetype": {
                        "type": "string",
                        "pattern": ARCHETYPE_NAME_PATTERN,
                    },
                    "signals": {
                        "type": "array",
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                },
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
    "feature_registry",
}

AGENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["agents"],
    "properties": {
        "policies": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "enforce_for": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "fallback": {"type": "string", "minLength": 1},
                    "scope": {"type": "string", "minLength": 1},
                },
                "additionalProperties": True,
            },
        },
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
                    # Bounds derive from the Unified Trust Scale (src/trust_levels.py,
                    # design D4) rather than repeating integer literals. The former
                    # 1–5 range was a bug: the agent_profiles CHECK constraint has
                    # always been 0–4.
                    "trust_level": {
                        "type": "integer",
                        "minimum": MIN_TRUST,
                        "maximum": MAX_TRUST,
                    },
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
                            # Attach the prompt as the value of this flag, e.g.
                            # `agy --prompt "<text>"`. Mutually exclusive with
                            # prompt_via_stdin (antigravity: prompt is a flag
                            # value, never stdin — design.md E7). The dispatching
                            # adapter appends [prompt_via_flag, prompt].
                            "prompt_via_flag": {"type": "string", "minLength": 1},
                            # Env var the CLI needs to serve a request (e.g. pi
                            # resolves OPENROUTER_API_KEY from the subprocess
                            # env). Availability checks treat the binary as
                            # unavailable when the var is unset (issue #383).
                            "api_key_env": {"type": "string", "minLength": 1},
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
    # When set, the dispatching adapter attaches the prompt as this flag's
    # value (``[prompt_via_flag, prompt]``) instead of via stdin or a trailing
    # positional. Antigravity needs this: its prompt is the value of
    # ``--prompt``/``--print`` and stdin is ignored (design.md E7).
    prompt_via_flag: str = ""
    # Env var the CLI resolves its provider credential from (pi:
    # OPENROUTER_API_KEY). A present binary with this var unset cannot serve
    # a request, so availability checks fail closed on it (issue #383).
    api_key_env: str = ""


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
    write_capable: bool = False
    escalation: EscalationConfig | None = None


@dataclass
class PhaseMappingEntry:
    """One entry in the ``phase_mapping`` section of ``archetypes.yaml``.

    Maps an autopilot phase to an archetype name plus the list of signal keys
    that ``_extract_signals_for_phase`` (skills side) reads from ``state_dict``
    for this phase. Coordinator-side resolution silently drops any signal whose
    key is not in :attr:`signals`.
    """

    archetype: str
    signals: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModelSpec:
    """A dispatchable model: id plus optional thinking/reasoning level.

    Thinking level is part of the model definition because it materially
    shifts both cost and capability; tier selection optimizes cost per
    successful task, not cost per token. ``thinking`` is a vendor-specific
    free string; the dispatching adapter translates it to CLI flags.
    """

    model: str
    thinking: str | None = None


@dataclass
class ResolvedArchetype:
    """Result of :func:`resolve_archetype_for_phase`.

    Returned to clients of ``POST /archetypes/resolve_for_phase`` and to
    in-process callers (autopilot phase agent via the bridge helper).
    """

    model: str
    system_prompt: str
    archetype: str
    reasons: list[str]
    provider: str | None = None
    write_capable: bool = False
    thinking: str | None = None


class ProviderModelMappingError(ValueError):
    """Raised when a logical/legacy model cannot resolve for a provider."""

    def __init__(self, provider: str, model: str, tier: str | None = None) -> None:
        self.provider = provider
        self.model = model
        self.tier = tier
        if tier:
            message = (
                f"missing provider model mapping for provider={provider!r}, "
                f"tier={tier!r}, source_model={model!r}"
            )
        else:
            message = (
                f"missing provider model mapping for provider={provider!r}, "
                f"source_model={model!r}"
            )
        super().__init__(message)


class LocalRosterConfigError(ValueError):
    """Raised at startup when a `local` roster entry breaks a hardware rule.

    Structured on purpose (``rule`` / ``tier`` / ``detail``): an unattended
    loop must be able to say which rule was violated, not just that the config
    is bad. Uses the same fail-fast mechanism as the undefined-archetype
    ``ValueError`` in :func:`load_archetypes_config`.
    """

    def __init__(self, rule: str, detail: str, *, tier: str | None = None) -> None:
        self.rule = rule
        self.tier = tier
        self.detail = detail
        location = (
            f"model_aliases.{LOCAL_PROVIDER}.{tier}"
            if tier
            else f"model_aliases.{LOCAL_PROVIDER}"
        )
        super().__init__(f"invalid local roster at {location}: {rule} — {detail}")


class LocalProviderTrustBoundaryError(ValueError):
    """Raised when an archetype outside the local trust boundary asks for `local`.

    Design D3: the boundary is enforced in the resolver (the single decision
    point every client goes through), not in the dispatching caller, and the
    refusal happens before any dispatch is attempted.
    """

    def __init__(self, archetype: str, *, phase: str | None = None) -> None:
        self.archetype = archetype
        self.phase = phase
        self.provider = LOCAL_PROVIDER
        self.permitted: tuple[str, ...] = tuple(sorted(LOCAL_TRUSTED_ARCHETYPES))
        where = f" (phase={phase})" if phase else ""
        super().__init__(
            f"local provider trust boundary: archetype {archetype!r}{where} may not "
            f"resolve to provider {LOCAL_PROVIDER!r}; permitted archetypes: "
            f"{', '.join(self.permitted)}"
        )


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
        ValueError: On duplicate agent names or duplicate ``profile`` values.
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
    #: profile name -> the agent that claimed it, so the second claimant can be
    #: named in the error.
    seen_profiles: dict[str, str] = {}

    for name, agent_data in raw["agents"].items():
        if name in seen_names:
            raise ValueError(f"Duplicate agent name: '{name}'")
        seen_names.add(name)

        # Two agents sharing one `profile` is not a harmless alias: sync_profiles()
        # upserts by profile name in file order, so the last entry silently
        # overwrites the first one's trust level and operations. An agent could
        # then be promoted to admin without its own trust_level line changing,
        # and neither orphan disabling nor the registry invariant check would
        # notice. One agent, one profile row.
        profile_name = agent_data["profile"]
        if profile_name in seen_profiles:
            raise ValueError(
                f"Duplicate profile: '{profile_name}' is declared by both "
                f"'{seen_profiles[profile_name]}' and '{name}'. Each agent needs "
                f"its own profile, or the later entry silently overwrites the "
                f"earlier one's trust level and operations."
            )
        seen_profiles[profile_name] = name

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
                prompt_via_flag=raw_cli.get("prompt_via_flag", ""),
                api_key_env=raw_cli.get("api_key_env", ""),
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


class DuplicateApiKeyError(ValueError):
    """Two registry agents resolve to the same API key (design D6).

    A shared key is an identity-confusion bug: the coordinator would attribute
    both principals' operations to whichever agent happened to win the map, so
    the audit trail silently lies. Fail at load with both agent names instead.
    """

    def __init__(self, first_agent: str, second_agent: str) -> None:
        self.first_agent = first_agent
        self.second_agent = second_agent
        super().__init__(
            f"Duplicate resolved API key: agents '{first_agent}' and "
            f"'{second_agent}' resolve to the same value. Every agent needs "
            f"its own key — a shared key makes audit attribution ambiguous."
        )


def get_api_key_identities(
    agents: list[AgentEntry] | None = None,
) -> dict[str, dict[str, str]]:
    """Generate ``COORDINATION_API_KEY_IDENTITIES`` for the full agent roster.

    Every agent with a resolvable ``api_key`` receives an identity entry,
    regardless of declared ``transport`` (design D5): the MCP server's
    HTTP-proxy fallback makes local agents HTTP principals in practice, so
    ``transport`` is dispatch metadata only and does not gate identity.

    When OpenBao is enabled, attempts to resolve API keys from OpenBao
    for agents with ``openbao_role_id``. Falls back to static interpolation.

    Returns:
        Dict mapping resolved API key values to
        ``{"agent_id": ..., "agent_type": ...}``.

    Raises:
        DuplicateApiKeyError: If two agents resolve to the same key.
    """
    if agents is None:
        agents = load_agents_config()

    # Check if OpenBao is available for key resolution
    openbao_enabled = bool(os.environ.get("BAO_ADDR"))

    identities: dict[str, dict[str, str]] = {}
    for agent in agents:
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
            raise DuplicateApiKeyError(identities[key]["agent_id"], agent.name)
        identities[key] = {
            "agent_id": agent.name,
            "agent_type": agent.type,
        }
    return identities


# ---------------------------------------------------------------------------
# Registry → agent_profiles projection (design D1 / D2)
# ---------------------------------------------------------------------------

#: Operations every projected profile receives. Migration 007 granted
#: ``get_my_profile`` to every seeded profile without exception: reading one's
#: own profile is not a privilege, it is how an agent discovers its own limits.
UNIVERSAL_OPERATIONS: tuple[str, ...] = ("get_my_profile",)

#: ``agents.yaml`` capability → the coordination operations it authorizes.
#: Derived from the operation lists the hand-written seeds granted (migrations
#: 007 / 019 / 022 / 026); ``tests/test_profile_sync.py`` pins the mapping
#: against the grants ``claude_code_local`` carries today.
CAPABILITY_OPERATIONS: dict[str, tuple[str, ...]] = {
    "lock": ("acquire_lock", "release_lock", "check_locks"),
    "queue": ("get_work", "get_task", "complete_work", "submit_work"),
    "memory": ("remember", "recall"),
    "guardrails": ("check_guardrails",),
    "handoff": ("write_handoff", "read_handoff"),
    "discover": ("register_session", "discover_agents", "heartbeat"),
    "audit": ("query_audit",),
    "feature_registry": ("register_feature", "deregister_feature"),
}

#: Operations granted by *trust level* rather than by capability, as
#: ``(minimum trust level, operations)`` pairs. Migration 022 granted the merge
#: queue operations with ``WHERE trust_level >= 3`` — no capability in
#: ``agents.yaml`` covers them, so the projection needs this second dimension
#: to reproduce the grants the migrations made.
TRUST_DERIVED_OPERATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        int(TrustLevel.ELEVATED),
        (
            "register_feature",
            "deregister_feature",
            "enqueue_merge",
            "run_pre_merge_checks",
            "mark_merged",
            "remove_from_merge_queue",
        ),
    ),
)

#: Profile rows the registry deliberately does NOT own (design D2 amendment).
#:
#: ``agents.yaml`` describes *harness identities*: things that can be
#: dispatched, that speak a transport, and that authenticate. Some profile rows
#: describe a *role* instead — ``evaluator`` (migration 026_evaluator_profile)
#: is the generator/evaluator split's read-only reviewer role, has no CLI and no
#: transport, and could never be given an ``agents.yaml`` entry without the
#: registry claiming to describe an agent it cannot dispatch. Orphan disabling
#: skips these names, so a role profile is not collateral damage of enforcing
#: the registry projection. Adding a name here is an explicit statement that
#: some other mechanism owns that row.
UNMANAGED_PROFILES: frozenset[str] = frozenset({"evaluator"})

#: Fields the sync reconciles (and reports in ``changed_fields`` per the
#: profile-sync audit contract). Everything else on the row — descriptions,
#: resource limits, network policy — stays operator-owned.
SYNC_TRACKED_FIELDS: tuple[str, ...] = (
    "agent_type",
    "trust_level",
    "allowed_operations",
    "enabled",
)

#: ``source`` value carried by every profile_sync audit event.
PROFILE_SYNC_SOURCE = "agents.yaml"

#: Audit ``operation`` name for registry projection mutations.
PROFILE_SYNC_OPERATION = "profile_sync"

#: ``assigned_by`` stamped on every ``agent_profile_assignments`` row the
#: registry projection writes, so an operator can tell a projected assignment
#: from a hand-written one (migration 018 wrote its rows with ``assigned_by``
#: NULL).
ASSIGNMENT_ASSIGNED_BY = "registry_sync"


class ProfileSyncError(RuntimeError):
    """The registry projection could not be materialized.

    Raised (never swallowed) so that a coordinator whose authorization state
    does not match ``agents.yaml`` fails boot instead of serving requests with
    a stale or partial projection.
    """


@dataclass
class ProfileSyncResult:
    """Outcome of one :func:`sync_profiles` run."""

    inserted: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    #: ``agent_profile_assignments`` outcomes (design D11), keyed by agent id
    #: rather than profile name — an assignment is a per-agent pointer.
    assigned: list[str] = field(default_factory=list)
    reassigned: list[str] = field(default_factory=list)
    unassigned: list[str] = field(default_factory=list)
    assignments_unchanged: list[str] = field(default_factory=list)
    #: ``None`` when the sync ran; otherwise why it performed no writes.
    skipped_reason: str | None = None

    @property
    def mutations(self) -> int:
        """Number of rows this run changed (profiles *and* assignments)."""
        return (
            len(self.inserted)
            + len(self.updated)
            + len(self.disabled)
            + len(self.assigned)
            + len(self.reassigned)
            + len(self.unassigned)
        )


def derive_allowed_operations(
    capabilities: list[str] | tuple[str, ...],
    trust_level: int,
) -> list[str]:
    """Project a registry entry's capabilities + trust level to operations.

    Two dimensions, because the hand-written migrations used two: capabilities
    map to the operation families they name, and trust level independently
    grants the merge-queue operations no capability covers (migration 022).

    Raises:
        ValueError: If a capability has no mapping — a half-onboarded harness
            must fail loudly rather than materialize a profile missing grants.
    """
    operations: set[str] = set(UNIVERSAL_OPERATIONS)
    for capability in capabilities:
        mapped = CAPABILITY_OPERATIONS.get(capability)
        if mapped is None:
            raise ValueError(
                f"Capability '{capability}' has no operation mapping; add it to "
                f"CAPABILITY_OPERATIONS. Known capabilities: "
                f"{sorted(CAPABILITY_OPERATIONS)}"
            )
        operations.update(mapped)

    for minimum_trust, granted in TRUST_DERIVED_OPERATIONS:
        if trust_level >= minimum_trust:
            operations.update(granted)

    return sorted(operations)


#: Substring PostgreSQL puts in the message of every UNIQUE-constraint failure.
#: The PostgREST/httpx backend surfaces the violation as text, so the string is
#: the only signal available there.
_UNIQUE_VIOLATION_TEXT = "duplicate key value violates unique constraint"

#: SQLSTATE for unique_violation. asyncpg exposes it as ``sqlstate``.
_UNIQUE_VIOLATION_SQLSTATE = "23505"


def _is_unique_violation(exc: BaseException) -> bool:
    """Is *exc* a genuine UNIQUE-constraint violation?

    The insert→update fallbacks below exist for exactly one situation: a
    concurrent worker won the race for the same unique key. Treating *every*
    insert failure as that race is what let an RLS denial, an FK violation, or
    a CHECK failure be retried as an UPDATE — which matches zero rows, raises
    nothing (``return_data=False`` never inspects rowcount), and is then
    recorded as a successful projection with an audit event for a row that
    does not exist. Anything that is not a uniqueness collision must fail the
    sync instead.
    """
    if type(exc).__name__ == "UniqueViolationError":  # asyncpg
        return True
    if getattr(exc, "sqlstate", None) == _UNIQUE_VIOLATION_SQLSTATE:
        return True
    return _UNIQUE_VIOLATION_TEXT in str(exc)


def _registry_sync_timestamp() -> datetime:
    """Value for ``agent_profiles.synced_from_registry_at`` on this write.

    Migration 032 added the column so operators can tell registry-projected
    rows from hand-maintained ones; it stays NULL unless the projection
    actually stamps it.

    Returns a ``datetime``, never an ISO string: asyncpg binds TIMESTAMPTZ
    parameters from datetime objects only, and a str here fails every boot
    whose sync needs a profile write (DataError at bind time) — which the
    mocked-DB tests cannot see because ``FakeDb`` accepts any payload. This
    took production down on 2026-08-22; the type is load-bearing.
    """
    return datetime.now(UTC)


def _desired_profile_row(agent: AgentEntry) -> dict[str, Any]:
    """Build the ``agent_profiles`` row a registry entry projects to."""
    return {
        "name": agent.profile,
        "agent_type": agent.type,
        "trust_level": agent.trust_level,
        "allowed_operations": derive_allowed_operations(
            agent.capabilities, agent.trust_level
        ),
        "enabled": True,
    }


def _profile_drift(
    desired: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return ``{field: {"from": old, "to": new}}`` for drifted tracked fields."""
    changed: dict[str, dict[str, Any]] = {}
    for name in SYNC_TRACKED_FIELDS:
        current = existing.get(name)
        target = desired[name]
        if name == "allowed_operations":
            current = sorted(current or [])
        if name == "enabled":
            current = bool(current)
        if current != target:
            changed[name] = {"from": current, "to": target}
    return changed


async def _emit_sync_audit(
    audit: AuditService,
    *,
    action: str,
    profile_name: str,
    agent_type: str,
    trust_level: int | None = None,
    changed_fields: dict[str, dict[str, Any]] | None = None,
    agent_id: str | None = None,
    previous_profile_name: str | None = None,
) -> None:
    """Emit one profile-sync audit event (contract: profile-sync-audit.schema.json)."""
    parameters: dict[str, Any] = {
        "action": action,
        "profile_name": profile_name,
        "agent_type": agent_type,
        "source": PROFILE_SYNC_SOURCE,
    }
    if trust_level is not None:
        parameters["trust_level"] = trust_level
    if changed_fields:
        parameters["changed_fields"] = changed_fields
    if agent_id is not None:
        parameters["agent_id"] = agent_id
    if previous_profile_name is not None:
        parameters["previous_profile_name"] = previous_profile_name

    try:
        await audit.log_operation(
            operation=PROFILE_SYNC_OPERATION,
            parameters=parameters,
            result={"profile_name": profile_name},
            success=True,
        )
    except Exception:  # noqa: BLE001
        # The projection itself succeeded; losing its audit event degrades
        # observability but must not roll back or block boot.
        logger.warning(
            "Failed to audit profile_sync %s for profile '%s'",
            action,
            profile_name,
            exc_info=True,
        )


async def _sync_assignments(
    agents: list[AgentEntry],
    *,
    db: DatabaseClient,
    audit: AuditService,
    result: ProfileSyncResult,
) -> None:
    """Project ``agent_profile_assignments`` from the registry (design D11).

    Profiles alone do not decide what an agent resolves to.
    ``get_agent_profile()`` (migration 007) reads the assignment first and only
    then falls back to ``agent_type`` + ``ORDER BY created_at ASC LIMIT 1``.
    That fallback silently serves the *oldest* row of the type when two agents
    share a type and neither is assigned — the bug migration 018 fixed by hand
    for the roster of its day and for nobody added since. Writing one assignment
    per registry agent makes the tiebreak unreachable rather than merely lucky.

    Idempotent and convergent under concurrent worker boot, like the profile
    phase: writes are keyed on ``agent_id`` (the table's UNIQUE column), so a
    worker that loses the INSERT race reconciles with an UPDATE.
    """
    # Profile ids are not returned by the upsert path above, so re-query. This
    # also picks up rows a concurrent worker inserted between our phases.
    try:
        profile_rows = await db.query("agent_profiles")
    except Exception as exc:
        raise ProfileSyncError(
            f"Could not re-read agent_profiles for the assignment projection: {exc}"
        ) from exc

    id_by_name: dict[str, Any] = {}
    row_by_id: dict[Any, dict[str, Any]] = {}
    for row in profile_rows:
        row_id = row.get("id")
        if row_id is None:
            continue
        row_by_id[row_id] = row
        name = row.get("name")
        if name:
            id_by_name[str(name)] = row_id

    try:
        assignment_rows = await db.query("agent_profile_assignments")
    except Exception as exc:
        raise ProfileSyncError(
            f"Could not read agent_profile_assignments for the registry "
            f"projection: {exc}"
        ) from exc

    existing: dict[str, dict[str, Any]] = {
        str(row.get("agent_id")): row for row in assignment_rows if row.get("agent_id")
    }

    declared: set[str] = set()
    for agent in agents:
        declared.add(agent.name)
        profile_id = id_by_name.get(agent.profile)
        if profile_id is None:
            raise ProfileSyncError(
                f"Agent '{agent.name}' has no agent_profiles row named "
                f"'{agent.profile}' after the profile phase, so its assignment "
                f"cannot be projected — resolution would fall back to the oldest "
                f"row of type '{agent.type}'."
            )

        current = existing.get(agent.name)
        if current is not None and current.get("profile_id") == profile_id:
            result.assignments_unchanged.append(agent.name)
            continue

        payload = {"profile_id": profile_id, "assigned_by": ASSIGNMENT_ASSIGNED_BY}

        if current is None:
            try:
                await db.insert(
                    "agent_profile_assignments",
                    {"agent_id": agent.name, **payload},
                    return_data=False,
                )
            except Exception as exc:
                # A concurrent worker may have inserted the same agent_id
                # between our read and our write (UNIQUE (agent_id)). Converge
                # via update rather than failing the slower worker's boot; both
                # workers project identical content. Narrowed to real
                # uniqueness collisions: an RLS denial or FK violation means no
                # row exists, so the retried UPDATE would match nothing, raise
                # nothing, and leave the agent with no assignment while this
                # run reported `assign`.
                if not _is_unique_violation(exc):
                    raise ProfileSyncError(
                        f"Could not assign agent '{agent.name}' to profile "
                        f"'{agent.profile}': {exc}"
                    ) from exc
                try:
                    await db.update(
                        "agent_profile_assignments",
                        {"agent_id": agent.name},
                        payload,
                        return_data=False,
                    )
                except Exception as update_exc:
                    raise ProfileSyncError(
                        f"Could not assign agent '{agent.name}' to profile "
                        f"'{agent.profile}': {update_exc}"
                    ) from exc

            result.assigned.append(agent.name)
            await _emit_sync_audit(
                audit,
                action="assign",
                profile_name=agent.profile,
                agent_type=agent.type,
                trust_level=agent.trust_level,
                agent_id=agent.name,
            )
            continue

        try:
            await db.update(
                "agent_profile_assignments",
                {"agent_id": agent.name},
                payload,
                return_data=False,
            )
        except Exception as exc:
            raise ProfileSyncError(
                f"Could not reassign agent '{agent.name}' to profile "
                f"'{agent.profile}': {exc}"
            ) from exc

        previous = row_by_id.get(current.get("profile_id"))
        result.reassigned.append(agent.name)
        await _emit_sync_audit(
            audit,
            action="reassign",
            profile_name=agent.profile,
            agent_type=agent.type,
            trust_level=agent.trust_level,
            agent_id=agent.name,
            previous_profile_name=str(previous.get("name")) if previous else "unknown",
        )

    for agent_id, row in existing.items():
        if agent_id in declared:
            continue
        # The sync garbage-collects only rows it wrote. `assigned_by` exists
        # precisely to tell a projected assignment from everything else:
        # migration 018's hand-written rows carry NULL, and per-host enrollment
        # (scripts/add_agent_keys.py) stamps its own name. Those agent_ids are
        # *instances* — deliberately not registry entries, because the registry
        # declares vendor types, not machines — so treating "absent from
        # agents.yaml" as "stale" would delete every enrolled host's assignment
        # at each startup and drop resolution back to the oldest-row-of-type
        # tiebreak that migration 018 was written to eliminate.
        if row.get("assigned_by") != ASSIGNMENT_ASSIGNED_BY:
            logger.debug(
                "Retaining assignment for undeclared agent '%s' "
                "(assigned_by=%r is not the registry projection's)",
                agent_id,
                row.get("assigned_by"),
            )
            continue
        # Stale pointers are DELETEd, deliberately unlike D2's
        # disable-don't-delete rule for profiles: this table has no `enabled`
        # column, and an assignment is a *pointer*, not authorization state. The
        # profile it referenced is retained (and disabled by the profile phase),
        # and the audit event below records the name it pointed at, so the
        # removal stays reconstructible from the audit trail alone.
        pointed = row_by_id.get(row.get("profile_id"))
        try:
            await db.delete("agent_profile_assignments", {"agent_id": agent_id})
        except Exception as exc:
            raise ProfileSyncError(
                f"Could not remove stale assignment for agent '{agent_id}': {exc}"
            ) from exc

        result.unassigned.append(agent_id)
        await _emit_sync_audit(
            audit,
            action="unassign",
            profile_name=str(pointed.get("name")) if pointed else "unknown",
            agent_type=str(pointed.get("agent_type")) if pointed else "unknown",
            agent_id=agent_id,
        )


async def sync_profiles(
    agents: list[AgentEntry] | None = None,
    *,
    db: DatabaseClient | None = None,
    audit: AuditService | None = None,
) -> ProfileSyncResult:
    """Project ``agents.yaml`` onto the profile tables (design D1 / D11).

    For every registry agent, upserts the row named by its ``profile`` field
    with the declared trust level and derived ``allowed_operations``. Enabled
    rows that are neither declared by the registry nor listed in
    :data:`UNMANAGED_PROFILES` are **disabled**, never deleted. Then projects
    ``agent_profile_assignments`` (see :func:`_sync_assignments`), which is the
    table resolution actually consults first. Every mutation emits a
    ``profile_sync`` audit event; unchanged rows emit nothing.

    Idempotent and safe under concurrent startup of multiple API workers
    (design D9 as amended): all writes are keyed on the profile name and
    converge on the same state, so two workers racing produce the same result.

    Args:
        agents: Registry entries; loaded from ``agents.yaml`` when omitted.
        db: Database client; the global client when omitted.
        audit: Audit service; the global service when omitted.

    Returns:
        A :class:`ProfileSyncResult` describing what changed.

    Raises:
        ProfileSyncError: On any failure to read or write the projection.
            Callers must not swallow this — a coordinator whose authorization
            state does not match the registry has to fail loudly.
    """
    from src.config import get_config

    result = ProfileSyncResult()

    if not get_config().profiles.sync_enabled:
        logger.warning(
            "PROFILE_SYNC_ENABLED=false — agent_profiles is NOT enforced as a "
            "projection of agents.yaml. Profile rows may drift from the registry."
        )
        result.skipped_reason = "disabled"
        return result

    if agents is None:
        try:
            agents = load_agents_config()
        except FileNotFoundError:
            logger.warning(
                "agents.yaml not found — skipping profile sync (nothing to project)."
            )
            result.skipped_reason = "no_registry"
            return result

    if not agents:
        # Refusing to run on an empty registry is a safety property, not a
        # convenience: orphan disabling against an empty roster would disable
        # every profile in the table.
        logger.warning("agents.yaml declares no agents — skipping profile sync.")
        result.skipped_reason = "no_registry"
        return result

    if db is None:
        from src.db import get_db

        db = get_db()
    if audit is None:
        from src.audit import get_audit_service

        audit = get_audit_service()

    try:
        rows = await db.query("agent_profiles")
    except Exception as exc:
        raise ProfileSyncError(
            f"Could not read agent_profiles for the registry projection: {exc}"
        ) from exc

    existing: dict[str, dict[str, Any]] = {
        str(row.get("name")): row for row in rows if row.get("name")
    }

    declared: set[str] = set()
    for agent in agents:
        try:
            desired = _desired_profile_row(agent)
        except ValueError as exc:
            raise ProfileSyncError(
                f"Agent '{agent.name}' cannot be projected to profile "
                f"'{agent.profile}': {exc}"
            ) from exc

        name = desired["name"]
        declared.add(name)
        current = existing.get(name)

        # Stamp every projected write so migration 032.s
        # synced_from_registry_at column means what its comment claims.
        row_payload = {**desired, "synced_from_registry_at": _registry_sync_timestamp()}
        update_payload = {k: v for k, v in row_payload.items() if k != "name"}

        if current is None:
            try:
                await db.insert("agent_profiles", row_payload, return_data=False)
            except Exception as exc:
                # A concurrent worker may have inserted the same name between
                # our read and our write (UNIQUE (name)). Converge via update
                # rather than failing the boot of the slower worker. ONLY for a
                # real uniqueness collision: any other failure means the row was
                # never written, and retrying it as an UPDATE would match zero
                # rows, raise nothing, and be reported as a successful insert.
                if not _is_unique_violation(exc):
                    raise ProfileSyncError(
                        f"Could not project agent '{agent.name}' onto profile "
                        f"'{name}': {exc}"
                    ) from exc
                try:
                    await db.update(
                        "agent_profiles",
                        {"name": name},
                        update_payload,
                        return_data=False,
                    )
                except Exception as update_exc:
                    raise ProfileSyncError(
                        f"Could not project agent '{agent.name}' onto profile "
                        f"'{name}': {update_exc}"
                    ) from exc
                result.updated.append(name)
                await _emit_sync_audit(
                    audit,
                    action="update",
                    profile_name=name,
                    agent_type=agent.type,
                    trust_level=agent.trust_level,
                )
                continue

            result.inserted.append(name)
            await _emit_sync_audit(
                audit,
                action="insert",
                profile_name=name,
                agent_type=agent.type,
                trust_level=agent.trust_level,
            )
            continue

        changed = _profile_drift(desired, current)
        if not changed:
            result.unchanged.append(name)
            continue

        try:
            await db.update(
                "agent_profiles",
                {"name": name},
                update_payload,
                return_data=False,
            )
        except Exception as exc:
            raise ProfileSyncError(
                f"Could not reconcile profile '{name}' for agent "
                f"'{agent.name}': {exc}"
            ) from exc

        result.updated.append(name)
        await _emit_sync_audit(
            audit,
            action="update",
            profile_name=name,
            agent_type=agent.type,
            trust_level=agent.trust_level,
            changed_fields=changed,
        )

    for name, row in existing.items():
        if name in declared or name in UNMANAGED_PROFILES:
            continue
        if not row.get("enabled", True):
            continue

        try:
            await db.update(
                "agent_profiles",
                {"name": name},
                {"enabled": False},
                return_data=False,
            )
        except Exception as exc:
            raise ProfileSyncError(
                f"Could not disable orphaned profile '{name}': {exc}"
            ) from exc

        result.disabled.append(name)
        await _emit_sync_audit(
            audit,
            action="disable",
            profile_name=name,
            agent_type=str(row.get("agent_type") or "unknown"),
        )

    await _sync_assignments(agents, db=db, audit=audit, result=result)

    if result.mutations:
        # The profiles service caches lookups by agent_id:agent_type with a
        # TTL. At boot the cache is empty and this is a no-op; on a re-sync in
        # a live process it stops pre-sync trust levels from being served until
        # the TTL expires.
        from src.profiles import get_profiles_service

        get_profiles_service().invalidate_cache()

    logger.info(
        "Profile sync: %d inserted, %d updated, %d disabled, %d unchanged; "
        "assignments: %d assigned, %d reassigned, %d removed, %d unchanged.",
        len(result.inserted),
        len(result.updated),
        len(result.disabled),
        len(result.unchanged),
        len(result.assigned),
        len(result.reassigned),
        len(result.unassigned),
        len(result.assignments_unchanged),
    )
    return result


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
                "prompt_via_flag": entry.cli.prompt_via_flag,
                "api_key_env": entry.cli.api_key_env,
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


def _as_positive_number(value: Any) -> float | None:
    """Return *value* as a float when it is a positive, non-boolean number."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value > 0 else None


def _validate_local_roster(
    raw_aliases: dict[str, Any] | None,
    raw_host_class: dict[str, Any] | None,
) -> None:
    """Validate the `local` roster against its host class (design D4).

    No-op unless ``model_aliases.local`` exists — nothing requires the local
    provider to be configured. When it does exist, every entry must use the
    extended form and satisfy both hardware rules, or startup fails with a
    :class:`LocalRosterConfigError` naming the rule.

    Contract: ``contracts/local-roster-entry.schema.json``.
    """
    if not raw_aliases:
        return
    roster = raw_aliases.get(LOCAL_PROVIDER)
    if not roster:
        return

    host_class = {**DEFAULT_LOCAL_HOST_CLASS, **(raw_host_class or {})}
    ceiling = _as_positive_number(host_class.get("active_params_ceiling_b"))
    dense_limit = _as_positive_number(host_class.get("dense_params_limit_b"))
    if ceiling is None or dense_limit is None:
        raise LocalRosterConfigError(
            "host-class-config",
            f"local_host_class must define positive active_params_ceiling_b and "
            f"dense_params_limit_b; got {host_class!r}",
        )

    # Defence in depth: on the load path jsonschema's `required` on
    # _LOCAL_ROSTER_SCHEMA fires first, so this never triggers there. It guards
    # direct callers of this function (tests, future programmatic loaders) that
    # hand over a roster which never went through ARCHETYPES_SCHEMA.
    missing_tiers = [tier for tier in LOCAL_REQUIRED_TIERS if tier not in roster]
    if missing_tiers:
        raise LocalRosterConfigError(
            "required-tiers",
            f"local roster must define {list(LOCAL_REQUIRED_TIERS)}; "
            f"missing {missing_tiers}",
        )

    for tier, entry in roster.items():
        if not isinstance(entry, dict):
            raise LocalRosterConfigError(
                "extended-entry-form",
                "local roster entries must be objects of the form "
                "{model, total_params_b, active_params_b, reviewed}; "
                f"got {entry!r}",
                tier=tier,
            )

        for required_field in ("model", "total_params_b", "active_params_b", "reviewed"):
            if required_field not in entry:
                raise LocalRosterConfigError(
                    "extended-entry-form",
                    f"local roster entry is missing required field "
                    f"{required_field!r} (declared fields: {sorted(entry)})",
                    tier=tier,
                )

        # Two checks, because neither alone is sufficient: the regex pins the
        # dashed YYYY-MM-DD shape (``date.fromisoformat`` also accepts the ISO
        # basic form "20260816"), and parsing rejects date-shaped strings that
        # are not real dates ("2026-13-45", "2026-02-30").
        reviewed = entry["reviewed"]
        if not isinstance(reviewed, str) or not _REVIEWED_DATE_RE.match(reviewed):
            raise LocalRosterConfigError(
                "operator-review-date",
                f"'reviewed' must be an operator-signed YYYY-MM-DD date "
                f"(quote it in YAML); got {reviewed!r}",
                tier=tier,
            )
        try:
            date.fromisoformat(reviewed)
        except ValueError as exc:
            raise LocalRosterConfigError(
                "operator-review-date",
                f"'reviewed' must be an operator-signed YYYY-MM-DD date "
                f"naming a real calendar day; got {reviewed!r}",
                tier=tier,
            ) from exc

        total = _as_positive_number(entry["total_params_b"])
        active = _as_positive_number(entry["active_params_b"])
        if total is None or active is None:
            raise LocalRosterConfigError(
                "extended-entry-form",
                f"total_params_b and active_params_b must be positive numbers; "
                f"got total={entry['total_params_b']!r}, "
                f"active={entry['active_params_b']!r}",
                tier=tier,
            )
        if active > total:
            raise LocalRosterConfigError(
                "extended-entry-form",
                f"active_params_b ({active}) exceeds total_params_b ({total})",
                tier=tier,
            )

        # Dense first: a dense model violates both rules, and the dense rule is
        # the one that explains *why* it can never be a roster entry here.
        if active == total and total >= dense_limit:
            raise LocalRosterConfigError(
                "dense-model-hardware-matching",
                f"{entry['model']!r} is dense ({total}B total == {active}B active) "
                f"and at or above the {dense_limit}B dense limit for host class "
                f"{host_class.get('name')!r}; this host is bandwidth-bound, so "
                f"dense models at this size must not be roster entries even "
                f"though they fit in memory",
                tier=tier,
            )
        if active > ceiling:
            raise LocalRosterConfigError(
                "active-parameter-hardware-matching",
                f"{entry['model']!r} declares {active}B active parameters, above "
                f"the {ceiling}B active ceiling for host class "
                f"{host_class.get('name')!r}; local rosters on bandwidth-bound "
                f"hardware must be MoE-first",
                tier=tier,
            )


def load_archetypes_config(
    path: Path | None = None,
) -> dict[str, ArchetypeConfig]:
    """Load and validate ``archetypes.yaml``.

    Returns a dict mapping archetype names to :class:`ArchetypeConfig`.
    Uses the global cache — subsequent calls return the same dict.

    Also populates the parallel ``_phase_mapping`` cache when the file
    contains a ``phase_mapping`` section (schema_version=2). The mapping is
    accessible via :func:`get_phase_mapping`. Raises ``ValueError`` if a
    ``phase_mapping`` entry references an archetype that is not defined in
    the same file.

    If the file does not exist, returns an empty dict and logs a warning
    (design decision D5: graceful degradation).
    """
    global _archetypes, _phase_mapping, _provider_model_map
    if _archetypes is not None:
        return _archetypes

    if path is None:
        path = _default_archetypes_path()

    if not path.exists():
        logger.warning("archetypes.yaml not found at %s — falling back to ambient model", path)
        _archetypes = {}
        _phase_mapping = {}
        return _archetypes

    with open(path) as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        raise ValueError("Empty archetypes.yaml file")

    validate(instance=raw, schema=ARCHETYPES_SCHEMA)
    _validate_local_roster(raw.get("model_aliases"), raw.get("local_host_class"))
    _provider_model_map = _normalize_provider_model_map(raw.get("model_aliases"))

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
        write_capable = bool(data["write_capable"])
        # D3 structured-field enforcement (supervisor invariant): the
        # supervisor archetype is a read-only adjudicator that delegates every
        # change to a write-capable worker. Reject any config that marks it
        # write_capable at load time — fail loud, same posture as the
        # write-capable-phase gate in resolve_archetype_for_phase.
        if name == SUPERVISOR_ARCHETYPE and write_capable:
            raise ValueError(
                f"archetype {SUPERVISOR_ARCHETYPE!r} must be "
                f"write_capable: false — it decomposes and delegates work to "
                f"write-capable worker archetypes and never edits code, specs, "
                f"tests, or configuration directly. Got write_capable: true."
            )
        result[name] = ArchetypeConfig(
            name=name,
            model=data["model"],
            system_prompt=data["system_prompt"],
            write_capable=write_capable,
            escalation=esc_config,
        )

    # Phase mapping (optional, schema_version=2). Validate archetype refs after
    # all archetypes are constructed so cross-references resolve.
    raw_mapping = raw.get("phase_mapping") or {}
    phase_mapping: dict[str, PhaseMappingEntry] = {}
    for phase_name, entry_data in raw_mapping.items():
        archetype_name = entry_data["archetype"]
        if archetype_name not in result:
            raise ValueError(
                f"phase_mapping[{phase_name!r}] references undefined archetype "
                f"{archetype_name!r}; defined archetypes: {sorted(result.keys())}"
            )
        phase_mapping[phase_name] = PhaseMappingEntry(
            archetype=archetype_name,
            signals=list(entry_data.get("signals", [])),
        )

    _archetypes = result
    _phase_mapping = phase_mapping
    return _archetypes


_archetypes: dict[str, ArchetypeConfig] | None = None
_phase_mapping: dict[str, PhaseMappingEntry] | None = None
_provider_model_map: dict[str, Any] | None = None


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


def get_phase_mapping() -> dict[str, PhaseMappingEntry]:
    """Return the loaded phase_mapping. Loads from the default path on miss.

    Returns ``{}`` for legacy ``schema_version=1`` configs that omit
    ``phase_mapping`` entirely (per spec agent-archetypes.1).
    """
    global _phase_mapping
    if _phase_mapping is None:
        load_archetypes_config()
    return _phase_mapping if _phase_mapping is not None else {}


def reset_archetypes_config() -> None:
    """Reset the global archetypes + phase_mapping caches (for testing)."""
    global _archetypes, _phase_mapping, _provider_model_map
    _archetypes = None
    _phase_mapping = None
    _provider_model_map = None


def _served_local_roster(roster: Any) -> Any:
    """Reduce a `local` roster to the tier-entry shape the contract serves.

    ``archetypes.yaml`` carries hardware metadata (``total_params_b``,
    ``active_params_b``, ``reviewed``) on every `local` entry so
    :func:`_validate_local_roster` can enforce the MoE-first rule at startup.
    That metadata is load-time *validation input*, not part of the provider
    model map: ``openspec/schemas/provider-model-map.schema.json`` admits only
    a bare model id or ``{model, thinking}`` per tier, so it is dropped here
    rather than leaking into every consumer of the served map.
    """
    if not isinstance(roster, dict):
        return roster
    served: dict[str, Any] = {}
    for tier, entry in roster.items():
        if isinstance(entry, dict):
            model = entry.get("model")
            thinking = entry.get("thinking")
            if isinstance(model, str) and model:
                served[tier] = (
                    {"model": model, "thinking": thinking}
                    if isinstance(thinking, str) and thinking
                    else model
                )
                continue
        served[tier] = entry
    return served


def _with_served_local_roster(providers: dict[str, Any]) -> dict[str, Any]:
    """Return *providers* with the `local` roster stripped to tier entries.

    Every other provider passes through untouched — resolution output for
    pre-existing providers must stay byte-identical (design D6).
    """
    if LOCAL_PROVIDER not in providers:
        return providers
    return {
        **providers,
        LOCAL_PROVIDER: _served_local_roster(providers[LOCAL_PROVIDER]),
    }


def _normalize_provider_model_map(raw_map: dict[str, Any] | None) -> dict[str, Any]:
    """Return a schema-shaped provider model map.

    ``archetypes.yaml`` stores only the ``model_aliases`` provider object for
    readability, while tests and contracts use the full schema shape.
    """
    if not raw_map:
        return {
            "schema_version": DEFAULT_PROVIDER_MODEL_MAP["schema_version"],
            "tiers": list(DEFAULT_PROVIDER_MODEL_MAP["tiers"]),
            "providers": _with_served_local_roster({
                provider: dict(mapping)
                for provider, mapping in DEFAULT_PROVIDER_MODEL_MAP["providers"].items()
            }),
        }
    if "providers" in raw_map:
        providers = raw_map.get("providers")
        if not isinstance(providers, dict) or LOCAL_PROVIDER not in providers:
            return raw_map
        return {**raw_map, "providers": _with_served_local_roster(providers)}
    return {
        "schema_version": 2,
        "tiers": list(ALL_MODEL_TIERS),
        "providers": _with_served_local_roster({
            provider: dict(mapping)
            for provider, mapping in raw_map.items()
        }),
    }


def get_provider_model_map() -> dict[str, Any]:
    """Return the currently loaded provider model map or defaults."""
    if _provider_model_map is None:
        return _normalize_provider_model_map(None)
    return _provider_model_map


def _tier_entry_to_spec(entry: Any) -> ModelSpec | None:
    """Coerce a provider-map tier entry (string or object form) to a spec."""
    if isinstance(entry, str) and entry:
        return ModelSpec(model=entry)
    if isinstance(entry, dict):
        name = entry.get("model")
        if isinstance(name, str) and name:
            thinking = entry.get("thinking")
            return ModelSpec(
                model=name,
                thinking=thinking if isinstance(thinking, str) and thinking else None,
            )
    return None


def _best_defined_tier(provider_map: dict[str, Any]) -> tuple[str, ModelSpec] | None:
    """Return the highest tier this provider actually defines, if any."""
    for candidate in ALL_MODEL_TIERS:
        spec = _tier_entry_to_spec(provider_map.get(candidate))
        if spec is not None:
            return candidate, spec
    return None


def resolve_provider_model_spec(
    model: str,
    *,
    provider: str | None,
    model_map: dict[str, Any] | None = None,
    reasons: list[str] | None = None,
) -> ModelSpec:
    """Resolve a logical/legacy model value for *provider* to a ModelSpec.

    Without a provider, the source model passes through with no thinking
    level. With a provider, logical tiers and legacy Claude aliases are
    translated through the provider map. Exact provider-specific model IDs
    already present in that provider's mapping are accepted as explicit
    aliases (their tier's thinking level applies).

    When *reasons* is supplied, tier degradations beyond the pre-existing
    optional-tier fallback are appended to it so callers can surface them.
    """
    if not provider:
        return ModelSpec(model=model)

    normalized = _normalize_provider_model_map(model_map or get_provider_model_map())
    providers = normalized.get("providers") or {}
    provider_map = providers.get(provider)
    if not isinstance(provider_map, dict):
        raise ProviderModelMappingError(provider, model)

    tier: str | None
    if model in ALL_MODEL_TIERS:
        tier = model
    else:
        tier = LEGACY_CLAUDE_ALIAS_TO_TIER.get(model)

    if tier:
        spec = _tier_entry_to_spec(provider_map.get(tier))
        if spec is not None:
            return spec
        if tier in OPTIONAL_MODEL_TIERS and provider != LOCAL_PROVIDER:
            # Optional tiers degrade gracefully: a provider without a
            # frontier model serves its premium model instead of failing.
            # `local` is excluded on purpose: this path returns silently, and
            # every local degradation must reach the caller's reasons. A local
            # roster that defines premium but not frontier falls through to the
            # best-defined-tier branch below, which resolves to the same
            # premium entry *and* records why.
            fallback = _tier_entry_to_spec(provider_map.get("premium"))
            if fallback is not None:
                logger.info(
                    "Provider %r has no %r mapping; falling back to premium (%s)",
                    provider, tier, fallback.model,
                )
                return fallback
        # The `local` roster may omit base tiers (frontier/premium): those
        # requests degrade to the best tier it does define. Scoped to `local`
        # on purpose — for every other provider a missing base tier stays a
        # structured mapping error, so their behavior is unchanged.
        degraded = (
            _best_defined_tier(provider_map) if provider == LOCAL_PROVIDER else None
        )
        if degraded is not None:
            best_tier, best_spec = degraded
            logger.info(
                "Provider %r has no %r mapping; degrading to best defined tier "
                "%r (%s)", provider, tier, best_tier, best_spec.model,
            )
            if reasons is not None:
                reasons.append(
                    f"provider={provider} roster omits tier {tier}; degraded to "
                    f"best defined tier {best_tier}"
                )
            return best_spec
        raise ProviderModelMappingError(provider, model, tier)

    for entry in provider_map.values():
        spec = _tier_entry_to_spec(entry)
        if spec is not None and spec.model == model:
            return spec

    raise ProviderModelMappingError(provider, model)


def resolve_provider_model(
    model: str,
    *,
    provider: str | None,
    model_map: dict[str, Any] | None = None,
) -> str:
    """Resolve a logical/legacy model value for *provider* (name only).

    Backward-compatible wrapper over :func:`resolve_provider_model_spec` for
    callers that only need the model id.
    """
    return resolve_provider_model_spec(
        model, provider=provider, model_map=model_map,
    ).model


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
    phase: str | None = None,
    provider: str | None = None,
    model_map: dict[str, Any] | None = None,
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
        phase: Optional autopilot phase name. Currently used only to enrich
            log messages (design decision D3); does not change escalation
            behavior. Reserved for future phase-specific escalation rules.
        provider: Optional provider id. When supplied, the logical or legacy
            archetype model resolves to a provider-specific model ID.

    Returns:
        The resolved model string, or (model, reasons) if *return_reasons*.
    """
    spec, reasons = _resolve_model_spec(
        archetype,
        package_metadata,
        phase=phase,
        provider=provider,
        model_map=model_map,
    )
    return (spec.model, reasons) if return_reasons else spec.model


def _resolve_model_spec(
    archetype: ArchetypeConfig,
    package_metadata: dict[str, Any],
    *,
    phase: str | None = None,
    provider: str | None = None,
    model_map: dict[str, Any] | None = None,
) -> tuple[ModelSpec, list[str]]:
    """Escalation pipeline returning the full ModelSpec (model + thinking)."""
    def _finalize(source_model: str, reasons: list[str]) -> tuple[ModelSpec, list[str]]:
        degradation: list[str] = []
        spec = resolve_provider_model_spec(
            source_model,
            provider=provider,
            model_map=model_map,
            reasons=degradation,
        )
        if degradation:
            reasons = [*reasons, *degradation]
        if provider and spec.model != source_model:
            suffix = f" (thinking={spec.thinking})" if spec.thinking else ""
            reasons = [
                *reasons,
                f"provider={provider} mapped {source_model} to {spec.model}{suffix}",
            ]
        return spec, reasons

    if not archetype.escalation:
        return _finalize(archetype.model, [])

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
        if phase:
            logger.info(
                "Escalating %s to %s for phase %s: %s",
                archetype.name, escalated_model, phase, ", ".join(reasons),
            )
        else:
            logger.info(
                "Escalating %s to %s: %s",
                archetype.name, escalated_model, ", ".join(reasons),
            )
        return _finalize(escalated_model, reasons)

    return _finalize(archetype.model, [])


# ---------------------------------------------------------------------------
# Phase-aware archetype resolution (D2: coordinator-owned phase mapping)
# ---------------------------------------------------------------------------


def resolve_archetype_for_phase(
    phase: str,
    signals: dict[str, Any] | None = None,
    *,
    provider: str | None = None,
) -> ResolvedArchetype:
    """Resolve archetype, model, and system_prompt for an autopilot phase.

    Looks up *phase* in the ``phase_mapping`` section of ``archetypes.yaml``,
    resolves the configured archetype, and runs the standard escalation
    pipeline against *signals* (filtered to the keys listed in the phase
    entry's ``signals`` field — unknown keys are silently dropped).

    Args:
        phase: One of the 13 non-terminal autopilot phase names.
        signals: Free-form signal dict from the caller; only keys listed in
            the phase entry's ``signals`` are used for escalation.

    Returns:
        A :class:`ResolvedArchetype` carrying the model, system prompt,
        archetype name, and a reasons trace.

    Raises:
        KeyError: If *phase* is not present in ``phase_mapping``.
        RuntimeError: If the cached archetypes config has been mutated such
            that the phase entry's archetype reference is no longer valid.
        LocalProviderTrustBoundaryError: If *provider* is ``local`` and the
            phase's archetype is outside :data:`LOCAL_TRUSTED_ARCHETYPES`
            (design D3) — raised before any model resolution or dispatch.
    """
    if _phase_mapping is None:
        load_archetypes_config()
    mapping = _phase_mapping if _phase_mapping is not None else {}

    if phase not in mapping:
        raise KeyError(
            f"Phase {phase!r} not found in phase_mapping; "
            f"defined phases: {sorted(mapping.keys()) or 'none'}"
        )

    entry = mapping[phase]
    archetype = get_archetype(entry.archetype)
    if archetype is None:
        # Validated at load time; this branch only fires if the cache is mutated.
        raise RuntimeError(
            f"phase_mapping[{phase!r}] references undefined archetype "
            f"{entry.archetype!r} (cache may be stale; call "
            f"reset_archetypes_config() and reload)"
        )

    # Enforce the `local` provider trust boundary (design D3) before anything
    # is resolved or dispatched: local models are permitted only where their
    # output is cheap to discard or verified downstream. The coordinator is the
    # single decision point, so no client can route around this check.
    boundary_reasons: list[str] = []
    if provider == LOCAL_PROVIDER:
        if archetype.name not in LOCAL_TRUSTED_ARCHETYPES:
            raise LocalProviderTrustBoundaryError(archetype.name, phase=phase)
        boundary_reasons.append(
            f"provider={LOCAL_PROVIDER} trust boundary checked: archetype="
            f"{archetype.name} is permitted "
            f"({', '.join(sorted(LOCAL_TRUSTED_ARCHETYPES))})"
        )

    # Enforce the write-capability contract at resolution time (design D3 /
    # Task 2.5): a write-capable phase MUST resolve to a write_capable archetype.
    # This is the structured-field gate — no substring matching over prompts.
    if phase in WRITE_CAPABLE_PHASES and not archetype.write_capable:
        raise ValueError(
            f"phase_mapping[{phase!r}] resolves to archetype "
            f"{archetype.name!r} with write_capable=false, but {phase} is a "
            f"write-capable phase that produces files/artifacts/handoffs. "
            f"Map it to an archetype with write_capable: true in archetypes.yaml."
        )

    # Filter signals to keys listed in the phase entry — security-style
    # whitelist that mirrors the spec's "unknown keys silently dropped" rule.
    filtered: dict[str, Any] = {
        k: v for k, v in (signals or {}).items() if k in entry.signals
    }

    spec, escalation_reasons = _resolve_model_spec(
        archetype,
        filtered,
        phase=phase,
        provider=provider,
    )

    reasons: list[str] = [
        f"phase={phase} maps to archetype={archetype.name}",
        # Empty for every provider except `local`, so existing providers keep
        # byte-identical reasons.
        *boundary_reasons,
        *escalation_reasons,
    ]
    if not escalation_reasons:
        reasons.append("no escalation triggered")

    return ResolvedArchetype(
        model=spec.model,
        system_prompt=archetype.system_prompt,
        archetype=archetype.name,
        reasons=reasons,
        provider=provider,
        write_capable=archetype.write_capable,
        thinking=spec.thinking,
    )
