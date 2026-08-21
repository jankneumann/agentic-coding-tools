"""Tests for the decision-choices.schema.json ledger schema.

Design D4: the header field set matches
skills/prioritize-proposals/scripts/artifact_header.py verbatim
(schema_version, generated_at, git_sha, generator, run_id, event_kind).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "openspec" / "schemas" / "decision-choices.schema.json"
CONTRACT_PATH = (
    REPO_ROOT
    / "openspec"
    / "changes"
    / "add-decision-choices-ledger"
    / "contracts"
    / "decision-choices.schema.json"
)

# The six header fields mandated by artifact_header.make_header() (D4).
EXPECTED_HEADER_FIELDS = {
    "schema_version",
    "generated_at",
    "git_sha",
    "generator",
    "run_id",
    "event_kind",
}

VALID_HEADER = {
    "schema_version": 1,
    "generated_at": "2026-08-21T00:00:00Z",
    "git_sha": "a" * 40,
    "generator": "audit-choices@1.0",
    "run_id": "run-001",
    "event_kind": "choices-ledger",
}

VALID_ENTRY = {
    "stable_id": "0123456789abcdef",
    "choice": "Chose per-request retry budget of 3",
    "scenario": (
        "WHEN a downstream call times out THEN the client retries up to 3 times "
        "with backoff instead of failing fast, as no retry policy was specified."
    ),
    "gap": "The design left retry policy on downstream timeouts unspecified.",
    "reach": "Future callers inherit a 3-retry default unless overridden per call site.",
    "verdict": "sound",
    "verdict_rationale": "Matches the conservative default used elsewhere in the codebase.",
    "confidence": "medium",
    "provenance": {
        "commits": ["abc1234"],
        "files": ["skills/example/scripts/client.py"],
    },
    "self_reported": True,
    "session_log_ref": "add-decision-choices-ledger#D1",
}

VALID_DOCUMENT = {
    "header": VALID_HEADER,
    "change_id": "add-decision-choices-ledger",
    "audited_range": {
        "base_sha": "b" * 40,
        "head_sha": "c" * 40,
    },
    "entries": [VALID_ENTRY],
}


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def test_ledger_schema_valid() -> None:
    """The canonical schema is itself a valid Draft 2020-12 JSON Schema."""
    assert SCHEMA_PATH.exists(), f"missing canonical schema at {SCHEMA_PATH}"
    schema = _load_schema()
    Draft202012Validator.check_schema(schema)


def test_header_required_fields() -> None:
    """The header block requires exactly the six artifact-header fields."""
    schema = _load_schema()
    header_schema = schema["properties"]["header"]
    assert set(header_schema["required"]) == EXPECTED_HEADER_FIELDS
    assert set(header_schema["properties"].keys()) == EXPECTED_HEADER_FIELDS


def test_valid_minimal_ledger_document_validates() -> None:
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    validator.validate(VALID_DOCUMENT)


@pytest.mark.parametrize(
    "missing_field",
    ["gap", "reach", "verdict", "confidence", "provenance", "self_reported"],
)
def test_entries_missing_required_fields_are_rejected(missing_field: str) -> None:
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    doc = copy.deepcopy(VALID_DOCUMENT)
    del doc["entries"][0][missing_field]
    with pytest.raises(ValidationError):
        validator.validate(doc)


def test_verdict_enum_exact() -> None:
    schema = _load_schema()
    entry_schema = schema["$defs"]["entry"]
    assert set(entry_schema["properties"]["verdict"]["enum"]) == {
        "sound",
        "unsound",
        "needs-user",
    }


def test_confidence_enum_exact() -> None:
    schema = _load_schema()
    entry_schema = schema["$defs"]["entry"]
    assert set(entry_schema["properties"]["confidence"]["enum"]) == {
        "low",
        "medium",
        "high",
    }


def test_canonical_matches_contract() -> None:
    """The canonical schema is byte-identical to the frozen contract copy."""
    assert CONTRACT_PATH.exists(), f"missing frozen contract at {CONTRACT_PATH}"
    assert SCHEMA_PATH.read_bytes() == CONTRACT_PATH.read_bytes()
