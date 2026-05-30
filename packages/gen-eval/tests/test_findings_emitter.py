"""Tests for gen_eval.findings_emitter.

Verifies the behavioral_findings emitter satisfies WP5 of the
factory-missions-architecture-alignment change:

  * emits a ``findings-gen-eval.json`` document conforming to
    ``openspec/schemas/review-findings.schema.json``,
  * preserves OpenSpec source location (``source.openspec_scenario``)
    so behavioral failures point back at the originating spec instead
    of gen-eval's internal scenario YAML,
  * only emits findings for failed scenarios (skips passes),
  * tolerates scenarios without an OpenSpec source by falling back to
    the template_path or "unknown".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from gen_eval.findings_emitter import (
    BehavioralFinding,
    build_findings,
    emit_findings,
    parse_openspec_source,
)

# ---------------------------------------------------------------------------
# Helpers — duck-typed scenario stand-ins
# ---------------------------------------------------------------------------


@dataclass
class _Source:
    openspec_scenario: str | None = None
    template_path: str | None = None


@dataclass
class _Scenario:
    """Minimal duck-typed scenario for emitter tests."""

    scenario_id: str = "s1"
    scenario_name: str = "scenario one"
    status: str = "fail"
    failure_summary: str | None = None
    source: _Source | None = field(default_factory=_Source)


# After relocation from agent-coordinator/tests/test_evaluation/test_gen_eval/
# (4 parents up = repo root) to packages/gen-eval/tests/ (3 parents up = repo
# root), the depth shrinks by one. Recompute relative to __file__.
SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "openspec"
    / "schemas"
    / "review-findings.schema.json"
)


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


# ---------------------------------------------------------------------------
# parse_openspec_source
# ---------------------------------------------------------------------------


class TestParseOpenSpecSource:
    def test_parses_well_formed_ref(self) -> None:
        f, s, e = parse_openspec_source("openspec/changes/foo/specs/api/spec.md:42-50")
        assert f == "openspec/changes/foo/specs/api/spec.md"
        assert s == 42
        assert e == 50

    def test_returns_none_for_empty(self) -> None:
        assert parse_openspec_source(None) == (None, None, None)
        assert parse_openspec_source("") == (None, None, None)

    def test_returns_none_for_unparseable(self) -> None:
        assert parse_openspec_source("not-a-ref") == (None, None, None)
        assert parse_openspec_source("file.md:abc-def") == (None, None, None)


# ---------------------------------------------------------------------------
# emit_findings — schema-valid output and source-location handling
# ---------------------------------------------------------------------------


def test_emit_findings_produces_schema_valid_file(tmp_path: Path) -> None:
    """2 failing scenarios → file exists, validates, has 2 entries with type behavioral_failure."""
    pytest.importorskip("jsonschema")
    import jsonschema

    failing = [
        _Scenario(
            scenario_id=f"fail-{i}",
            scenario_name=f"failing scenario {i}",
            status="fail",
            failure_summary="step exit_code=1",
            source=_Source(template_path="evaluation/gen_eval/scenarios/foo.yaml"),
        )
        for i in range(2)
    ]

    out = tmp_path / "findings-gen-eval.json"
    emit_findings(failed_scenarios=failing, output_path=out, target="demo")

    assert out.exists()

    document = json.loads(out.read_text())
    jsonschema.validate(document, _load_schema())

    assert len(document["findings"]) == 2
    assert all(f["type"] == "behavioral_failure" for f in document["findings"])
    # Required schema fields populated
    for f in document["findings"]:
        assert f["criticality"] in ("low", "medium", "high", "critical")
        assert f["disposition"] in ("fix", "regenerate", "accept", "escalate")
        assert isinstance(f["description"], str) and f["description"]
        assert isinstance(f["id"], int)


def test_emit_findings_preserves_openspec_source_location(tmp_path: Path) -> None:
    """source.openspec_scenario "<file>:<a>-<b>" → location.file/line_start/line_end populated."""
    failing = [
        _Scenario(
            scenario_id="s-openspec",
            scenario_name="openspec-sourced",
            status="fail",
            source=_Source(
                openspec_scenario="openspec/changes/foo/specs/api/spec.md:42-50",
            ),
        )
    ]

    out = tmp_path / "findings-gen-eval.json"
    emit_findings(failed_scenarios=failing, output_path=out, target="foo")

    document = json.loads(out.read_text())
    assert len(document["findings"]) == 1
    f = document["findings"][0]
    assert f["file_path"] == "openspec/changes/foo/specs/api/spec.md"
    assert f["line_range"]["start"] == 42
    assert f["line_range"]["end"] == 50


def test_emit_findings_handles_missing_source(tmp_path: Path) -> None:
    """Without openspec_scenario, fall back to template_path; else "unknown"."""
    no_openspec = _Scenario(
        scenario_id="s-no-os",
        scenario_name="no openspec source",
        status="fail",
        source=_Source(template_path="evaluation/gen_eval/scenarios/foo.yaml"),
    )
    no_source = _Scenario(
        scenario_id="s-bare",
        scenario_name="no source at all",
        status="fail",
        source=None,
    )

    out = tmp_path / "findings-gen-eval.json"
    emit_findings(
        failed_scenarios=[no_openspec, no_source], output_path=out, target="t"
    )

    document = json.loads(out.read_text())
    paths = [f.get("file_path") for f in document["findings"]]
    assert "evaluation/gen_eval/scenarios/foo.yaml" in paths
    assert "unknown" in paths


def test_behavioral_failure_type_validates_against_schema() -> None:
    """A constructed BehavioralFinding must round-trip through the schema."""
    pytest.importorskip("jsonschema")
    import jsonschema

    finding = BehavioralFinding(
        id=1,
        description="behavioral failure in scenario 'x'",
        criticality="high",
        disposition="fix",
        file_path="openspec/changes/foo/specs/api/spec.md",
        line_start=42,
        line_end=50,
    )

    document = {
        "review_type": "implementation",
        "target": "demo",
        "reviewer_vendor": "gen-eval",
        "findings": [finding.to_dict()],
    }

    schema = json.loads(SCHEMA_PATH.read_text())
    # MUST NOT raise
    jsonschema.validate(document, schema)


def test_emit_findings_only_emits_failures(tmp_path: Path) -> None:
    """2 failing + 5 passing → output has 2 entries (passes ignored)."""
    scenarios = [
        _Scenario(scenario_id=f"pass-{i}", status="pass") for i in range(5)
    ] + [_Scenario(scenario_id=f"fail-{i}", status="fail") for i in range(2)]

    out = tmp_path / "findings-gen-eval.json"
    emit_findings(failed_scenarios=scenarios, output_path=out, target="demo")

    document = json.loads(out.read_text())
    assert len(document["findings"]) == 2


def test_behavioral_failure_in_schema_type_enum() -> None:
    """Asserts wp-contracts added behavioral_failure to the schema's type enum."""
    schema = json.loads(SCHEMA_PATH.read_text())
    type_enum = schema["properties"]["findings"]["items"]["properties"]["type"][
        "enum"
    ]
    assert "behavioral_failure" in type_enum


def test_build_findings_skips_passing_scenarios() -> None:
    """build_findings (lower-level helper) also filters by status."""
    scenarios = [
        _Scenario(scenario_id="p", status="pass"),
        _Scenario(scenario_id="f", status="fail"),
        _Scenario(scenario_id="e", status="error"),
        _Scenario(scenario_id="s", status="skip"),
    ]
    findings = build_findings(scenarios)
    assert len(findings) == 2  # fail + error
    assert all(f.type == "behavioral_failure" for f in findings)
