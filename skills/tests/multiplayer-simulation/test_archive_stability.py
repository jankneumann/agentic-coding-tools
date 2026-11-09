"""Archive stability (A.1, A.2, A.3; design D10).

A.3 holds by construction: harness tests read this change's artifacts only through
``change_dir()`` (see ``test_contracts.py``) and read contracts only from their promoted
paths under ``openspec/contracts/multiplayer-simulation/``. No harness module holds a
literal ``openspec/changes/<id>`` path, which A.1 enforces through the shared guard.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml
from openspec_paths import repo_root_from

HARNESS = Path(__file__).resolve().parent
REPO = repo_root_from(__file__, 3)
CHANGES = REPO / "openspec" / "changes"


def _real_change_ids() -> set[str]:
    """Active and archived change ids, read the way the path-stability guard reads them."""
    ids = {e.name for e in CHANGES.iterdir() if e.is_dir() and e.name != "archive"}
    archive = CHANGES / "archive"
    if archive.is_dir():
        for entry in archive.iterdir():
            if entry.is_dir():
                parts = entry.name.split("-", 3)
                ids.add(parts[3] if len(parts) == 4 and parts[0].isdigit() else entry.name)
    return ids


def _fixture_change_ids() -> set[str]:
    ids: set[str] = set()
    for descriptor in sorted((HARNESS / "fixtures").glob("*/scenario.yaml")):
        for principal in yaml.safe_load(descriptor.read_text())["principals"]:
            ids.add(principal["change_id"])
    for changes_dir in (HARNESS / "fixtures").rglob("changes"):
        ids.update(p.name for p in changes_dir.iterdir() if p.is_dir())
    return ids


def test_fixture_change_ids_are_synthetic_and_not_real():
    fixture_ids = _fixture_change_ids()
    assert fixture_ids, "no fixture change ids found"
    assert all(i.startswith("sim-") for i in fixture_ids)
    assert fixture_ids & _real_change_ids() == set()


def test_the_path_stability_guard_reports_nothing_in_the_harness():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/openspec_paths", "-q", "-p", "no:cacheprovider"],
        cwd=REPO / "skills", capture_output=True, text=True,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "multiplayer-simulation" not in output
