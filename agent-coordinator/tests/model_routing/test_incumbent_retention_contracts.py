"""Static contract checks for the incumbent-retention overlay (v1.2)."""

from __future__ import annotations

import ast
import json
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from openspec_paths import change_dir, repo_root_from

_CHANGE = change_dir(
    repo_root_from(__file__, 3),
    "retain-static-model-until-routing-evidence",
)
_CONTRACTS = _CHANGE / "contracts"
_OPENAPI = _CONTRACTS / "openapi/v1.2.yaml"
_DECISION_RECORD = _CONTRACTS / "events/routing-decision-record.schema.json"
_MODELS = _CONTRACTS / "generated/models.py"

_KEPT = {
    "no-evidence",
    "below-margin",
    "incumbent-unresolved",
    "incumbent-infeasible-no-evidenced-alternative",
}
_NULL_SELECTED = {"incumbent-unresolved", "incumbent-infeasible-no-evidenced-alternative"}


def _schemas() -> dict[str, Any]:
    return yaml.safe_load(_OPENAPI.read_text())["components"]["schemas"]


def _validator(name: str) -> Draft202012Validator:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/components/schemas/{name}",
        "components": {"schemas": _schemas()},
    }
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _record_validator() -> Draft202012Validator:
    schema = json.loads(_DECISION_RECORD.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _assignment() -> dict[str, Any]:
    return {
        "agent_id": "claude-local",
        "vendor_type": "claude_code",
        "policy_vendor": "claude_code",
        "catalog_vendor": "claude_code",
        "location": "local",
        "isolation": "worktree",
        "dispatch_mode": "quick",
        "model": "fable",
        "endpoint_kind": "vendor-cli",
        "base_url": None,
    }


def _provenance(catalog_key: list[Any] | None) -> dict[str, Any]:
    return {
        "source": "coordinator",
        "policy_version": "dg04-v1",
        "policy_checksum": "a" * 64,
        "matched_rule_ids": [],
        "rationale": [],
        "persisted": True,
        "durable_audit": True,
        "catalog_key": catalog_key,
    }


def _retained_response(reason: str = "no-evidence") -> dict[str, Any]:
    assignment = _assignment()
    return {
        "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
        "selected": {
            "vendor": "claude_code",
            "model": "fable",
            "endpoint_kind": "vendor-cli",
            "score": 0.05,
            "assignment": assignment,
        },
        "alternatives": [],
        "assignment": assignment,
        "provenance": _provenance(["claude_code", "fable", "vendor-cli", None]),
        "retention": {"retained": True, "reason": reason, "margin": 0.05, "incumbent_score": 0.05},
    }


def _null_selected_response(reason: str = "incumbent-unresolved") -> dict[str, Any]:
    return {
        "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
        "selected": None,
        "alternatives": [],
        "assignment": None,
        "provenance": _provenance(None),
        "retention": {"retained": True, "reason": reason, "margin": 0.05, "incumbent_score": None},
    }


def test_request_incumbent_is_optional_and_strict() -> None:
    validator = _validator("SelectModelRequest")
    validator.validate({"task_signals": {"archetype": "architect"}})
    validator.validate(
        {
            "task_signals": {"archetype": "architect"},
            "incumbent": {"vendor": None, "model": "premium"},
        }
    )
    for bad in ({"vendor": "claude_code"}, {"model": "fable", "endpoint_kind": "vendor-cli"}):
        with pytest.raises(ValidationError):
            validator.validate({"task_signals": {"archetype": "architect"}, "incumbent": bad})


def test_response_accepts_retained_incumbent_with_selected_candidate() -> None:
    _validator("SelectModelResponse").validate(_retained_response())


@pytest.mark.parametrize("reason", sorted(_NULL_SELECTED))
def test_null_selected_is_valid_only_for_catalogless_retention(reason: str) -> None:
    _validator("SelectModelResponse").validate(_null_selected_response(reason))


@pytest.mark.parametrize("reason", ["no-evidence", "below-margin"])
def test_null_selected_is_rejected_for_catalog_backed_retention(reason: str) -> None:
    with pytest.raises(ValidationError):
        _validator("SelectModelResponse").validate(_null_selected_response(reason))


def test_null_selected_requires_retention() -> None:
    response = _null_selected_response()
    del response["retention"]
    with pytest.raises(ValidationError):
        _validator("SelectModelResponse").validate(response)


def test_non_null_selected_still_requires_an_assignment_object() -> None:
    response = _retained_response()
    response["assignment"] = None
    with pytest.raises(ValidationError):
        _validator("SelectModelResponse").validate(response)


@pytest.mark.parametrize(
    "reason", sorted(set(_schemas()["Retention"]["properties"]["reason"]["enum"]))
)
def test_retained_flag_is_determined_by_reason(reason: str) -> None:
    validator = _validator("Retention")
    retained = reason in _KEPT
    validator.validate({"retained": retained, "reason": reason, "margin": 0.0})
    with pytest.raises(ValidationError):
        validator.validate({"retained": not retained, "reason": reason, "margin": 0.0})


def test_retention_rejects_negative_margin() -> None:
    with pytest.raises(ValidationError):
        _validator("Retention").validate(
            {"retained": True, "reason": "no-evidence", "margin": -0.1}
        )


def _record(selected: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    return {
        "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
        "request": {
            "task_signals": {"archetype": "architect"},
            "incumbent": {"vendor": None, "model": "premium"},
            "allow_exploration": True,
        },
        "selected": selected,
        "alternatives": [],
        "excluded": [],
        "exploration": False,
        "fallback": False,
        "policy_version": "linear-utility-v1",
        "budget_state": {},
        "assignment": {},
        "provenance": {},
        "created_at": "2026-09-23T12:00:00+00:00",
        **extra,
    }


def test_record_persists_retention_and_incumbent_request() -> None:
    retention = {"retained": True, "reason": "incumbent-unresolved", "margin": 0.05}
    _record_validator().validate(_record(None, retention=retention))
    _record_validator().validate(_record({}, retention={**retention, "reason": "no-evidence"}))


def test_record_rejects_null_selected_without_retention() -> None:
    with pytest.raises(ValidationError):
        _record_validator().validate(_record(None))


def test_generated_models_match_overlay_fields() -> None:
    tree = ast.parse(_MODELS.read_text())
    fields = {
        node.name: {
            stmt.target.id
            for stmt in node.body
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            and stmt.target.id != "model_config"
        }
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    schemas = _schemas()
    for name in ("Incumbent", "Retention"):
        assert fields[name] == set(schemas[name]["properties"]), name


def test_record_allows_null_assignment_only_with_null_selected() -> None:
    retention = {"retained": True, "reason": "incumbent-unresolved", "margin": 0.05}
    _record_validator().validate(_record(None, retention=retention, assignment=None))
    with pytest.raises(ValidationError):
        _record_validator().validate(
            _record({}, retention={**retention, "reason": "no-evidence"}, assignment=None)
        )
