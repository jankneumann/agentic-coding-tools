"""Resolve analyzer-relative node paths to repository-relative paths.

Each Layer 1 analyzer records ``file`` relative to *its own* source root: the
Python analyzer emits ``coordination_api.py``, the TypeScript analyzer emits
``kanban-viz/src/App.tsx``, and the Postgres analyzer emits
``000_bootstrap.sql``. That is fine for the canonical graph, whose node IDs are
already namespaced by language, but a handbook evidence locator has to be
openable from the repository root — a reviewer clicks it, and
``verify_locators`` re-reads it.

This module owns that mapping so exactly one place knows how an analyzer's
relative path becomes a repo-relative one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

#: Defaults mirror the Makefile's PYTHON_SRC_DIR / TS_SRC_DIR / MIGRATIONS_DIR.
DEFAULT_SOURCE_ROOTS: dict[str, str] = {
    "python": "agent-coordinator/src",
    "typescript": "apps",
    "sql": "agent-coordinator/database/migrations",
}


def parse_source_roots(pairs: list[str] | None) -> dict[str, str]:
    """Parse ``language=path`` CLI overrides onto the defaults."""
    roots = dict(DEFAULT_SOURCE_ROOTS)
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"source root override must be language=path, got {pair!r}")
        language, path = pair.split("=", 1)
        roots[language.strip()] = path.strip().rstrip("/")
    return roots


def resolve_node_path(
    node: Mapping[str, Any], roots: Mapping[str, str] | None = None
) -> str | None:
    """Return the repo-relative path for *node*, or ``None`` if it has none.

    Nodes without a file (e.g. synthetic SQL aggregates) resolve to ``None`` so
    callers can skip them rather than fabricate a path.
    """
    roots = roots or DEFAULT_SOURCE_ROOTS
    rel = str(node.get("file") or "").strip()
    if not rel:
        return None
    root = roots.get(str(node.get("language") or ""))
    if not root:
        return rel
    return f"{root.rstrip('/')}/{rel}"


def resolve_existing_path(
    node: Mapping[str, Any],
    repo_root: Path | str,
    roots: Mapping[str, str] | None = None,
) -> str | None:
    """Return the repo-relative path for *node* only if it exists on disk.

    Locators are only worth stamping when they point at a real file; a path that
    does not resolve now would be recorded as immediately ``unresolvable``.
    """
    rel = resolve_node_path(node, roots)
    if rel is None:
        return None
    return rel if (Path(repo_root) / rel).is_file() else None
