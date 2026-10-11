"""Seed-suite coverage-floor guard (task 2.1) with negative cases against temp suites."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent_scenarios import load_scenarios
from agent_scenarios.suite import REQUIRED_FAMILIES, skill_family

from .conftest import SCENARIOS_DIR

OUTCOMES_DIR = Path(__file__).resolve().parent / "scenario_outcomes"
MIN_SCENARIOS = 10
MIN_PER_FAMILY = 2
MIN_VENDORS = 2


def suite_problems(scenarios_dir: Path, outcomes_dir: Path) -> list[str]:
    """Return a list of human-readable guard violations (empty == healthy suite)."""
    problems: list[str] = []
    scenarios = load_scenarios(scenarios_dir)
    if len(scenarios) < MIN_SCENARIOS:
        problems.append(f"floor: {len(scenarios)} scenarios < {MIN_SCENARIOS}")
    ids = [s.id for s in scenarios]
    for dup in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"duplicate scenario id: {dup}")
    for family in REQUIRED_FAMILIES:
        n = sum(1 for s in scenarios if skill_family(s.skill_under_test) == family)
        if n < MIN_PER_FAMILY:
            problems.append(f"floor: family {family!r} has {n} scenarios < {MIN_PER_FAMILY}")
    for s in scenarios:
        if len(s.vendors) < MIN_VENDORS:
            problems.append(f"{s.id}: declares {len(s.vendors)} vendors < {MIN_VENDORS}")
        if f"/{s.skill_under_test}" not in s.task_prompt:
            problems.append(f"{s.id}: task_prompt does not invoke /{s.skill_under_test}")
        if not (outcomes_dir / f"{s.id}.py").is_file():
            problems.append(f"{s.id}: missing outcome module")
        has_pr_gate = any(g.check == "pr" for g in s.goal_gates.all_gates())
        if has_pr_gate and not s.fixture.local_remote:
            problems.append(f"{s.id}: pr gate requires fixture.local_remote")
    return problems


def _copy_suite(tmp_path: Path, *, drop: set[str] | None = None) -> tuple[Path, Path]:
    sdir, odir = tmp_path / "scenarios", tmp_path / "outcomes"
    shutil.copytree(SCENARIOS_DIR, sdir)
    shutil.copytree(OUTCOMES_DIR, odir, ignore=shutil.ignore_patterns("__pycache__"))
    for sid in drop or ():
        (sdir / f"{sid}.scenario.yaml").unlink()
    return sdir, odir


def test_shipped_suite_meets_the_floor() -> None:
    assert suite_problems(SCENARIOS_DIR, OUTCOMES_DIR) == []
    scenarios = load_scenarios(SCENARIOS_DIR)
    assert len(scenarios) >= MIN_SCENARIOS
    assert len({s.id for s in scenarios}) == len(scenarios)


def test_removing_scenarios_below_the_floor_fails(tmp_path: Path) -> None:
    sdir, odir = _copy_suite(
        tmp_path, drop={"plan-feature-basic", "validate-feature-spec-gap"}
    )
    problems = suite_problems(sdir, odir)
    assert any(p.startswith("floor: 9 scenarios") for p in problems)


def test_missing_merge_family_fails(tmp_path: Path) -> None:
    sdir, odir = _copy_suite(
        tmp_path, drop={"merge-pull-requests-local-merge", "cleanup-feature-archive"}
    )
    assert any("family 'merge'" in p for p in suite_problems(sdir, odir))


def test_prompt_without_skill_invocation_fails(tmp_path: Path) -> None:
    sdir, odir = _copy_suite(tmp_path)
    f = sdir / "validate-feature-clean-pass.scenario.yaml"
    f.write_text(f.read_text().replace("/validate-feature Validate", "Validate"))
    problems = suite_problems(sdir, odir)
    assert any(
        "validate-feature-clean-pass" in p and "does not invoke /validate-feature" in p
        for p in problems
    )


def test_scenario_without_outcome_module_is_rejected(tmp_path: Path) -> None:
    sdir, odir = _copy_suite(tmp_path)
    (odir / "cleanup-feature-archive.py").unlink()
    assert any(
        "cleanup-feature-archive" in p and "missing outcome" in p
        for p in suite_problems(sdir, odir)
    )


def test_pr_gate_requires_local_remote(tmp_path: Path) -> None:
    sdir, odir = _copy_suite(tmp_path)
    f = sdir / "implement-feature-basic.scenario.yaml"
    f.write_text(
        f.read_text().replace("  local_remote: true\n", "").replace(
            "    - id: pushed-to-origin", "    - id: pr-opened\n      check: pr\n"
            "      pr_head: feature/fix-add\n    - id: pushed-to-origin"
        )
    )
    assert any("pr gate requires" in p for p in suite_problems(sdir, odir))


@pytest.mark.parametrize(
    ("skill", "family"),
    [("plan-feature", "plan"), ("iterate-on-implementation", "implement"),
     ("validate-feature", "validate"), ("cleanup-feature", "merge"), ("zzz", "other")],
)
def test_skill_family_map(skill: str, family: str) -> None:
    assert skill_family(skill) == family
