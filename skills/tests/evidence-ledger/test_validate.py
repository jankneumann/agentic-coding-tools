"""Single-ledger validation (spec requirements: schema, signals, referential integrity).

Each invalid fixture is named ``<expected_code>__<case>.json``. The test asserts that
the validator reports exactly that code and nothing else, so that a fixture cannot pass
because of an unrelated violation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import evidence_ledger  # on sys.path via conftest.py

FIXTURES = Path(__file__).resolve().parent / "fixtures"

VALID = sorted((FIXTURES / "valid").glob("*"))
INVALID = sorted((FIXTURES / "invalid").glob("*.json"))


def _codes(violations: list[evidence_ledger.Violation]) -> set[str]:
    return {v.code for v in violations}


def test_fixture_directories_are_populated() -> None:
    assert VALID
    assert len(INVALID) >= 15


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_fixtures_have_no_violations(path: Path) -> None:
    doc = evidence_ledger.load_ledger(path)
    assert evidence_ledger.validate_ledger(doc) == []


def test_full_ledger_contains_the_acceptance_shape() -> None:
    """Variable and control facts, a derived signal and a cited hypothesis."""
    doc = evidence_ledger.load_ledger(FIXTURES / "valid" / "full_ledger.json")
    roles = {f["role"] for f in doc["facts"]}
    assert roles == {"variable", "control"}
    assert any(s["classification"] == "signal" for s in doc["signals"])
    assert any(s["classification"] == "noise" for s in doc["signals"])
    assert any(h["cites"] for h in doc["hypotheses"])


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_fixture_reports_exactly_its_code(path: Path) -> None:
    expected = path.stem.split("__", 1)[0]
    assert expected in evidence_ledger.VIOLATION_CODES, expected
    violations = evidence_ledger.validate_ledger(evidence_ledger.load_ledger(path))
    assert _codes(violations) == {expected}, violations


def test_every_single_ledger_code_has_a_fixture() -> None:
    covered = {p.stem.split("__", 1)[0] for p in INVALID}
    assert covered == set(evidence_ledger.SINGLE_LEDGER_CODES)


def test_schema_violation_path_names_the_offending_fact() -> None:
    path = FIXTURES / "invalid" / "schema_violation__fact_missing_tool_version.json"
    (violation,) = evidence_ledger.validate_ledger(evidence_ledger.load_ledger(path))
    assert violation.path == "/facts/0"
    assert "tool_version" in violation.message


def test_signal_role_mismatch_names_the_signal_field() -> None:
    path = FIXTURES / "invalid" / "signal_role_mismatch__control_is_variable.json"
    (violation,) = evidence_ledger.validate_ledger(evidence_ledger.load_ledger(path))
    assert violation.path == "/signals/0/control_fact"


def test_yaml_and_json_report_identical_violations(tmp_path: Path) -> None:
    doc = evidence_ledger.load_ledger(FIXTURES / "valid" / "full_ledger.json")
    doc["signals"][0]["control_fact"] = "F3"
    doc["hypotheses"][0]["cites"].append("F9")
    as_json = tmp_path / "ledger.json"
    as_json.write_text(json.dumps(doc), encoding="utf-8")
    import yaml

    as_yaml = tmp_path / "ledger.yaml"
    as_yaml.write_text(yaml.safe_dump(doc), encoding="utf-8")
    from_json = evidence_ledger.validate_ledger(evidence_ledger.load_ledger(as_json))
    from_yaml = evidence_ledger.validate_ledger(evidence_ledger.load_ledger(as_yaml))
    assert from_json == from_yaml
    assert _codes(from_json) == {"signal_role_mismatch", "unknown_fact_ref"}


def test_unquoted_yaml_timestamps_stay_strings() -> None:
    raw = (FIXTURES / "valid" / "full_ledger.yaml").read_text(encoding="utf-8")
    assert "start: 2026-10-12T02:00:00Z" in raw  # deliberately unquoted
    doc = evidence_ledger.load_ledger(FIXTURES / "valid" / "full_ledger.yaml")
    assert doc["facts"][0]["time_window"]["start"] == "2026-10-12T02:00:00Z"
    assert doc == evidence_ledger.load_ledger(FIXTURES / "valid" / "full_ledger.json")


def test_violations_are_deterministically_ordered() -> None:
    doc = evidence_ledger.load_ledger(FIXTURES / "valid" / "full_ledger.json")
    doc["signals"][0]["control_fact"] = "F3"
    doc["hypotheses"][0]["cites"].append("F9")
    doc["reverify_requests"][0]["fact_id"] = "F8"
    first = evidence_ledger.validate_ledger(doc)
    assert first == evidence_ledger.validate_ledger(doc)
    assert [v.path for v in first] == sorted(v.path for v in first)


def test_non_mapping_document_is_a_schema_violation() -> None:
    violations = evidence_ledger.validate_ledger(["not", "a", "ledger"])
    assert _codes(violations) == {"schema_violation"}
