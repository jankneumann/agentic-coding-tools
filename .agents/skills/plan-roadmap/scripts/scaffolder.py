"""Scaffold OpenSpec change directories from approved roadmap items.

Creates the directory structure, proposal.md (with parent_roadmap link),
tasks.md skeleton, and specs/ directory for each approved item.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import shared runtime models
# ---------------------------------------------------------------------------
_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from models import (  # type: ignore[import-untyped]
    ItemStatus,
    Roadmap,
    RoadmapItem,
)


def _slugify(text: str) -> str:
    """Convert text to a URL/directory-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60]


def _derive_change_id(item: RoadmapItem) -> str:
    """Derive an OpenSpec change-id from a roadmap item."""
    return _slugify(item.title)


def _write_proposal(item: RoadmapItem, roadmap_id: str, change_dir: Path) -> None:
    """Write a proposal.md for the given item."""
    outcomes_md = "\n".join(f"- {o}" for o in item.acceptance_outcomes) if item.acceptance_outcomes else "- TBD"
    deps_md = "\n".join(f"- `{d}`" for d in item.depends_on) if item.depends_on else "- None"

    content = f"""\
# {item.title}

> Parent roadmap: `{roadmap_id}`
> Change ID: `{item.change_id or _derive_change_id(item)}`
> Effort: {item.effort.value}
> Priority: {item.priority}

## Summary

{item.description or 'TBD — fill in detailed description.'}

## Dependencies

{deps_md}

## Acceptance Outcomes

{outcomes_md}

## Rationale

{item.rationale or 'Derived from roadmap decomposition.'}
"""
    (change_dir / "proposal.md").write_text(content)


def _write_tasks(item: RoadmapItem, change_dir: Path) -> None:
    """Write a tasks.md skeleton for the given item."""
    content = f"""\
# Tasks: {item.title}

> Change ID: `{item.change_id or _derive_change_id(item)}`

## Status

- [ ] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## Tasks

- [ ] Define detailed requirements
- [ ] Implement core functionality
- [ ] Write tests
- [ ] Update documentation
- [ ] Review and merge
"""
    (change_dir / "tasks.md").write_text(content)


def scaffold_changes(roadmap: Roadmap, repo_root: Path) -> list[Path]:
    """Create OpenSpec change directories for approved/candidate items.

    Args:
        roadmap: The roadmap containing items to scaffold.
        repo_root: Repository root where openspec/changes/ lives.

    Returns:
        List of created change directory paths.
    """
    changes_dir = repo_root / "openspec" / "changes"
    changes_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []

    for item in roadmap.items:
        # Only scaffold items that are candidates or approved
        if item.status not in (ItemStatus.CANDIDATE, ItemStatus.APPROVED):
            continue

        change_id = item.change_id or _derive_change_id(item)
        # Update the item's change_id so it's tracked
        item.change_id = change_id

        change_dir = changes_dir / change_id
        change_dir.mkdir(parents=True, exist_ok=True)

        # Create specs directory
        specs_dir = change_dir / "specs"
        specs_dir.mkdir(exist_ok=True)

        # Write proposal and tasks
        _write_proposal(item, roadmap.roadmap_id, change_dir)
        _write_tasks(item, change_dir)

        created.append(change_dir)

    return created
