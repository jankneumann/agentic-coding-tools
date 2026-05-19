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

# IMPL_REVIEW claude#11 (high contract_mismatch) + live-smoke Finding A:
# the file-write helpers must validate the supplied payload against the
# checked-in JSON schemas before writing. Schemas have two valid homes:
#
#   1. agent-coordinator/src/schemas/kanban_viz/ — bundled with the
#      Python package, available at runtime in Docker (the COPY src/ in
#      the Dockerfile picks them up automatically as a side effect).
#   2. openspec/changes/add-coordinator-kanban-viz/contracts/schemas/ —
#      the canonical home in the spec repo (dev tree only; openspec/ is
#      not COPY'd into Docker).
#
# We look in the package-bundled location first (so Docker hits the same
# schema), then fall back to the openspec/ canonical for completeness in
# any setup where the bundle is stale or absent. The bundled copies are
# kept in sync by the precommit hook (TODO if drift becomes an issue;
# for now, a quick manual diff before merge is sufficient).
_SCHEMA_ROOTS: list[Path] = [
    Path(__file__).resolve().parent / "schemas" / "kanban_viz",
    Path(__file__).resolve().parents[2]
    / "openspec"
    / "changes"
    / "add-coordinator-kanban-viz"
    / "contracts"
    / "schemas",
]


def _load_schema(name: str) -> dict[str, Any]:
    """Load a schema file by name (e.g. ``saved-view.json``).

    Tries each root in ``_SCHEMA_ROOTS`` in order and returns the first
    that loads cleanly. If none can be loaded, returns an empty schema
    (no constraints) so a misconfigured deploy doesn't reject all writes —
    the fallback is logged WARNING-level so the gap is observable.
    """
    last_path: Path | None = None
    for root in _SCHEMA_ROOTS:
        schema_path = root / name
        last_path = schema_path
        if not schema_path.is_file():
            continue
        try:
            with open(schema_path, encoding="utf-8") as fh:
                return json.load(fh)  # type: ignore[no-any-return]
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "kanban_viz_files: failed to load schema %s (%s) — trying next root",
                schema_path,
                exc,
            )
            continue
    logger.warning(
        "kanban_viz_files: schema %s not found in any of %s "
        "(last tried: %s) — proceeding without validation",
        name,
        [str(r) for r in _SCHEMA_ROOTS],
        last_path,
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
