"""Every CI job must be bounded, and superseded PR runs must be cancelled.

A job with no ``timeout-minutes`` inherits GitHub's default of 360 minutes. That
is not a slow job, it is an unbounded one: a hang presents to the operator as
``pending`` forever, which is indistinguishable from a busy queue. Nothing in
the check output says "this will never finish".

This guard exists because of PR #463. Its ``test-integration`` job hung on the
first test in ``tests/e2e/postgres/``. The same job takes about 55 seconds when
healthy, so the hang was three orders of magnitude outside normal -- and still
nothing failed. It was found only by reading the job's step list by hand and
noticing the pytest step had been ``in_progress`` for 68 minutes.

Two runs were hung simultaneously, which is the second half of this guard. There
was no ``concurrency`` group, so pushing the fix did not cancel the superseded
run; both sat burning runner time toward a 6-hour ceiling. Cancellation is
restricted to ``pull_request`` events on purpose: a push to ``main`` or a
``merge_group`` entry must always run to completion, because nothing re-runs it
later and cancelling it would leave ``main`` with no recorded verdict.

Fifteen of twenty-one jobs were unbounded when this was written, including all
six required status checks. A hang in any required check blocks every merge in
the repository for six hours.

The specific ceilings are deliberately loose. They are not performance budgets
and should not be tuned to observed runtimes -- a job drifting from 55s to 3
minutes is a question for a human, not a CI failure. The only property asserted
here is that a hung job dies in minutes rather than hours.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_SKILLS_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SKILLS_ROOT.parent
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"

# A job may take longer than this and still be healthy; that is fine. The
# ceiling only has to be low enough that a hang is caught the same working day.
_MAX_TIMEOUT_MINUTES = 30


def _workflow_files() -> list[Path]:
    return sorted(_WORKFLOWS.glob("*.yml")) + sorted(_WORKFLOWS.glob("*.yaml"))


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_workflow_directory_is_where_we_think_it_is() -> None:
    """Fail loudly rather than vacuously passing over an empty glob.

    Every assertion below iterates over discovered files. If the path were
    wrong, the iteration would be empty and the whole module would pass while
    checking nothing -- the exact failure mode the sibling coverage guard in
    this directory was written to catch.
    """
    assert _WORKFLOWS.is_dir(), f"no workflow directory at {_WORKFLOWS}"
    assert _workflow_files(), f"no workflow files under {_WORKFLOWS}"


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_every_job_declares_a_timeout(path: Path) -> None:
    """No job may inherit GitHub's 360-minute default."""
    workflow = _load(path)
    jobs = workflow.get("jobs") or {}
    assert jobs, f"{path.name} declares no jobs"

    missing = sorted(
        name
        for name, body in jobs.items()
        if isinstance(body, dict) and "timeout-minutes" not in body
    )
    assert not missing, (
        f"{path.name}: {len(missing)} job(s) have no timeout-minutes and will "
        f"run to GitHub's 360-minute default if they hang: {', '.join(missing)}"
    )


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_timeouts_are_short_enough_to_catch_a_hang(path: Path) -> None:
    """A ceiling of hours is not meaningfully different from no ceiling."""
    workflow = _load(path)
    for name, body in (workflow.get("jobs") or {}).items():
        if not isinstance(body, dict):
            continue
        timeout = body.get("timeout-minutes")
        if timeout is None:
            continue  # reported by the test above
        assert isinstance(timeout, int), (
            f"{path.name}:{name}: timeout-minutes must be an integer, got {timeout!r}"
        )
        assert 0 < timeout <= _MAX_TIMEOUT_MINUTES, (
            f"{path.name}:{name}: timeout-minutes={timeout} exceeds the "
            f"{_MAX_TIMEOUT_MINUTES}-minute ceiling. Raise the ceiling "
            f"deliberately if a job genuinely needs longer."
        )


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_superseded_pull_request_runs_are_cancelled(path: Path) -> None:
    """A new push must cancel the run it supersedes -- for PRs only."""
    workflow = _load(path)
    concurrency = workflow.get("concurrency")
    assert concurrency, (
        f"{path.name}: no concurrency group, so a push does not cancel the run "
        f"it supersedes. Two hung jobs ran simultaneously on PR #463 for this "
        f"reason."
    )

    group = str(concurrency.get("group", ""))
    assert "github.workflow" in group, (
        f"{path.name}: concurrency group {group!r} is not workflow-scoped, so "
        f"unrelated workflows would cancel each other."
    )
    assert "pull_request" in group or "github.ref" in group, (
        f"{path.name}: concurrency group {group!r} does not vary per PR/ref, so "
        f"one PR's run would cancel another's."
    )

    cancel = str(concurrency.get("cancel-in-progress", ""))
    assert "pull_request" in cancel, (
        f"{path.name}: cancel-in-progress={cancel!r}. It must be conditioned on "
        f"the event being a pull_request. Cancelling a push to main or a "
        f"merge_group entry would leave main with no recorded verdict, because "
        f"nothing re-runs those."
    )


def test_required_status_checks_are_all_bounded() -> None:
    """The six required checks are the ones a hang hurts most.

    A hang in any of these blocks every merge in the repository until it times
    out. They are named explicitly so that moving one between workflow files, or
    renaming it, surfaces here rather than silently dropping it from the guard.
    """
    required = {
        "test",
        "test-infra-skills",
        "test-skills",
        "validate-specs",
        "check-docker-imports",
        "secret-scan",
    }

    found: dict[str, int] = {}
    for path in _workflow_files():
        for name, body in (_load(path).get("jobs") or {}).items():
            if name in required and isinstance(body, dict):
                timeout = body.get("timeout-minutes")
                if timeout is not None:
                    found[name] = timeout

    missing = sorted(required - set(found))
    assert not missing, (
        f"required status check(s) {missing} have no timeout-minutes, or no "
        f"longer exist under these names. A hang in a required check blocks "
        f"every merge in the repository."
    )
