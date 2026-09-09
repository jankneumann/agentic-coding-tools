"""Resolve OpenSpec change directories that survive archival.

`openspec archive <id>` moves `openspec/changes/<id>/` to
`openspec/changes/archive/<YYYY-MM-DD>-<id>/`. A test that pins the active path
therefore fails on the day its change *lands* rather than the day its contract
*drifts* — the failure is uncorrelated with the thing being guarded, and it is
invisible until archival, which happens once per change and often years after
the test was written.

Resolving at read time removes the coupling entirely: there is no stored path to
update, so nothing has to run at archive time and nothing can be bypassed by a
direct `openspec archive` invocation.

This module is mirrored at `agent-coordinator/tests/_shared/openspec_paths.py`
and `packages/code-search/tests/_shared/openspec_paths.py` because those test
trees have separate virtualenvs and no shared importable package. Each tree puts
this directory on `pythonpath` via its own `[tool.pytest.ini_options]`.
`skills/tests/openspec_paths/test_change_path_stability.py` asserts the copies
stay byte-identical.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["change_dir", "repo_root_from"]


def repo_root_from(test_file: str | Path, up: int) -> Path:
    """The repo root, `up` levels above `test_file`.

    Spelled out rather than left as a bare `parents[N]` because that index is
    itself archive-fragile when the *test* moves: a path segment added or removed
    anywhere above silently changes which directory is returned, with no error.
    """
    return Path(test_file).resolve().parents[up]


def change_dir(repo_root: Path, change_id: str) -> Path:
    """Locate `change_id`'s directory whether it is active or archived.

    Returns the active `openspec/changes/<id>/` when it exists, otherwise the
    most recent `openspec/changes/archive/<date>-<id>/`. The archive prefix is
    date-stamped, hence the glob; sorting puts the latest date last, which
    matters only in the rare case of an id archived more than once.

    When neither exists the *active* path is returned rather than raising, so
    the caller's own assertion reports the path a contributor would look for
    first instead of an opaque lookup error from in here.
    """
    changes = repo_root / "openspec" / "changes"
    active = changes / change_id
    if active.is_dir():
        return active
    archived = sorted(changes.glob(f"archive/*-{change_id}"))
    if archived:
        return archived[-1]
    return active
