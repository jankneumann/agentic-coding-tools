"""Contract tests for supervisor candidate rubric and digest documents."""

from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from openspec_paths import change_dir

REPO_ROOT = Path(__file__).resolve().parents[3]
CHANGE_SCHEMA_DIR = change_dir(REPO_ROOT, "add-supervisor-candidate-work-digest") / "contracts/schemas"
RUNTIME_SCHEMA_DIR = REPO_ROOT / "openspec/schemas"
FIXTURE_DIR = Path(__file__).parent / "fixtures/digest"
RECORD_FIXTURE_DIR = Path(__file__).parent / "fixtures/supervisor-record"
FACTORS = {"relevance", "value", "readiness", "scope_fit", "risk"}


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_score_coverage(document: dict, expected_keys: list[str]) -> None:
    """Pin rank's semantic validation that JSON Schema cannot express."""
    actual_keys = [score["stub_key"] for score in document["scores"]]
    duplicates = sorted(key for key, count in Counter(actual_keys).items() if count > 1)
    missing = sorted(set(expected_keys) - set(actual_keys))
    unknown = sorted(set(actual_keys) - set(expected_keys))
    defects = []
    if duplicates:
        defects.append(f"duplicate={','.join(duplicates)}")
    if missing:
        defects.append(f"missing={','.join(missing)}")
    if unknown:
        defects.append(f"unknown={','.join(unknown)}")
    if defects:
        raise ValueError("; ".join(defects))


@pytest.fixture(scope="module")
def rubric_schema() -> dict:
    return _load_json(RUNTIME_SCHEMA_DIR / "supervise-rubric-score.schema.json")


@pytest.fixture(scope="module")
def digest_schema() -> dict:
    return _load_json(RUNTIME_SCHEMA_DIR / "supervise-digest.schema.json")


@pytest.fixture
def rubric_document() -> dict:
    return _load_json(FIXTURE_DIR / "rubric-valid.json")


@pytest.fixture
def digest_document() -> dict:
    return _load_json(FIXTURE_DIR / "digest-valid.json")


def test_change_local_and_runtime_schemas_are_valid_and_byte_identical(rubric_schema: dict, digest_schema: dict) -> None:
    pairs = (
        ("rubric-score.schema.json", "supervise-rubric-score.schema.json", rubric_schema),
        ("digest.schema.json", "supervise-digest.schema.json", digest_schema),
    )
    for source_name, runtime_name, schema in pairs:
        Draft202012Validator.check_schema(schema)
        assert (CHANGE_SCHEMA_DIR / source_name).read_bytes() == (RUNTIME_SCHEMA_DIR / runtime_name).read_bytes()


def test_valid_rubric_document_has_exactly_five_justified_factors(rubric_schema: dict, rubric_document: dict) -> None:
    _validator(rubric_schema).validate(rubric_document)
    for score in rubric_document["scores"]:
        assert FACTORS == (set(score) & FACTORS)
        assert all(score[factor]["justification"] for factor in FACTORS)


@pytest.mark.parametrize("invalid_key", [
    "change:feature", "change:Add-feature", "change:add_feature", "change:add-feature/escape",
    "prov:0123456789abcdef", "prov:0123456789ABCDEF0123456789ABCDEF",
    "other:0123456789abcdef0123456789abcdef",
])
def test_rubric_rejects_noncanonical_stub_keys(rubric_schema: dict, rubric_document: dict, invalid_key: str) -> None:
    rubric_document["scores"][0]["stub_key"] = invalid_key
    with pytest.raises(jsonschema.ValidationError):
        _validator(rubric_schema).validate(rubric_document)


@pytest.mark.parametrize("factor", sorted(FACTORS))
def test_rubric_rejects_a_missing_factor_or_justification(rubric_schema: dict, rubric_document: dict, factor: str) -> None:
    missing_factor = copy.deepcopy(rubric_document)
    del missing_factor["scores"][0][factor]
    with pytest.raises(jsonschema.ValidationError):
        _validator(rubric_schema).validate(missing_factor)
    missing_justification = copy.deepcopy(rubric_document)
    del missing_justification["scores"][0][factor]["justification"]
    with pytest.raises(jsonschema.ValidationError):
        _validator(rubric_schema).validate(missing_justification)


@pytest.mark.parametrize(("mutation", "defect"), [
    ("duplicate", "duplicate=change:add-candidate-digest"),
    ("missing", "missing=prov:0123456789abcdef0123456789abcdef"),
    ("unknown", "unknown=change:update-unknown-candidate"),
])
def test_score_coverage_semantics_reject_duplicate_missing_and_unknown_keys(
    rubric_schema: dict, rubric_document: dict, mutation: str, defect: str
) -> None:
    expected = [score["stub_key"] for score in rubric_document["scores"]]
    if mutation == "duplicate":
        rubric_document["scores"].append(copy.deepcopy(rubric_document["scores"][0]))
    elif mutation == "missing":
        rubric_document["scores"].pop()
    else:
        rubric_document["scores"][0]["stub_key"] = "change:update-unknown-candidate"
    _validator(rubric_schema).validate(rubric_document)
    with pytest.raises(ValueError, match=defect):
        _validate_score_coverage(rubric_document, expected)


def test_digest_document_carries_complete_interpretable_ranking_policy(digest_schema: dict, digest_document: dict) -> None:
    _validator(digest_schema).validate(digest_document)
    assert set(digest_document["ranked"][0]["factors"]) == FACTORS
    assert set(digest_document["ranked"][0]["justifications"]) == FACTORS
    assert set(digest_document["weights"]) == {
        "relevance", "value", "readiness", "scope_fit", "risk", "staleness_penalty_per_30d",
        "staleness_penalty_cap", "risk_higher_is_safer", "decision_bucket_order",
        "dependency_bucket_order", "tie_breaker",
    }


def test_digest_rejects_missing_factor_justification(digest_schema: dict, digest_document: dict) -> None:
    del digest_document["ranked"][0]["justifications"]["risk"]
    with pytest.raises(jsonschema.ValidationError):
        _validator(digest_schema).validate(digest_document)


@pytest.mark.parametrize(
    "decision_name",
    ["approved_refine_roadmap", "approved_plan_roadmap", "deferred", "rejected", "pending"],
)
def test_decision_metadata_round_trips_through_both_record_schemas(decision_name: str) -> None:
    decisions = _load_json(FIXTURE_DIR / "supervisor-decisions.json")
    full_record = _load_json(RECORD_FIXTURE_DIR / "minimal.json")
    full_record["back_edge"]["digested_stubs"] = [decisions[decision_name]]
    mirror_record = {
        key: copy.deepcopy(value)
        for key, value in full_record.items()
        if key not in {"written_by", "active_changes"}
    }
    _validator(_load_json(RUNTIME_SCHEMA_DIR / "supervisor-record.schema.json")).validate(full_record)
    _validator(_load_json(RUNTIME_SCHEMA_DIR / "supervisor-record-mirror.schema.json")).validate(mirror_record)


@pytest.mark.parametrize(
    ("decision_name", "removed_field"),
    [("approved_refine_roadmap", "route"), ("approved_refine_roadmap", "roadmap_ref"), ("rejected", "reason")],
)
def test_record_schemas_reject_missing_decision_metadata(decision_name: str, removed_field: str) -> None:
    decisions = _load_json(FIXTURE_DIR / "supervisor-decisions.json")
    record = _load_json(RECORD_FIXTURE_DIR / "minimal.json")
    decision = copy.deepcopy(decisions[decision_name])
    del decision[removed_field]
    record["back_edge"]["digested_stubs"] = [decision]
    with pytest.raises(jsonschema.ValidationError):
        _validator(_load_json(RUNTIME_SCHEMA_DIR / "supervisor-record.schema.json")).validate(record)


def test_approved_decision_requires_a_non_null_route() -> None:
    decisions = _load_json(FIXTURE_DIR / "supervisor-decisions.json")
    record = _load_json(RECORD_FIXTURE_DIR / "minimal.json")
    decision = copy.deepcopy(decisions["approved_plan_roadmap"])
    decision["route"] = None
    record["back_edge"]["digested_stubs"] = [decision]
    with pytest.raises(jsonschema.ValidationError):
        _validator(_load_json(RUNTIME_SCHEMA_DIR / "supervisor-record.schema.json")).validate(record)


def test_plan_roadmap_approval_requires_null_roadmap_ref() -> None:
    decisions = _load_json(FIXTURE_DIR / "supervisor-decisions.json")
    record = _load_json(RECORD_FIXTURE_DIR / "minimal.json")
    decision = copy.deepcopy(decisions["approved_plan_roadmap"])
    decision["roadmap_ref"] = "roadmap-supervisor-orchestration:ri-13"
    record["back_edge"]["digested_stubs"] = [decision]
    with pytest.raises(jsonschema.ValidationError):
        _validator(_load_json(RUNTIME_SCHEMA_DIR / "supervisor-record.schema.json")).validate(record)
