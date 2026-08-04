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


def _capability_for(item: RoadmapItem, roadmap_id: str) -> str:
    """Resolve the capability directory a scaffolded spec delta belongs under.

    An item may name its capability explicitly. When it does not, the roadmap id
    is used, which keeps the scaffold valid and keeps every item of one roadmap
    together — a placeholder the refinement pass is expected to correct, not a
    claim about where the requirement finally belongs.
    """
    return _slugify(item.capability or roadmap_id)


def _shall_sentence(outcome: str) -> str:
    """Render an acceptance outcome as a requirement line carrying a modal verb.

    OpenSpec's strict mode inspects only a requirement's **first** line for
    SHALL/MUST, so the modal verb has to lead. Outcomes that already state one
    are passed through; the rest are wrapped.
    """
    text = outcome.strip().rstrip(".")
    if not text:
        return "The system SHALL satisfy this outcome."
    if re.search(r"\b(SHALL|MUST)\b", text):
        return f"{text}."
    return f"The system SHALL ensure that {text[0].lower()}{text[1:]}."


def _requirement_title(outcome: str) -> str:
    """Derive a short requirement heading from an acceptance outcome."""
    text = " ".join(outcome.strip().rstrip(".").split())
    return text if len(text) <= 80 else text[:77].rsplit(" ", 1)[0] + "..."


def _write_specs(item: RoadmapItem, roadmap_id: str, change_dir: Path) -> Path:
    """Write a preliminary spec delta derived from the item's acceptance outcomes.

    Every roadmap item carries ``acceptance_outcomes``, and each outcome is
    already a statement about observable behavior — which is what a requirement
    is. One outcome becomes one requirement plus one scenario.

    The result is deliberately a **sketch**: it validates under
    ``openspec validate --strict`` so the change is a well-formed OpenSpec change
    from the moment the roadmap is written, and it is explicitly marked for
    refinement before implementation. Without this the scaffold produces an empty
    ``specs/`` directory, git drops it on commit, and the change fails validation
    with "no deltas found".
    """
    capability = _capability_for(item, roadmap_id)
    spec_dir = change_dir / "specs" / capability
    spec_dir.mkdir(parents=True, exist_ok=True)

    outcomes = [o for o in (item.acceptance_outcomes or []) if o.strip()]
    blocks: list[str] = []

    if outcomes:
        for outcome in outcomes:
            blocks.append(
                f"### Requirement: {_requirement_title(outcome)}\n\n"
                f"{_shall_sentence(outcome)}\n\n"
                f"#### Scenario: {_requirement_title(outcome)}\n\n"
                f"WHEN `{item.change_id or _derive_change_id(item)}` is implemented\n"
                f"THEN {outcome.strip().rstrip('.')}.\n"
            )
    else:
        # No outcomes recorded — still emit something that validates, and make the
        # gap obvious rather than silently shipping an unvalidatable change.
        blocks.append(
            f"### Requirement: {item.title}\n\n"
            f"The system SHALL deliver the behavior described by roadmap item "
            f"`{item.item_id}`.\n\n"
            f"#### Scenario: Behavior is specified before implementation\n\n"
            f"WHEN `{item.change_id or _derive_change_id(item)}` is planned\n"
            f"THEN this requirement SHALL be replaced with concrete requirements "
            f"derived from the refined proposal.\n"
        )

    header = (
        f"<!-- SCAFFOLD: generated by plan-roadmap from roadmap `{roadmap_id}`, "
        f"item `{item.item_id}`.\n"
        f"     Preliminary and intended for refinement by /plan-feature or "
        f"/iterate-on-plan\n"
        f"     before implementation. The capability directory "
        f"(`{capability}`) is a\n"
        f"     placeholder unless the item named one explicitly. -->\n\n"
        f"## ADDED Requirements\n\n"
    )

    spec_path = spec_dir / "spec.md"
    spec_path.write_text(header + "\n".join(blocks))
    return spec_path


def _write_design(item: RoadmapItem, roadmap_id: str, change_dir: Path) -> Path | None:
    """Write an optional design.md sketch when the item carries design context.

    Emitted only when there is something to say — a rationale or declared
    dependencies. A design document that restates the title helps nobody, so the
    absence of one is meaningful rather than an omission.
    """
    if not item.rationale and not item.depends_on:
        return None

    deps_md = (
        "\n".join(f"- `{d}`" for d in item.depends_on)
        if item.depends_on
        else "- None"
    )
    content = f"""\
<!-- SCAFFOLD: generated by plan-roadmap from roadmap `{roadmap_id}`, item `{item.item_id}`.
     Preliminary. Refine before implementation. -->

# Design: {item.title}

## Context

{item.description or 'TBD — fill in during refinement.'}

## Why this item exists

{item.rationale or 'TBD — fill in during refinement.'}

## Depends on

{deps_md}

## Open questions

- Which capability do these requirements finally belong to?
- What are the non-goals for this item?
- Which decisions here need recording before implementation starts?
"""
    design_path = change_dir / "design.md"
    design_path.write_text(content)
    return design_path


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

        # Write proposal, tasks, and the preliminary spec delta. The spec delta is
        # what makes the scaffold a *valid* OpenSpec change rather than a directory
        # that fails `openspec validate --strict` with "no deltas found" — and,
        # because git does not track empty directories, it is also what makes the
        # specs/ tree survive being committed at all.
        _write_proposal(item, roadmap.roadmap_id, change_dir)
        _write_tasks(item, change_dir)
        _write_specs(item, roadmap.roadmap_id, change_dir)
        _write_design(item, roadmap.roadmap_id, change_dir)

        created.append(change_dir)

    return created
