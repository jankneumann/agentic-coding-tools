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

import jsonschema

from .config import resolve_workdir_path

logger = logging.getLogger(__name__)

KANBAN_GENERATOR = "kanban-viz@0.1.0"
KANBAN_SCHEMA_VERSION = 1

# Slug/run-id must match: start with alnum, then alphanums and hyphens, 1-64 chars.
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# IMPL_REVIEW claude#11 (high contract_mismatch): the file-write helpers must
# validate the supplied payload against the checked-in JSON schemas before
# writing, otherwise arbitrary malformed artifacts can land under
# docs/kanban-viz/. Schemas live in the change directory; we cache them at
# module load so each write is a single jsonschema.validate call.
_SCHEMA_ROOT = (
    Path(__file__).resolve().parents[2]
    / "openspec"
    / "changes"
    / "add-coordinator-kanban-viz"
    / "contracts"
    / "schemas"
)


def _load_schema(name: str) -> dict[str, Any]:
    """Load a schema file by name (e.g. ``saved-view.json``) from the change
    directory. Returns an empty schema (no constraints) if the file is missing
    — defensive default so a misconfigured deploy doesn't reject all writes.
    The empty-fallback is logged so misconfiguration is visible.
    """
    schema_path = _SCHEMA_ROOT / name
    if not schema_path.is_file():
        logger.warning(
            "kanban_viz_files: schema %s not found at %s — proceeding without validation",
            name,
            schema_path,
        )
        return {}
    try:
        with open(schema_path, encoding="utf-8") as fh:
            return json.load(fh)  # type: ignore[no-any-return]
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "kanban_viz_files: failed to load schema %s (%s) — proceeding without validation",
            name,
            exc,
        )
        return {}


_SAVED_VIEW_SCHEMA = _load_schema("saved-view.json")
_AUDIT_EVENT_SCHEMA = _load_schema("audit-event.json")


class SchemaValidationError(ValueError):
    """Raised when a payload fails JSON-schema validation.

    Subclasses ValueError so existing callers that catch ValueError keep
    working; the dedicated subclass lets new code distinguish schema errors
    from slug-format errors and other ValueErrors.
    """

    def __init__(self, schema_name: str, jsonschema_error: jsonschema.ValidationError):
        self.schema_name = schema_name
        self.json_path = "/".join(str(p) for p in jsonschema_error.absolute_path)
        super().__init__(
            f"{schema_name} validation failed at /{self.json_path}: "
            f"{jsonschema_error.message}"
        )


def _validate_against(schema_name: str, schema: dict[str, Any], document: dict[str, Any]) -> None:
    """Validate *document* against *schema*. No-op when the schema is empty
    (file missing — see _load_schema)."""
    if not schema:
        return
    try:
        jsonschema.validate(document, schema)
    except jsonschema.ValidationError as exc:
        raise SchemaValidationError(schema_name, exc) from exc


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
    # Validate against contracts/schemas/saved-view.json BEFORE writing —
    # better to fail fast with a precise pointer than to commit a malformed
    # artifact and let downstream tools choke.
    _validate_against("saved-view", _SAVED_VIEW_SCHEMA, document)
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
    # Validate against contracts/schemas/audit-event.json BEFORE writing.
    # The audit-event schema requires action/class/outcome, so callers
    # MUST supply those — otherwise we'd commit half-formed audit rows.
    _validate_against("audit-event", _AUDIT_EVENT_SCHEMA, document)
    _atomic_write(dest, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    rel_path = str(dest.relative_to(repo_root))
    return {"appended": True, "path": rel_path}
