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


#: A change-id becomes a single directory name under ``openspec/changes/``.
#: Dots are allowed because real change-ids use them (``adopt-opsx-1.0-workflow``),
#: but a leading dot is not, and ``..`` is rejected separately below.
_CHANGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def validate_change_id(change_id: str) -> str | None:
    """Check that ``change_id`` is safe to use as a single path component.

    Derived ids are always safe — ``_slugify`` strips everything outside
    ``[a-z0-9-]``. Explicit ids are not: ``change_id`` is an optional field in
    ``roadmap.yaml``, so its value can come from a hand edit or from a model,
    and it flows unmodified into ``repo_root / "openspec" / "changes" / id``.
    A value like ``../../../escaped`` writes outside the repository entirely.

    Args:
        change_id: The candidate id.

    Returns:
        An error message, or ``None`` when the id is safe.
    """
    if not change_id:
        return "change_id is empty — it must be a non-empty directory name."
    if ".." in change_id:
        return f"change_id {change_id!r} contains '..' — it must not traverse directories."
    if not _CHANGE_ID_RE.match(change_id):
        return (
            f"change_id {change_id!r} is not a safe directory name — it must start "
            f"with a lowercase letter or digit and contain only lowercase letters, "
            f"digits, '.', '_' and '-'."
        )
    return None


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


def populate_change_ids(roadmap: Roadmap) -> dict[str, str]:
    """Derive and set ``change_id`` on every item that lacks one, in place.

    Call this **before** ``save_roadmap`` so the ids are persisted in
    ``roadmap.yaml``. The generation contract does not ask the model for
    ``change_id`` and the schema leaves it optional, so without this step a
    generated roadmap carries none — and every downstream consumer that must
    locate ``openspec/changes/<change-id>/`` has to re-derive it and hope it
    agrees.

    Derivation is deterministic and shares ``_derive_change_id`` with
    :func:`scaffold_change`, so the id recorded in the roadmap is always the
    id of the directory that later gets created. Items that already carry an
    explicit ``change_id`` keep it, which makes this idempotent and safe to run
    on a roadmap an operator has hand-edited.

    Slugs that collide (two items whose titles reduce to the same slug) are
    disambiguated with a numeric suffix in item order, so ids stay unique
    without depending on title uniqueness.

    Args:
        roadmap: Roadmap to populate, mutated in place.

    Returns:
        Mapping of ``item_id`` to the resulting ``change_id`` for every item.
    """
    taken = {item.change_id for item in roadmap.items if item.change_id}
    assigned: dict[str, str] = {}

    for item in roadmap.items:
        if not item.change_id:
            base = _derive_change_id(item)
            candidate = base
            suffix = 2
            while candidate in taken:
                candidate = f"{base}-{suffix}"
                suffix += 1
            item.change_id = candidate
            taken.add(candidate)
        assigned[item.item_id] = item.change_id

    return assigned


def scaffold_change(roadmap: Roadmap, repo_root: Path, item_id: str) -> Path:
    """Create the OpenSpec change directory for a single roadmap item.

    Scaffold **one item at a time, at the moment it is picked up for work** —
    never the whole roadmap up front.

    The directory this writes is an intermediate stub: it has a `specs/`
    directory with no delta files in it, and `openspec validate --strict`
    rejects any change without at least one delta carrying a
    `#### Scenario:` block. Scaffolding every item of an N-item roadmap
    therefore lands N validation failures in `openspec validate --strict --all`,
    which CI runs on every push.

    The stub is only valid as the first step of authoring one change. The
    caller must complete it — normally by running `/plan-feature`, which writes
    the spec deltas — before committing. A scaffolded directory with an empty
    `specs/` must never reach a commit.

    Args:
        roadmap: The roadmap containing the item.
        repo_root: Repository root where openspec/changes/ lives.
        item_id: The `item_id` of the single item to scaffold.

    Returns:
        The created change directory path.

    Raises:
        KeyError: If `item_id` is not in the roadmap.
        ValueError: If the item's status is not candidate or approved.
    """
    item = next((i for i in roadmap.items if i.item_id == item_id), None)
    if item is None:
        raise KeyError(f"item_id {item_id!r} not found in roadmap {roadmap.roadmap_id!r}")

    if item.status not in (ItemStatus.CANDIDATE, ItemStatus.APPROVED):
        raise ValueError(
            f"item {item_id!r} has status {item.status.value!r}; "
            "only candidate or approved items can be scaffolded"
        )

    change_id = item.change_id or _derive_change_id(item)
    # Explicit ids come from roadmap.yaml and are never passed through
    # _slugify, so they must be checked before touching the filesystem.
    id_error = validate_change_id(change_id)
    if id_error:
        raise ValueError(f"Item {item_id!r}: {id_error}")

    # Update the item's change_id so it's tracked
    item.change_id = change_id

    change_dir = repo_root / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)

    # Create specs directory — deliberately empty; the caller authors the deltas.
    (change_dir / "specs").mkdir(exist_ok=True)

    # Write proposal and tasks
    _write_proposal(item, roadmap.roadmap_id, change_dir)
    _write_tasks(item, change_dir)

    return change_dir
