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

Two spellings are matched, because the first version of this guard checked only
the first one and therefore passed while ``packages/code-search`` — the file this
docstring already cited as the six-week-hidden case — was still red:

1. a single string constant containing ``openspec/changes/<id>``;
2. a ``pathlib`` join whose segments spell the same thing one constant at a
   time, ``root / "openspec" / "changes" / "<id>"``. No single constant here
   contains the joined substring, so spelling-based matching cannot see it.

Matching the *shape* rather than one spelling of it is the point: a guard
derived from a single instance of a bug tends to encode that instance.

Deliberately matched against *real* change ids read off the filesystem, so the
synthetic ids tests use as fixtures (``my-change``, ``foo``,
``add-health-check-endpoint``) are not flagged. A test that needs a change
directory inside a ``tmp_path`` fixture repo should therefore name it with a
synthetic id, not borrow a real one.
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
#
# This listed `agent-coordinator/tests` until 2026-09-10, which is a second way
# the same blind spot was expressed: even after the file glob was widened past
# `test_*.py`, `agent-coordinator/src/` was still unreachable, so
# `kanban_viz_files.py` went on holding a dead path to an archived change.
# The whole of `agent-coordinator` is scanned now — a pin in `src/` is worse
# than a pin in `tests/`, not better.
SCANNED_TREES = (
    REPO_ROOT / "agent-coordinator",
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


def _scanned_files() -> list[Path]:
    """Every module in the scanned trees — production code included.

    This scanned ``test_*.py`` only until 2026-09-10, which is how
    ``skills/playwright-validator/scripts/descriptor.py`` kept an active
    ``openspec/changes/<id>/contracts/`` path as a module constant while the
    test constant beside it was already fixed. Archiving that change took out
    six tests at once. Production code is where the consequence is worse, not
    better: a test fails loudly, whereas
    ``agent-coordinator/src/kanban_viz_files.py`` fell back to an empty schema
    and validated writes against nothing.
    """
    found: list[Path] = []
    for tree in SCANNED_TREES:
        if not tree.is_dir():
            continue
        for path in tree.rglob("*.py"):
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


def _join_spine(node: ast.AST) -> list[str] | None:
    """String constants down the left spine of a ``/`` chain, outermost last.

    ``a / "openspec" / "changes"`` yields ``["openspec", "changes"]``. Returns
    ``None`` as soon as a non-``/`` operator appears, so unrelated division is
    not mistaken for a path join. The non-constant head of the chain (``a``,
    typically a ``Path(...)`` call or a name) simply terminates the walk — what
    it evaluates to does not matter, only that the literal tail spells
    ``openspec/changes/<id>``.
    """
    segments: list[str] = []
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = node.right
        if not (isinstance(right, ast.Constant) and isinstance(right.value, str)):
            return None
        segments.append(right.value)
        node = node.left
    segments.reverse()
    return segments


def _offending_joins(path: Path, tree: ast.AST, change_ids: frozenset[str]) -> list[str]:
    """Change ids reached by a segment-at-a-time ``pathlib`` join."""
    hits: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
            continue
        right = node.right
        if not (isinstance(right, ast.Constant) and isinstance(right.value, str)):
            continue
        if right.value not in change_ids:
            continue
        segments = _join_spine(node)
        if segments is None:
            continue
        # segments[-1] is the change id itself; the two before it must spell the
        # changes directory. `"openspec/changes"` as one constant counts too.
        prefix = "/".join(segments[:-1])
        if prefix.endswith("openspec/changes"):
            hits.append(f'line {right.lineno}: .../{prefix}/{right.value}')
    return hits


def _offending_literals(tree: ast.AST, change_ids: frozenset[str]) -> list[str]:
    """Change ids pinned inside a single string constant."""
    skip = _docstring_nodes(tree)
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or id(node) in skip:
            continue
        value = node.value
        if not isinstance(value, str) or "openspec/changes/" not in value:
            continue
        for cid in change_ids:
            needle = f"openspec/changes/{cid}"
            if needle not in value:
                continue
            # A change id must end at a path boundary. Without this,
            # `openspec/changes/vendor-neutral-autopilot-smoke/design.md` matches
            # the real id `vendor-neutral-autopilot`, and the synthetic fixture
            # ids this guard's own docstring asks contributors to use get flagged
            # whenever one happens to extend a real id.
            tail = value[value.index(needle) + len(needle):]
            if tail and not tail.startswith("/"):
                continue
            hits.append(f"line {node.lineno}: {value!r}")
            break
    return hits


_CHANGE_IDS = _real_change_ids()


def _offences(path: Path, change_ids: frozenset[str]) -> list[str]:
    """Both spellings, from one parse of the file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - a broken file is another test's problem
        return []
    return _offending_literals(tree, change_ids) + _offending_joins(
        path, tree, change_ids
    )


@pytest.mark.parametrize("path", _scanned_files(), ids=lambda p: str(p.name))
def test_no_test_pins_a_real_change_directory(path: Path) -> None:
    hits = _offences(path, _CHANGE_IDS)
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
    files = _scanned_files()
    assert len(files) > 100, f"only {len(files)} files found; SCANNED_TREES is wrong"
    assert _CHANGE_IDS, "no change ids discovered; CHANGES path is wrong"


def test_the_join_detector_actually_detects() -> None:
    """A widening that matches nothing would pass as vacuously as a zero scan.

    The first version of this guard matched only single-constant literals, so it
    reported a clean tree while `packages/code-search` was red. This asserts the
    join spelling is really caught, using an id read off the filesystem so the
    test does not rot when a hardcoded change is archived or renamed.
    """
    real_id = sorted(_CHANGE_IDS)[0]
    caught = ast.parse(
        f'P = root / "openspec" / "changes" / "{real_id}" / "contracts"\n'
    )
    assert _offending_joins(Path("x.py"), caught, _CHANGE_IDS), (
        "the segment-joined spelling is no longer detected"
    )

    # Same shape via one pre-joined constant, which is also a real spelling.
    packed = ast.parse(f'P = root / "openspec/changes" / "{real_id}"\n')
    assert _offending_joins(Path("x.py"), packed, _CHANGE_IDS)


def test_the_join_detector_leaves_legitimate_joins_alone() -> None:
    """Two shapes that look similar and must not be flagged.

    A directory that merely shares a name with a change (skills are routinely
    named after the change that introduced them), and a synthetic change
    directory built inside a `tmp_path` fixture repo — the latter only stays
    unflagged because fixtures use synthetic ids, which is why the module
    docstring asks for them.
    """
    real_id = sorted(_CHANGE_IDS)[0]
    sibling = ast.parse(f'SKILL_DIR = here.parents[2] / "{real_id}"\n')
    assert not _offending_joins(Path("x.py"), sibling, _CHANGE_IDS)

    synthetic = ast.parse(
        'D = tmp / "openspec" / "changes" / "a-change-that-does-not-exist"\n'
    )
    assert not _offending_joins(Path("x.py"), synthetic, _CHANGE_IDS)


def test_shared_helper_copies_are_byte_identical() -> None:
    """The helper is mirrored per test tree because the venvs are separate."""
    copies = [
        REPO_ROOT / "skills" / "tests" / "_shared" / "openspec_paths.py",
        REPO_ROOT / "agent-coordinator" / "tests" / "_shared" / "openspec_paths.py",
        REPO_ROOT / "packages" / "code-search" / "tests" / "_shared" / "openspec_paths.py",
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


def test_the_scan_reaches_production_code() -> None:
    """Not just `test_*.py`, and not just `agent-coordinator/tests`.

    Both halves of that blind spot shipped a live defect.
    `skills/playwright-validator/scripts/descriptor.py` kept an active change
    path as a module constant while the test constant beside it was fixed, and
    `agent-coordinator/src/kanban_viz_files.py` stayed unreachable even after
    the file glob widened, because the tree list named only `tests`.
    """
    scanned = {p.relative_to(REPO_ROOT).as_posix() for p in _scanned_files()}
    for expected in (
        "agent-coordinator/src/kanban_viz_files.py",
        "skills/playwright-validator/scripts/descriptor.py",
        "skills/explore-feature/scripts/backfill_decision_tags.py",
    ):
        assert expected in scanned, f"{expected} is not scanned"
    assert any(p.startswith("agent-coordinator/src/") for p in scanned), (
        "agent-coordinator/src/ is unreachable; SCANNED_TREES is wrong"
    )


def test_a_longer_id_that_extends_a_real_one_is_not_flagged(tmp_path: Path) -> None:
    """`<real-id>-smoke` is a synthetic fixture id, not a pin.

    The matcher used a bare substring test, so any id extending a real one was
    flagged — which punishes exactly the synthetic-fixture convention the module
    docstring asks for. Uses a real id read off the filesystem so the test does
    not rot when a hardcoded change is archived or renamed.
    """
    real_id = sorted(_CHANGE_IDS)[0]

    extended = ast.parse(f'P = "openspec/changes/{real_id}-smoke/design.md"\n')
    assert not _offending_literals(extended, _CHANGE_IDS), (
        f"{real_id}-smoke is a distinct id and must not match {real_id}"
    )

    # The control: the real id at a path boundary must still be caught, or the
    # boundary rule could pass by matching nothing at all.
    exact = ast.parse(f'P = "openspec/changes/{real_id}/design.md"\n')
    assert _offending_literals(exact, _CHANGE_IDS)

    bare = ast.parse(f'P = "openspec/changes/{real_id}"\n')
    assert _offending_literals(bare, _CHANGE_IDS), "a trailing-boundary id counts"

