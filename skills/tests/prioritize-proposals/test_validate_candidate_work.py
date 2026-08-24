"""Tests for the candidate-work schema validation seam (ri-11).

Covers: the canonical schema loads, a conforming fixture passes, a malformed
fixture is rejected with a clear multi-field error, and the CLI exits non-zero
on bad input.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "prioritize-proposals" / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMA_PATH = REPO_ROOT / "openspec" / "schemas" / "candidate-work.schema.json"

sys.path.insert(0, str(SCRIPTS))

from validate_candidate_work import (  # noqa: E402
    CandidateWorkValidationError,
    find_schema_path,
    load_candidate_work,
    load_schema,
    validate_candidate_work,
    validate_candidate_work_batch,
)


def _minimal_valid() -> dict:
    return {
        "schema_version": 1,
        "title": "Do the thing",
        "description": "Make the thing happen.",
        "rationale": "Because a finding said so.",
        "provenance": {
            "source_artifact": "openspec/scrub/report.json",
            "finding_ids": ["f-1"],
        },
        "effort": "S",
        "priority": 1,
        "suggested_change_id": "add-the-thing",
    }


class TestSchemaWiring:
    def test_schema_file_exists_and_has_id(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        assert schema["$id"].endswith("candidate-work.schema.json")
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_find_schema_path_locates_canonical_schema(self):
        assert find_schema_path() == SCHEMA_PATH.resolve()

    def test_required_fields_are_the_canonical_set(self):
        schema = load_schema()
        assert set(schema["required"]) == {
            "schema_version",
            "title",
            "description",
            "rationale",
            "provenance",
            "effort",
            "priority",
            "suggested_change_id",
        }


class TestValidInput:
    def test_minimal_stub_passes(self):
        assert validate_candidate_work(_minimal_valid()) == _minimal_valid()

    def test_valid_fixture_batch_passes(self):
        result = load_candidate_work(FIXTURES / "candidate_work_valid.json")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["suggested_change_id"] == "update-auth-token-refresh"

    def test_empty_finding_ids_allowed(self):
        stub = _minimal_valid()
        stub["provenance"]["finding_ids"] = []
        assert validate_candidate_work(stub)


class TestInvalidInput:
    def test_invalid_fixture_rejected(self):
        with pytest.raises(CandidateWorkValidationError) as exc_info:
            load_candidate_work(FIXTURES / "candidate_work_invalid.json")
        message = str(exc_info.value)
        # The message names the offending fields clearly.
        assert "provenance" in message
        assert "rationale" in message
        # Multiple violations are surfaced at once, not just the first.
        assert len(exc_info.value.errors) >= 3

    def test_missing_required_field_rejected(self):
        stub = _minimal_valid()
        del stub["effort"]
        with pytest.raises(CandidateWorkValidationError) as exc_info:
            validate_candidate_work(stub)
        assert "effort" in str(exc_info.value)

    def test_bad_effort_enum_rejected(self):
        stub = _minimal_valid()
        stub["effort"] = "HUGE"
        with pytest.raises(CandidateWorkValidationError):
            validate_candidate_work(stub)

    def test_priority_below_one_rejected(self):
        stub = _minimal_valid()
        stub["priority"] = 0
        with pytest.raises(CandidateWorkValidationError):
            validate_candidate_work(stub)

    def test_bad_change_id_pattern_rejected(self):
        stub = _minimal_valid()
        stub["suggested_change_id"] = "Fix_Stuff"
        with pytest.raises(CandidateWorkValidationError):
            validate_candidate_work(stub)

    def test_unknown_top_level_field_rejected(self):
        stub = _minimal_valid()
        stub["surprise"] = "not allowed"
        with pytest.raises(CandidateWorkValidationError):
            validate_candidate_work(stub)

    def test_batch_reports_offending_index(self):
        good = _minimal_valid()
        bad = _minimal_valid()
        del bad["title"]
        with pytest.raises(CandidateWorkValidationError) as exc_info:
            validate_candidate_work_batch([good, bad])
        assert exc_info.value.index == 1


class TestCli:
    def test_cli_accepts_valid_fixture(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_candidate_work.py"),
             str(FIXTURES / "candidate_work_valid.json")],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert "valid" in proc.stdout

    def test_cli_rejects_invalid_fixture(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_candidate_work.py"),
             str(FIXTURES / "candidate_work_invalid.json")],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "schema validation" in proc.stderr
