"""Findings emitter conforms to review-findings.schema.json."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from agent_scenarios import FakeExecutor, Outcome, PRRef, load_scenario, run_scenario
from agent_scenarios.findings_emitter import build_findings, emit_findings
from agent_scenarios.models import (
    GateVerdict,
    ParityMatrix,
    TrajectoryFinding,
    TrajectoryVerdict,
    VendorRunVerdict,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "openspec" / "schemas" / "review-findings.schema.json"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _matrix_with_failures() -> ParityMatrix:
    return ParityMatrix(
        scenario_id="fix-add",
        scenario_name="fix add",
        results=[
            VendorRunVerdict(
                scenario_id="fix-add",
                vendor="gemini",
                gate_verdicts=[
                    GateVerdict(
                        gate_id="fixed",
                        check="file",
                        mode="verify",
                        status="fail",
                        detail="not fixed",
                    ),
                    GateVerdict(
                        gate_id="ok", check="branch", mode="verify", status="pass", detail="ok"
                    ),
                ],
                trajectory=TrajectoryVerdict(
                    status="fail",
                    reasoning="wasteful",
                    findings=[
                        TrajectoryFinding(
                            kind="inefficiency", description="re-read 5x", severity="medium"
                        ),
                        TrajectoryFinding(
                            kind="wrong_but_passed", description="hardcoded", severity="high"
                        ),
                    ],
                ),
                deterministic_status="fail",
            ),
        ],
    )


def test_build_findings_maps_gates_and_judge() -> None:
    findings = build_findings([_matrix_with_failures()])
    # 1 failed gate + 2 judge findings.
    assert len(findings) == 3
    types = {f["type"] for f in findings}
    assert "behavioral_failure" in types  # failed gate + wrong_but_passed
    assert "performance" in types  # inefficiency
    # IDs are unique and sequential.
    assert [f["id"] for f in findings] == [1, 2, 3]


def test_emitted_document_validates_against_schema(tmp_path: Path) -> None:
    out = emit_findings(
        matrices=[_matrix_with_failures()],
        output_path=tmp_path / "findings-agent-scenarios.json",
        target="build-agent-trajectory-scenario-harness",
        source_paths={"fix-add": "scenarios/fix-add.scenario.yaml"},
    )
    document = json.loads(out.read_text(encoding="utf-8"))
    # Explicit validation against the canonical repo schema.
    jsonschema.validate(instance=document, schema=_load_schema())
    assert document["review_type"] == "implementation"
    assert document["reviewer_vendor"] == "agent-scenarios"
    assert document["target"] == "build-agent-trajectory-scenario-harness"
    for f in document["findings"]:
        assert set(
            ["id", "type", "criticality", "description", "disposition", "axis", "severity"]
        ) <= set(f)


def test_end_to_end_emit_from_runner(scenarios_dir: Path, tmp_path: Path) -> None:
    scenario = load_scenario(scenarios_dir / "implement-feature-basic.scenario.yaml")
    # Script a FAILING outcome (bug left in place, no PR) so findings are produced.
    bad = Outcome(
        write_files={"src/calc.py": "def add(a, b):\n    return a - b\n"}, commit_message="noop"
    )
    matrix = run_scenario(scenario, FakeExecutor({scenario.id: bad}))
    out = emit_findings(
        matrices=[matrix],
        output_path=tmp_path / "findings.json",
        target="build-agent-trajectory-scenario-harness",
        source_paths={scenario.id: scenario.source_path or ""},
    )
    document = json.loads(out.read_text(encoding="utf-8"))
    jsonschema.validate(instance=document, schema=_load_schema())
    assert document["findings"], "a failing run must produce findings"


def test_pass_run_emits_empty_findings(scenarios_dir: Path, tmp_path: Path) -> None:
    scenario = load_scenario(scenarios_dir / "implement-feature-basic.scenario.yaml")
    good = Outcome(
        write_files={"src/calc.py": "def add(a, b):\n    return a + b\n"},
        new_branch="feature/fix-add",
        commit_message="fix: correct add",
        pr=PRRef(number=1, head="feature/fix-add", url="http://pr/1"),
    )
    matrix = run_scenario(scenario, FakeExecutor({scenario.id: good}))
    # Deterministic gates should all pass for this scripted-correct outcome.
    assert matrix.all_vendors_pass
    out = emit_findings(
        matrices=[matrix],
        output_path=tmp_path / "findings.json",
        target="build-agent-trajectory-scenario-harness",
    )
    document = json.loads(out.read_text(encoding="utf-8"))
    jsonschema.validate(instance=document, schema=_load_schema())
    assert document["findings"] == []


@pytest.mark.gx10
def test_placeholder_live_vendor_marker() -> None:
    """Live multi-vendor execution runs on the GX10; skipped in-container."""
    pytest.skip("requires live vendor CLIs (GX10)")
