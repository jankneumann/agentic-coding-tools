"""Tests for skills/playwright-validator/scripts/findings.py."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import jsonschema
import pytest

from findings import (
    BehavioralFinding,
    build_findings,
    emit_playwright_findings,
    parse_source_ref,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "openspec" / "schemas" / "review-findings.schema.json"


@dataclass
class _Failure:
    test_name: str
    browser: str
    error_message: str = ""
    file: str | None = None


@dataclass
class _Scenario:
    name: str
    source_ref: str = ""


def test_parse_source_ref_valid():
    f, s, e = parse_source_ref("openspec/changes/x/specs/y/spec.md:42-50")
    assert f == "openspec/changes/x/specs/y/spec.md"
    assert s == 42
    assert e == 50


def test_parse_source_ref_invalid_returns_none_tuple():
    assert parse_source_ref("") == (None, None, None)
    assert parse_source_ref(None) == (None, None, None)
    assert parse_source_ref("no-line-info.md") == (None, None, None)


def test_build_findings_maps_failure_to_scenario():
    scenarios = [
        _Scenario("User logs in", "spec.md:5-20"),
    ]
    failures = [
        _Failure("User logs in", "chromium", "expect(...).toBeVisible failed"),
    ]
    findings = build_findings(failures, scenarios)
    assert len(findings) == 1
    f = findings[0]
    assert f.id == 1
    assert f.type == "behavioral_failure"
    assert f.criticality == "high"
    assert f.disposition == "fix"
    assert f.file_path == "spec.md"
    assert f.line_start == 5
    assert f.line_end == 20
    assert f.metadata["browser"] == "chromium"
    assert f.metadata["scenario_id"] == "User logs in"
    assert "User logs in" in f.description


def test_build_findings_unmatched_failure_falls_back_to_file_field():
    scenarios = []
    failures = [_Failure("Stranded", "firefox", "boom", file="generated.spec.ts")]
    findings = build_findings(failures, scenarios)
    assert findings[0].file_path == "generated.spec.ts"
    assert findings[0].line_start is None
    assert findings[0].line_end is None


def test_build_findings_increments_ids():
    scenarios = [_Scenario("a", "x:1-2"), _Scenario("b", "x:3-4")]
    failures = [_Failure("a", "chromium"), _Failure("b", "firefox")]
    findings = build_findings(failures, scenarios)
    assert [f.id for f in findings] == [1, 2]


def test_emit_playwright_findings_validates_against_schema(tmp_path: Path):
    scenarios = [_Scenario("login", "openspec/changes/foo/specs/ui/spec.md:30-45")]
    failures = [_Failure("login", "chromium", "boom")]
    out = tmp_path / "findings-playwright.json"
    emit_playwright_findings(
        failures=failures,
        scenarios=scenarios,
        output_path=out,
        target="foo",
    )
    schema = json.loads(SCHEMA_PATH.read_text())
    doc = json.loads(out.read_text())
    jsonschema.validate(instance=doc, schema=schema)
    assert doc["reviewer_vendor"] == "playwright"
    assert doc["target"] == "foo"
    assert doc["findings"][0]["type"] == "behavioral_failure"
    assert doc["findings"][0]["line_range"] == {"start": 30, "end": 45}
    assert doc["findings"][0]["file_path"] == "openspec/changes/foo/specs/ui/spec.md"


def test_emit_zero_failures_produces_empty_findings_list(tmp_path: Path):
    out = tmp_path / "findings-playwright.json"
    emit_playwright_findings(
        failures=[],
        scenarios=[],
        output_path=out,
        target="empty",
    )
    schema = json.loads(SCHEMA_PATH.read_text())
    doc = json.loads(out.read_text())
    jsonschema.validate(instance=doc, schema=schema)
    assert doc["findings"] == []


def test_metadata_browser_is_present_for_each_finding(tmp_path: Path):
    """Per the 'Browser matrix' spec scenario."""
    scenarios = [_Scenario("login", "spec.md:1-5")]
    failures = [
        _Failure("login", "chromium", "boom1"),
        _Failure("login", "firefox", "boom2"),
    ]
    out = tmp_path / "findings-playwright.json"
    emit_playwright_findings(
        failures=failures,
        scenarios=scenarios,
        output_path=out,
        target="x",
    )
    doc = json.loads(out.read_text())
    browsers = {f["metadata"]["browser"] for f in doc["findings"]}
    assert browsers == {"chromium", "firefox"}


def test_to_dict_serialization_matches_schema_field_names():
    f = BehavioralFinding(
        id=7,
        description="x",
        criticality="high",
        disposition="fix",
        file_path="a.md",
        line_start=1,
        line_end=2,
        metadata={"browser": "chromium"},
    )
    d = f.to_dict()
    assert d["id"] == 7
    assert d["type"] == "behavioral_failure"
    assert d["file_path"] == "a.md"
    assert d["line_range"] == {"start": 1, "end": 2}
    assert d["metadata"] == {"browser": "chromium"}
