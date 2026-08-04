"""Guard: every skill test directory is actually executed by CI.

The bug this pins
-----------------
``testpaths`` in ``skills/pyproject.toml`` is a hand-maintained enumeration.
Skills that added a test directory without appending to it were never run —
47 directories, ~2,400 tests, at the time this guard was written. pytest gives
no signal for either failure mode:

  * a directory missing from ``testpaths`` is simply not collected, and
  * a ``testpaths`` entry pointing at a deleted directory is silently ignored.

Both look identical to a green build. As the note beside ``tests/coordination-
bridge`` in pyproject puts it: a test CI never runs fails the same way as one
that always passes.

Coverage is now a partition — ``testpaths`` for suites that can share a pytest
process, ``tests/run_isolated_suites.py`` for those that cannot (see that
module for why they cannot). These tests assert the partition is total and that
neither side lists anything that no longer exists.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(SKILLS_ROOT / "tests"))

from run_isolated_suites import (  # noqa: E402
    EXCLUDED,
    QUARANTINED,
    _covered_by_testpaths,
    discover_all_test_dirs,
    isolated_suites,
)


def test_no_test_directory_is_invisible_to_ci() -> None:
    """Every discovered suite is in testpaths, the isolated runner, or EXCLUDED."""
    testpaths = _covered_by_testpaths()
    in_process = {
        d
        for d in discover_all_test_dirs()
        if any(d == t or d.startswith(t + os.sep) for t in testpaths)
    }
    isolated = set(isolated_suites("all"))
    accounted = in_process | isolated | set(EXCLUDED)

    orphans = sorted(discover_all_test_dirs() - accounted)
    assert not orphans, (
        "These test directories run in no CI job:\n  "
        + "\n  ".join(orphans)
        + "\n\nAdd each to testpaths in skills/pyproject.toml if it can share a "
        "pytest process with the others, otherwise it is picked up "
        "automatically by tests/run_isolated_suites.py. If it is not a suite at "
        "all, add it to EXCLUDED there with a justification."
    )


def test_testpaths_entries_all_exist() -> None:
    """A testpaths entry pointing at a deleted directory is collected silently."""
    missing = [t for t in _covered_by_testpaths() if not (SKILLS_ROOT / t).is_dir()]
    assert not missing, (
        "testpaths in skills/pyproject.toml lists directories that do not exist:\n  "
        + "\n  ".join(missing)
        + "\n\npytest ignores these without warning, so the entry looks like "
        "coverage while providing none. Delete them."
    )


def test_excluded_entries_all_exist() -> None:
    """EXCLUDED is a debt ledger; entries for deleted paths are noise."""
    missing = [d for d in EXCLUDED if not (SKILLS_ROOT / d).is_dir()]
    assert not missing, (
        "EXCLUDED in tests/run_isolated_suites.py names directories that no "
        "longer exist:\n  " + "\n  ".join(missing) + "\n\nDelete these entries."
    )


@pytest.mark.parametrize("suite", sorted(QUARANTINED))
def test_quarantined_suites_still_exist(suite: str) -> None:
    """A quarantine entry for a deleted suite hides nothing and should go."""
    assert (SKILLS_ROOT / suite).is_dir(), (
        f"{suite} is quarantined in tests/run_isolated_suites.py but does not "
        "exist. Delete the QUARANTINED entry."
    )


@pytest.mark.parametrize("suite,reason", sorted(QUARANTINED.items()))
def test_quarantined_suites_carry_a_reason(suite: str, reason: str) -> None:
    """Quarantine is a ledger, not a parking lot — every entry states why."""
    assert reason.strip(), f"{suite} is quarantined with no stated reason."
