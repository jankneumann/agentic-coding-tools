"""Every test directory must actually be run by CI.

A test CI never runs fails the same way as one that always passes. This repo has
hit that three times. ``tests/coordination-bridge`` was missing from
``testpaths`` (recorded in a comment there). Four in-skill directories --
``validate-feature/scripts/tests``, ``autopilot/scripts/tests``,
``security-review/tests`` and ``parallel-infrastructure/tests`` -- were absent
too. Between them they hold the gate-logic, linter, GATEKEEPER, security-gate
and consensus suites: the checks that decide whether other work may merge were
themselves unchecked, 438 tests that no CI run executed.

The third time was this guard. It reported full coverage while 24 directories
under ``skills/tests`` -- 1182 tests, 23 of them failing -- went unrun, because
``_ci_pytest_arguments`` resolved every pytest token against ``skills/`` no
matter which directory the step ran in, and the context-eval job's
``pytest tests`` (from ``packages/context-eval``) therefore credited
``skills/tests``. The guard could not catch its own blind spot for a second
reason: it lived loose in ``skills/tests``, a directory no ``testpaths`` entry
names, so it was itself never run by CI. Both are fixed -- the resolver is
working-directory-aware and pinned by the regression tests at the bottom of
this file, and the guard now sits in its own listed directory.

They were left out because skills import siblings by flat module name and twelve
of those names are defined by more than one skill, so a single pytest session
resolves the wrong one. CI runs them in a second process instead. This test
holds the invariant that matters regardless of which mechanism a directory uses:
it is reached by one of them.

The fourth time was a whole tree rather than a directory: ``packages/`` grew to
four members while CI had jobs for two, so ``packages/code-search`` and
``packages/agent-scenarios`` ran nowhere. Nobody removed them from a list --
there was no list to remove them from, because the checks above only reason
about ``skills/``. code-search was red for six weeks as a result (the
2026-07-25 archival of ``complete-incremental-semantic-indexing`` moved contract
schemas out from under 14 assertions). ``test_every_package_suite_runs_in_ci``
below closes that at the tree level: a new ``packages/<name>/tests/`` is unrun
until some CI job runs pytest inside it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

# This guard lives in its own directory rather than loose in skills/tests so
# that every unit the coverage check reasons about is a directory. Loose in
# skills/tests it was unreachable: bare `tests` is not in testpaths, so the
# test asserting "every test directory is run by CI" was itself never run by
# CI -- which is why the working-directory bug below survived.
_SKILLS_ROOT = Path(__file__).resolve().parents[2]
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


def _step_working_directory(
    workflow: dict, job: dict, step: dict
) -> Path:
    """Resolve a step's working directory the way GitHub Actions does.

    Precedence: step-level ``working-directory``, then the job's
    ``defaults.run.working-directory``, then the workflow's, then the repo
    root. A pytest argument means nothing without this: half the jobs in this
    workflow run from a package subdirectory.
    """
    for candidate in (
        step.get("working-directory"),
        (job.get("defaults") or {}).get("run", {}).get("working-directory"),
        (workflow.get("defaults") or {}).get("run", {}).get("working-directory"),
    ):
        if candidate:
            return _REPO_ROOT / candidate
    return _REPO_ROOT


def _ci_pytest_arguments() -> set[str]:
    """Directories under skills/ named as explicit pytest arguments in ci.yml.

    Each token is resolved against its step's working directory and kept only
    if it lands inside ``skills/``. Resolving against ``skills/`` unconditionally
    -- as this did until 2026-08-24 -- credits any job that happens to name a
    path that also exists under skills/. The context-eval job runs
    ``uv run pytest tests -q`` from ``packages/context-eval``; the bare token
    ``tests`` resolved to ``skills/tests``, and because a covered ancestor
    covers everything beneath it, that one false positive marked all 26 test
    directories under skills/tests as reached by CI. None of them were.
    """
    if not _CI_WORKFLOW.exists():  # pragma: no cover - workflow always present
        pytest.skip(f"CI workflow not found at {_CI_WORKFLOW}")
    workflow = yaml.safe_load(_CI_WORKFLOW.read_text())

    args: set[str] = set()
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            run = step.get("run")
            if not run or "pytest" not in run:
                continue
            base = _step_working_directory(workflow, job, step)
            for line in run.splitlines():
                # A leading `cd <dir> &&` moves the rest of the line. Modelling
                # it keeps the resolver honest rather than accidentally right.
                cwd = base
                cd_match = re.match(r"\s*cd\s+(\S+)\s*&&", line)
                if cd_match:
                    cwd = base / cd_match.group(1)
                for token in re.split(r"[\s\\]+", line):
                    token = token.strip().rstrip("/")
                    if not token or token.startswith("-"):
                        continue
                    resolved = (cwd / token).resolve()
                    if not resolved.is_dir():
                        continue
                    try:
                        rel = resolved.relative_to(_SKILLS_ROOT)
                    except ValueError:
                        continue  # a real directory, but not one of ours
                    args.add(rel.as_posix())
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


def _this_module():
    """This module object, for monkeypatching module-level constants."""
    import sys
    return sys.modules[__name__]


# ---------------------------------------------------------------------------
# Resolver regression tests
#
# The guard is only as good as _ci_pytest_arguments(). These pin the specific
# way it was wrong: a pytest argument was resolved against skills/ no matter
# which directory the step actually ran in.
# ---------------------------------------------------------------------------


def _fake_workflow(job: dict) -> dict:
    return {"jobs": {"j": job}}


def test_working_directory_precedence_follows_github_actions() -> None:
    """step > job defaults > workflow defaults > repo root."""
    workflow = {"defaults": {"run": {"working-directory": "wf"}}}
    job = {"defaults": {"run": {"working-directory": "job"}}}

    assert _step_working_directory(workflow, job, {"working-directory": "step"}) == (
        _REPO_ROOT / "step"
    )
    assert _step_working_directory(workflow, job, {}) == _REPO_ROOT / "job"
    assert _step_working_directory(workflow, {}, {}) == _REPO_ROOT / "wf"
    assert _step_working_directory({}, {}, {}) == _REPO_ROOT


def test_foreign_job_running_pytest_on_its_own_tests_dir_is_not_credited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """The exact false positive this guard shipped with.

    ``packages/context-eval`` has its own ``tests/`` directory and its CI job
    runs ``uv run pytest tests -q`` from there. Resolved against ``skills/``,
    that bare ``tests`` token marked ``skills/tests`` -- and by the
    covered-ancestor rule every directory beneath it -- as reached by CI.
    """
    workflow = _fake_workflow({
        "defaults": {"run": {"working-directory": "packages/context-eval"}},
        "steps": [{"run": 'uv run pytest tests -q -m "not e2e"'}],
    })
    fake_ci = tmp_path / "ci.yml"
    fake_ci.write_text(yaml.safe_dump(workflow))
    monkeypatch.setattr(_this_module(), "_CI_WORKFLOW", fake_ci)

    assert "tests" not in _ci_pytest_arguments(), (
        "a bare `tests` token from a job rooted outside skills/ must not credit "
        "skills/tests"
    )


def test_a_skills_rooted_job_is_still_credited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """The fix must not overcorrect: real skills/ coverage still counts."""
    workflow = _fake_workflow({
        "defaults": {"run": {"working-directory": "skills"}},
        "steps": [{"run": "uv run pytest tests/ci_coverage -q"}],
    })
    fake_ci = tmp_path / "ci.yml"
    fake_ci.write_text(yaml.safe_dump(workflow))
    monkeypatch.setattr(_this_module(), "_CI_WORKFLOW", fake_ci)

    assert "tests/ci_coverage" in _ci_pytest_arguments()


def test_repo_root_relative_skills_path_is_credited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A job with no working-directory names paths from the repo root."""
    workflow = _fake_workflow({
        "steps": [{
            "run": "python -m pytest skills/bug-scrub/tests/ skills/fix-scrub/tests/ -v",
        }],
    })
    fake_ci = tmp_path / "ci.yml"
    fake_ci.write_text(yaml.safe_dump(workflow))
    monkeypatch.setattr(_this_module(), "_CI_WORKFLOW", fake_ci)

    args = _ci_pytest_arguments()
    assert {"bug-scrub/tests", "fix-scrub/tests"} <= args


def test_leading_cd_moves_the_resolution_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """``cd agent-coordinator && pytest tests/...`` must not credit skills/."""
    workflow = _fake_workflow({
        "steps": [{
            "run": "cd agent-coordinator && uv run pytest tests/integration -v",
        }],
    })
    fake_ci = tmp_path / "ci.yml"
    fake_ci.write_text(yaml.safe_dump(workflow))
    monkeypatch.setattr(_this_module(), "_CI_WORKFLOW", fake_ci)

    assert "tests/integration" not in _ci_pytest_arguments()


def test_the_guard_itself_is_reached_by_ci() -> None:
    """The one directory that must never be unrun is this one.

    This guard sat loose in skills/tests, which no testpaths entry names, so it
    never ran -- and a guard that never runs is exactly the failure it exists to
    prevent. Its own directory is now in testpaths; assert that explicitly
    rather than relying on the parametrized sweep to notice.
    """
    own_dir = Path(__file__).resolve().parent.relative_to(_SKILLS_ROOT).as_posix()
    assert own_dir in _covered(), (
        f"{own_dir} is not reached by CI -- the coverage guard is unguarded"
    )


# --- packages/ coverage -------------------------------------------------------
#
# The checks above ask "is this skills/ directory reached by CI". This one asks
# the question a level up, because the gap that actually bit was an entire
# package tree with no job at all -- something a skills-rooted scan cannot see
# by construction.

_PACKAGES_ROOT = _REPO_ROOT / "packages"


def _package_suites() -> list[str]:
    """Package names under packages/ that ship a non-empty tests/ directory."""
    if not _PACKAGES_ROOT.is_dir():  # pragma: no cover - always present here
        return []
    found = []
    for entry in sorted(_PACKAGES_ROOT.iterdir()):
        tests = entry / "tests"
        if entry.is_dir() and tests.is_dir() and any(tests.rglob("test_*.py")):
            found.append(entry.name)
    return found


def _packages_running_pytest_in_ci() -> set[str]:
    """Package names some CI job runs pytest inside.

    Credited on the step's resolved working directory rather than on job names
    or pytest arguments: a job is only covering a package if the process it
    starts actually runs there. `packages/gen-eval` also hosts steps that run
    from the repo root, and those must not count for it.
    """
    if not _CI_WORKFLOW.exists():  # pragma: no cover - workflow always present
        pytest.skip(f"CI workflow not found at {_CI_WORKFLOW}")
    workflow = yaml.safe_load(_CI_WORKFLOW.read_text())

    covered: set[str] = set()
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            run = step.get("run")
            if not run or "pytest" not in run:
                continue
            cwd = _step_working_directory(workflow, job, step).resolve()
            try:
                rel = cwd.relative_to(_PACKAGES_ROOT)
            except ValueError:
                continue
            if rel.parts:
                covered.add(rel.parts[0])
    return covered


@pytest.mark.parametrize("package", _package_suites())
def test_every_package_suite_runs_in_ci(package: str) -> None:
    assert package in _packages_running_pytest_in_ci(), (
        f"packages/{package}/tests/ exists but no CI job runs pytest from "
        f"packages/{package}. Add a job to .github/workflows/ci.yml modelled on "
        "`code-search-tests`. A suite CI never runs fails the same way as one "
        "that always passes -- packages/code-search was red for six weeks this "
        "way."
    )


def test_the_package_scan_finds_the_known_suites() -> None:
    """A zero-length parametrization would pass vacuously.

    Names the four members present when this guard was written; a fifth is
    expected to appear and is not asserted against.
    """
    suites = set(_package_suites())
    assert {"agent-scenarios", "code-search", "context-eval", "gen-eval"} <= suites, (
        f"packages/ scan returned {sorted(suites)}; _PACKAGES_ROOT is wrong"
    )
