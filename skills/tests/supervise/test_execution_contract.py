"""Fixture validation for the supervised dispatch callback boundary."""

from __future__ import annotations

import copy
import hashlib
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
# dispatch-contract D2: the v2 request/result live under openspec/schemas/ and
# the attempt schema $refs them, so the registry spans both directories.
_SCHEMA_DIRS = (_REPO_ROOT / "openspec" / "schemas", _SCHEMA_ROOT)
_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "execution" / "contracts"
_SCHEMA_FILES = {
    "context": _SCHEMA_ROOT / "bounded-dispatch-context.schema.json",
    # Frozen v1 reader schemas (D2): version-1 documents validate here.
    "request": _SCHEMA_ROOT / "supervised-dispatch-request.schema.json",
    "result": _SCHEMA_ROOT / "supervised-dispatch-result.schema.json",
    # The single checkpoint attempt definition.
    "attempt": _SCHEMA_ROOT / "delegated-dispatch-attempt.schema.json",
    "request_v2": _REPO_ROOT / "openspec" / "schemas" / "dispatch-request.schema.json",
    "result_v2": _REPO_ROOT / "openspec" / "schemas" / "dispatch-result.schema.json",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _registry() -> Registry:
    resources = []
    for directory in _SCHEMA_DIRS:
        for path in sorted(directory.glob("*.json")):
            contents = _load_json(path)
            if isinstance(contents, dict) and "$id" in contents:
                resources.append(
                    (
                        contents["$id"],
                        Resource.from_contents(contents, default_specification=DRAFT202012),
                    )
                )
    return Registry().with_resources(resources)


def _legacy_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    """The legacy-reader conversion the checkpoint applies to a v1 attempt (D6, D7).

    The fixture predates launch digests and portable isolation; it is kept
    byte-unchanged, so the conversion happens here at read time.
    """
    converted = copy.deepcopy(attempt)
    token = converted.pop("launch_token")
    converted["launch_digest"] = "sha256:" + hashlib.sha256(token.encode()).hexdigest()
    isolation = converted["isolation"]
    converted["isolation"] = {
        "mode": isolation["mode"],
        "worktree_ref": Path(isolation["worktree_path"]).name,
        "branch": isolation["branch"],
        "host_id": "test-host",
    }
    return converted


@pytest.fixture(scope="module")
def validators() -> dict[str, Draft202012Validator]:
    schemas = {name: _load_json(path) for name, path in _SCHEMA_FILES.items()}
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    registry = _registry()
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
    attempt = _legacy_attempt(_load_json(_FIXTURE_ROOT / "valid-prepared-attempt.json"))

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
    attempt = _legacy_attempt(_load_json(_FIXTURE_ROOT / "valid-prepared-attempt.json"))
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
    attempt = _legacy_attempt(_load_json(_FIXTURE_ROOT / "valid-prepared-attempt.json"))
    attempt["lease_generation"] = 2
    attempt["continuation"] = {"approval_ref": "gate-decision:33333333-4444-4555-8666-777777777777"}

    assert _errors(validators["attempt"], attempt)
    for parked_kind in ("pending_gate", "policy_pause"):
        request["continuation"]["kind"] = parked_kind
        attempt["continuation"]["kind"] = parked_kind
        assert _errors(validators["request"], request) == []
        assert _errors(validators["attempt"], attempt) == []


def test_attempt_contract_freezes_ack_go_lease_and_quarantine_fields() -> None:
    schema = _load_json(_SCHEMA_FILES["attempt"])
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


# --------------------------------------------------------------------------- #
# Version-2 boundary (dispatch-contract D1-D3, D6, D7)
# --------------------------------------------------------------------------- #

_V2_ISOLATION = {
    "mode": "managed_worktree",
    "worktree_ref": "add-alpha-capability",
    "branch": "openspec/add-alpha-capability",
    "host_id": "test-host",
}


def _v2_request() -> dict[str, Any]:
    request = _load_json(_FIXTURE_ROOT / "valid-request.json")
    request["schema_version"] = 2
    request["isolation"] = dict(_V2_ISOLATION)
    request["execution_profile"] = {
        "lanes": {"review": ["claude_code"], "alternative": [], "quick": []},
        "location": "cloud",
        "isolation": "managed_worktree",
        "probe_command": "review_dispatcher.py --check-vendors --json",
    }
    request["review_requirements"] = {
        "min_quorum": {"PLAN_REVIEW": 2, "IMPL_REVIEW": 2, "VAL_REVIEW": 2},
        "counting_lanes": ["claude_code", "codex"],
    }
    request["roadmap_approval_ref"] = "gate-decision:11111111-2222-4333-8444-555555555555"
    return request


def _v2_result(kind: str = "success") -> dict[str, Any]:
    result = _load_json(_FIXTURE_ROOT / "valid-results.json")[kind]
    result["schema_version"] = 2
    result.pop("worktree_path")
    result["worktree_ref"] = "add-alpha-capability"
    result["host_id"] = "test-host"
    result["degradations"] = []
    result["evidence"]["loop_state_path"] = (
        "openspec/changes/add-alpha-capability/loop-state.json"
    )
    if kind == "parked":
        result["parked"]["gate"] = "proposal_approval"
    return result


def test_v2_request_and_results_validate(
    validators: dict[str, Draft202012Validator],
) -> None:
    assert _errors(validators["request_v2"], _v2_request()) == []
    assert _errors(validators["result_v2"], _v2_result("success")) == []
    assert _errors(validators["result_v2"], _v2_result("parked")) == []


def test_v2_result_rejects_absolute_paths_and_roadmap_approval_parks(
    validators: dict[str, Draft202012Validator],
) -> None:
    absolute = _v2_result("success")
    absolute["worktree_ref"] = "/workspace/.git-worktrees/add-alpha-capability"
    escaping = _v2_result("success")
    escaping["evidence"]["loop_state_path"] = "../outside/loop-state.json"
    roadmap_park = _v2_result("parked")
    roadmap_park["parked"]["gate"] = "roadmap_approval"
    free_string_gate = _v2_result("parked")
    free_string_gate["parked"]["gate"] = "implementation_review"

    for document in (absolute, escaping, roadmap_park, free_string_gate):
        assert _errors(validators["result_v2"], document)


def test_v2_gate_answer_travels_only_with_a_continuation(
    validators: dict[str, Draft202012Validator],
) -> None:
    answer = {
        "gate": "escalate_resume",
        "decision": "approved",
        "approval_ref": "gate-decision:33333333-4444-4555-8666-777777777777",
        "provenance": {"source": "human", "approval_ref": None},
    }
    orphan = _v2_request()
    orphan["gate_answer"] = dict(answer)
    assert _errors(validators["request_v2"], orphan)

    request = _v2_request()
    request["lease_generation"] = 2
    request["continuation"] = {
        "kind": "permission_blocked",
        "approval_ref": "gate-decision:33333333-4444-4555-8666-777777777777",
    }
    request["gate_answer"] = dict(answer)
    assert _errors(validators["request_v2"], request) == []
    request["gate_answer"]["gate"] = "roadmap_approval"
    assert _errors(validators["request_v2"], request)


def test_attempt_persists_only_a_launch_digest_and_portable_isolation(
    validators: dict[str, Draft202012Validator],
) -> None:
    raw = _load_json(_FIXTURE_ROOT / "valid-prepared-attempt.json")
    # The raw (legacy) shape is no longer a valid persisted attempt.
    assert _errors(validators["attempt"], raw)
    attempt = _legacy_attempt(raw)
    assert _errors(validators["attempt"], attempt) == []
    attempt["launch_digest"] = "launch-token-0001"
    assert _errors(validators["attempt"], attempt)


def test_checkpoint_attempts_and_results_are_single_definitions() -> None:
    checkpoint = _load_json(_REPO_ROOT / "openspec" / "schemas" / "checkpoint.schema.json")
    attempt = _load_json(_SCHEMA_FILES["attempt"])
    assert checkpoint["properties"]["dispatch_attempts"]["items"] == {
        "$ref": attempt["$id"]
    }
    assert "delegated_dispatch_attempt" not in checkpoint.get("$defs", {})
    result_v2 = _load_json(_SCHEMA_FILES["result_v2"])
    assert attempt["properties"]["application_journal"]["properties"]["result"] == {
        "$ref": result_v2["$id"]
    }


def test_gate_answer_may_name_validate_as_the_resume_target(
    validators: dict[str, Draft202012Validator],
) -> None:
    request = _v2_request()
    request["lease_generation"] = 2
    request["continuation"] = {
        "kind": "policy_pause",
        "approval_ref": "gate-decision:33333333-4444-4555-8666-777777777777",
    }
    request["gate_answer"] = {
        "gate": "escalate_resume",
        "decision": "approved",
        "approval_ref": "gate-decision:33333333-4444-4555-8666-777777777777",
        "resume_at": "VALIDATE",
    }
    assert _errors(validators["request_v2"], request) == []
    request["gate_answer"]["resume_at"] = "IMPLEMENT"
    assert _errors(validators["request_v2"], request)


def test_the_continuation_answer_carries_the_recorded_resume_target() -> None:
    from types import SimpleNamespace

    import execution

    ref = "gate-decision:33333333-4444-4555-8666-777777777777"
    record = {
        "decision_id": ref.removeprefix("gate-decision:"),
        "gate": "escalate_resume",
        "outcome": "proceed",
        "resume_at": "VALIDATE",
    }
    checkpoint = SimpleNamespace(gate_decisions=[record])
    attempt = {"continuation": {"kind": "policy_pause", "approval_ref": ref}}

    assert execution._gate_answer(checkpoint, attempt)["resume_at"] == "VALIDATE"
    record.pop("resume_at")
    assert "resume_at" not in execution._gate_answer(checkpoint, attempt)
