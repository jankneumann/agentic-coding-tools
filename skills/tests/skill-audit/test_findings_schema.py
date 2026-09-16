"""Contract tests for skill-audit-findings.schema.json (design D5).

The schema shipped under ``install_assets`` is the copy consumers install; it
must stay byte-identical to the change's contract file and reject the shapes
the spec forbids.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

TESTS_DIR = Path(__file__).resolve().parent
SKILLS_ROOT = TESTS_DIR.parents[1]
SCHEMA_PATH = (
    SKILLS_ROOT
    / "skill-audit"
    / "install_assets"
    / "openspec"
    / "schemas"
    / "skill-audit-findings.schema.json"
)
LEDGERS = TESTS_DIR / "fixtures" / "ledgers"


@pytest.fixture(scope="module")
def validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _load(name: str) -> dict:
    return json.loads((LEDGERS / name).read_text(encoding="utf-8"))


def _errors(validator, instance) -> list[str]:
    return [e.message for e in validator.iter_errors(instance)]


def test_minimal_ledger_validates(validator):
    assert _errors(validator, _load("minimal_valid.json")) == []


def test_contract_delete_rejected(validator):
    errors = _errors(validator, _load("contract_delete.json"))
    assert errors, "layer=contract with remediation=delete must fail schema validation"


def test_unknown_kind_rejected(validator):
    errors = _errors(validator, _load("unknown_kind.json"))
    assert any("vibes_bad" in e for e in errors)


def test_benchmark_slot_may_be_null_or_absent(validator):
    ledger = _load("minimal_valid.json")
    finding = ledger["findings"][0]
    finding["evidence"]["benchmark"] = None
    assert _errors(validator, ledger) == []
    finding["evidence"]["benchmark"] = {"runs": 3, "anything": True}
    assert _errors(validator, ledger) == []
    del finding["evidence"]["benchmark"]
    assert _errors(validator, ledger) == []


def test_non_contract_delete_is_allowed(validator):
    ledger = _load("minimal_valid.json")
    ledger["findings"][0]["remediation"] = "delete"
    assert _errors(validator, ledger) == []


def test_unclassified_layer_is_representable(validator):
    ledger = _load("minimal_valid.json")
    ledger["layers"].append(
        {
            "section_id": "SKILL.md#02-notes",
            "file": "SKILL.md",
            "heading": "Notes",
            "layer": "unclassified",
            "decided_by": "none",
        }
    )
    assert _errors(validator, ledger) == []
