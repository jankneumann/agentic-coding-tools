"""Acceptance: a deliberately broken skill change fails the suite and feeds /improve-harness.

A skill-reading fake executor plays the scenario's golden outcome, or its broken outcome when
the materialized SKILL.md carries the break marker. Nothing here runs a vendor CLI.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import types
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent_scenarios import FakeExecutor, Outcome, load_scenarios
from agent_scenarios.nightly import NightlyConfig, run_nightly
from agent_scenarios.results_store import JsonlResultsStore, RunRecord
from tests.test_nightly_config import write_config
from tests.test_seed_outcomes import outcome_module

from .conftest import SCENARIOS_DIR

SCENARIO_ID = "validate-feature-clean-pass"
SKILL = "validate-feature"
BREAK_MARKER = "<!-- BREAK: report no longer carries a Status line -->"
SKILLS_PY = Path(__file__).resolve().parents[3] / "skills" / "improve-harness" / "scripts"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class GapSink:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def send(self, entry: dict[str, Any]) -> bool:
        self.entries.append(entry)
        return True


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    """A temp checkout with a skills tree, a one-scenario suite and a config."""
    repo = tmp_path / "repo"
    skills = repo / "skills"
    for name in (SKILL, "worktree"):
        (skills / name).mkdir(parents=True)
        (skills / name / "SKILL.md").write_text(f"# {name}\nProduce the report.\n")
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "t@t.local")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "skills")
    suite = tmp_path / "scenarios"
    suite.mkdir()
    for s in load_scenarios(SCENARIOS_DIR):
        if s.id == SCENARIO_ID:
            (suite / f"{s.id}.scenario.yaml").write_text(
                yaml.safe_dump(s.model_dump(mode="json", exclude={"source_path"}))
            )
    return repo, skills


def _skill_reading_factory(cfg: NightlyConfig) -> FakeExecutor:
    mod = outcome_module(SCENARIO_ID)

    def play(workdir: Path) -> Outcome:
        text = (workdir / ".claude" / "skills" / SKILL / "SKILL.md").read_text()
        return mod.broken(workdir) if BREAK_MARKER in text else mod.golden(workdir)

    return FakeExecutor({SCENARIO_ID: play}, skills_root=cfg.skills_dir())


def _run(tmp_path: Path, sink: GapSink) -> int:
    path = write_config(
        tmp_path, scenarios_dir=str(tmp_path / "scenarios"), repo_root=str(tmp_path / "repo"),
        gaps={"enabled": True},
    )
    return run_nightly(path, executor_factory=_skill_reading_factory, coordinator_sink=sink)


def _store(tmp_path: Path) -> JsonlResultsStore:
    return JsonlResultsStore(tmp_path / "state" / "results.jsonl")


def test_broken_skill_fails_emits_gap_and_findings_then_intact_skill_passes(
    tmp_path: Path,
) -> None:
    repo, skills = _setup(tmp_path)

    # 1. Break the skill (uncommitted, as in a working-tree experiment).
    skill_md = skills / SKILL / "SKILL.md"
    intact = skill_md.read_text()
    skill_md.write_text(intact + BREAK_MARKER + "\n")
    sink = GapSink()
    assert _run(tmp_path, sink) == 1

    results = list(_store(tmp_path).iter_results())
    assert sorted((r.vendor, r.deterministic_status) for r in results) == [
        ("claude", "fail"), ("codex", "fail")]
    assert all(r.failed_gates == ["report-has-status"] for r in results)
    assert all(r.skills_sha and r.skills_sha.endswith("+dirty") for r in results)
    run = next(r for r in _store(tmp_path).iter_records() if isinstance(r, RunRecord))
    findings = json.loads((tmp_path / "state" / "findings" / f"{run.run_id}.json").read_text())
    assert findings["findings"]

    assert len(sink.entries) == 2
    for entry in sink.entries:
        assert "affected_skill:validate-feature" in entry["tags"]
        assert "source:scenario-parity" in entry["tags"]
        assert (
            f"capability_gap:scenario-parity/{SCENARIO_ID}/report-has-status" in entry["tags"]
        )

    # 2. /improve-harness failure analysis ranks the gap with scenario-parity as a source.
    analyze = SKILLS_PY / "analyze_failures.py"
    if analyze.is_file():
        spec = importlib.util.spec_from_file_location("af_acceptance", analyze)
        assert spec and spec.loader
        af: types.ModuleType = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(af)
        ranked = af.rank_findings(sink.entries)
        assert len(ranked) == 1
        assert "scenario-parity" in ranked[0]["sources"]
        assert ranked[0]["affected_skills"] == ["validate-feature"]
        assert ranked[0]["frequency"] == 2  # (run, vendor) pairs

    # 3. Restore the skill: same scenario passes, no new gap.
    skill_md.write_text(intact)
    sink2 = GapSink()
    assert _run(tmp_path, sink2) == 0
    latest = {r.vendor: r for r in _store(tmp_path).iter_results()
              if r.run_id != run.run_id}
    assert {v: r.deterministic_status for v, r in latest.items()} == {
        "claude": "pass", "codex": "pass"}
    assert all(r.skills_sha and not r.skills_sha.endswith("+dirty") for r in latest.values())
    assert sink2.entries == []


def test_missing_skill_in_skills_root_is_an_error_not_a_gap(tmp_path: Path) -> None:
    repo, skills = _setup(tmp_path)
    import shutil

    shutil.rmtree(skills / SKILL)
    sink = GapSink()
    assert _run(tmp_path, sink) == 3
    results = list(_store(tmp_path).iter_results())
    assert {r.deterministic_status for r in results} == {"error"}
    assert all(SKILL in (r.error or "") for r in results)
    assert sink.entries == []


@pytest.mark.parametrize("which", ["golden", "broken"])
def test_outcome_modules_expose_callables(which: str) -> None:
    assert callable(getattr(outcome_module(SCENARIO_ID), which))
