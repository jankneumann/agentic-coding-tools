"""Tests for the review-findings.schema.json axis/severity extension."""
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

# Schema lives in the OpenSpec schemas directory at the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "openspec" / "schemas" / "review-findings.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())

# The canonical schema is mirrored in the install payload. agents.yaml carries
# only a sentinel that review_dispatcher resolves from that canonical schema.
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
SCRIPTS_DIR = REPO_ROOT / "skills" / "parallel-infrastructure" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from review_findings_schema import (  # noqa: E402
    GROK_SCHEMA_SENTINEL,
    derive_output_schema,
)

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


def _schema_args_from_agents_yaml() -> list[str]:
    """Return every --json-schema argument found in agents.yaml."""
    config = yaml.safe_load(AGENTS_YAML_PATH.read_text())
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                if item == "--json-schema" and i + 1 < len(node):
                    found.append(node[i + 1])
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


def test_axis_enum_identical_across_canonical_mirror_and_derived_output():
    """The mirror and runtime-derived Grok schema must agree with canonical."""
    canonical = _axis_enum_from_findings_schema(SCHEMA)
    assert canonical == AXIS_ENUM

    mirror = json.loads(MIRROR_SCHEMA_PATH.read_text())
    assert _axis_enum_from_findings_schema(mirror) == canonical, (
        "install_assets mirror axis enum drifted from the canonical schema"
    )

    schema_args = _schema_args_from_agents_yaml()
    assert schema_args, "expected a --json-schema argument in agents.yaml"
    assert set(schema_args) == {GROK_SCHEMA_SENTINEL}

    derived = derive_output_schema(SCHEMA)
    assert _axis_enum_from_findings_schema(derived) == canonical


def test_agents_yaml_type_enum_untouched():
    """The type enum is separate from axis and must keep its own values."""
    derived = derive_output_schema(SCHEMA)
    items = derived["properties"]["findings"]["items"]
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
