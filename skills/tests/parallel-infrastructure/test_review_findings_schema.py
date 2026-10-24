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


def test_prompt_contract_required_matches_schema():
    from review_findings_schema import prompt_contract

    required, enums = prompt_contract()
    finding = _finding_schema()
    assert set(required) == set(finding["required"])
    assert "axis" in required
    assert "severity" in required
    assert "criticality" in enums
    assert "severity" in enums


def test_existing_code_and_line_resolution_are_optional():
    """add-deterministic-review-preprocessing: existing_code anchor and its
    resolution marker are optional per-finding fields, not required — every
    emitter that predates this change stays valid."""
    finding = _finding_schema()
    props = finding["properties"]
    assert "existing_code" in props
    assert props["existing_code"]["type"] == "string"
    assert "line_resolution" in props
    assert set(props["line_resolution"]["enum"]) == {
        "vendor", "hunk_new", "hunk_old", "file", "unresolved",
    }
    required = finding["required"]
    assert "existing_code" not in required
    assert "line_resolution" not in required


def test_coverage_block_is_optional_and_top_level():
    coverage = SCHEMA["properties"].get("coverage")
    assert coverage is not None, "review-findings.schema.json must define `coverage`"
    assert coverage["type"] == "object"
    assert "reviewed" in coverage["properties"]
    assert "skipped" in coverage["properties"]
    assert "coverage" not in SCHEMA["required"]


def test_snippet_and_coverage_validate_together():
    """A payload with both fields, and one with neither, both pass."""
    validator = Draft202012Validator(SCHEMA)
    minimal = {
        "review_type": "implementation",
        "target": "demo",
        "findings": [{
            "id": 1, "type": "correctness", "criticality": "high",
            "description": "x", "disposition": "fix", "axis": "correctness",
            "severity": "critical",
        }],
    }
    validator.validate(minimal)

    full = {
        "review_type": "implementation",
        "target": "demo",
        "reviewer_vendor": "ocr",
        "coverage": {
            "reviewed": ["a.py"],
            "skipped": [{"path": "b.py", "reason": "too_large"}],
            "rate": 0.5,
        },
        "findings": [{
            "id": 1, "type": "correctness", "criticality": "high",
            "description": "x", "disposition": "fix", "axis": "correctness",
            "severity": "critical", "existing_code": "x = 1",
            "line_resolution": "hunk_new",
        }],
    }
    validator.validate(full)


def test_new_fields_present_in_mirror_and_derived_schema():
    mirror = json.loads(MIRROR_SCHEMA_PATH.read_text())
    mirror_props = mirror["properties"]["findings"]["items"]["properties"]
    assert "existing_code" in mirror_props
    assert "line_resolution" in mirror_props
    assert "coverage" in mirror["properties"]


def test_prompt_contract_block_names_axis_and_severity():
    from review_findings_schema import prompt_contract_block

    block = prompt_contract_block()
    assert "axis" in block
    assert "severity" in block
    assert "criticality" in block


def test_prompt_contract_block_requests_coverage_as_optional():
    from review_findings_schema import prompt_contract_block

    block = prompt_contract_block()
    assert "coverage" in block
    assert "OPTIONAL" in block
    assert "reviewed" in block
    assert "skipped" in block


# ── evidence_level (add-why-mode-to-explain-code-with-epistemic-tiers) ──

EVIDENCE_LEVELS = ["direct", "supported", "inferred", "speculative", "unknown"]


def _minimal_payload(**extra) -> dict:
    finding = {
        "id": 1, "type": "correctness", "criticality": "high",
        "description": "x", "disposition": "fix", "axis": "correctness",
        "severity": "critical",
    }
    finding.update(extra)
    return {"review_type": "implementation", "target": "demo", "findings": [finding]}


def test_evidence_level_is_optional_without_default():
    item = _finding_schema()
    spec = item["properties"]["evidence_level"]
    assert spec["type"] == "string"
    assert spec["enum"] == EVIDENCE_LEVELS
    assert "evidence_level" not in item.get("required", [])
    assert "default" not in spec
    assert not spec.get("readOnly")


def test_evidence_level_validates_known_value_and_rejects_unknown():
    validator = Draft202012Validator(SCHEMA)
    validator.validate(_minimal_payload(evidence_level="inferred"))
    assert list(validator.iter_errors(_minimal_payload(evidence_level="certain")))


def test_evidence_level_mirror_is_byte_identical():
    assert MIRROR_SCHEMA_PATH.read_bytes() == SCHEMA_PATH.read_bytes()


def test_prompt_contract_exposes_evidence_level_in_schema_order():
    from review_findings_schema import prompt_contract, prompt_contract_block

    _, enums = prompt_contract()
    assert list(enums["evidence_level"]) == EVIDENCE_LEVELS
    lines = [ln for ln in prompt_contract_block().splitlines() if "evidence_level" in ln]
    assert len(lines) == 1
    assert "OPTIONAL" in lines[0]
    assert "|".join(EVIDENCE_LEVELS) in lines[0]


def _error_set(validator, doc) -> set:
    return {(tuple(e.absolute_path), e.message) for e in validator.iter_errors(doc)}


def test_evidence_level_adds_no_error_to_committed_findings_documents():
    """Every existing emitter still validates: the new property adds no error."""
    without = json.loads(SCHEMA_PATH.read_text())
    del without["properties"]["findings"]["items"]["properties"]["evidence_level"]
    current_v = Draft202012Validator(SCHEMA)
    without_v = Draft202012Validator(without)
    docs = sorted((REPO_ROOT / "openspec" / "changes").glob("**/findings-*.json"))
    assert docs, "expected committed findings documents to regress against"
    for path in docs:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        added = _error_set(current_v, doc) - _error_set(without_v, doc)
        assert not added, f"{path.relative_to(REPO_ROOT)}: {sorted(added)[:3]}"


def test_invalid_evidence_level_is_dropped_and_the_finding_kept():
    """A bad optional field must not cost the vendor its whole payload (PR #484 class)."""
    from review_findings_schema import coerce_findings_payload, validate_findings_payload

    payload = _minimal_payload(evidence_level="certain")
    payload["findings"].append(dict(payload["findings"][0], id=2, evidence_level="Direct"))
    payload["findings"].append(dict(payload["findings"][0], id=3, evidence_level="inferred"))
    coerced, notes = coerce_findings_payload(payload)
    assert [f["id"] for f in coerced["findings"]] == [1, 2, 3]
    assert "evidence_level" not in coerced["findings"][0]
    assert coerced["findings"][1]["evidence_level"] == "direct"
    assert coerced["findings"][2]["evidence_level"] == "inferred"
    assert "evidence_level:dropped:'certain'" in notes
    assert "evidence_level:Direct->direct" in notes
    assert len([n for n in notes if n.startswith("evidence_level:")]) == 2
    assert validate_findings_payload(coerced) == []


def test_dispatch_keeps_every_finding_when_one_evidence_level_is_bogus():
    from review_dispatcher import CliConfig, CliVendorAdapter, ModeConfig

    base = _minimal_payload()["findings"][0]
    findings = [dict(base, id=i) for i in (1, 2, 3)]
    findings[1]["evidence_level"] = "very-high"
    adapter = CliVendorAdapter(
        agent_id="grok-local",
        vendor="grok",
        cli_config=CliConfig(
            command="grok",
            dispatch_modes={"review": ModeConfig(args=["--output-format", "json"])},
            model_flag="-m",
        ),
    )
    result = adapter._ingest_stdout(
        json.dumps({"findings": findings}), "",
        elapsed=60.0, model_name="m", models_attempted=["m"],
    )
    assert result.success is True, result.error
    assert [f["id"] for f in result.findings["findings"]] == [1, 2, 3]
    assert "evidence_level" not in result.findings["findings"][1]
    assert "evidence_level:dropped:'very-high'" in result.coercions
