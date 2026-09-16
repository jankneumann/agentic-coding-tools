"""Path resolution for the skill-audit scripts.

Sibling skills are resolved relative to this skill's own directory
(``<skill-base-dir>/../<sibling>/scripts``) per
``skills/references/skill-path-resolution.md``, so the scripts work unchanged
in the source checkout and in ``.claude/skills`` / ``.agents/skills`` installs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS_DIR.parent
SKILLS_ROOT = SKILL_DIR.parent
REFERENCES_DIR = SKILL_DIR / "references"

_SIBLING_SUBDIRS = (
    "shared",
    "improve-harness/scripts",
    "coordination-bridge/scripts",
)


def ensure_sibling_paths() -> None:
    """Put the sibling script directories on ``sys.path`` (idempotent)."""
    for sub in _SIBLING_SUBDIRS:
        candidate = SKILLS_ROOT / sub
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


def load_bridge() -> Any | None:
    """Import ``coordination_bridge`` or return ``None`` when it is absent."""
    ensure_sibling_paths()
    try:
        import coordination_bridge  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - consumer install without the bridge
        return None
    return coordination_bridge


def find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from *start* (default: cwd) to a directory holding ``openspec/``."""
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / "openspec").is_dir() or (candidate / "agent-coordinator" / "archetypes.yaml").is_file():
            return candidate
    return None


def default_archetypes_path() -> Path | None:
    """Locate ``agent-coordinator/archetypes.yaml`` from the skill dir, then cwd."""
    for base in (SKILLS_ROOT.parent, find_repo_root()):
        if base is None:
            continue
        candidate = base / "agent-coordinator" / "archetypes.yaml"
        if candidate.is_file():
            return candidate
    return None
