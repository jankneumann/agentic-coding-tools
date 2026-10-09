"""Run one scenario and produce its report (shared by the CLI and the tests)."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mpsim import probes as probe_registry
from mpsim.errors import ScenarioError, UsageError
from mpsim.fixture import load_fixture
from mpsim.model import RunContext
from mpsim.paths import FIXTURES_ROOT
from mpsim.report import new_report, render
from mpsim.scenarios import discover

DEFAULT_TICK_BUDGET = 50


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    report: dict[str, Any]
    text: str


def run(
    scenario_id: str,
    *,
    probe_ids: Sequence[str] | None = None,
    tick_budget: int = DEFAULT_TICK_BUDGET,
    fixture_dir: Path | None = None,
) -> RunResult:
    scenarios = discover()
    if scenario_id not in scenarios:
        raise UsageError(f"unknown scenario {scenario_id!r}; known: {', '.join(scenarios)}")
    scenario = scenarios[scenario_id]
    if tick_budget < 1:
        raise UsageError("--tick-budget must be at least 1")
    if fixture_dir is not None and not Path(fixture_dir).is_dir():
        raise UsageError("--fixture-dir does not exist or is not a directory")
    fixture = load_fixture(Path(fixture_dir) if fixture_dir else FIXTURES_ROOT / scenario.fixture_name)
    selected = probe_registry.select(probe_ids)

    work_root = Path(tempfile.mkdtemp(prefix="mpsim-", dir=os.environ.get("TMPDIR") or None))
    scrub = _scrub_values(work_root, fixture.dir)
    try:
        ctx = RunContext(scenario_id, fixture, selected, tick_budget, work_root)
        try:
            report = scenario.run(ctx)
            exit_code = 0
        except ScenarioError as exc:
            report = new_report(scenario_id, error=_scrub(str(exc), scrub))
            exit_code = 1
        text = render(report, forbidden_paths=[v for v, _ in scrub])
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
    return RunResult(exit_code, report, text)


def _scrub_values(work_root: Path, fixture_dir: Path) -> list[tuple[str, str]]:
    values = []
    for path, label in ((work_root, "<world>"), (fixture_dir, "<fixture>")):
        for variant in {str(path), str(path.resolve())}:
            values.append((variant, label))
    return sorted(values, key=lambda v: -len(v[0]))


def _scrub(message: str, scrub: list[tuple[str, str]]) -> str:
    for value, label in scrub:
        message = message.replace(value, label)
    return message
