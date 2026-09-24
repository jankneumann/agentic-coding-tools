"""Static validation for the versioned task-routing policy."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError
from openspec_paths import change_dir, repo_root_from

_ROOT = repo_root_from(__file__, 3)
_CHANGE = change_dir(_ROOT, "implement-the-task-router-vendor-x-location-x-model")
_POLICY = _ROOT / "agent-coordinator/routing.yaml"
_POLICY_SCHEMA = _CHANGE / "contracts/config/routing.schema.json"
_ARCHETYPES = _ROOT / "agent-coordinator/archetypes.yaml"


def _schema() -> dict[str, Any]:
    return json.loads(_POLICY_SCHEMA.read_text())


def _policy() -> dict[str, Any]:
    return yaml.safe_load(_POLICY.read_text())


def test_deployed_policy_matches_versioned_strict_schema() -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_policy())

    assert _policy()["schema_version"] == 1
    assert _policy()["policy_version"] == "dg04-v1"


def test_policy_rules_are_ordered_unique_and_typed() -> None:
    policy = _policy()
    rule_ids = [rule["id"] for rule in policy["rules"]]

    assert rule_ids == [
        "direct-secrets-local",
        "interactive-local",
        "read-only-review",
    ]
    assert len(rule_ids) == len(set(rule_ids))
    assert all(rule["when"] and rule["constrain"] for rule in policy["rules"])


def test_phase_defaults_reference_only_configured_phases() -> None:
    configured_phases = set(yaml.safe_load(_ARCHETYPES.read_text())["phase_mapping"])
    policy_phases = set(_policy()["defaults"]["phase_dispatch_modes"])

    assert policy_phases
    assert policy_phases <= configured_phases


def test_fallback_orders_cover_each_typed_dimension_once() -> None:
    schema = _schema()
    fallback = _policy()["fallback"]

    assert set(fallback["location_order"]) == set(
        schema["$defs"]["location"]["enum"]
    )
    assert set(fallback["isolation_order"]) == set(
        schema["$defs"]["isolation"]["enum"]
    )
    assert set(fallback["dispatch_mode_order"]) == set(
        schema["$defs"]["dispatchMode"]["enum"]
    )


@pytest.mark.parametrize(
    ("path", "invalid_value"),
    [
        (("schema_version",), 2),
        (("defaults", "dispatch_mode"), "auto"),
        (("fallback", "location_order"), ["local", "local"]),
    ],
)
def test_policy_schema_rejects_unsupported_or_ambiguous_values(
    path: tuple[str, ...], invalid_value: Any
) -> None:
    policy = copy.deepcopy(_policy())
    target = policy
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = invalid_value

    with pytest.raises(ValidationError):
        Draft202012Validator(_schema()).validate(policy)


def test_policy_schema_rejects_unknown_fields() -> None:
    policy = copy.deepcopy(_policy())
    policy["allow_unconfigured_lanes"] = True

    with pytest.raises(ValidationError):
        Draft202012Validator(_schema()).validate(policy)
