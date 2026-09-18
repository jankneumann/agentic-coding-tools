"""Tests for finding coercion alias table and coerce_findings_payload."""

from __future__ import annotations

import json
import sys

import pytest
from jsonschema import Draft202012Validator, validate

from openspec_paths import change_dir, repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
CHANGE = change_dir(REPO_ROOT, "harden-review-dispatch-parse-and-timeouts")
CONTRACTS = CHANGE / "contracts"
SCRIPTS = REPO_ROOT / "skills" / "parallel-infrastructure" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text())


def test_coercion_table_validates_against_its_schema() -> None:
    schema = _load("finding-coercion.schema.json")
    Draft202012Validator.check_schema(schema)
    validate(_load("finding-coercion.json"), schema)


def test_timeout_budget_validates_against_its_schema() -> None:
    schema = _load("dispatch-timeout-budget.schema.json")
    Draft202012Validator.check_schema(schema)
    validate(_load("dispatch-timeout-budget.json"), schema)


def test_raw_output_schema_is_draft2020() -> None:
    schema = _load("vendor-raw-output.schema.json")
    Draft202012Validator.check_schema(schema)


def test_bug_type_is_coerced_to_correctness() -> None:
    from review_findings_schema import coerce_findings_payload

    payload = {
        "findings": [
            {
                "id": 1,
                "type": "bug",
                "criticality": "high",
                "description": "Critical: off by one",
                "disposition": "fix",
                "axis": "correctness",
                "severity": "critical",
            }
        ]
    }
    coerced, notes = coerce_findings_payload(payload)
    assert coerced["findings"][0]["type"] == "correctness"
    assert any("type" in n for n in notes)


def test_completeness_type_is_coerced() -> None:
    from review_findings_schema import coerce_findings_payload

    payload = {
        "findings": [
            {
                "id": 1,
                "type": "completeness",
                "criticality": "medium",
                "description": "Nit: missing SHALL",
                "disposition": "fix",
            }
        ]
    }
    coerced, notes = coerce_findings_payload(payload)
    finding = coerced["findings"][0]
    assert finding["type"] == "architecture"
    assert finding["axis"] == "architecture"
    assert finding["severity"] == "nit"
    assert notes


def test_testability_type_sets_correctness_axis() -> None:
    from review_findings_schema import coerce_findings_payload

    payload = {
        "findings": [
            {
                "id": 2,
                "type": "testability",
                "criticality": "low",
                "description": "Optional: no scenario",
                "disposition": "accept",
            }
        ]
    }
    coerced, _notes = coerce_findings_payload(payload)
    finding = coerced["findings"][0]
    assert finding["type"] == "correctness"
    assert finding["axis"] == "correctness"


def test_unknown_type_is_left_for_schema_validation() -> None:
    from review_findings_schema import coerce_findings_payload

    payload = {
        "findings": [
            {
                "id": 3,
                "type": "not-a-real-type",
                "criticality": "high",
                "description": "x",
                "disposition": "fix",
                "axis": "correctness",
                "severity": "critical",
            }
        ]
    }
    coerced, notes = coerce_findings_payload(payload)
    assert coerced["findings"][0]["type"] == "not-a-real-type"
    assert notes == []


def test_severity_filled_from_criticality() -> None:
    from review_findings_schema import coerce_findings_payload

    payload = {
        "findings": [
            {
                "id": 1,
                "type": "security",
                "criticality": "medium",
                "description": "Nit: x",
                "disposition": "fix",
                "axis": "security",
            }
        ]
    }
    coerced, notes = coerce_findings_payload(payload)
    assert coerced["findings"][0]["severity"] == "nit"
    assert any("severity" in n for n in notes)


def test_criticality_filled_from_severity() -> None:
    from review_findings_schema import coerce_findings_payload

    payload = {
        "findings": [
            {
                "id": 1,
                "type": "style",
                "severity": "optional",
                "description": "Optional: name",
                "disposition": "accept",
                "axis": "readability",
            }
        ]
    }
    coerced, notes = coerce_findings_payload(payload)
    assert coerced["findings"][0]["criticality"] == "low"
    assert any("criticality" in n for n in notes)


def _severity_payload(severity: str, criticality: str = "high") -> dict:
    return {
        "review_type": "pr",
        "target": "PR #1",
        "reviewer_vendor": "vendor",
        "findings": [
            {
                "id": 1,
                "type": "correctness",
                "criticality": criticality,
                "severity": severity,
                "description": "d",
                "disposition": "fix",
                "axis": "correctness",
            }
        ],
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("high", "critical"), ("medium", "nit"), ("low", "optional")],
)
def test_criticality_word_in_severity_field_is_coerced(raw: str, expected: str) -> None:
    """A vendor writing ``severity: high`` must not lose its whole review.

    #484 (2026-09-14): one vendor's five findings used ``high``/``medium`` as
    severities, the payload failed validation, and every finding from that
    vendor was discarded before consensus. The contracted
    ``severity_from_criticality`` table already knows these words.
    """
    from review_findings_schema import coerce_findings_payload, validate_findings_payload

    coerced, notes = coerce_findings_payload(_severity_payload(raw))
    assert coerced["findings"][0]["severity"] == expected
    assert f"severity:{raw}->{expected}" in notes
    assert not [e for e in validate_findings_payload(coerced) if "severity" in e]


def test_legal_severity_is_left_alone() -> None:
    from review_findings_schema import coerce_findings_payload

    coerced, notes = coerce_findings_payload(_severity_payload("critical", "critical"))
    assert coerced["findings"][0]["severity"] == "critical"
    assert not [n for n in notes if n.startswith("severity:")]


def test_unknown_severity_still_fails_closed() -> None:
    from review_findings_schema import coerce_findings_payload, validate_findings_payload

    coerced, notes = coerce_findings_payload(_severity_payload("blocker"))
    assert coerced["findings"][0]["severity"] == "blocker"
    assert not [n for n in notes if n.startswith("severity:")]
    assert any("severity" in e for e in validate_findings_payload(coerced))
