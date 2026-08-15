"""Wiring test for the full-capability requirement-traceability sweep (task 5.7).

The ``requirement-traceability-sweep`` job in ``.github/workflows/ci.yml`` is ONE
job on all three declared events (``push`` to main, ``pull_request``,
``merge_group``), selecting both its invocation and whether its result blocks on
``github.event_name``. We test that bash logic by extracting it into a shell
script fragment and driving it against a real throwaway git repository (change
scope tests a merge base, so a fixture needs real commits — see task 3.15's
note) and a stub ``check_traceability.py`` whose exit code and stdout we
control, mirroring
``skills/tests/validate-feature/test_validate_feature_gate.py``'s approach for
the neighboring change-scoped gate.

Spec scenarios covered (openspec/changes/trace-requirements-to-contracts/specs/
gen-eval-framework/spec.md, "The full sweep blocks opted-in surfaces and
reports the rest"):
- "A pull request that was not planned through OpenSpec skips"
  (non-openspec-pr-skips)
- "An archive pull request derives no change id" (archive-pull-requests-skip)
- "A pull request touching two change directories fails as ambiguous"
  (ambiguous-change-fails)
- "An unresolvable base fails rather than skipping"
  (unresolvable-base-fails-not-skips) — both `pull_request` and `merge_group`
- "A merge group batching two changes is evaluated once per change"
  (merge-group-iterates-over-the-batch)
- "The run on the integration branch cannot fail"
  (push-to-integration-branch-reports)
- "The job is not guarded off any declared event"
  (job-runs-on-every-declared-event)

Two scenarios on the same spec requirement line are NOT covered here by
design: "An opted-in surface fails the sweep" / "A surface that has not
opted in is reported, not failed" are wp-gate's tests (they exercise the
gate itself, not this job's argv), and "the change flag selects which delta
shadows the archive" / "omitting the change flag unions every on-branch
delta" / "a merge group is not evaluated against changes outside the batch"
are task 3.16's resolution-mode tests — a wiring test asserts the argv this
job builds, not what the gate resolves once invoked with it.
"""
from __future__ import annotations

import stat
import subprocess
import textwrap
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_JOB_NAME = "requirement-traceability-sweep"


def _load_job() -> dict:
    with _CI_YML.open() as fh:
        workflow = yaml.safe_load(fh)
    return workflow["jobs"][_JOB_NAME]


def _sweep_step() -> dict:
    job = _load_job()
    for step in job["steps"]:
        if step.get("name") == "Full-capability requirement traceability sweep":
            return step
    raise AssertionError(f"no sweep step found in job {_JOB_NAME!r}")


# Bash fragment extracted from .github/workflows/ci.yml's
# "Full-capability requirement traceability sweep" step. Kept byte-for-byte
# in sync with that step's code block; test_fragment_matches_ci_yml (below)
# fails loudly the moment the two diverge, so "kept in sync" is enforced,
# not just asserted in a comment.
SWEEP_FRAGMENT = textwrap.dedent("""
set -uo pipefail
# GitHub Actions runs a `run:` step with no `shell:` key as `bash -e {0}`,
# so errexit is ON here by default. Every branch below deliberately
# inspects a command's status rather than dying on it: a diff that touches
# no change directory is a SKIP at exit 0, the post-merge run must never
# block whatever the gate returns, and the merge_group loop must visit
# every batched id instead of stopping at the first failure. Under errexit
# all three of those collapse into "abort with the gate's status", so turn
# it off explicitly and check each status by hand. The suite drives this
# fragment with `bash -e` for the same reason.
set +e

TRACE_GATE="packages/gen-eval/scripts/check_traceability.py"
TRACE_PYTHON="packages/gen-eval/.venv/bin/python"
if [ ! -f "$TRACE_PYTHON" ]; then TRACE_PYTHON="python3"; fi

# Change-id derivation (task 5.7). All three conditions are
# load-bearing: --no-renames so the derived set does not depend on
# git's similarity heuristic; --diff-filter=d (exclude deletions) so
# the source half of an archive `git mv` does not name the change
# being archived; grep -v archive so the destination half does not
# name the literal id `archive`. Dropping any one breaks a real
# archive pull request (see design D12's measured table).
derive_change_ids() {
  # Returns 2 — distinct from "resolved the base and derived nothing" —
  # when git cannot resolve the base commit. Run as a single pipeline the
  # two are indistinguishable: `fatal: bad object` and "grep matched
  # nothing" both arrive as a non-zero status with empty stdout, and the
  # caller then takes the no-change SKIP path on a base it never read.
  # The spec puts those on different exit paths, so the git status is
  # captured on its own before anything is piped.
  local raw
  raw="$(git diff --no-renames --diff-filter=d --name-only "$1" HEAD \\
    -- openspec/changes/)" || return 2
  printf '%s\\n' "$raw" \\
    | sed 's#^openspec/changes/\\([^/]*\\)/.*#\\1#' \\
    | sort -u \\
    | grep -v '^archive$'
  return 0
}

run_gate() {
  # $1: a change id, or empty string for union mode (--change
  # omitted). Bare invocation, never piped — a pipeline's $? is the
  # last stage's status.
  if [ -n "$1" ]; then
    "$TRACE_PYTHON" "$TRACE_GATE" --scope capability --change "$1"
  else
    "$TRACE_PYTHON" "$TRACE_GATE" --scope capability
  fi
}

case "$EVENT_NAME" in
  pull_request)
    if [ -z "${PR_BASE_SHA:-}" ]; then
      echo "::error::requirement-traceability sweep: unresolvable base for pull_request (github.event.pull_request.base.sha is empty)"
      exit 1
    fi
    CHANGE_IDS="$(derive_change_ids "$PR_BASE_SHA")"
        if [ $? -eq 2 ]; then
          echo "::error::requirement-traceability sweep: unresolvable base for pull_request (github.event.pull_request.base.sha='$PR_BASE_SHA' could not be resolved against this checkout)"
          exit 1
        fi
    if [ -z "$CHANGE_IDS" ]; then
      echo "SKIP: requirement-traceability sweep — no openspec/changes/<id>/ directory touched on ${PR_HEAD_REF:-this branch}"
      exit 0
    fi
    COUNT=$(printf '%s\\n' "$CHANGE_IDS" | grep -c .)
    if [ "$COUNT" -gt 1 ]; then
      echo "::error::requirement-traceability sweep: ambiguous — pull request touches multiple change directories: $(printf '%s' "$CHANGE_IDS" | tr '\\n' ' ')"
      exit 1
    fi
    run_gate "$CHANGE_IDS"
    exit $?
    ;;
  merge_group)
    if [ -z "${MERGE_GROUP_BASE_SHA:-}" ]; then
      echo "::error::requirement-traceability sweep: unresolvable base for merge_group (github.event.merge_group.base_sha is empty)"
      exit 1
    fi
    CHANGE_IDS="$(derive_change_ids "$MERGE_GROUP_BASE_SHA")"
        if [ $? -eq 2 ]; then
          echo "::error::requirement-traceability sweep: unresolvable base for merge_group (github.event.merge_group.base_sha='$MERGE_GROUP_BASE_SHA' could not be resolved against this checkout)"
          exit 1
        fi
    if [ -z "$CHANGE_IDS" ]; then
      echo "SKIP: requirement-traceability sweep — no openspec/changes/<id>/ directory touched in merge group ${MERGE_GROUP_REF:-<unknown>}"
      exit 0
    fi
    # No ambiguity rule here: a merge group's diff spans every
    # batched pull request, so several change directories is the
    # ordinary case. Iterate and block if any invocation fails.
    OVERALL=0
    while IFS= read -r id; do
      [ -z "$id" ] && continue
      echo "requirement-traceability sweep: evaluating batched change '$id'"
      run_gate "$id"
      [ $? -ne 0 ] && OVERALL=1
    done <<< "$CHANGE_IDS"
    exit "$OVERALL"
    ;;
  push)
    # Union mode: every on-branch delta shadows the archive at once.
    # Report-only — its exit status must not depend on what it found.
    echo "requirement-traceability sweep: post-merge report (union of every on-branch delta, non-blocking)"
    run_gate ""
    echo "requirement-traceability sweep: post-merge run never blocks; exiting 0 regardless of the result above"
    exit 0
    ;;
  *)
    echo "::error::requirement-traceability sweep: unhandled event '$EVENT_NAME' — no rule for this trigger"
    exit 1
    ;;
esac
""")


def test_fragment_matches_ci_yml() -> None:
    """The hardcoded SWEEP_FRAGMENT above must be byte-for-byte identical to
    the real step in ci.yml — this is what makes "kept in sync" true rather
    than aspirational."""
    step = _sweep_step()
    assert step["run"].strip("\n") == SWEEP_FRAGMENT.strip("\n"), (
        "SWEEP_FRAGMENT has drifted from the 'Full-capability requirement "
        "traceability sweep' step in .github/workflows/ci.yml — update the "
        "constant in this test file to match."
    )


def test_job_has_no_if_guard() -> None:
    """Spec: 'The job is not guarded off any declared event' — the job must
    not carry a condition excluding it from any of the three declared
    triggers, and CI must actually declare all three."""
    with _CI_YML.open() as fh:
        workflow = yaml.safe_load(fh)
    job = workflow["jobs"][_JOB_NAME]
    assert "if" not in job, (
        f"{_JOB_NAME} carries an `if:` guard — a required check that does not "
        "run on merge_group is not a check on the merge candidate"
    )
    # PyYAML parses the unquoted `on:` workflow key as the boolean True
    # (YAML 1.1's bareword-boolean rule) rather than the string "on".
    triggers = workflow[True]
    assert "push" in triggers and "main" in triggers["push"]["branches"]
    assert "pull_request" in triggers
    assert "merge_group" in triggers
    for step in job["steps"]:
        assert "if" not in step, f"step {step.get('name')!r} carries an `if:` guard"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README.md").write_text("hello\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _make_stub_gate(
    project_root: Path, *, fail_ids: tuple[str, ...] = (), violation_text: str = "uncited requirement"
) -> Path:
    """A fake check_traceability.py that records its argv and fails only for
    the change ids (or "__union__" for --change omitted) named in fail_ids —
    hermetic, no real gen_eval/pydantic/yaml dependency required."""
    scripts_dir = project_root / "packages" / "gen-eval" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    stub = scripts_dir / "check_traceability.py"
    stub.write_text(
        textwrap.dedent(f"""\
            #!/usr/bin/env python3
            import sys
            argv = sys.argv[1:]
            print("argv: " + " ".join(argv))
            change_id = argv[argv.index("--change") + 1] if "--change" in argv else "__union__"
            if change_id in {list(fail_ids)!r}:
                print({violation_text!r})
                sys.exit(1)
            sys.exit(0)
            """)
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def _run(repo: Path, env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    """Drive the fragment the way GitHub Actions actually drives it.

    A ``run:`` step that declares no ``shell:`` key runs as ``bash -e {0}`` — a
    SCRIPT FILE, with errexit ON. Driving it here as ``bash -c <string>`` instead
    silently drops the ``-e``, and that one difference hid six of this job's nine
    spec-mandated behaviours: under errexit the no-change SKIP, the archive SKIP,
    the never-blocking push run and the per-id merge_group loop all collapse into
    "abort with the first non-zero status". Tests that cannot observe errexit
    cannot observe the job. Both properties — file, not -c; -e, not bare — are
    load-bearing; do not "simplify" either away.
    """
    import os

    env = dict(os.environ)
    env.update(env_extra)
    script = repo / ".sweep-under-test.sh"
    script.write_text(SWEEP_FRAGMENT)
    return subprocess.run(
        ["bash", "-e", str(script)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_non_openspec_pr_skips(tmp_path: Path) -> None:
    """Spec: 'A pull request that was not planned through OpenSpec skips' —
    base resolves, diff touches nothing under openspec/changes/ -> SKIP
    naming the branch, exit 0."""
    repo = _init_repo(tmp_path)
    base_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "README.md").write_text("hello, updated\n")
    _commit_all(repo, "unrelated change")

    result = _run(
        repo,
        {
            "EVENT_NAME": "pull_request",
            "PR_BASE_SHA": base_sha,
            "PR_HEAD_REF": "dependabot/pip/foo",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "SKIP: requirement-traceability sweep" in result.stdout
    assert "dependabot/pip/foo" in result.stdout
    assert "::error::" not in result.stdout


def test_archive_pull_request_derives_no_change_id(tmp_path: Path) -> None:
    """Spec: 'An archive pull request derives no change id' — a `git mv` from
    openspec/changes/<id>/ to openspec/changes/archive/<date>-<id>/, diffed
    with --no-renames, decomposes into a deletion and an addition. Neither
    half should yield a change id, so this SKIPs rather than deriving
    `archive` or the id being archived."""
    repo = _init_repo(tmp_path)
    change_dir = repo / "openspec" / "changes" / "derive-descriptors-from-contracts"
    change_dir.mkdir(parents=True)
    (change_dir / "spec.md").write_text("# a change\n")
    pre_archive_sha = _commit_all(repo, "add change")

    archive_dir = repo / "openspec" / "changes" / "archive" / "2026-08-15-derive-descriptors-from-contracts"
    archive_dir.mkdir(parents=True)
    (archive_dir / "spec.md").write_text("# a change\n")
    _git(repo, "rm", "-q", "-r", str(change_dir.relative_to(repo)))
    _commit_all(repo, "archive change")

    result = _run(
        repo,
        {
            "EVENT_NAME": "pull_request",
            "PR_BASE_SHA": pre_archive_sha,
            "PR_HEAD_REF": "openspec/archive-derive-descriptors-from-contracts",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "SKIP: requirement-traceability sweep" in result.stdout
    assert "::error::" not in result.stdout
    assert "ambiguous" not in result.stdout


def test_ambiguous_change_fails_on_pull_request(tmp_path: Path) -> None:
    """Spec: 'A pull request touching two change directories fails as
    ambiguous' — fail naming both candidates, do not choose."""
    repo = _init_repo(tmp_path)
    base_sha = _git(repo, "rev-parse", "HEAD")
    for change_id in ("change-a", "change-b"):
        change_dir = repo / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True)
        (change_dir / "spec.md").write_text(f"# {change_id}\n")
    _commit_all(repo, "add two changes")

    result = _run(
        repo,
        {
            "EVENT_NAME": "pull_request",
            "PR_BASE_SHA": base_sha,
            "PR_HEAD_REF": "some-branch",
        },
    )
    assert result.returncode == 1, result.stdout
    assert "::error::" in result.stdout
    assert "ambiguous" in result.stdout
    assert "change-a" in result.stdout
    assert "change-b" in result.stdout
    assert "SKIP" not in result.stdout


def test_single_change_pull_request_blocks_when_the_gate_fails(tmp_path: Path) -> None:
    """Spec: on `pull_request` the job invokes the gate with `--change <id>`
    and SHALL block.

    This is the primary blocking event, and until this test existed nothing
    covered it: the other pull_request cases all return before `run_gate` is
    ever reached (SKIP, SKIP, ambiguous, unresolvable base), so rewriting the
    arm's `exit $?` to `exit 0` left the whole suite green while the gate
    stopped gating. Both halves are asserted here — the argv built, and the
    non-zero status propagated."""
    repo = _init_repo(tmp_path)
    base_sha = _git(repo, "rev-parse", "HEAD")
    change_dir = repo / "openspec" / "changes" / "only-change"
    change_dir.mkdir(parents=True)
    (change_dir / "spec.md").write_text("# only-change\n")
    _commit_all(repo, "one change")
    _make_stub_gate(repo, fail_ids=("only-change",))

    result = _run(
        repo,
        {
            "EVENT_NAME": "pull_request",
            "PR_BASE_SHA": base_sha,
            "PR_HEAD_REF": "openspec/only-change",
        },
    )
    assert result.returncode == 1, result.stdout
    assert "argv: --scope capability --change only-change" in result.stdout
    assert "uncited requirement" in result.stdout
    assert "SKIP" not in result.stdout


def test_single_change_pull_request_passes_when_the_gate_passes(tmp_path: Path) -> None:
    """The same path's success half: a clean gate leaves the job at exit 0
    while still having invoked it change-scoped. Without this, a fragment that
    always failed would satisfy the blocking test above."""
    repo = _init_repo(tmp_path)
    base_sha = _git(repo, "rev-parse", "HEAD")
    change_dir = repo / "openspec" / "changes" / "only-change"
    change_dir.mkdir(parents=True)
    (change_dir / "spec.md").write_text("# only-change\n")
    _commit_all(repo, "one change")
    _make_stub_gate(repo)

    result = _run(
        repo,
        {
            "EVENT_NAME": "pull_request",
            "PR_BASE_SHA": base_sha,
            "PR_HEAD_REF": "openspec/only-change",
        },
    )
    assert result.returncode == 0, result.stdout
    assert "argv: --scope capability --change only-change" in result.stdout


def test_unresolvable_base_fails_pull_request(tmp_path: Path) -> None:
    """Spec: 'An unresolvable base fails rather than skipping' —
    github.event.pull_request.base.sha empty must fail naming the event, not
    take the no-change-directory SKIP path."""
    repo = _init_repo(tmp_path)
    result = _run(repo, {"EVENT_NAME": "pull_request", "PR_BASE_SHA": ""})
    assert result.returncode == 1, result.stdout
    assert "::error::" in result.stdout
    assert "pull_request" in result.stdout
    assert "SKIP" not in result.stdout


def test_nonempty_unresolvable_base_fails_pull_request(tmp_path: Path) -> None:
    """The reachable half of 'an unresolvable base fails rather than skipping'.

    An empty base sha is the easy case and the only one previously covered. The
    case that actually happens — a base commit that is a well-formed sha the
    checkout does not contain (force-pushed base, a fetch depth that did not
    reach it) — made `git diff` fail inside the command substitution, which the
    old single-pipeline derivation could not distinguish from "derived no ids".
    The job then printed the no-change SKIP and exited 0 against a base it had
    never read: a blocking gate silently not running."""
    repo = _init_repo(tmp_path)
    _make_stub_gate(repo)
    result = _run(
        repo,
        {
            "EVENT_NAME": "pull_request",
            "PR_BASE_SHA": "deadbeef" * 5,
            "PR_HEAD_REF": "openspec/some-change",
        },
    )
    assert result.returncode == 1, result.stdout
    assert "::error::" in result.stdout
    assert "pull_request" in result.stdout
    assert "SKIP" not in result.stdout


def test_nonempty_unresolvable_base_fails_merge_group(tmp_path: Path) -> None:
    """Same rule on merge_group, whose base sha is likewise a real commit that
    a shallow or stale checkout may simply not have."""
    repo = _init_repo(tmp_path)
    _make_stub_gate(repo)
    result = _run(
        repo,
        {
            "EVENT_NAME": "merge_group",
            "MERGE_GROUP_BASE_SHA": "deadbeef" * 5,
            "MERGE_GROUP_REF": "gh-readonly-queue/main/pr-9",
        },
    )
    assert result.returncode == 1, result.stdout
    assert "::error::" in result.stdout
    assert "merge_group" in result.stdout
    assert "SKIP" not in result.stdout


def test_unresolvable_base_fails_merge_group(tmp_path: Path) -> None:
    """Same rule on the merge_group event, which carries a different base
    field (github.event.merge_group.base_sha) and is the reachable instance
    per design D12 — a derivation only written against the PR payload would
    read empty here and silently SKIP the merge queue."""
    repo = _init_repo(tmp_path)
    result = _run(repo, {"EVENT_NAME": "merge_group", "MERGE_GROUP_BASE_SHA": ""})
    assert result.returncode == 1, result.stdout
    assert "::error::" in result.stdout
    assert "merge_group" in result.stdout
    assert "SKIP" not in result.stdout


def test_merge_group_iterates_once_per_change(tmp_path: Path) -> None:
    """Spec: 'A merge group batching two changes is evaluated once per
    change' — invoke the gate twice, once per derived change id, each with
    --change <id>; do NOT apply the ambiguity rule."""
    repo = _init_repo(tmp_path)
    base_sha = _git(repo, "rev-parse", "HEAD")
    for change_id in ("change-a", "change-b"):
        change_dir = repo / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True)
        (change_dir / "spec.md").write_text(f"# {change_id}\n")
    _commit_all(repo, "batch two changes")
    _make_stub_gate(repo)

    result = _run(
        repo,
        {"EVENT_NAME": "merge_group", "MERGE_GROUP_BASE_SHA": base_sha, "MERGE_GROUP_REF": "gh-readonly-queue/main/pr-1"},
    )
    assert result.returncode == 0, result.stdout
    assert "argv: --scope capability --change change-a" in result.stdout
    assert "argv: --scope capability --change change-b" in result.stdout
    assert "ambiguous" not in result.stdout
    assert "SKIP" not in result.stdout


def test_merge_group_blocks_if_any_invocation_fails(tmp_path: Path) -> None:
    """Same batch, but one change's invocation fails — the merge group must
    block (non-zero exit) without treating the two-directory diff as
    ambiguous."""
    repo = _init_repo(tmp_path)
    base_sha = _git(repo, "rev-parse", "HEAD")
    for change_id in ("change-a", "change-b"):
        change_dir = repo / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True)
        (change_dir / "spec.md").write_text(f"# {change_id}\n")
    _commit_all(repo, "batch two changes")
    _make_stub_gate(repo, fail_ids=("change-b",), violation_text="change-b: cites no requirement")

    result = _run(
        repo,
        {"EVENT_NAME": "merge_group", "MERGE_GROUP_BASE_SHA": base_sha, "MERGE_GROUP_REF": "gh-readonly-queue/main/pr-1"},
    )
    assert result.returncode == 1, result.stdout
    assert "change-b: cites no requirement" in result.stdout
    assert "ambiguous" not in result.stdout


def test_merge_group_evaluates_every_id_even_after_one_fails(tmp_path: Path) -> None:
    """Spec: 'invoke the gate once per derived change id ... and block if any
    invocation fails' — *once per id*, not "until one fails".

    The neighbouring test fails the LAST id in the batch, which a fragment that
    aborts on the first failure would still satisfy. Failing the FIRST id is
    what distinguishes the two: the batch must still be evaluated to the end so
    one merge-queue run reports every offending change, rather than making the
    queue rediscover them one eviction at a time."""
    repo = _init_repo(tmp_path)
    base_sha = _git(repo, "rev-parse", "HEAD")
    for change_id in ("change-a", "change-b"):
        change_dir = repo / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True)
        (change_dir / "spec.md").write_text(f"# {change_id}\n")
    _commit_all(repo, "batch two changes")
    _make_stub_gate(repo, fail_ids=("change-a",), violation_text="change-a: cites no requirement")

    result = _run(
        repo,
        {"EVENT_NAME": "merge_group", "MERGE_GROUP_BASE_SHA": base_sha, "MERGE_GROUP_REF": "gh-readonly-queue/main/pr-2"},
    )
    assert result.returncode == 1, result.stdout
    assert "change-a: cites no requirement" in result.stdout
    # The id AFTER the failing one must still have been invoked.
    assert "argv: --scope capability --change change-b" in result.stdout


def test_push_run_never_blocks(tmp_path: Path) -> None:
    """Spec: 'The run on the integration branch cannot fail' — union mode
    (--change omitted), reports every violation, exits zero regardless."""
    repo = _init_repo(tmp_path)
    _make_stub_gate(repo, fail_ids=("__union__",), violation_text="some-other-change: cites no requirement")

    result = _run(repo, {"EVENT_NAME": "push"})
    assert result.returncode == 0, result.stdout
    assert "argv: --scope capability" in result.stdout
    assert "some-other-change: cites no requirement" in result.stdout
    assert "non-blocking" in result.stdout


def test_push_run_omits_change_flag(tmp_path: Path) -> None:
    """The post-merge run is the only one entitled to omit --change (union
    mode); confirm the argv actually reflects that rather than assuming it."""
    repo = _init_repo(tmp_path)
    _make_stub_gate(repo)

    result = _run(repo, {"EVENT_NAME": "push"})
    assert result.returncode == 0, result.stdout
    argv_lines = [line for line in result.stdout.splitlines() if line.startswith("argv:")]
    assert argv_lines == ["argv: --scope capability"], argv_lines
