"""Local, coordinator-unreachable fallback for task routing (dg-04 design D8).

Loads the checkout's validated ``routing.yaml``, ``agents.yaml``, and archetype
model map, then derives a deterministic assignment for the caller's
already-resolved static provider/model. This module never contacts the
coordinator, never embeds a live roster, and never fabricates availability --
a lane the coordinator would exclude for being rate-limited or unavailable is
indistinguishable from one that is fine, because no live signal exists once
the coordinator is unreachable. It only combines what the checkout's own
config files say is exactly configured.

Change: implement-the-task-router-vendor-x-location-x-model (dg-04), package
        "Local fallback and bridge".
Design decisions: D3 (rules are ordered/typed/versioned), D8 (local fallback
        is configuration-derived and honest).
Spec: openspec/changes/implement-the-task-router-vendor-x-location-x-model/
      specs/task-routing/spec.md -- Requirement: Honest local fallback.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

_CONSTRAINT_CONFLICT = "__constraint-conflict__"

# Matches contracts/openapi/v1.1.yaml's SelectModelResponse.alternatives.maxItems.
_ALTERNATIVES_MAX = 64

_LOCATION_VALUES = frozenset({"local", "cloud", "unknown"})
_DISPATCH_MODE_VALUES = frozenset({"review", "alternative", "quick", "sdk"})
_SCOPE_VALUES = frozenset({"read-only", "bounded-write", "broad-write"})
_INTERACTIVITY_VALUES = frozenset({"interactive", "headless"})
_SECRET_NEED_VALUES = frozenset({"none", "brokered", "direct"})
_REPO_SHAPE_VALUES = frozenset({"single-package", "monorepo", "unknown"})

_DIRECT_PROFILE_FIELDS = (
    "phase",
    "archetype",
    "scope",
    "interactivity",
    "secret_need",
    "repo_shape",
)

# Mirrors TaskRoutingProfile's pydantic field defaults (api.py). A caller here
# never goes through SelectModelRequest validation -- this path exists
# precisely because the coordinator (which would apply those defaults) is
# unreachable -- so an omitted or explicit-null field must still resolve to
# the same default the coordinator would have used. Leaving it unset instead
# evaluates the policy against an empty profile, which can match a *different*
# rule (or none) than the coordinator would have matched, silently weakening
# routing constraints during an outage (Codex review on PR #605).
_PROFILE_DEFAULTS: dict[str, Any] = {
    "scope": "read-only",
    "interactivity": "headless",
    "secret_need": "none",
    "parallelism": 1,
    "repo_shape": "unknown",
}


def _apply_profile_defaults(profile: dict[str, Any]) -> dict[str, Any]:
    for field_name, default in _PROFILE_DEFAULTS.items():
        if profile.get(field_name) is None:
            profile[field_name] = default
    return profile

_RULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_POLICY_VERSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")

_TOP_LEVEL_FIELDS = frozenset({"schema_version", "policy_version", "defaults", "rules", "fallback"})
_RULE_FIELDS = frozenset({"id", "when", "constrain"})
_DEFAULTS_FIELDS = frozenset({"dispatch_mode", "phase_dispatch_modes"})
_FALLBACK_FIELDS = frozenset({"location_order", "isolation_order", "dispatch_mode_order"})
_WHEN_FIELDS = frozenset(
    {
        "phase",
        "archetype",
        "scope",
        "interactivity",
        "secret_need",
        "min_duration_seconds",
        "max_duration_seconds",
        "min_parallelism",
        "max_parallelism",
        "repo_shape",
    }
)
_CONSTRAIN_FIELDS = frozenset({"location", "isolation", "dispatch_mode"})
_WHEN_ENUM_FIELDS: dict[str, frozenset[str]] = {
    "scope": _SCOPE_VALUES,
    "interactivity": _INTERACTIVITY_VALUES,
    "secret_need": _SECRET_NEED_VALUES,
    "repo_shape": _REPO_SHAPE_VALUES,
}


class LocalRoutingFallbackError(Exception):
    """No exact local lane/dispatch-mode assignment could be derived.

    Raised instead of fabricating an assignment -- see spec scenario
    "No exact local fallback lane exists". Callers should preserve whatever
    static result they already had rather than treat this as routable.
    """


def _archetype_roster() -> Any:
    """Import skills.shared.archetype_roster, tolerating path layouts.

    Mirrors the established import shim in
    ``skills/parallel-infrastructure/scripts/review_dispatcher.py`` so this
    module works the same way whether or not ``skills`` is on the path as a
    package.
    """
    try:
        from skills.shared import archetype_roster  # type: ignore[import-untyped]

        return archetype_roster
    except ImportError:
        shared = Path(__file__).resolve().parents[2] / "shared"
        if str(shared.parent) not in sys.path:
            sys.path.insert(0, str(shared.parent))
        try:
            from skills.shared import archetype_roster  # type: ignore[import-untyped]

            return archetype_roster
        except ImportError:
            import importlib.util

            path = shared / "archetype_roster.py"
            spec = importlib.util.spec_from_file_location("archetype_roster", path)
            if not spec or not spec.loader:
                raise
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod


def find_repo_root(start: Path | None = None) -> Path:
    """Walk parents until ``agent-coordinator/routing.yaml`` is found."""
    cur = (start or Path(__file__).resolve()).parent
    for candidate in (cur, *cur.parents):
        if (candidate / "agent-coordinator" / "routing.yaml").is_file():
            return candidate
    raise FileNotFoundError(
        "could not locate agent-coordinator/routing.yaml above "
        f"{start or Path(__file__)}"
    )


def _routing_yaml_path(repo_root: Path | None) -> Path:
    root = repo_root or find_repo_root()
    return root / "agent-coordinator" / "routing.yaml"


def _agents_yaml_path(repo_root: Path | None) -> Path:
    root = repo_root or find_repo_root()
    return root / "agent-coordinator" / "agents.yaml"


def _isolation_contract(repo_root: Path | None) -> Any:
    """Load the canonical contract from the checkout being routed."""
    root = repo_root or find_repo_root()
    path = root / "agent-coordinator" / "src" / "isolation_contract.py"
    module_name = f"_routing_fallback_isolation_contract_{hash(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load canonical isolation contract at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _reject_unknown_fields(obj: dict[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        raise ValueError(f"{where} has unknown field(s): {sorted(unknown)}")


def _validate_when(when: Any, where: str) -> None:
    if not isinstance(when, dict) or not when:
        raise ValueError(f"{where}.when must be a non-empty mapping")
    _reject_unknown_fields(when, _WHEN_FIELDS, f"{where}.when")
    for field, allowed_values in _WHEN_ENUM_FIELDS.items():
        value = when.get(field)
        if value is not None and value not in allowed_values:
            raise ValueError(f"{where}.when.{field} has an invalid value: {value!r}")
    for field in ("phase", "archetype"):
        value = when.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{where}.when.{field} must be a string")
    for lo, hi in (("min_duration_seconds", "max_duration_seconds"), ("min_parallelism", "max_parallelism")):
        lo_value, hi_value = when.get(lo), when.get(hi)
        floor = 0 if lo == "min_duration_seconds" else 1
        for name, value in ((lo, lo_value), (hi, hi_value)):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < floor):
                raise ValueError(f"{where}.when.{name} must be an integer >= {floor}")
        if lo_value is not None and hi_value is not None and lo_value > hi_value:
            raise ValueError(f"{where}.when has {lo} greater than {hi}")


def _validate_constrain(constrain: Any, where: str, isolation_contract: Any) -> None:
    if not isinstance(constrain, dict) or not constrain:
        raise ValueError(f"{where}.constrain must be a non-empty mapping")
    _reject_unknown_fields(constrain, _CONSTRAIN_FIELDS, f"{where}.constrain")
    for field, allowed_values in (
        ("location", _LOCATION_VALUES),
        ("dispatch_mode", _DISPATCH_MODE_VALUES),
    ):
        value = constrain.get(field)
        if value is not None and value not in allowed_values:
            raise ValueError(f"{where}.constrain.{field} has an invalid value: {value!r}")
    isolation = constrain.get("isolation")
    if isolation is not None:
        isolation_contract.validate_isolation(isolation, rung="routing_policy")


def load_routing_policy_document(repo_root: Path | None = None) -> tuple[dict[str, Any], str]:
    """Load and fully validate ``routing.yaml``. Fails loud, never permissive.

    Returns ``(document, checksum)``. This intentionally re-validates the same
    shape the coordinator's strict pydantic ``RoutingPolicyDocument`` enforces
    (``routing_policy.py``) rather than importing it: this module runs in the
    skills environment, which does not depend on the coordinator package, and
    must still refuse a document the coordinator's own loader would reject --
    duplicate rule IDs, unknown fields, invalid enum values, or an invalid
    phase dispatch mode -- rather than silently ignore the bad parts and route
    anyway (design D8; Codex review on PR #605).
    """
    path = _routing_yaml_path(repo_root)
    isolation_contract = _isolation_contract(repo_root)
    isolation_values = frozenset(isolation_contract.ISOLATION_MODES)
    raw_bytes = path.read_bytes()
    document = yaml.safe_load(raw_bytes)
    if not isinstance(document, dict):
        raise ValueError(f"routing.yaml at {path} must be a mapping")
    _reject_unknown_fields(document, _TOP_LEVEL_FIELDS, f"routing.yaml at {path}")
    if document.get("schema_version") != 1:
        raise ValueError(f"routing.yaml at {path} has unsupported schema_version")
    if not isinstance(document.get("policy_version"), str) or not _POLICY_VERSION_PATTERN.match(
        document["policy_version"]
    ):
        raise ValueError(f"routing.yaml at {path} has an invalid policy_version")

    defaults = document.get("defaults")
    if not isinstance(defaults, dict):
        raise ValueError(f"routing.yaml at {path} is missing defaults")
    _reject_unknown_fields(defaults, _DEFAULTS_FIELDS, f"routing.yaml at {path}: defaults")
    if defaults.get("dispatch_mode") not in _DISPATCH_MODE_VALUES:
        raise ValueError(f"routing.yaml at {path} has an invalid defaults.dispatch_mode")
    phase_dispatch_modes = defaults.get("phase_dispatch_modes")
    if not isinstance(phase_dispatch_modes, dict):
        raise ValueError(f"routing.yaml at {path} has an invalid defaults.phase_dispatch_modes")
    for phase, mode in phase_dispatch_modes.items():
        if not isinstance(phase, str) or mode not in _DISPATCH_MODE_VALUES:
            raise ValueError(
                f"routing.yaml at {path} has an invalid defaults.phase_dispatch_modes entry: "
                f"{phase!r}={mode!r}"
            )
    # Mirror routing_policy.load_routing_policy's cross-check against the
    # authored phase roster: a phase this coordinator was never configured
    # for (a typo like IMPL_REVEIW) must fail loud here exactly as it would
    # against the coordinator's own strict loader (Codex review on PR #605).
    archetypes_path = (repo_root / "agent-coordinator" / "archetypes.yaml") if repo_root else None
    configured_phases = set(_archetype_roster().phase_mapping(archetypes_path))
    unknown_phases = set(phase_dispatch_modes) - configured_phases
    if unknown_phases:
        raise ValueError(
            f"routing.yaml at {path} has an unconfigured phase dispatch default: "
            f"{sorted(unknown_phases)[0]!r}"
        )

    rules = document.get("rules")
    if not isinstance(rules, list):
        raise ValueError(f"routing.yaml at {path} has an invalid rules list")
    seen_ids: set[str] = set()
    for index, rule in enumerate(rules):
        where = f"routing.yaml at {path}: rules[{index}]"
        if not isinstance(rule, dict):
            raise ValueError(f"{where} must be a mapping")
        _reject_unknown_fields(rule, _RULE_FIELDS, where)
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not _RULE_ID_PATTERN.match(rule_id):
            raise ValueError(f"{where}.id is missing or invalid: {rule_id!r}")
        if rule_id in seen_ids:
            raise ValueError(f"routing.yaml at {path} has a duplicate rule id: {rule_id!r}")
        seen_ids.add(rule_id)
        _validate_when(rule.get("when"), where)
        _validate_constrain(rule.get("constrain"), where, isolation_contract)

    fallback = document.get("fallback")
    if not isinstance(fallback, dict):
        raise ValueError(f"routing.yaml at {path} is missing fallback")
    _reject_unknown_fields(fallback, _FALLBACK_FIELDS, f"routing.yaml at {path}: fallback")
    for key, allowed in (
        ("location_order", _LOCATION_VALUES),
        ("isolation_order", isolation_values),
        ("dispatch_mode_order", _DISPATCH_MODE_VALUES),
    ):
        order = fallback.get(key)
        if not isinstance(order, list) or not order or not set(order) <= allowed:
            raise ValueError(f"routing.yaml at {path} has an invalid fallback.{key}")
        if len(order) != len(set(order)):
            raise ValueError(f"routing.yaml at {path} has a duplicate value in fallback.{key}")

    return document, hashlib.sha256(raw_bytes).hexdigest()


def _within(value: Any, minimum: int | None, maximum: int | None) -> bool:
    if minimum is None and maximum is None:
        return True
    if not isinstance(value, int):
        return False
    return (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


def _rule_matches(when: dict[str, Any], profile: dict[str, Any]) -> bool:
    for name in _DIRECT_PROFILE_FIELDS:
        expected = when.get(name)
        if expected is not None and profile.get(name) != expected:
            return False
    return _within(
        profile.get("expected_duration_seconds"),
        when.get("min_duration_seconds"),
        when.get("max_duration_seconds"),
    ) and _within(
        profile.get("parallelism"),
        when.get("min_parallelism"),
        when.get("max_parallelism"),
    )


def evaluate_policy(document: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Port of ``RoutingPolicy.evaluate`` (routing_policy.py) over raw dicts.

    Same first-matching-rule-per-dimension semantics and rationale format, so
    a decision made here is directly comparable to one the coordinator would
    have made from the identical ``routing.yaml`` and profile.
    """
    dimensions: dict[str, str | None] = {"location": None, "isolation": None, "dispatch_mode": None}
    matched: list[str] = []
    rationale: list[str] = []
    for rule in document["rules"]:
        when = rule.get("when") or {}
        if not _rule_matches(when, profile):
            continue
        constrain = rule.get("constrain") or {}
        applied = False
        for dimension in dimensions:
            value = constrain.get(dimension)
            if value is not None and dimensions[dimension] is None:
                dimensions[dimension] = value
                applied = True
                rationale.append(f"rule:{rule.get('id')}:{dimension}={value}")
        if applied:
            matched.append(str(rule.get("id")))

    dispatch_mode = dimensions["dispatch_mode"]
    if dispatch_mode is None:
        phase = profile.get("phase")
        defaults = document["defaults"]
        dispatch_mode = defaults["phase_dispatch_modes"].get(str(phase), defaults["dispatch_mode"])
        rationale.append(f"default:dispatch_mode={dispatch_mode}")

    return {
        "location": dimensions["location"],
        "isolation": dimensions["isolation"],
        "dispatch_mode": dispatch_mode,
        "rule_dispatch_mode": dimensions["dispatch_mode"],
        "matched_rule_ids": tuple(matched),
        "rationale": tuple(rationale),
    }


def _resolve_constraint(explicit: str | None, rule_value: str | None) -> str | None:
    """Mirror ``select_model``'s explicit-vs-rule conflict handling (api.py)."""
    if explicit is not None and rule_value is not None and explicit != rule_value:
        return _CONSTRAINT_CONFLICT
    return explicit if explicit is not None else rule_value


def _lane_model_set(
    entry: dict[str, Any], agent_type: str, model_aliases: dict[str, Any], roster: Any
) -> set[str]:
    """Exact configured model set for a lane -- never inferred or fuzzy.

    Mirrors ``ConfiguredCatalogSync._models`` (configured_catalog.py): an
    ``sdk``-only lane's model set comes only from its own ``sdk`` block; every
    other lane's comes from the authored ``model_aliases`` tier map for its
    ``type``.
    """
    if entry.get("endpoint_kind") == "vendor-sdk" and isinstance(entry.get("sdk"), dict):
        sdk = entry["sdk"]
        models = {sdk.get("model"), *sdk.get("model_fallbacks", [])}
        return {m for m in models if isinstance(m, str) and m}
    provider_tiers = model_aliases.get(agent_type)
    if not isinstance(provider_tiers, dict):
        return set()
    models = set()
    for tier_entry in provider_tiers.values():
        model = roster.tier_entry_model(tier_entry)
        if model:
            models.add(model)
    return models


_STRING_AGENT_FIELDS = ("type", "location", "isolation", "endpoint_kind", "base_url", "policy_vendor", "catalog_vendor")


def _validate_agent_entry(agent_id: str, entry: Any, isolation_contract: Any) -> None:
    """Fail loud on the shape ``local_static_route`` actually reads.

    This is a bounded subset of the coordinator's full ``AGENTS_SCHEMA``
    (``agents_config.py``) -- just the fields this module consumes (type,
    location, isolation, endpoint_kind, base_url, policy_vendor,
    catalog_vendor, and the cli/sdk substructures it reads for dispatch
    modes and model identity). The full schema also enforces trust levels,
    capability enums, and archetype-name patterns this module never reads;
    duplicating those here would mean hand-copying and maintaining a
    security-adjacent schema skills-side with no shared source of truth,
    which is a larger, separate change (extracting AGENTS_SCHEMA to a
    static file both sides load) rather than a bug fix. Codex review on
    PR #605 (round 3) -- see the PR reply for that scoping call.
    """
    where = f"agents.yaml agents.{agent_id}"
    if not isinstance(entry, dict):
        raise ValueError(f"{where} must be a mapping")
    for field_name in _STRING_AGENT_FIELDS:
        value = entry.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{where}.{field_name} must be a string")
    if "isolation" in entry:
        isolation_contract.validate_isolation(
            entry["isolation"], rung=f"agents_yaml agents.{agent_id}"
        )
    cli = entry.get("cli")
    if cli is not None:
        if not isinstance(cli, dict):
            raise ValueError(f"{where}.cli must be a mapping")
        dispatch_modes = cli.get("dispatch_modes")
        if dispatch_modes is not None and not isinstance(dispatch_modes, dict):
            raise ValueError(f"{where}.cli.dispatch_modes must be a mapping")
        if isinstance(dispatch_modes, dict):
            for mode_name, mode in dispatch_modes.items():
                if not isinstance(mode, dict):
                    raise ValueError(
                        f"{where}.cli.dispatch_modes.{mode_name} must be a mapping"
                    )
                if "isolation" in mode:
                    isolation_contract.validate_isolation(
                        mode["isolation"],
                        rung=(
                            f"agents_yaml agents.{agent_id}.cli.dispatch_modes.{mode_name}"
                        ),
                    )
    sdk = entry.get("sdk")
    if sdk is not None:
        if not isinstance(sdk, dict):
            raise ValueError(f"{where}.sdk must be a mapping")
        model = sdk.get("model")
        if model is not None and not isinstance(model, str):
            raise ValueError(f"{where}.sdk.model must be a string")
        fallbacks = sdk.get("model_fallbacks")
        if fallbacks is not None and (
            not isinstance(fallbacks, list) or not all(isinstance(m, str) for m in fallbacks)
        ):
            raise ValueError(f"{where}.sdk.model_fallbacks must be a list of strings")


def _lane_dispatch_modes(entry: dict[str, Any]) -> set[str]:
    modes: set[str] = set()
    cli = entry.get("cli")
    if isinstance(cli, dict) and isinstance(cli.get("dispatch_modes"), dict):
        modes.update(cli["dispatch_modes"].keys())
    if isinstance(entry.get("sdk"), dict):
        modes.add("sdk")
    return modes & _DISPATCH_MODE_VALUES


def _build_assignment(agent_id: str, entry: dict[str, Any], static_provider: str, static_model: str,
                       location: str, isolation: str, dispatch_mode: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "vendor_type": static_provider,
        "policy_vendor": entry.get("policy_vendor") or static_provider,
        "catalog_vendor": entry.get("catalog_vendor") or static_provider,
        "location": location,
        "isolation": isolation,
        "dispatch_mode": dispatch_mode,
        "model": static_model,
        "endpoint_kind": entry.get("endpoint_kind") or "unknown",
        "base_url": entry.get("base_url"),
    }


def _candidate_from_assignment(assignment: dict[str, Any], score: float) -> dict[str, Any]:
    return {
        "vendor": assignment["catalog_vendor"],
        "model": assignment["model"],
        "endpoint_kind": assignment["endpoint_kind"],
        "base_url": assignment["base_url"],
        # Ordinal position among honest local candidates only -- not the
        # dg-00 quality/cost/latency utility score, which needs live catalog
        # data this path deliberately does not have.
        "score": score,
        "quality": None,
        "norm_cost": None,
        "norm_latency": None,
        "posterior_sample_size": None,
        "stale_catalog": False,
        "cost_source": None,
        "assignment": assignment,
    }


def _string_set(value: Any, field_name: str) -> set[str]:
    """Coerce a roadmap-policy list field, rejecting non-list/non-string shapes.

    ``routing_profile`` is caller-supplied and, unlike the HTTP path, never
    passed through ``SelectModelRequest``'s pydantic validation before
    reaching here -- so a malformed shape (a string instead of a list, a
    non-string element) must fail loud with ``ValueError`` rather than raise
    an uncaught ``AttributeError``/``TypeError`` that would break
    ``try_select_model_for_task``'s never-raises contract (Codex review on
    PR #605).
    """
    if value is None:
        return set()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"routing_profile.roadmap_policy.{field_name} must be a list of strings")
    return set(value)


def _parse_roadmap_policy(
    roadmap_policy: Any,
) -> tuple[set[str], set[str], set[str], set[str], set[str]]:
    if roadmap_policy is None:
        return set(), set(), set(), set(), set()
    if not isinstance(roadmap_policy, dict):
        raise ValueError("routing_profile.roadmap_policy must be a mapping")
    return (
        _string_set(roadmap_policy.get("allowed_agent_ids"), "allowed_agent_ids"),
        _string_set(roadmap_policy.get("excluded_agent_ids"), "excluded_agent_ids"),
        _string_set(roadmap_policy.get("allowed_vendor_types"), "allowed_vendor_types"),
        _string_set(roadmap_policy.get("excluded_vendor_types"), "excluded_vendor_types"),
        _string_set(roadmap_policy.get("allowed_locations"), "allowed_locations"),
    )


def local_static_route(
    task_signals: dict[str, Any],
    *,
    static_provider: str,
    static_model: str,
    routing_profile: dict[str, Any] | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Derive a ``SelectModelResponse``-shaped dict without the coordinator.

    ``static_provider``/``static_model`` are the caller's own already-resolved
    static default (e.g. from ``AUTOPILOT_PHASE_MODEL_OVERRIDE`` or a hardcoded
    harness default) -- this function only attaches location/isolation/
    dispatch_mode to that pair, deterministically, from checked-in config. It
    never picks a *different* provider/model: that would require live cost or
    quality data this path does not have.

    Raises ``LocalRoutingFallbackError`` when no exact lane/dispatch-mode
    combination matches; raises ``ValueError``/``FileNotFoundError`` when
    ``routing.yaml``/``agents.yaml`` are missing or malformed (fail loud, per
    design D8 -- never substitute a permissive default).
    """
    document, checksum = load_routing_policy_document(repo_root)
    profile: dict[str, Any] = _apply_profile_defaults(dict(routing_profile or {}))
    profile["phase"] = task_signals.get("phase")
    profile["archetype"] = task_signals.get("archetype")
    evaluation = evaluate_policy(document, profile)

    required_location = _resolve_constraint(profile.get("required_location"), evaluation["location"])
    required_isolation = _resolve_constraint(profile.get("required_isolation"), evaluation["isolation"])
    dispatch_mode = _resolve_constraint(profile.get("required_dispatch_mode"), evaluation["rule_dispatch_mode"])
    if dispatch_mode is None:
        dispatch_mode = evaluation["dispatch_mode"]

    # Same allow/exclude roadmap-policy filters resolver.py's
    # _lane_exclusion_reason applies server-side -- an outage must not route
    # onto a lane/vendor/location the caller explicitly prohibited (Codex
    # review on PR #605).
    (
        allowed_agents,
        excluded_agents,
        allowed_vendor_types,
        excluded_vendor_types,
        allowed_locations_policy,
    ) = _parse_roadmap_policy(profile.get("roadmap_policy"))

    agents_raw = yaml.safe_load(_agents_yaml_path(repo_root).read_bytes())
    if not isinstance(agents_raw, dict) or not isinstance(agents_raw.get("agents"), dict):
        raise ValueError(f"agents.yaml at {_agents_yaml_path(repo_root)} has no 'agents' mapping")
    isolation_contract = _isolation_contract(repo_root)
    for agent_id, entry in agents_raw["agents"].items():
        _validate_agent_entry(agent_id, entry, isolation_contract)
    roster = _archetype_roster()
    archetypes_path = (repo_root / "agent-coordinator" / "archetypes.yaml") if repo_root else None
    model_aliases = roster.model_aliases(archetypes_path)

    fallback = document["fallback"]
    location_order = fallback["location_order"]
    isolation_order = fallback["isolation_order"]
    dispatch_mode_order = fallback["dispatch_mode_order"]

    scored: list[tuple[tuple[int, int, int, str], dict[str, Any]]] = []
    for agent_id, entry in agents_raw["agents"].items():
        if not isinstance(entry, dict) or entry.get("type") != static_provider:
            continue
        if static_model not in _lane_model_set(entry, static_provider, model_aliases, roster):
            continue
        location = str(entry.get("location") or "unknown")
        configured_isolation = isolation_contract.configured_isolation_value(
            entry, dispatch_mode
        )
        isolation = isolation_contract.resolve_isolation(
            router_reachable=False,
            router_value=None,
            configured_value=configured_isolation,
        ).value
        if required_location is not None and location != required_location:
            continue
        if required_isolation is not None and isolation != required_isolation:
            continue
        if allowed_locations_policy and location not in allowed_locations_policy:
            continue
        if allowed_agents and agent_id not in allowed_agents:
            continue
        if agent_id in excluded_agents:
            continue
        if allowed_vendor_types and static_provider not in allowed_vendor_types:
            continue
        if static_provider in excluded_vendor_types:
            continue
        lane_modes = _lane_dispatch_modes(entry)
        if dispatch_mode not in lane_modes:
            continue
        try:
            sort_key = (
                location_order.index(location),
                isolation_order.index(isolation),
                dispatch_mode_order.index(dispatch_mode),
                agent_id,
            )
        except ValueError:
            # Lane carries a location/isolation value the fallback order does
            # not enumerate -- exclude rather than guess a tiebreak position.
            continue
        assignment = _build_assignment(
            agent_id, entry, static_provider, static_model, location, isolation, dispatch_mode
        )
        scored.append((sort_key, assignment))

    if not scored:
        raise LocalRoutingFallbackError(
            f"no exact local lane for provider={static_provider!r} model={static_model!r} "
            f"dispatch_mode={dispatch_mode!r} location={required_location!r} "
            f"isolation={required_isolation!r}"
        )
    scored.sort(key=lambda item: item[0])
    assignments = [assignment for _, assignment in scored]

    candidates = [
        _candidate_from_assignment(assignment, score=1.0 - (0.01 * index))
        for index, assignment in enumerate(assignments)
    ]
    selected = candidates[0]

    return {
        "decision_id": str(uuid.uuid4()),
        "selected": selected,
        # Match contracts/openapi/v1.1.yaml's SelectModelResponse.alternatives
        # maxItems -- a checkout configuring many exact lanes for one
        # provider/model must not emit a contract-invalid response during an
        # outage (Codex review on PR #605, round 6).
        "alternatives": candidates[1:][:_ALTERNATIVES_MAX],
        "exploration": False,
        "fallback": True,
        "excluded": [],
        "assignment": selected["assignment"],
        "provenance": {
            "source": "local-static",
            "policy_version": document["policy_version"],
            "policy_checksum": checksum,
            "matched_rule_ids": list(evaluation["matched_rule_ids"]),
            "rationale": list(evaluation["rationale"]),
            "persisted": False,
            "durable_audit": False,
            "catalog_key": None,
        },
    }
