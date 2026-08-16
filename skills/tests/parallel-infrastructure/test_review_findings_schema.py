"""Tests for the review-findings.schema.json axis/severity extension."""
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

# Schema lives in the OpenSpec schemas directory at the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "openspec" / "schemas" / "review-findings.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())

# The axis enum is duplicated in three places (canonical schema, the
# install_assets mirror shipped with parallel-infrastructure, and the
# hand-inlined --json-schema block in agent-coordinator/agents.yaml).
# See contracts/review-findings-axis.md rule 1: drift is a test failure.
MIRROR_SCHEMA_PATH = (
    REPO_ROOT
    / "skills"
    / "parallel-infrastructure"
    / "install_assets"
    / "openspec"
    / "schemas"
    / "review-findings.schema.json"
)
AGENTS_YAML_PATH = REPO_ROOT / "agent-coordinator" / "agents.yaml"

AXIS_ENUM = [
    "correctness",
    "readability",
    "architecture",
    "security",
    "performance",
    "observability",
    "resilience",
    "compatibility",
]


def _axis_enum_from_findings_schema(schema: dict) -> list:
    """Pull the axis enum out of a review-findings-shaped JSON schema."""
    items = schema["properties"]["findings"]["items"]
    return items["properties"]["axis"]["enum"]


def _inline_schemas_from_agents_yaml() -> list[dict]:
    """Return every inlined --json-schema payload found in agents.yaml."""
    config = yaml.safe_load(AGENTS_YAML_PATH.read_text())
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                if item == "--json-schema" and i + 1 < len(node):
                    found.append(json.loads(node[i + 1]))
                walk(item)

    walk(config)
    return found


def _finding_schema():
    """Return the schema for a single finding object (handle nested location)."""
    if "$defs" in SCHEMA and "Finding" in SCHEMA["$defs"]:
        return SCHEMA["$defs"]["Finding"]
    if "properties" in SCHEMA and "findings" in SCHEMA["properties"]:
        return SCHEMA["properties"]["findings"]["items"]
    return SCHEMA


def test_axis_field_exists_with_8_enum_values():
    finding = _finding_schema()
    axis = finding.get("properties", {}).get("axis")
    assert axis is not None, "review-findings.schema.json must define `axis` field"
    assert set(axis["enum"]) == set(AXIS_ENUM)


def test_axis_enum_identical_across_all_three_copies():
    """Canonical schema, install_assets mirror, and agents.yaml must agree."""
    canonical = _axis_enum_from_findings_schema(SCHEMA)
    assert canonical == AXIS_ENUM

    mirror = json.loads(MIRROR_SCHEMA_PATH.read_text())
    assert _axis_enum_from_findings_schema(mirror) == canonical, (
        "install_assets mirror axis enum drifted from the canonical schema"
    )

    inline_schemas = _inline_schemas_from_agents_yaml()
    assert inline_schemas, "expected at least one inlined --json-schema in agents.yaml"
    for inline in inline_schemas:
        assert _axis_enum_from_findings_schema(inline) == canonical, (
            "agents.yaml inline axis enum drifted from the canonical schema"
        )


def test_agents_yaml_type_enum_untouched():
    """The `type` enum is separate from `axis` and must keep its own values."""
    for inline in _inline_schemas_from_agents_yaml():
        items = inline["properties"]["findings"]["items"]
        type_enum = set(items["properties"]["type"]["enum"])
        assert {"observability", "compatibility", "resilience"} <= type_enum
        assert "readability" not in type_enum


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
