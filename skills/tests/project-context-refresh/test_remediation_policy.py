"""Policy tests for the dependency-update remediation servo (tasks 5.1, 5.2).

The servo introduced by ``rescope-context-drift-enforcement`` section 4 is this
repository's FIRST ``contents: write`` grant. Both workflows are
``permissions: contents: read`` today with no job-level overrides anywhere, and
``GITHUB_TOKEN`` appears exactly once, as a read token. Design D5 makes the
confinement of that grant normative rather than conventional, so it is tested
here rather than left to review:

* the write steps are unreachable on anything but a dependency-update bot pull
  request opened from a branch of this repository, and
* the grant is declared on that one job and nowhere else.

Spec scenarios covered
(``openspec/changes/rescope-context-drift-enforcement/specs/
project-context-refresh-orchestration/spec.md``, requirement "Automated
remediation is confined to dependency-update pull requests"):

* "Human pull request is not written to" — :func:`test_human_pull_request_never_reaches_the_write_steps`
  and :func:`test_no_job_outside_the_servo_writes_to_the_repository`
* "Write permission is scoped to the remediation job" —
  :func:`test_no_workflow_declares_a_workflow_level_write_grant`,
  :func:`test_exactly_one_job_declares_the_write_grant` and
  :func:`test_the_write_grant_is_confined_to_repository_contents`

The guard is asserted BEHAVIOURALLY, not by string match. A job-level ``if:``
that mentions ``dependabot[bot]`` somewhere proves nothing; what matters is the
verdict the expression reaches for a given event payload. :func:`_evaluate`
therefore parses the guard into comparison terms and evaluates it against
synthetic ``github`` contexts. It understands exactly one expression shape — a
conjunction of ``==``/``!=`` comparisons — and raises rather than guessing on
anything else, so the suite can never silently green-light a guard it did not
actually understand.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW_DIR = _REPO_ROOT / ".github" / "workflows"
_CI_YML = _WORKFLOW_DIR / "ci.yml"

#: The one job that may carry a write grant.
_SERVO_JOB = "dependency-update-remediation"

#: The dependency-update bot's login, as GitHub reports it in both
#: ``github.actor`` and ``github.event.pull_request.user.login``.
_BOT = "dependabot[bot]"

#: Stand-in for ``github.repository`` in the synthetic contexts below. Its value
#: is irrelevant; what matters is whether the head repository equals it.
_THIS_REPO = "owner/agentic-coding-tools"

#: Every permission scope GitHub accepts a ``write`` value for. Used to detect a
#: write grant without hard-coding the assumption that ``contents`` is the only
#: interesting one.
_WRITE_VALUES = {"write", "write-all"}


# ---------------------------------------------------------------------------
# Workflow loading
# ---------------------------------------------------------------------------


def _load(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        return yaml.safe_load(handle) or {}


def _workflow_paths() -> list[Path]:
    paths = sorted(_WORKFLOW_DIR.glob("*.yml")) + sorted(_WORKFLOW_DIR.glob("*.yaml"))
    assert paths, f"no workflows found under {_WORKFLOW_DIR}"
    return paths


def _all_jobs() -> list[tuple[Path, str, dict[str, Any]]]:
    """Every (workflow, job id, job) triple across ``.github/workflows``."""
    triples: list[tuple[Path, str, dict[str, Any]]] = []
    for path in _workflow_paths():
        for job_id, job in (_load(path).get("jobs") or {}).items():
            if isinstance(job, dict):
                triples.append((path, job_id, job))
    return triples


def _servo_job() -> dict[str, Any]:
    jobs = _load(_CI_YML).get("jobs") or {}
    job = jobs.get(_SERVO_JOB)
    assert job is not None, (
        f"no {_SERVO_JOB!r} job in {_CI_YML}; the dependency-update remediation "
        "servo (task 5.3) has not been added"
    )
    return job


def _job_script(job: dict[str, Any]) -> str:
    """Every ``run:`` script in *job*, concatenated."""
    return "\n".join(
        str(step.get("run", ""))
        for step in job.get("steps") or []
        if isinstance(step, dict)
    )


def _write_scopes(permissions: Any) -> set[str]:
    """The scopes *permissions* grants at ``write`` level.

    Handles both accepted shapes: the ``write-all`` shorthand string and the
    per-scope mapping. An unrecognised shape returns nothing granted, which is
    the safe direction only because every other test here asserts a grant is
    *present* where it must be, not merely absent where it must not.
    """
    if isinstance(permissions, str):
        return {"*"} if permissions in _WRITE_VALUES else set()
    if isinstance(permissions, dict):
        return {
            scope
            for scope, level in permissions.items()
            if isinstance(level, str) and level in _WRITE_VALUES
        }
    return set()


# ---------------------------------------------------------------------------
# A deliberately small GitHub-expression evaluator
# ---------------------------------------------------------------------------

_OPERAND = r"[A-Za-z_][A-Za-z0-9_.\-\[\]]*"
_TERM = re.compile(
    rf"^(?P<left>{_OPERAND})\s*(?P<op>==|!=)\s*(?P<right>'[^']*'|{_OPERAND})$"
)


def _parse_guard(expression: str) -> list[tuple[str, str, str]]:
    """Split *expression* into ``(left, op, right)`` comparison terms.

    Raises on anything that is not a plain ``&&`` conjunction of comparisons.
    That refusal is the point: a guard this parser cannot evaluate is a guard
    this suite has not tested, and reporting it as a pass would be exactly the
    unfalsifiable green the surrounding gates exist to prevent.
    """
    text = expression.strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2].strip()
    if "||" in text or "!" in text.replace("!=", ""):
        raise AssertionError(
            f"the {_SERVO_JOB!r} guard is not a plain conjunction and this test "
            f"cannot evaluate it: {expression!r}"
        )
    terms: list[tuple[str, str, str]] = []
    for raw in text.split("&&"):
        match = _TERM.match(raw.strip())
        if match is None:
            raise AssertionError(
                f"the {_SERVO_JOB!r} guard contains a term this test cannot "
                f"evaluate: {raw.strip()!r}. Keep the guard a conjunction of "
                "`<context.path> ==|!= '<literal>'|<context.path>` terms, or "
                "teach this parser the new shape -- do not leave it untested."
            )
        terms.append((match["left"], match["op"], match["right"]))
    assert terms, f"the {_SERVO_JOB!r} guard is empty"
    return terms


def _lookup(context: dict[str, Any], path: str) -> Any:
    node: Any = context
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _resolve(context: dict[str, Any], operand: str) -> Any:
    if operand.startswith("'"):
        return operand[1:-1]
    return _lookup(context, operand)


def _evaluate(expression: str, context: dict[str, Any]) -> bool:
    for left, op, right in _parse_guard(expression):
        equal = _resolve(context, left) == _resolve(context, right)
        if not (equal if op == "==" else not equal):
            return False
    return True


def _pull_request_context(
    *,
    author: str,
    actor: str | None = None,
    head_repo: str = _THIS_REPO,
) -> dict[str, Any]:
    return {
        "github": {
            "event_name": "pull_request",
            "repository": _THIS_REPO,
            "actor": actor if actor is not None else author,
            "event": {
                "pull_request": {
                    "user": {"login": author},
                    "head": {
                        "ref": "dependabot/pip/skills/ruff-0.16.0",
                        "repo": {"full_name": head_repo},
                    },
                }
            },
        }
    }


def _non_pull_request_context(event_name: str) -> dict[str, Any]:
    """A ``push``/``merge_group`` context: ``github.event.pull_request`` is null."""
    return {
        "github": {
            "event_name": event_name,
            "repository": _THIS_REPO,
            "actor": _BOT,
            "event": {},
        }
    }


def _guard() -> str:
    job = _servo_job()
    guard = job.get("if")
    assert isinstance(guard, str) and guard.strip(), (
        f"{_SERVO_JOB!r} has no job-level `if:`. The guard must prevent the job "
        "from REACHING its write steps; a job that runs on a human pull request "
        "and merely decides not to commit is a weaker confinement of the "
        "repository's first `contents: write` grant."
    )
    return guard


# ---------------------------------------------------------------------------
# 5.1 -- human pull requests are never written to
# ---------------------------------------------------------------------------


def test_the_servo_actually_carries_write_steps() -> None:
    """The reachability tests below are vacuous unless the steps exist.

    If the job stopped committing and pushing, "a human pull request is never
    written to" would hold trivially and every guard test would still pass while
    testing nothing.
    """
    script = _job_script(_servo_job())
    assert "git commit" in script, f"{_SERVO_JOB!r} never commits"
    assert "git push" in script, f"{_SERVO_JOB!r} never pushes"


def test_guard_admits_a_dependency_update_pull_request() -> None:
    assert _evaluate(_guard(), _pull_request_context(author=_BOT)) is True, (
        "the guard rejects a genuine dependency-update pull request, so the "
        "servo would never remediate anything"
    )


def test_human_pull_request_never_reaches_the_write_steps() -> None:
    """Spec scenario: "Human pull request is not written to"."""
    context = _pull_request_context(author="a-human-contributor")
    assert _evaluate(_guard(), context) is False, (
        "the guard admits a pull request opened by a person; the job would "
        "reach its commit and push steps on a human branch"
    )


def test_a_human_actor_on_a_bot_branch_does_not_widen_the_guard() -> None:
    """Authorship, not who happened to trigger the run, is the gate.

    ``github.actor`` is the run's initiator and is the wrong thing to key on
    alone: a person who re-runs or pushes to a branch becomes the actor without
    becoming the author. Whichever of the two the guard reads, admitting a
    human-authored pull request is the failure.
    """
    context = _pull_request_context(author="a-human-contributor", actor=_BOT)
    assert _evaluate(_guard(), context) is False


def test_fork_pull_request_never_reaches_the_write_steps() -> None:
    """A fork's ``GITHUB_TOKEN`` is read-only whatever ``permissions:`` says.

    Genuine dependency-update pull requests are always opened from a branch of
    this repository, so excluding forks costs nothing and stops the job from
    attempting a push it provably cannot complete.
    """
    context = _pull_request_context(author=_BOT, head_repo="someone-else/fork")
    assert _evaluate(_guard(), context) is False


@pytest.mark.parametrize("event_name", ["push", "merge_group"])
def test_non_pull_request_events_never_reach_the_write_steps(event_name: str) -> None:
    assert _evaluate(_guard(), _non_pull_request_context(event_name)) is False


def test_no_step_reintroduces_itself_past_the_job_guard() -> None:
    """No step may carry its own ``if:``.

    A step-level condition on a job-level-guarded job is either redundant or an
    attempt to run something the job guard excluded; either way it makes the
    confinement harder to read than it is worth.
    """
    offenders = [
        step.get("name", step.get("uses", "<unnamed>"))
        for step in _servo_job().get("steps") or []
        if isinstance(step, dict) and step.get("if")
    ]
    assert not offenders, (
        f"steps in {_SERVO_JOB!r} carry their own `if:`: {offenders}. The single "
        "job-level guard is the whole confinement story."
    )


def test_no_job_outside_the_servo_writes_to_the_repository() -> None:
    """File-wide form of "a human pull request is not written to".

    Every other job in every workflow runs unguarded on human pull requests, so
    the confinement holds only if none of them commits or pushes.
    """
    offenders = [
        f"{path.name}:{job_id}"
        for path, job_id, job in _all_jobs()
        if job_id != _SERVO_JOB
        and re.search(r"git (commit|push)\b", _job_script(job))
    ]
    assert not offenders, (
        f"jobs other than {_SERVO_JOB!r} commit or push: {offenders}"
    )


# ---------------------------------------------------------------------------
# 5.2 -- the write grant is job-scoped
# ---------------------------------------------------------------------------


def test_no_workflow_declares_a_workflow_level_write_grant() -> None:
    """Spec scenario: "Write permission is scoped to the remediation job".

    A workflow-level grant applies to every job in the file, including the ones
    that run unguarded on every human pull request.
    """
    offenders = {
        path.name: sorted(scopes)
        for path in _workflow_paths()
        if (scopes := _write_scopes(_load(path).get("permissions")))
    }
    assert not offenders, (
        f"workflow-level write grants found: {offenders}. Write permission "
        f"belongs on {_SERVO_JOB!r} alone."
    )


def test_exactly_one_job_declares_the_write_grant() -> None:
    granting = {
        f"{path.name}:{job_id}": sorted(scopes)
        for path, job_id, job in _all_jobs()
        if (scopes := _write_scopes(job.get("permissions")))
    }
    assert list(granting) == [f"{_CI_YML.name}:{_SERVO_JOB}"], (
        f"expected exactly one job to declare a write grant, got: {granting}"
    )


def test_the_write_grant_is_confined_to_repository_contents() -> None:
    permissions = _servo_job().get("permissions")
    assert isinstance(permissions, dict), (
        f"{_SERVO_JOB!r} must declare an explicit per-scope `permissions:` "
        f"mapping, not {permissions!r}"
    )
    assert _write_scopes(permissions) == {"contents"}, (
        f"{_SERVO_JOB!r} grants more than repository contents: {permissions!r}. "
        "The servo commits and pushes; it neither reads nor writes anything else."
    )


# ---------------------------------------------------------------------------
# 5.4 / 5.5 -- the two design-D5 constraints the servo has to satisfy
# ---------------------------------------------------------------------------


def _step_index(job: dict[str, Any], needle: str) -> int:
    for index, step in enumerate(job.get("steps") or []):
        if isinstance(step, dict) and needle in str(step.get("run", "")):
            return index
    raise AssertionError(f"no step in {_SERVO_JOB!r} runs {needle!r}")


def test_the_base_is_refreshed_before_anything_is_regenerated() -> None:
    """Design D5 constraint 1.

    ``docs/merge-logs/2026-08-24.md:29`` records that re-running checks was
    "theatre" because it replays the same merge commit; the fix was
    ``refresh-branch``. Artifacts regenerated on a stale base are themselves
    drift.
    """
    job = _servo_job()
    assert _step_index(job, "git fetch") < _step_index(job, "cli.py"), (
        "the servo regenerates before it refreshes the base"
    )
    assert _step_index(job, "git merge") < _step_index(job, "cli.py"), (
        "the servo regenerates before it merges the refreshed base"
    )


def test_one_argv_builder_serves_both_the_write_and_the_check() -> None:
    """Design D5 constraint 2.

    ``generate_tool_descriptor.py:570-573``: check mode asserts byte identity
    against what it would generate from its own argv, so a writer invoked with
    different flags than the checker reports drift on a perfectly up-to-date
    file, forever. The servo therefore builds ONE argv and varies only the
    subcommand word.
    """
    script = _job_script(_servo_job())
    hardcoded = re.findall(r"cli\.py\s+(?:generate|check)\b.*", script)
    assert not hardcoded, (
        "the servo hard-codes a producer mode into an invocation: "
        f"{hardcoded}. Generate and check must come from one parametrised "
        "argv, or the two can drift apart unnoticed."
    )
    parametrised = re.findall(r'cli\.py"?\s+"\$\{?\w+\}?"', script)
    assert len(parametrised) == 1, (
        "expected exactly one mode-parametrised cli.py invocation in "
        f"{_SERVO_JOB!r}, found {len(parametrised)}: {parametrised}"
    )
