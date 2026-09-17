"""Static contract checks for the additive DG-04 routing surface."""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from openspec_paths import change_dir, repo_root_from

_CHANGE = change_dir(
    repo_root_from(__file__, 3),
    "implement-the-task-router-vendor-x-location-x-model",
)
_CONTRACTS = _CHANGE / "contracts"
_OPENAPI = _CONTRACTS / "openapi/v1.1.yaml"
_DECISION_RECORD = _CONTRACTS / "events/routing-decision-record.schema.json"
_AUDIT_LINK = _CONTRACTS / "events/routing-decision.schema.json"


def _openapi() -> dict[str, Any]:
    return yaml.safe_load(_OPENAPI.read_text())


def _json_schema(path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _openapi_schema_validator(name: str) -> Draft202012Validator:
    schemas = _openapi()["components"]["schemas"]
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/components/schemas/{name}",
        "components": {"schemas": schemas},
    }
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _valid_assignment() -> dict[str, Any]:
    return {
        "agent_id": "codex-local",
        "vendor_type": "codex",
        "policy_vendor": "codex",
        "catalog_vendor": "codex",
        "location": "local",
        "isolation": "worktree",
        "dispatch_mode": "quick",
        "model": "gpt-5.6-terra",
        "endpoint_kind": "vendor-cli",
        "base_url": None,
    }


def test_overlay_extends_only_existing_select_model_operation() -> None:
    document = _openapi()

    assert document["openapi"] == "3.1.0"
    assert set(document["paths"]) == {"/routing/select_model"}
    assert set(document["paths"]["/routing/select_model"]) == {"post"}
    assert "/route/task" not in document["paths"]


def test_request_keeps_legacy_signals_permissive_and_profile_strict() -> None:
    schemas = _openapi()["components"]["schemas"]
    request = schemas["SelectModelRequest"]

    assert request["required"] == ["task_signals"]
    assert request["properties"]["task_signals"]["additionalProperties"] is True
    assert "routing_profile" not in request["required"]
    assert schemas["TaskRoutingProfile"]["additionalProperties"] is False
    assert schemas["RoadmapRoutingPolicy"]["additionalProperties"] is False

    _openapi_schema_validator("SelectModelRequest").validate(
        {
            "task_signals": {
                "archetype": "implementer",
                "write_allow": ["agent-coordinator/routing.yaml"],
            },
            "routing_profile": {
                "expected_duration_seconds": 900,
                "scope": "bounded-write",
                "interactivity": "headless",
                "secret_need": "brokered",
                "parallelism": 2,
                "repo_shape": "monorepo",
                "roadmap_policy": {
                    "allowed_agent_ids": ["codex-local"],
                    "allowed_locations": ["local"],
                },
                "required_isolation": "worktree",
                "required_dispatch_mode": "quick",
            },
        }
    )


@pytest.mark.parametrize(
    "routing_profile",
    [
        {"expected_duration_seconds": -1},
        {"parallelism": 0},
        {"scope": "repository"},
        {"roadmap_policy": {"write_allow": ["secrets/**"]}},
        {"unexpected": True},
    ],
)
def test_task_profile_rejects_invalid_or_unbounded_fields(
    routing_profile: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        _openapi_schema_validator("SelectModelRequest").validate(
            {
                "task_signals": {"archetype": "implementer"},
                "routing_profile": routing_profile,
            }
        )


def test_success_contract_requires_assignment_and_provenance() -> None:
    schemas = _openapi()["components"]["schemas"]
    response = schemas["SelectModelResponse"]
    candidate = schemas["Candidate"]

    assert {"assignment", "provenance"} <= set(response["required"])
    assert "assignment" in candidate["required"]
    assert (
        response["properties"]["assignment"]
        == candidate["properties"]["assignment"]
        == {"$ref": "#/components/schemas/RoutingAssignment"}
    )
    assert schemas["RoutingAssignment"]["additionalProperties"] is False
    assert schemas["RoutingProvenance"]["additionalProperties"] is False

    assignment = _valid_assignment()
    candidate_value = {
        "vendor": "codex",
        "model": "gpt-5.6-terra",
        "endpoint_kind": "vendor-cli",
        "score": 0.9,
        "assignment": assignment,
    }
    _openapi_schema_validator("SelectModelResponse").validate(
        {
            "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
            "selected": candidate_value,
            "alternatives": [],
            "assignment": assignment,
            "provenance": {
                "source": "coordinator",
                "policy_version": "dg04-v1",
                "policy_checksum": "a" * 64,
                "matched_rule_ids": ["interactive-local"],
                "rationale": ["rule:interactive-local"],
                "persisted": True,
                "durable_audit": True,
                "catalog_key": [
                    "codex",
                    "gpt-5.6-terra",
                    "vendor-cli",
                    None,
                ],
            },
        }
    )


def _valid_local_fallback_response() -> dict[str, Any]:
    assignment = _valid_assignment()
    return {
        "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
        "selected": {
            "vendor": "codex",
            "model": "gpt-5.6-terra",
            "endpoint_kind": "vendor-cli",
            "score": 0.0,
            "assignment": assignment,
        },
        "alternatives": [],
        "fallback": True,
        "assignment": assignment,
        "provenance": {
            "source": "local-static",
            "policy_version": "dg04-v1",
            "policy_checksum": "a" * 64,
            "matched_rule_ids": [],
            "rationale": ["coordinator-unreachable"],
            "persisted": False,
            "durable_audit": False,
            "catalog_key": None,
        },
    }


def test_local_fallback_contract_accepts_honest_provenance() -> None:
    _openapi_schema_validator("SelectModelResponse").validate(
        _valid_local_fallback_response()
    )


@pytest.mark.parametrize(
    ("field", "dishonest_value"),
    [
        ("source", "coordinator"),
        ("persisted", True),
        ("durable_audit", True),
        ("catalog_key", ["codex", "gpt-5.6-terra", "vendor-cli", None]),
    ],
)
def test_local_fallback_contract_rejects_dishonest_provenance(
    field: str, dishonest_value: Any
) -> None:
    response = _valid_local_fallback_response()
    response["provenance"][field] = dishonest_value

    with pytest.raises(ValidationError):
        _openapi_schema_validator("SelectModelResponse").validate(response)


def test_persistence_contract_is_bounded_and_strips_no_fields_implicitly() -> None:
    schema = _json_schema(_DECISION_RECORD)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    record = {
        "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
        "request": {
            "task_signals": {"archetype": "implementer"},
            "routing_profile": {
                "roadmap_policy": {"allowed_agent_ids": ["codex-local"]}
            },
            "allow_exploration": False,
        },
        "selected": {},
        "alternatives": [],
        "excluded": [],
        "exploration": False,
        "fallback": False,
        "policy_version": "linear-utility-v1",
        "budget_state": {},
    }
    validator.validate(record)

    for invalid_request in (
        {
            "task_signals": {
                "archetype": "implementer",
                "write_allow": ["agent-coordinator/**"],
            },
            "allow_exploration": False,
        },
        {
            "task_signals": {"archetype": "implementer"},
            "routing_profile": {
                "roadmap_policy": {"paths": ["agent-coordinator/**"]}
            },
            "allow_exploration": False,
        },
        {
            "task_signals": {"archetype": "implementer"},
            "routing_profile": {
                "roadmap_policy": {
                    "allowed_agent_ids": [f"agent-{index}" for index in range(65)]
                }
            },
            "allow_exploration": False,
        },
    ):
        invalid = {**record, "request": invalid_request}
        with pytest.raises(ValidationError):
            validator.validate(invalid)


def test_audit_link_is_schema_valid_and_coordinator_only() -> None:
    schema = _json_schema(_AUDIT_LINK)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    event = {
        "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
        "selected_agent_id": "codex-local",
        "selected_model": "gpt-5.6-terra",
        "routing_policy_version": "dg04-v1",
        "routing_policy_checksum": "a" * 64,
        "source": "coordinator",
        "success": True,
    }
    validator.validate(event)

    with pytest.raises(ValidationError):
        validator.validate({**event, "source": "local-static"})
