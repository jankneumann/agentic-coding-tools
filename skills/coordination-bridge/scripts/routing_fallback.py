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
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

_CONSTRAINT_CONFLICT = "__constraint-conflict__"

_LOCATION_VALUES = frozenset({"local", "cloud", "unknown"})
_ISOLATION_VALUES = frozenset({"none", "worktree", "sandbox"})
_DISPATCH_MODE_VALUES = frozenset({"review", "alternative", "quick", "sdk"})

_DIRECT_PROFILE_FIELDS = (
    "phase",
    "archetype",
    "scope",
    "interactivity",
    "secret_need",
    "repo_shape",
)


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


def load_routing_policy_document(repo_root: Path | None = None) -> tuple[dict[str, Any], str]:
    """Load and minimally validate ``routing.yaml``. Fails loud, never permissive.

    Returns ``(document, checksum)``. This intentionally re-validates shape
    rather than importing ``agent-coordinator``'s pydantic models: this module
    runs in the skills environment, which does not depend on the coordinator
    package, and must still refuse malformed config rather than invent
    defaults (design D8).
    """
    path = _routing_yaml_path(repo_root)
    raw_bytes = path.read_bytes()
    document = yaml.safe_load(raw_bytes)
    if not isinstance(document, dict):
        raise ValueError(f"routing.yaml at {path} must be a mapping")
    if document.get("schema_version") != 1:
        raise ValueError(f"routing.yaml at {path} has unsupported schema_version")
    if not isinstance(document.get("policy_version"), str) or not document["policy_version"]:
        raise ValueError(f"routing.yaml at {path} is missing policy_version")
    defaults = document.get("defaults")
    if not isinstance(defaults, dict) or defaults.get("dispatch_mode") not in _DISPATCH_MODE_VALUES:
        raise ValueError(f"routing.yaml at {path} has an invalid defaults.dispatch_mode")
    if not isinstance(defaults.get("phase_dispatch_modes"), dict):
        raise ValueError(f"routing.yaml at {path} has an invalid defaults.phase_dispatch_modes")
    if not isinstance(document.get("rules"), list):
        raise ValueError(f"routing.yaml at {path} has an invalid rules list")
    fallback = document.get("fallback")
    if not isinstance(fallback, dict):
        raise ValueError(f"routing.yaml at {path} is missing fallback")
    for key, allowed in (
        ("location_order", _LOCATION_VALUES),
        ("isolation_order", _ISOLATION_VALUES),
        ("dispatch_mode_order", _DISPATCH_MODE_VALUES),
    ):
        order = fallback.get(key)
        if not isinstance(order, list) or not order or not set(order) <= allowed:
            raise ValueError(f"routing.yaml at {path} has an invalid fallback.{key}")
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
    profile: dict[str, Any] = dict(routing_profile or {})
    profile["phase"] = task_signals.get("phase")
    profile["archetype"] = task_signals.get("archetype")
    evaluation = evaluate_policy(document, profile)

    required_location = _resolve_constraint(profile.get("required_location"), evaluation["location"])
    required_isolation = _resolve_constraint(profile.get("required_isolation"), evaluation["isolation"])
    dispatch_mode = _resolve_constraint(profile.get("required_dispatch_mode"), evaluation["rule_dispatch_mode"])
    if dispatch_mode is None:
        dispatch_mode = evaluation["dispatch_mode"]

    agents_raw = yaml.safe_load(_agents_yaml_path(repo_root).read_bytes())
    if not isinstance(agents_raw, dict) or not isinstance(agents_raw.get("agents"), dict):
        raise ValueError(f"agents.yaml at {_agents_yaml_path(repo_root)} has no 'agents' mapping")
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
        isolation = str(entry.get("isolation") or "none")
        if required_location is not None and location != required_location:
            continue
        if required_isolation is not None and isolation != required_isolation:
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
        "alternatives": candidates[1:],
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
