"""Determinism guards for architecture.report.md (issue #362).

The report is a committed artifact covered by architecture provenance, so it
must be reproducible from one graph. Its "single points of failure" list was
ranked by importer count alone and fed from a *set*, so equal-count modules
swapped places between runs and every refresh produced a large, contentless
diff.

Ranking order is fixed at interpreter start by ``PYTHONHASHSEED``, so the guard
renders the section in subprocesses under several pinned seeds.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent

#: Enough distinct seeds that an accidental agreement across all of them is not
#: a plausible explanation for a green run.
_SEEDS = ("0", "1", "2", "3", "4")

_RUNNER = """
import json
import sys

sys.path.insert(0, {scripts!r})
from reports.architecture_report import _section_dependency_layers

with open(sys.argv[1]) as handle:
    py = json.load(handle)
sys.stdout.write(_section_dependency_layers(py))
"""

#: Four modules with an identical importer count (3) plus one clear leader (4).
#: The tied names are listed in an order that is neither sorted nor reversed, so
#: "came out in fixture order" is distinguishable from "came out sorted".
_TIED = ["f_zeta", "f_alpha", "f_mid", "f_beta"]
_LEADER = "f_hot"


def _python_analysis() -> dict:
    """Build a python_analysis payload with a tie among foundation modules."""
    importers = [f"caller_{i}" for i in range(4)]
    modules: list[dict] = []

    for index, importer in enumerate(importers):
        imports = list(_TIED) if index < 3 else []
        imports.append(_LEADER)  # every importer pulls the leader -> count 4
        modules.append({"name": importer, "imports": imports})

    for name in [*_TIED, _LEADER]:
        modules.append({"name": name, "imports": []})

    return {"modules": modules, "entry_points": [], "functions": []}


def _render(analysis_path: Path, seed: str) -> str:
    """Render the dependency-layers section in a subprocess pinned to *seed*."""
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    result = subprocess.run(
        [sys.executable, "-c", _RUNNER.format(scripts=str(SCRIPTS_DIR)), str(analysis_path)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"report section failed under seed {seed}:\n{result.stderr}"
    return result.stdout


def _spof_modules(section: str) -> list[str]:
    """Extract the module names from the single-points-of-failure list."""
    return [
        line.split("`")[1]
        for line in section.splitlines()
        if line.startswith("- `") and "imported by" in line
    ]


def test_single_points_of_failure_order_is_hash_seed_independent(tmp_path: Path) -> None:
    """Equal-count modules must not swap places between runs."""
    analysis_path = tmp_path / "python_analysis.json"
    analysis_path.write_text(json.dumps(_python_analysis()))

    orders = {seed: _spof_modules(_render(analysis_path, seed)) for seed in _SEEDS}

    baseline = orders[_SEEDS[0]]
    assert baseline, "fixture produced no single points of failure — guard is vacuous"
    for seed in _SEEDS[1:]:
        assert orders[seed] == baseline, (
            f"single-points-of-failure order under PYTHONHASHSEED={seed} differs "
            f"from seed {_SEEDS[0]}"
        )


def test_single_points_of_failure_breaks_ties_by_name(tmp_path: Path) -> None:
    """The imposed total order is (descending count, then name)."""
    analysis_path = tmp_path / "python_analysis.json"
    analysis_path.write_text(json.dumps(_python_analysis()))

    expected = [_LEADER, *sorted(_TIED)]
    for seed in _SEEDS:
        assert _spof_modules(_render(analysis_path, seed)) == expected
