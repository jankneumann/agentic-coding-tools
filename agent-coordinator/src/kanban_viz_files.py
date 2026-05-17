"""Coordinator-owned file-write endpoints for the Kanban UI.

Implements the persistence-boundary helpers for:
  PUT /kanban-viz/saved-views/{slug}
  POST /kanban-viz/audit

Design decision D10: the browser cannot write repo files; the coordinator owns
these writes so the "frontend never bypasses the coordinator" invariant holds.

Both helpers perform:
  1. Slug/run-id validation (regex + path-safety).
  2. Path resolution via ``resolve_workdir_path()`` from config.py.
  3. Mandatory artifact-header stamping (server-side).
  4. Atomic write via tmp-file + rename.

The coordinator version is ``kanban-viz@0.1.0``.  Update when the schema
version bumps.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess  # noqa: S404 — used only for git rev-parse
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import resolve_workdir_path

logger = logging.getLogger(__name__)

KANBAN_GENERATOR = "kanban-viz@0.1.0"
KANBAN_SCHEMA_VERSION = 1

# Slug/run-id must match: start with alnum, then alphanums and hyphens, 1-64 chars.
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _validate_slug(slug: str) -> None:
    if not SLUG_PATTERN.match(slug):
        raise ValueError(
            f"Invalid slug {slug!r}: must match ^[a-z0-9][a-z0-9-]{{0,63}}$"
        )


def _git_sha(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() or "0000000"
    except Exception:
        return "0000000"


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via a temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    ) as fh:
        fh.write(content)
        tmp_path = Path(fh.name)
    tmp_path.replace(path)


def write_saved_view(
    slug: str,
    view_payload: dict[str, Any],
    *,
    workdir_root: Path | None = None,
) -> dict[str, Any]:
    """Write a saved-view JSON file for the given slug.

    Returns:
        {saved: bool, path: str, git_sha: str}
    Raises:
        ValueError on slug validation or path-traversal failure.
    """
    _validate_slug(slug)
    dest = resolve_workdir_path(
        "docs", "kanban-viz", "saved-views", f"{slug}.json",
        root=workdir_root,
    )
    from .config import _default_workdir_root
    repo_root = workdir_root or _default_workdir_root()

    generated_at = datetime.now(UTC).isoformat()
    sha = _git_sha(repo_root)

    document = {
        "schema_version": KANBAN_SCHEMA_VERSION,
        "generated_at": generated_at,
        "git_sha": sha,
        "generator": KANBAN_GENERATOR,
        "view": view_payload,
    }
    _atomic_write(dest, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    rel_path = str(dest.relative_to(repo_root))
    return {"saved": True, "path": rel_path, "git_sha": sha}


def write_audit_event(
    run_id: str,
    event_payload: dict[str, Any],
    *,
    workdir_root: Path | None = None,
) -> dict[str, Any]:
    """Write a UI audit-event JSON file.

    The date subdirectory is derived server-side from ``generated_at`` (UTC).
    Returns:
        {appended: bool, path: str}
    Raises:
        ValueError on run-id validation or path-traversal failure.
    """
    _validate_slug(run_id)
    generated_at = datetime.now(UTC)
    date_dir = generated_at.strftime("%Y-%m-%d")

    dest = resolve_workdir_path(
        "docs", "kanban-viz", "audit", date_dir, f"{run_id}.json",
        root=workdir_root,
    )
    from .config import _default_workdir_root
    repo_root = workdir_root or _default_workdir_root()

    sha = _git_sha(repo_root)

    document = {
        "schema_version": KANBAN_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "git_sha": sha,
        "generator": KANBAN_GENERATOR,
        "run_id": run_id,
        "event_kind": "kanban-viz.ui-action",
        **event_payload,
    }
    _atomic_write(dest, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    rel_path = str(dest.relative_to(repo_root))
    return {"appended": True, "path": rel_path}
