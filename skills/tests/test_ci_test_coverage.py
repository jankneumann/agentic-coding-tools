"""Every test directory must actually be run by CI.

A test CI never runs fails the same way as one that always passes. This repo has
hit that twice: ``tests/coordination-bridge`` was missing from ``testpaths``
(recorded in a comment there), and four in-skill directories --
``validate-feature/scripts/tests``, ``autopilot/scripts/tests``,
``security-review/tests`` and ``parallel-infrastructure/tests`` -- were absent
too. Between them they hold the gate-logic, linter, GATEKEEPER, security-gate
and consensus suites: the checks that decide whether other work may merge were
themselves unchecked, 438 tests that no CI run executed.

They were left out because skills import siblings by flat module name and twelve
of those names are defined by more than one skill, so a single pytest session
resolves the wrong one. CI runs them in a second process instead. This test
holds the invariant that matters regardless of which mechanism a directory uses:
it is reached by one of them.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

_SKILLS_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _SKILLS_ROOT.parent
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

#: Directories whose tests are deliberately not part of the skills sweep.
#: Keep this list short and justified -- it is the escape hatch that lets a
#: directory go unrun, so every entry needs a reason.
_EXEMPT: dict[str, str] = {
    # Run by the separate `test-skills` CI job, not the skills sweep.
    "bug-scrub/tests": "run by the test-skills job",
    "fix-scrub/tests": "run by the test-skills job",
    # Fixture trees consumed by other tests rather than collected themselves.
    "validate-feature/scripts/smoke_tests": "live-service fixtures, not unit tests",
    # Not tests. `insights/test_linker.py` is a production module -- the "test
    # linker" that walks test files and emits TEST_COVERS edges into the
    # architecture graph. It matches test_*.py by name only, and collecting it
    # yields zero tests.
    "refresh-architecture/scripts/insights": "test_linker.py is a producer, not a test",
}


def _test_dirs() -> set[str]:
    """Every directory under skills/ that contains test_*.py files."""
    found: set[str] = set()
    for path in _SKILLS_ROOT.rglob("test_*.py"):
        if any(part in {".venv", "__pycache__", "node_modules"} for part in path.parts):
            continue
        found.add(path.parent.relative_to(_SKILLS_ROOT).as_posix())
    return found


def _testpaths() -> set[str]:
    with (_SKILLS_ROOT / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    paths = config["tool"]["pytest"]["ini_options"]["testpaths"]
    return {p.rstrip("/") for p in paths}


def _ci_pytest_arguments() -> set[str]:
    """Directories named as explicit pytest arguments anywhere in ci.yml."""
    if not _CI_WORKFLOW.exists():  # pragma: no cover - workflow always present
        pytest.skip(f"CI workflow not found at {_CI_WORKFLOW}")
    workflow = yaml.safe_load(_CI_WORKFLOW.read_text())

    args: set[str] = set()
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            run = step.get("run")
            if not run or "pytest" not in run:
                continue
            for token in re.split(r"[\s\\]+", run):
                token = token.strip().rstrip("/")
                if not token or token.startswith("-"):
                    continue
                candidate = token[len("skills/"):] if token.startswith("skills/") else token
                if (_SKILLS_ROOT / candidate).is_dir():
                    args.add(candidate)
    return args


def _covered() -> set[str]:
    return _testpaths() | _ci_pytest_arguments() | set(_EXEMPT)


@pytest.mark.parametrize("test_dir", sorted(_test_dirs()))
def test_directory_is_reached_by_ci(test_dir: str) -> None:
    """Each test directory is in testpaths, named in ci.yml, or exempt."""
    covered = _covered()
    if test_dir in covered:
        return
    # A nested directory is covered when an ancestor is collected, since pytest
    # recurses into it.
    parts = test_dir.split("/")
    for depth in range(len(parts) - 1, 0, -1):
        if "/".join(parts[:depth]) in covered:
            return
    pytest.fail(
        f"{test_dir} contains tests but no CI invocation reaches it. Add it to "
        f"testpaths in skills/pyproject.toml, name it in a ci.yml pytest step, "
        f"or record why it is exempt in _EXEMPT in {Path(__file__).name}."
    )


def test_the_four_recovered_directories_stay_covered() -> None:
    """Pin the specific directories this guard was written for.

    The parametrized test above would also catch these, but only while they
    still contain files matching ``test_*.py``. Naming them makes the
    regression explicit rather than incidental.
    """
    covered = _covered()
    for recovered in (
        "validate-feature/scripts/tests",
        "autopilot/scripts/tests",
        "security-review/tests",
        "parallel-infrastructure/tests",
    ):
        assert recovered in covered, f"{recovered} dropped out of CI again"


def test_exemptions_are_real_directories() -> None:
    """An exemption for a directory that no longer exists is stale."""
    for exempt in _EXEMPT:
        assert (_SKILLS_ROOT / exempt).is_dir(), (
            f"_EXEMPT lists {exempt}, which does not exist -- remove the entry"
        )
