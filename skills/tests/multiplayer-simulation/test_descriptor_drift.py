"""The committed descriptor cannot drift from the CLI contract (G.4; design D3, D8)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from openspec_paths import repo_root_from

HARNESS = Path(__file__).resolve().parent
REPO = repo_root_from(__file__, 3)
GENERATOR = REPO / "packages" / "gen-eval" / "scripts" / "generate_tool_descriptor.py"
CONTRACT = REPO / "openspec" / "contracts" / "multiplayer-simulation" / "cli" / "mpsim.yaml"
DESCRIPTOR = HARNESS / "evaluation" / "descriptor.yaml"


def _check(descriptor: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GENERATOR), "--contract", str(CONTRACT), "--out", str(descriptor),
         "--check"],
        capture_output=True, text=True,
    )


def test_committed_descriptor_matches_the_contract():
    proc = _check(DESCRIPTOR)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_mutated_descriptor_fails_the_check(tmp_path):
    mutated = tmp_path / "descriptor.yaml"
    mutated.write_text(DESCRIPTOR.read_text().replace("name: --tick-budget", "name: --tick-budgets"))
    assert mutated.read_text() != DESCRIPTOR.read_text()
    proc = _check(mutated)
    assert proc.returncode != 0
