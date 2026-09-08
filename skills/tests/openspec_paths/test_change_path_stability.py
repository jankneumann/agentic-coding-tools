"""Guard: no test may pin a real OpenSpec change directory by literal path.

``openspec archive <id>`` moves ``openspec/changes/<id>/`` to
``openspec/changes/archive/<YYYY-MM-DD>-<id>/``. A test holding the active path
as a literal therefore breaks on the day its change *lands*, not the day its
contract *drifts*, and stays correct right up until that one moment — so no
amount of ordinary review or CI catches it in advance.

This is not hypothetical. The 2026-09-08 archive sweep broke 30 assertions
across four files in one commit, and a fifth (``packages/code-search``) had been
red since 2026-07-25 without anyone noticing, because CI runs only two of the
four ``packages/`` suites. An earlier instance is recorded in
``packages/context-eval/tests/test_promoted_contracts.py``: ``run_eval.py:31``'s
``REPO_ROOT = HERE.parents[3]`` was "correct only until archival added a path
segment".

The fix is to resolve at read time — see ``openspec_paths.change_dir`` and
``docs/guides/openspec-path-stability.md``. This guard is what makes that a rule
rather than a habit.

Deliberately matched against *real* change ids read off the filesystem, so the
synthetic ids tests use as fixtures (``my-change``, ``foo``,
``add-health-check-endpoint``) are not flagged.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHANGES = REPO_ROOT / "openspec" / "changes"

# Trees that hold tests. `packages/*/tests` is included even though CI runs only
# gen-eval and context-eval today: an unrun suite is exactly where this defect
# hid for six weeks, so the guard covers it whether or not CI does.
TEST_TREES = (
    REPO_ROOT / "agent-coordinator" / "tests",
    REPO_ROOT / "skills",
    REPO_ROOT / "packages",
)

# Matched against the path *relative to REPO_ROOT*. Absolute matching is wrong:
# this repo is routinely checked out inside `.git-worktrees/<branch>/`, so every
# absolute path contains that segment and the whole scan would skip itself —
# which is precisely what `test_the_guard_actually_scans_something` caught the
# first time this file ran.
SKIP_PARTS = frozenset(
    {".venv", "__pycache__", "node_modules", ".git", ".git-worktrees", "archive"}
)

# The two files whose whole job is to talk about this pattern.
ALLOWED = frozenset({Path(__file__).name, "openspec_paths.py"})


def _real_change_ids() -> frozenset[str]:
    """Every change id the repo actually has, active or archived.

    Archived directories carry a ``YYYY-MM-DD-`` prefix; strip it so a test that
    pins the *active* spelling of an already-archived change is still caught.
    """
    ids: set[str] = set()
    for entry in CHANGES.iterdir():
        if entry.is_dir() and entry.name != "archive":
            ids.add(entry.name)
    archive = CHANGES / "archive"
    if archive.is_dir():
        for entry in archive.iterdir():
            if not entry.is_dir():
                continue
            name = entry.name
            # `2026-09-08-add-foo` -> `add-foo`
            parts = name.split("-", 3)
            if len(parts) == 4 and parts[0].isdigit():
                ids.add(parts[3])
            else:
                ids.add(name)
    return frozenset(ids)


def _test_files() -> list[Path]:
    found: list[Path] = []
    for tree in TEST_TREES:
        if not tree.is_dir():
            continue
        for path in tree.rglob("test_*.py"):
            if SKIP_PARTS & set(path.relative_to(REPO_ROOT).parts):
                continue
            if path.name in ALLOWED:
                continue
            found.append(path)
    return sorted(found)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Identity of every Constant node that is a docstring.

    Docstrings and comments legitimately name change ids — a ``Spec:`` reference
    is documentation, not a filesystem read. Comments never reach the AST;
    docstrings do, so they are excluded explicitly.
    """
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                out.add(id(first.value))
    return out


def _offending_literals(path: Path, change_ids: frozenset[str]) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - a broken file is another test's problem
        return []
    skip = _docstring_nodes(tree)
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or id(node) in skip:
            continue
        value = node.value
        if not isinstance(value, str) or "openspec/changes/" not in value:
            continue
        for cid in change_ids:
            if f"openspec/changes/{cid}" in value:
                hits.append(f"line {node.lineno}: {value!r}")
                break
    return hits


_CHANGE_IDS = _real_change_ids()


@pytest.mark.parametrize("path", _test_files(), ids=lambda p: str(p.name))
def test_no_test_pins_a_real_change_directory(path: Path) -> None:
    hits = _offending_literals(path, _CHANGE_IDS)
    assert not hits, (
        f"{path.relative_to(REPO_ROOT)} pins a real OpenSpec change directory:\n  "
        + "\n  ".join(hits)
        + "\n\nThat path moves to openspec/changes/archive/<date>-<id>/ when the "
        "change is archived, so this test will break on an unrelated day.\n"
        "Use `from openspec_paths import change_dir, repo_root_from` and build "
        "the path with `change_dir(repo_root_from(__file__, N), '<change-id>')`.\n"
        "See docs/guides/openspec-path-stability.md."
    )


def test_the_guard_actually_scans_something() -> None:
    """A zero-file scan would pass vacuously and hide a broken tree list."""
    files = _test_files()
    assert len(files) > 100, f"only {len(files)} test files found; TEST_TREES is wrong"
    assert _CHANGE_IDS, "no change ids discovered; CHANGES path is wrong"


def test_shared_helper_copies_are_byte_identical() -> None:
    """The helper is mirrored per test tree because the venvs are separate."""
    copies = [
        REPO_ROOT / "skills" / "tests" / "_shared" / "openspec_paths.py",
        REPO_ROOT / "agent-coordinator" / "tests" / "_shared" / "openspec_paths.py",
    ]
    missing = [p for p in copies if not p.is_file()]
    assert not missing, f"missing helper copies: {missing}"
    bodies = {p: p.read_bytes() for p in copies}
    first = copies[0]
    drifted = [str(p.relative_to(REPO_ROOT)) for p in copies[1:] if bodies[p] != bodies[first]]
    assert not drifted, (
        f"these copies have drifted from {first.relative_to(REPO_ROOT)}: {drifted}. "
        "Copy the canonical file over them."
    )
