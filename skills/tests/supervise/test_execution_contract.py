"""Fixture validation for the supervised dispatch callback boundary."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_ROOT = (
    _REPO_ROOT
    / "openspec"
    / "contracts"
    / "roadmap-orchestration"
    / "schemas"
)
_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "execution" / "contracts"
_SCHEMA_FILES = {
    "context": "bounded-dispatch-context.schema.json",
    "request": "supervised-dispatch-request.schema.json",
    "result": "supervised-dispatch-result.schema.json",
    "attempt": "delegated-dispatch-attempt.schema.json",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validators() -> dict[str, Draft202012Validator]:
    schemas = {
        name: _load_json(_SCHEMA_ROOT / filename) for name, filename in _SCHEMA_FILES.items()
    }
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    registry = Registry().with_resources(
        [
            (
                schema["$id"],
                Resource.from_contents(schema, default_specification=DRAFT202012),
            )
            for schema in schemas.values()
        ]
    )
    return {
        name: Draft202012Validator(
            schema,
            registry=registry,
            format_checker=FormatChecker(),
        )
        for name, schema in schemas.items()
    }


def _errors(validator: Draft202012Validator, instance: dict[str, Any]) -> list[str]:
    return [error.message for error in validator.iter_errors(instance)]


def test_schema_valid_fixtures_cover_request_result_and_attempt(
    validators: dict[str, Draft202012Validator],
) -> None:
    request = _load_json(_FIXTURE_ROOT / "valid-request.json")
    results = _load_json(_FIXTURE_ROOT / "valid-results.json")
    attempt = _load_json(_FIXTURE_ROOT / "valid-prepared-attempt.json")

    assert _errors(validators["request"], request) == []
    assert _errors(validators["result"], results["success"]) == []
    assert _errors(validators["result"], results["parked"]) == []
    assert _errors(validators["attempt"], attempt) == []


def test_request_context_is_recursively_bounded_and_sanitized(
    validators: dict[str, Draft202012Validator],
) -> None:
    request = _load_json(_FIXTURE_ROOT / "valid-request.json")
    secret = copy.deepcopy(request)
    secret["context"]["routing"]["decision"]["metadata"]["Api_Token"] = "nope"
    over_depth = copy.deepcopy(request)
    over_depth["context"]["routing"]["decision"]["metadata"]["nested"] = {"too_deep": True}

    assert _errors(validators["request"], secret)
    assert _errors(validators["request"], over_depth)
    canonical = json.dumps(request["context"], sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    assert len(canonical) <= 16 * 1024


def test_request_and_result_structurally_exclude_transcripts(
    validators: dict[str, Draft202012Validator],
) -> None:
    request = _load_json(_FIXTURE_ROOT / "valid-request.json")
    result = _load_json(_FIXTURE_ROOT / "valid-results.json")["success"]
    request["context"]["childTranscript"] = "SENTINEL_DO_NOT_PERSIST"
    result["transcript"] = "SENTINEL_DO_NOT_PERSIST"

    assert _errors(validators["request"], request)
    assert _errors(validators["result"], result)


def test_parked_result_requires_a_bounded_snapshot(
    validators: dict[str, Draft202012Validator],
) -> None:
    parked = _load_json(_FIXTURE_ROOT / "valid-results.json")["parked"]
    missing_snapshot = copy.deepcopy(parked)
    missing_snapshot.pop("parked")
    parked["parked"]["reason"] = "x" * 1025

    assert _errors(validators["result"], missing_snapshot)
    assert _errors(validators["result"], parked)


def test_prepared_attempt_cannot_claim_terminal_state(
    validators: dict[str, Draft202012Validator],
) -> None:
    attempt = _load_json(_FIXTURE_ROOT / "valid-prepared-attempt.json")
    attempt["outcome"] = "success"
    attempt["resolved_at"] = "2026-08-31T14:01:00Z"

    assert _errors(validators["attempt"], attempt)


def test_continuation_requires_a_parked_kind_discriminator(
    validators: dict[str, Draft202012Validator],
) -> None:
    request = _load_json(_FIXTURE_ROOT / "invalid-continuation-without-kind.json")

    assert _errors(validators["request"], request)


def test_only_gate_or_policy_parking_authorizes_continuation(
    validators: dict[str, Draft202012Validator],
) -> None:
    request = _load_json(_FIXTURE_ROOT / "invalid-continuation-without-kind.json")
    attempt = _load_json(_FIXTURE_ROOT / "valid-prepared-attempt.json")
    attempt["lease_generation"] = 2
    attempt["continuation"] = {"approval_ref": "approval-ri04-001"}

    assert _errors(validators["attempt"], attempt)
    for parked_kind in ("pending_gate", "policy_pause"):
        request["continuation"]["kind"] = parked_kind
        attempt["continuation"]["kind"] = parked_kind
        assert _errors(validators["request"], request) == []
        assert _errors(validators["attempt"], attempt) == []


def test_attempt_contract_freezes_ack_go_lease_and_quarantine_fields() -> None:
    schema = _load_json(_SCHEMA_ROOT / _SCHEMA_FILES["attempt"])
    properties = schema["properties"]
    assert properties["status"]["enum"] == [
        "prepared",
        "claimed",
        "acknowledged",
        "launched",
        "quarantined",
        "parked",
        "completed",
        "failed",
    ]
    assert set(properties["lease"]["required"]) == {
        "generation",
        "owner_nonce",
        "state",
        "acquired_at",
        "heartbeat_at",
        "expires_at",
    }
    assert set(properties["launch_gate"]["required"]) == {"generation", "state"}
    assert properties["launch_history"]["maxItems"] == 64

    transitions = {
        rule["if"]["properties"]["status"]["const"]: rule["then"]
        for rule in schema["allOf"]
        if "status" in rule.get("if", {}).get("properties", {})
        and "const" in rule["if"]["properties"]["status"]
    }
    assert transitions["claimed"]["properties"]["launch_gate"]["properties"]["state"] == {
        "const": "waiting_ack"
    }
    assert transitions["acknowledged"]["properties"]["launch_gate"]["properties"]["state"] == {
        "const": "go_released"
    }
    assert transitions["launched"]["properties"]["launch_gate"]["properties"]["state"] == {
        "const": "entered"
    }
    assert transitions["quarantined"]["properties"]["lease"]["properties"]["state"] == {
        "const": "uncertain"
    }
    assert "quarantine" in transitions["quarantined"]["required"]
    assert transitions["parked"]["properties"]["lease"]["properties"]["state"] == {
        "const": "released"
    }
