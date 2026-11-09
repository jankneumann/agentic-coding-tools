"""Memory-store blocked-dependency scenario tests (B.1-B.6; design D5, D7)."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
from pathlib import Path

import jsonschema
import pytest
import yaml
from openspec_paths import repo_root_from

from mpsim.runner import run

HARNESS = Path(__file__).resolve().parent
REPO = repo_root_from(__file__, 3)
SCHEMA = json.loads(
    (REPO / "openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json").read_text()
)
BLOCKED = "memory-store-blocked-dependency"
CONTROL = "independent-principals-control"
STATUS_LITERALS = {"approved", "in_progress", "completed"}


def _copy_fixture(tmp_path: Path, name: str) -> Path:
    dest = tmp_path / "fixture"
    shutil.copytree(HARNESS / "fixtures" / name, dest)
    return dest


def _edit_yaml(path: Path, mutate) -> None:
    data = yaml.safe_load(path.read_text())
    mutate(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(cwd)},
    ).stdout.strip()


def test_baseline_dependent_principal_is_blocked_until_the_dependency_is_implemented():
    result = run(BLOCKED)
    assert result.exit_code == 0
    report = result.report
    assert report["blocked_ticks"] == {"retrieval-owner": 10, "storage-owner": 0}
    assert report["unblocked"] == {"retrieval-owner": True, "storage-owner": True}
    assert report["collision_present"] is None and report["collision_detected"] is None
    assert report["probes"] is None
    assert report["final_tick"] == 15
    jsonschema.Draft202012Validator(SCHEMA).validate(report)


def test_dependency_completed_at_tick_11_admits_the_dependent_at_tick_11():
    timeline = run(BLOCKED).report["timeline"]
    admitted = [e for e in timeline if e["event"] == "admitted" and e["principal"] == "retrieval-owner"]
    assert [e["tick"] for e in admitted] == [11]
    assert admitted[0]["step"] == "implement"
    finished = [e for e in timeline if (e["principal"], e["step"], e["event"]) ==
                ("storage-owner", "implement", "finished")]
    assert [e["tick"] for e in finished] == [11]


def test_independent_principals_are_never_blocked():
    result = run(CONTROL)
    assert result.exit_code == 0
    assert set(result.report["blocked_ticks"].values()) == {0}
    assert set(result.report["unblocked"].values()) == {True}


def test_a_tick_budget_below_completion_bounds_the_run():
    result = run(BLOCKED, tick_budget=5)
    assert result.exit_code == 0
    report = result.report
    assert report["final_tick"] == 5
    assert report["unblocked"]["retrieval-owner"] is False
    assert report["blocked_ticks"]["retrieval-owner"] == 4
    assert report["unblocked"]["storage-owner"] is True
    jsonschema.Draft202012Validator(SCHEMA).validate(report)


def test_a_dependency_that_starts_completed_unblocks_through_the_admission_rule(tmp_path):
    fixture = _copy_fixture(tmp_path, BLOCKED)

    def complete(data):
        for item in data["items"]:
            if item["item_id"] == "ri-storage":
                item["status"] = "completed"

    _edit_yaml(fixture / "seed" / "roadmap.yaml", complete)
    result = run(BLOCKED, fixture_dir=fixture, tick_budget=20)
    assert result.exit_code == 0
    assert result.report["blocked_ticks"]["retrieval-owner"] == 0
    assert result.report["unblocked"]["retrieval-owner"] is True


def test_status_transitions_reach_only_the_integration_ref(tmp_path):
    work = tmp_path / "kept"
    result = run(BLOCKED, work_root=work)
    assert result.exit_code == 0
    remote = work / "world" / "remote.git"
    seed = _git(remote, "rev-list", "--max-parents=0", "main")

    branches = _git(remote, "for-each-ref", "--format=%(refname)", "refs/heads/sim/").splitlines()
    assert len(branches) == 2
    for ref in branches:
        touched = _git(remote, "log", "--name-only", "--format=", f"{seed}..{ref}").splitlines()
        assert "roadmap.yaml" not in touched, ref

    authors = _git(remote, "log", "--format=%an", f"{seed}..main").splitlines()
    assert authors and set(authors) == {"sim-supervisor"}

    final = yaml.safe_load(_git(remote, "show", "main:roadmap.yaml"))
    assert {i["item_id"]: i["status"] for i in final["items"]} == {
        "ri-storage": "completed", "ri-retrieval": "completed"}


def test_no_status_literal_is_used_as_a_set_status_value_in_the_driver():
    offenders = []
    for path in sorted((HARNESS / "mpsim").rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in STATUS_LITERALS:
                offenders.append(f"{path.name}:{node.lineno}:{node.value}")
    assert offenders == []


def test_a_fixture_without_on_finish_leaves_the_dependent_blocked(tmp_path):
    fixture = _copy_fixture(tmp_path, BLOCKED)

    def drop_finish(data):
        for principal in data["principals"]:
            for step in principal["steps"]:
                if principal["name"] == "storage-owner" and step["name"] == "implement":
                    step.pop("on_finish")

    _edit_yaml(fixture / "scenario.yaml", drop_finish)
    result = run(BLOCKED, fixture_dir=fixture, tick_budget=30)
    assert result.exit_code == 0
    assert result.report["unblocked"]["retrieval-owner"] is False
    assert result.report["blocked_ticks"]["retrieval-owner"] == 29


@pytest.mark.parametrize("scenario", [BLOCKED, CONTROL])
def test_report_names_two_principals_with_distinct_agents(scenario):
    report = run(scenario).report
    assert [p["name"] for p in report["principals"]] == ["storage-owner", "retrieval-owner"]
    assert len({p["agent_id"] for p in report["principals"]}) == 2
