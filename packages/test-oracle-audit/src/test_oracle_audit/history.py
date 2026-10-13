"""History stage: git-derived signals per test (spec: Git History Signals; design D6).

Per test it records

- ``co_change_ratio``: of the commits that changed any covered source module, the
  fraction that also rewrote this test function's assertion lines (``"insufficient"``
  when fewer than :data:`MIN_DENOMINATOR` such commits exist), and
- ``added_with_fix``: whether the commit that introduced the test function has a
  conventional ``fix`` subject (a regression pin added with its fix).

The stage only ever runs local, read-only git commands (``log``, ``show``,
``diff-tree``, ``rev-parse``, ``rev-list``, ``ls-files``). It never fetches or
unshallows: on a shallow clone every record is ``degraded`` / ``shallow_history``.
"""

from __future__ import annotations

import ast
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from test_oracle_audit.records import StageRecord, TestEntry, find_function

STAGE = "history"
MIN_DENOMINATOR = 3
INSUFFICIENT = "insufficient"

# Conventional-commit ``fix`` type: ``fix:``, ``fix(scope):``, ``fix!:``, ``fix(scope)!:``.
# ``fixup!`` and every other type do not match.
FIX_SUBJECT_RE = re.compile(r"^fix(\([^)]*\))?!?:")

# Adapted from skills/simplify/scripts/check_test_contract.py (ASSERT_LINE_RE). Vendored rather
# than imported so the package does not depend on the skills tree. Differences from the original:
# the diff-prefix (``^[+\-]\s*``) is dropped because lines are classified after the diff marker
# is stripped, and the pattern is anchored with ``match`` on the left-stripped line.
ASSERT_LINE_RE = re.compile(
    r"""(?x)
    (?:
        assert_eq!\s*\(                         # Rust
        | assert_ne!\s*\(
        | assert_ok!\s*\(
        | assert_err!\s*\(
        | assert(?:equal|Equals|True|False|In|Is|IsNone|Raises|AlmostEqual)?\b
        | expect\s*\(
        | expect\w*\s*\(
        | self\.assert\w+\s*\(
        | pytest\.raises\s*\(
        | should\s*\(
        | assertThat\s*\(
        | EXPECT_\w+\s*\(
        | ASSERT_\w+\s*\(
        | t\.(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow|Logf)\s*\(
        | \.to(?:Be|Equal|Equal|StrictEqual|Match|Contain|Throw|HaveBeenCalled)\s*\(
        | \.to_(?:eq|equal|be|match|include)\b
    )
    """,
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def is_assertion_line(text: str) -> bool:
    """Whether a source line (without any diff marker) looks like an assertion."""
    return bool(ASSERT_LINE_RE.match(text.lstrip()))


# --- git plumbing -----------------------------------------------------------


class GitError(RuntimeError):
    """A local git command failed."""


def _git(repo_root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        if check:
            raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
        return ""
    return proc.stdout


def _git_show(repo_root: Path, rev: str, path: str) -> str | None:
    proc = subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else None


def is_shallow(repo_root: Path) -> bool:
    return _git(repo_root, "rev-parse", "--is-shallow-repository").strip() == "true"


@dataclass(frozen=True)
class _FileChange:
    """One commit in a file's ``--follow`` log: the file's path before and after it."""

    sha: str
    path_before: str
    path_after: str


def _follow_log(repo_root: Path, path: str) -> list[_FileChange]:
    """Commits touching ``path`` (following renames), newest first."""
    out = _git(repo_root, "log", "--follow", "-M", "--name-status", "--format=%H", "--", path, check=False)
    changes: list[_FileChange] = []
    sha: str | None = None
    for line in out.splitlines():
        line = line.rstrip("\n")
        if _SHA_RE.match(line):
            sha = line
            continue
        if not line or sha is None:
            continue
        fields = line.split("\t")
        status, paths = fields[0], fields[1:]
        if not paths:
            continue
        if status[:1] in ("R", "C") and len(paths) >= 2:
            changes.append(_FileChange(sha, paths[0], paths[-1]))
        else:
            changes.append(_FileChange(sha, paths[-1], paths[-1]))
        sha = None
    return changes


def _commits_touching(repo_root: Path, paths: Sequence[str]) -> set[str]:
    if not paths:
        return set()
    out = _git(repo_root, "log", "--format=%H", "--", *paths, check=False)
    return {line for line in out.split() if _SHA_RE.match(line)}


def _subject(repo_root: Path, sha: str) -> str:
    return _git(repo_root, "log", "-1", "--format=%s", sha, check=False).strip()


# --- locating a test function in a revision ----------------------------------


def _function_span(source: str | None, name: str, cls: str | None) -> tuple[int, int] | None:
    """1-based inclusive line range of the function in ``source``, else ``None``."""
    if source is None:
        return None
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    node = find_function(tree, name, cls)
    if node is None:
        return None
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None) or start
    if start is None or end is None:
        return None
    decorators = getattr(node, "decorator_list", [])
    if decorators:
        start = min(start, *(d.lineno for d in decorators))
    return start, end


# --- co_change_ratio ---------------------------------------------------------


def _resolve_source_paths(
    repo_root: Path, modules: Iterable[str], source_paths: Mapping[str, str] | None
) -> list[str]:
    """Repo-relative paths of the covered modules; unresolvable modules are ignored."""
    known = dict(source_paths or {})
    tracked: list[str] | None = None
    paths: list[str] = []
    for module in modules:
        path = known.get(module)
        if path is None:
            if tracked is None:
                tracked = _git(repo_root, "ls-files", "-z", check=False).split("\0")
            stem = module.replace(".", "/")
            wanted = (f"{stem}.py", f"{stem}/__init__.py")
            path = next((t for t in tracked if any(t == w or t.endswith("/" + w) for w in wanted)), None)
        if path is not None and path not in paths:
            paths.append(path)
    return paths


def _changed_assertion_in_span(
    diff_text: str,
    path_after: str,
    old_span: tuple[int, int],
    new_span: tuple[int, int],
) -> bool:
    """Whether the diff of ``path_after`` adds/removes an assertion line inside the function.

    ``diff_text`` is ``-U0`` output; removed lines are located in the old span and
    added lines in the new span.
    """
    in_file = False
    old_ln = new_ln = 0
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            in_file = False
            continue
        if line.startswith("+++ "):
            in_file = line[4:].strip() == f"b/{path_after}"
            continue
        if not in_file:
            continue
        hunk = _HUNK_RE.match(line)
        if hunk:
            old_ln, new_ln = int(hunk.group(1)), int(hunk.group(3))
            continue
        if line.startswith("-") and not line.startswith("---"):
            if old_span[0] <= old_ln <= old_span[1] and is_assertion_line(line[1:]):
                return True
            old_ln += 1
        elif line.startswith("+") and not line.startswith("+++"):
            if new_span[0] <= new_ln <= new_span[1] and is_assertion_line(line[1:]):
                return True
            new_ln += 1
    return False


def _commit_rewrites_assertions(repo_root: Path, change: _FileChange, name: str, cls: str | None) -> bool:
    """Did this commit add/remove an assertion line of the test function?

    A commit in which the function cannot be found by name, before or after, is not
    counted (not yet added, deleted, or unparsable).
    """
    new_span = _function_span(_git_show(repo_root, change.sha, change.path_after), name, cls)
    old_span = _function_span(_git_show(repo_root, f"{change.sha}^", change.path_before), name, cls)
    if new_span is None or old_span is None:
        return False
    pathspec = sorted({change.path_before, change.path_after})
    diff_text = _git(
        repo_root,
        "diff-tree",
        "-p",
        "-M",
        "--unified=0",
        "--no-color",
        "--no-ext-diff",
        "--no-commit-id",
        change.sha,
        "--",
        *pathspec,
        check=False,
    )
    return _changed_assertion_in_span(diff_text, change.path_after, old_span, new_span)


# --- added_with_fix ----------------------------------------------------------


def _introducing_commit(
    repo_root: Path, changes: Sequence[_FileChange], name: str, cls: str | None
) -> str | None:
    """Oldest commit (following renames) whose revision of the file contains the function."""
    for change in reversed(changes):  # oldest first
        if _function_span(_git_show(repo_root, change.sha, change.path_after), name, cls) is not None:
            return change.sha
    return None


# --- stage entry point -------------------------------------------------------


def _record(entry: TestEntry, status: str, payload: dict, reason: str | None = None) -> StageRecord:
    return StageRecord(test_id=entry.test_id, stage=STAGE, status=status, payload=payload, reason=reason)


def run_history(
    entries: Sequence[TestEntry],
    *,
    repo_root: Path,
    source_paths: Mapping[str, str] | None = None,
) -> list[StageRecord]:
    """One ``history`` record per entry, in order.

    ``source_paths`` maps covered module names to repo-relative file paths; modules
    missing from it are resolved against tracked files by dotted-path suffix.
    """
    repo_root = Path(repo_root)
    entries = list(entries)
    if not entries:
        return []

    try:
        shallow = is_shallow(repo_root)
    except (GitError, OSError) as exc:
        return [_record(e, "error", {"detail": str(exc)}, reason="git_unavailable") for e in entries]
    if shallow:
        depth = _git(repo_root, "rev-list", "--count", "HEAD", check=False).strip()
        payload = {"commit_count": int(depth)} if depth.isdigit() else {}
        return [_record(e, "degraded", dict(payload), reason="shallow_history") for e in entries]

    commits_cache: dict[tuple[str, ...], set[str]] = {}
    follow_cache: dict[str, list[_FileChange]] = {}
    fix_cache: dict[str, bool] = {}
    records: list[StageRecord] = []
    for entry in entries:
        paths = tuple(_resolve_source_paths(repo_root, entry.covered_modules, source_paths))
        if paths not in commits_cache:
            commits_cache[paths] = _commits_touching(repo_root, paths)
        source_commits = commits_cache[paths]
        denominator = len(source_commits)

        if entry.path not in follow_cache:
            follow_cache[entry.path] = _follow_log(repo_root, entry.path)
        changes = follow_cache[entry.path]

        if denominator < MIN_DENOMINATOR:
            ratio: float | str = INSUFFICIENT
        else:
            hits = sum(
                1
                for change in changes
                if change.sha in source_commits
                and _commit_rewrites_assertions(repo_root, change, entry.function_name, entry.class_name)
            )
            ratio = hits / denominator

        introducing = _introducing_commit(repo_root, changes, entry.function_name, entry.class_name)
        added_with_fix = False
        if introducing is not None:
            if introducing not in fix_cache:
                fix_cache[introducing] = bool(FIX_SUBJECT_RE.match(_subject(repo_root, introducing)))
            added_with_fix = fix_cache[introducing]

        records.append(
            _record(
                entry,
                "ok",
                {
                    "co_change_ratio": ratio,
                    "co_change_denominator": denominator,
                    "added_with_fix": added_with_fix,
                },
            )
        )
    return records
