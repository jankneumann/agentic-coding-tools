"""Collision scenario tests (C.1, C.2, C.3; design D4, D6)."""

from __future__ import annotations

import shutil
from pathlib import Path

import jsonschema
import json
import pytest
from openspec_paths import repo_root_from

from mpsim import probes
from mpsim.runner import run

HARNESS = Path(__file__).resolve().parent
REPO = repo_root_from(__file__, 3)
SCHEMA = json.loads(
    (REPO / "openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json").read_text()
)


@pytest.fixture(autouse=True)
def _empty_registry():
    saved = dict(probes.REGISTRY)
    probes.REGISTRY.clear()
    yield
    probes.REGISTRY.clear()
    probes.REGISTRY.update(saved)


def test_baseline_collision_is_present_but_not_detected():
    result = run("same-requirement-collision")
    assert result.exit_code == 0
    report = result.report
    assert report["collision_present"] is True
    assert report["collision_detected"] is False
    assert report["probes"] == []
    jsonschema.Draft202012Validator(SCHEMA).validate(report)


def test_report_names_both_principals_with_distinct_agents():
    report = run("same-requirement-collision").report
    assert [p["name"] for p in report["principals"]] == ["alice", "bob"]
    assert len({p["agent_id"] for p in report["principals"]}) == 2
    assert [p["change_id"] for p in report["principals"]] == ["sim-alice-notes", "sim-bob-notes"]
    assert report["blocked_ticks"] is None and report["unblocked"] is None


def test_timeline_has_bob_planning_after_alice_pushed():
    timeline = run("same-requirement-collision").report["timeline"]
    pushed = next(i for i, e in enumerate(timeline)
                  if (e["principal"], e["event"]) == ("alice", "pushed"))
    bob_started = next(i for i, e in enumerate(timeline)
                       if (e["principal"], e["event"]) == ("bob", "started"))
    assert pushed < bob_started
    assert any(e["event"] == "probed" and e["principal"] == "bob" for e in timeline)


def test_different_requirements_produce_no_collision():
    result = run("different-requirement-control")
    assert result.exit_code == 0
    assert result.report["collision_present"] is False
    assert result.report["collision_detected"] is False


def test_a_fixture_that_loses_the_shared_requirement_fails_loudly(tmp_path):
    fixture = tmp_path / "fixture"
    shutil.copytree(HARNESS / "fixtures" / "same-requirement-collision", fixture)
    bob_spec = (fixture / "principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md")
    bob_spec.write_text(bob_spec.read_text().replace("Note Titles", "Note Bodies"))

    result = run("same-requirement-collision", fixture_dir=fixture)

    assert result.exit_code == 1
    assert result.report["error"]
    assert "collision" in result.report["error"]
    assert "absent" in result.report["error"]
    jsonschema.Draft202012Validator(SCHEMA).validate(result.report)
    assert str(tmp_path) not in result.text


def test_a_control_fixture_that_gains_a_collision_also_fails_loudly(tmp_path):
    fixture = tmp_path / "fixture"
    shutil.copytree(HARNESS / "fixtures" / "different-requirement-control", fixture)
    bob_spec = (fixture / "principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md")
    bob_spec.write_text(bob_spec.read_text().replace("Note Bodies", "Note Titles"))
    result = run("different-requirement-control", fixture_dir=fixture)
    assert result.exit_code == 1
    assert "unexpected" in result.report["error"]
