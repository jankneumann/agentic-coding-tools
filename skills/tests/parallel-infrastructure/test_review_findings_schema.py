"""Tests for the review-findings.schema.json axis/severity extension."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

# Schema lives in the OpenSpec schemas directory at the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "openspec" / "schemas" / "review-findings.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())


def _finding_schema():
    """Return the schema for a single finding object (handle nested location)."""
    if "$defs" in SCHEMA and "Finding" in SCHEMA["$defs"]:
        return SCHEMA["$defs"]["Finding"]
    if "properties" in SCHEMA and "findings" in SCHEMA["properties"]:
        return SCHEMA["properties"]["findings"]["items"]
    return SCHEMA


def test_axis_field_exists_with_5_enum_values():
    finding = _finding_schema()
    axis = finding.get("properties", {}).get("axis")
    assert axis is not None, "review-findings.schema.json must define `axis` field"
    assert set(axis["enum"]) == {
        "correctness",
        "readability",
        "architecture",
        "security",
        "performance",
    }


def test_severity_field_exists_with_5_enum_values():
    finding = _finding_schema()
    sev = finding.get("properties", {}).get("severity")
    assert sev is not None, "review-findings.schema.json must define `severity` field"
    assert set(sev["enum"]) == {"critical", "nit", "optional", "fyi", "none"}


def test_axis_and_severity_required():
    finding = _finding_schema()
    required = finding.get("required", [])
    assert "axis" in required, "axis must be required"
    assert "severity" in required, "severity must be required"


def test_existing_required_fields_preserved():
    """Pre-existing required fields must remain after the extension."""
    finding = _finding_schema()
    required = finding.get("required", [])
    for field in ("id", "type", "criticality", "description", "disposition"):
        assert field in required, f"pre-existing required field {field!r} was dropped"


def test_schema_is_valid_jsonschema():
    """Sanity check: the schema is itself a valid Draft 2020-12 schema."""
    Draft202012Validator.check_schema(SCHEMA)
