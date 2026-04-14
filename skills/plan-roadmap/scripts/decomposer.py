"""Structural decomposition of markdown proposals into roadmap items.

Parses headings, lists, and keyword markers to extract capabilities,
constraints, and phases — then builds a prioritized dependency DAG
of RoadmapItem objects without any LLM inference.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Import shared runtime models
# ---------------------------------------------------------------------------
_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from models import (  # type: ignore[import-untyped]
    Effort,
    ItemStatus,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
)

# ---------------------------------------------------------------------------
# Effort ordering for size comparison
# ---------------------------------------------------------------------------
_EFFORT_ORDER: list[Effort] = [Effort.XS, Effort.S, Effort.M, Effort.L, Effort.XL]
_EFFORT_INDEX: dict[Effort, int] = {e: i for i, e in enumerate(_EFFORT_ORDER)}

# ---------------------------------------------------------------------------
# Markdown section markers
# ---------------------------------------------------------------------------
_CAPABILITY_MARKERS = re.compile(
    r"\b(capabilit|feature|function|component|module|service|endpoint|system)\w*\b",
    re.IGNORECASE,
)
_CONSTRAINT_MARKERS = re.compile(
    r"\b(constraint|requirement|must|shall|limit|invariant|non-?functional)\b",
    re.IGNORECASE,
)
_PHASE_MARKERS = re.compile(
    r"\b(phase|milestone|stage|step|iteration|sprint|epoch)\b",
    re.IGNORECASE,
)
_INFRA_MARKERS = re.compile(
    r"\b(infrastructure|foundation|setup|bootstrap|scaffold|migration|database|schema|config)\b",
    re.IGNORECASE,
)

# Heading pattern: captures level (number of #) and text
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Fenced code block fence pattern (``` or ~~~, optionally with language id)
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")

# Markdown table separator row: |---|---|...
_TABLE_SEP_RE = re.compile(r"^\|[\s:]*-{2,}[\s:]*(\|[\s:]*-{2,}[\s:]*)+\|?\s*$")

# Priority column header markers
_PRIORITY_MARKERS = re.compile(
    r"\b(priority|p[0-3]|impact|module|status)\b", re.IGNORECASE
)

# Bullet list item pattern
_BULLET_RE = re.compile(r"^[\s]*[-*+]\s+(.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------
@dataclass
class _Section:
    """A parsed markdown section with heading and body text."""

    level: int
    title: str
    body: str
    line_start: int
    is_capability: bool = False
    is_constraint: bool = False
    is_phase: bool = False
    phase_index: int = 0


@dataclass
class _Constraint:
    """A constraint extracted from the proposal."""

    text: str
    applies_to: list[str] = field(default_factory=list)  # item_ids or "global"


# ---------------------------------------------------------------------------
# Proposal validation
# ---------------------------------------------------------------------------
def validate_proposal(text: str) -> list[str]:
    """Check minimum required sections. Returns list of error messages (empty = valid)."""
    errors: list[str] = []

    if not text or not text.strip():
        errors.append("Proposal is empty")
        return errors

    # Must have at least one heading
    headings = _HEADING_RE.findall(text)
    if not headings:
        errors.append("Proposal has no headings — cannot identify sections")

    # Must have at least one capability/feature indicator
    if not _CAPABILITY_MARKERS.search(text):
        errors.append(
            "No actionable capabilities found — proposal must contain at least one "
            "capability, feature, component, or service description"
        )

    return errors


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------
def _parse_sections(text: str) -> list[_Section]:
    """Split markdown into sections by headings.

    Fenced code blocks (``` or ~~~) are tracked so that headings inside
    them are not treated as section boundaries — this prevents YAML/code
    examples from generating noise sections.
    """
    lines = text.split("\n")
    sections: list[_Section] = []
    current_level = 0
    current_title = ""
    current_body_lines: list[str] = []
    current_start = 0
    in_fenced_block = False
    fence_marker = ""
    fence_length = 0

    for i, line in enumerate(lines):
        # Track fenced code blocks (```, ~~~~, etc.)
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fenced_block:
                in_fenced_block = True
                fence_marker = marker[0]  # ` or ~
                fence_length = len(marker)
            else:
                # Closing fence: same char, at least as many as opening,
                # nothing else on the line (after stripping whitespace)
                stripped = line.strip()
                if (
                    stripped[0] == fence_marker
                    and len(stripped) >= fence_length
                    and stripped == fence_marker * len(stripped)
                ):
                    in_fenced_block = False
                    fence_marker = ""
                    fence_length = 0
            current_body_lines.append(line)
            continue

        if in_fenced_block:
            current_body_lines.append(line)
            continue

        m = _HEADING_RE.match(line)
        if m:
            # Flush previous section
            if current_title:
                body = "\n".join(current_body_lines).strip()
                sections.append(
                    _Section(
                        level=current_level,
                        title=current_title,
                        body=body,
                        line_start=current_start,
                    )
                )
            current_level = len(m.group(1))
            current_title = m.group(2).strip()
            current_body_lines = []
            current_start = i
        else:
            current_body_lines.append(line)

    # Flush last section
    if current_title:
        body = "\n".join(current_body_lines).strip()
        sections.append(
            _Section(
                level=current_level,
                title=current_title,
                body=body,
                line_start=current_start,
            )
        )

    return sections


def _classify_sections(sections: list[_Section]) -> list[_Section]:
    """Tag each section as capability, constraint, or phase.

    Sub-section propagation: when a parent H2/H3 is classified as a
    capability, child H4/H5 sections that don't match any markers
    themselves inherit the capability classification.
    """
    phase_counter = 0
    parent_is_capability = False
    parent_level = 0

    for section in sections:
        combined = f"{section.title} {section.body}"
        section.is_capability = bool(_CAPABILITY_MARKERS.search(combined))
        section.is_constraint = bool(_CONSTRAINT_MARKERS.search(combined))

        if _PHASE_MARKERS.search(section.title):
            section.is_phase = True
            phase_counter += 1
            section.phase_index = phase_counter

        # Sub-section propagation: if parent (H2/H3) is capability,
        # propagate to children (H4+) that don't match any marker
        if section.level <= 3:
            parent_is_capability = section.is_capability
            parent_level = section.level
        elif (
            section.level > parent_level
            and parent_is_capability
            and not section.is_capability
            and not section.is_constraint
            and not section.is_phase
        ):
            section.is_capability = True

    return sections


# ---------------------------------------------------------------------------
# Item extraction
# ---------------------------------------------------------------------------
def _generate_item_id(title: str, index: int) -> str:
    """Generate a deterministic short item ID from title."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:30]
    return f"ri-{index + 1:02d}-{slug}"


def _estimate_effort(section: _Section) -> Effort:
    """Heuristic effort estimate based on section length and bullet count."""
    bullets = _BULLET_RE.findall(section.body)
    body_len = len(section.body)

    if body_len < 100 and len(bullets) <= 1:
        return Effort.XS
    elif body_len < 300 and len(bullets) <= 3:
        return Effort.S
    elif body_len < 800 and len(bullets) <= 8:
        return Effort.M
    elif body_len < 1500 and len(bullets) <= 15:
        return Effort.L
    else:
        return Effort.XL


def _extract_acceptance_outcomes(section: _Section) -> list[str]:
    """Extract acceptance outcomes from bullet lists in the section."""
    outcomes: list[str] = []
    bullets = _BULLET_RE.findall(section.body)
    for bullet in bullets:
        # Use bullets that look like testable outcomes
        if any(
            kw in bullet.lower()
            for kw in ("should", "must", "pass", "verify", "test", "accept", "outcome", "expect")
        ):
            outcomes.append(bullet.strip())
    # If no explicit outcomes, synthesize from the title
    if not outcomes:
        outcomes.append(f"{section.title} is implemented and tested")
    return outcomes


def _sections_to_items(sections: list[_Section]) -> list[RoadmapItem]:
    """Convert capability sections into RoadmapItem objects."""
    items: list[RoadmapItem] = []
    capability_sections = [s for s in sections if s.is_capability]

    if not capability_sections:
        # Fallback: treat all non-phase, non-constraint sections at level >= 2 as capabilities
        capability_sections = [
            s
            for s in sections
            if s.level >= 2 and not s.is_constraint and not s.is_phase
        ]

    for i, section in enumerate(capability_sections):
        item_id = _generate_item_id(section.title, i)
        effort = _estimate_effort(section)
        outcomes = _extract_acceptance_outcomes(section)

        item = RoadmapItem(
            item_id=item_id,
            title=section.title,
            status=ItemStatus.CANDIDATE,
            priority=i + 1,
            effort=effort,
            description=section.body[:500] if section.body else None,
            acceptance_outcomes=outcomes,
        )
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Size validation (merge/split)
# ---------------------------------------------------------------------------
def validate_item_sizes(
    items: list[RoadmapItem],
    min_effort: Effort = Effort.S,
    max_effort: Effort = Effort.L,
) -> list[RoadmapItem]:
    """Merge undersized items and split oversized items.

    - Items below min_effort are merged with adjacent items of similar scope.
    - Items above max_effort are split if their description contains
      multiple independent sub-bullets.

    Returns a new list (does not mutate the input).
    """
    min_idx = _EFFORT_INDEX[min_effort]
    max_idx = _EFFORT_INDEX[max_effort]

    result: list[RoadmapItem] = []
    merge_buffer: list[RoadmapItem] = []

    for item in items:
        effort_idx = _EFFORT_INDEX[item.effort]

        if effort_idx < min_idx:
            # Accumulate undersized items for merging
            merge_buffer.append(item)

            # When we have 2+ undersized items, merge them
            if len(merge_buffer) >= 2:
                merged = _merge_items(merge_buffer)
                result.append(merged)
                merge_buffer.clear()

        elif effort_idx > max_idx:
            # Flush any pending merges first
            if merge_buffer:
                result.extend(merge_buffer)
                merge_buffer.clear()

            # Split oversized item
            split_items = _split_item(item)
            result.extend(split_items)

        else:
            # Flush any pending merge buffer (single undersized item stays as-is)
            if merge_buffer:
                result.extend(merge_buffer)
                merge_buffer.clear()
            result.append(item)

    # Flush remaining merge buffer
    if merge_buffer:
        result.extend(merge_buffer)

    # Re-assign priorities based on new ordering
    for i, item in enumerate(result):
        item.priority = i + 1

    return result


def _merge_items(items: list[RoadmapItem]) -> RoadmapItem:
    """Merge multiple small items into one larger item."""
    titles = [it.title for it in items]
    combined_title = " + ".join(titles)
    descriptions = [it.description or it.title for it in items]
    combined_desc = "\n\n".join(descriptions)
    combined_outcomes = []
    for it in items:
        combined_outcomes.extend(it.acceptance_outcomes)

    # Effort bumps up one level from the largest constituent
    max_effort_idx = max(_EFFORT_INDEX[it.effort] for it in items)
    new_effort_idx = min(max_effort_idx + 1, len(_EFFORT_ORDER) - 1)

    return RoadmapItem(
        item_id=_generate_item_id(combined_title, 0),
        title=combined_title,
        status=ItemStatus.CANDIDATE,
        priority=items[0].priority,
        effort=_EFFORT_ORDER[new_effort_idx],
        description=combined_desc[:500],
        acceptance_outcomes=combined_outcomes,
        depends_on=[],
    )


def _split_item(item: RoadmapItem) -> list[RoadmapItem]:
    """Split an oversized item into sub-items based on bullet points."""
    bullets = _BULLET_RE.findall(item.description or "")

    if len(bullets) < 2:
        # Cannot meaningfully split — return as-is
        return [item]

    # Split bullets into roughly equal groups
    mid = len(bullets) // 2
    groups = [bullets[:mid], bullets[mid:]]

    split_items: list[RoadmapItem] = []
    for i, group in enumerate(groups):
        sub_title = f"{item.title} (part {i + 1})"
        sub_desc = "\n".join(f"- {b}" for b in group)
        sub_outcomes = [f"{sub_title} is implemented and tested"]

        # Effort drops one level from the original
        effort_idx = max(_EFFORT_INDEX[item.effort] - 1, 0)

        sub_item = RoadmapItem(
            item_id=_generate_item_id(sub_title, i),
            title=sub_title,
            status=ItemStatus.CANDIDATE,
            priority=item.priority + i,
            effort=_EFFORT_ORDER[effort_idx],
            description=sub_desc[:500],
            acceptance_outcomes=sub_outcomes,
            depends_on=[],
        )
        split_items.append(sub_item)

    # Part 2 depends on part 1
    if len(split_items) > 1:
        split_items[1].depends_on = [split_items[0].item_id]

    return split_items


# ---------------------------------------------------------------------------
# Dependency DAG construction
# ---------------------------------------------------------------------------
def build_dependency_dag(items: list[RoadmapItem]) -> list[RoadmapItem]:
    """Infer dependency edges between items using two-tier inference.

    Tier A (deterministic): When both items declare ``scope``, edges are
    added based on write/read glob overlap and shared lock keys.  No edge
    is added when scopes are declared but don't overlap.

    Tier B is handled by ``semantic_decomposer.py`` when an LLM client
    is available.  This function only applies Tier A and preserves
    existing edges (from splits or explicit declarations).

    Design principle (PR #113): use determinism where input→output is
    crisp; use LLM inference where ambiguity requires reasoning.

    Returns the same list with updated depends_on fields (no cycles guaranteed).
    """
    _apply_scope_overlap(items)

    # Verify no cycles — if cycles found, break them
    _break_cycles(items)

    return items


def _apply_scope_overlap(items: list[RoadmapItem]) -> None:
    """Tier A: add edges based on declared scope overlap.

    Uses shared primitives from ``roadmap-runtime/scripts/scope_overlap.py``.
    Only runs when both items in a pair declare scope.  When neither or
    only one item has scope, no deterministic edge is added — that case
    is handled by Tier B (LLM) in the semantic decomposer.
    """
    try:
        from scope_overlap import check_scope_overlap  # type: ignore[import-untyped]
    except ImportError:
        return  # scope_overlap not on path — skip Tier A

    for i, item_a in enumerate(items):
        if not getattr(item_a, "scope", None):
            continue
        for item_b in items[i + 1:]:
            if not getattr(item_b, "scope", None):
                continue

            # Skip if already connected
            if item_b.item_id in item_a.depends_on or item_a.item_id in item_b.depends_on:
                continue

            rationale = check_scope_overlap(
                write_a=getattr(item_a.scope, "write_allow", []),
                read_a=getattr(item_a.scope, "read_allow", []),
                lock_a=getattr(item_a.scope, "lock_keys", []),
                write_b=getattr(item_b.scope, "write_allow", []),
                read_b=getattr(item_b.scope, "read_allow", []),
                lock_b=getattr(item_b.scope, "lock_keys", []),
            )
            if rationale:
                # Higher priority (lower number) is the dependency
                if item_a.priority < item_b.priority:
                    item_b.depends_on.append(item_a.item_id)
                else:
                    item_a.depends_on.append(item_b.item_id)


def _break_cycles(items: list[RoadmapItem]) -> None:
    """Remove edges to break any cycles in the dependency graph."""
    id_map = {it.item_id: it for it in items}
    visited: set[str] = set()
    in_stack: set[str] = set()
    path: list[str] = []

    def _dfs(item_id: str) -> None:
        if item_id in in_stack:
            # Found cycle — remove the back-edge
            # Remove the last edge in the cycle (from path[-1] to item_id)
            if path:
                last = id_map.get(path[-1])
                if last and item_id in last.depends_on:
                    last.depends_on.remove(item_id)
            return
        if item_id in visited:
            return
        visited.add(item_id)
        in_stack.add(item_id)
        path.append(item_id)

        item = id_map.get(item_id)
        if item:
            for dep in list(item.depends_on):
                _dfs(dep)

        path.pop()
        in_stack.discard(item_id)

    for it in items:
        _dfs(it.item_id)


# ---------------------------------------------------------------------------
# Table row extraction (for priority tables in proposal body)
# ---------------------------------------------------------------------------
def _extract_table_items(body: str) -> list[_Section]:
    """Extract items from markdown priority tables in a section's body.

    Looks for markdown tables with priority-related column headers
    (Priority, P0, P1, Module, etc.) and creates a synthetic _Section
    for each data row.  Returns an empty list if no priority tables found.
    """
    lines = body.split("\n")
    items: list[_Section] = []

    i = 0
    while i < len(lines):
        # Look for a table separator row (|---|---|)
        if i > 0 and _TABLE_SEP_RE.match(lines[i].strip()):
            header_line = lines[i - 1].strip()
            if not header_line.startswith("|"):
                i += 1
                continue

            # Parse header columns
            headers = [
                h.strip() for h in header_line.strip("|").split("|")
            ]

            # Check if this is a priority table
            header_text = " ".join(headers)
            if not _PRIORITY_MARKERS.search(header_text):
                i += 1
                continue

            # Find the "name" column — prefer "Module", "Component",
            # "Feature", "Item"; fall back to the first column.
            _NAME_COLS = re.compile(
                r"\b(module|component|feature|item|name|task|capability)\b",
                re.IGNORECASE,
            )
            name_col = 0  # default: first column
            for ci, h in enumerate(headers):
                if _NAME_COLS.search(h):
                    name_col = ci
                    break

            # Parse data rows
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("|"):
                row = lines[j].strip()
                cells = [c.strip() for c in row.strip("|").split("|")]
                if len(cells) > name_col:
                    title = cells[name_col].strip("`").strip("*").strip()
                    if title and title != "---":
                        # Build a description from all cells
                        desc_parts = [
                            f"{headers[ci]}: {cells[ci]}"
                            for ci in range(len(cells))
                            if ci < len(headers) and ci != name_col
                        ]
                        items.append(
                            _Section(
                                level=4,  # synthetic sub-section level
                                title=title,
                                body="\n".join(desc_parts),
                                line_start=j,
                                is_capability=True,
                            )
                        )
                j += 1
            i = j
        else:
            i += 1

    return items


# ---------------------------------------------------------------------------
# Repo state scanning (archive and active changes)
# ---------------------------------------------------------------------------
def scan_archive_state(repo_root: Path) -> dict[str, str]:
    """Walk openspec/changes/archive/ and openspec/changes/ to build a
    {change_id: status} map.

    Archive entries (``YYYY-MM-DD-<change-id>/``) → ``completed``.
    Active change dirs (``openspec/changes/<name>/``) → ``in_progress``.
    """
    state: dict[str, str] = {}

    # Archived changes
    archive_dir = repo_root / "openspec" / "changes" / "archive"
    if archive_dir.is_dir():
        for entry in archive_dir.iterdir():
            if entry.is_dir():
                name = entry.name
                # Strip date prefix (YYYY-MM-DD-)
                if len(name) > 11 and name[4] == "-" and name[7] == "-" and name[10] == "-":
                    change_id = name[11:]
                else:
                    change_id = name
                state[change_id] = "completed"

    # Active (non-archived) changes
    changes_dir = repo_root / "openspec" / "changes"
    if changes_dir.is_dir():
        for entry in changes_dir.iterdir():
            if entry.is_dir() and entry.name != "archive":
                if entry.name not in state:
                    state[entry.name] = "in_progress"

    return state


def make_repo_relative(path: str, repo_root: Path) -> str:
    """Normalize an absolute path to repo-relative.

    If ``path`` is already relative or ``repo_root`` is not a prefix,
    return ``path`` unchanged.
    """
    try:
        p = Path(path)
        if p.is_absolute():
            return str(p.relative_to(repo_root))
    except (ValueError, TypeError):
        pass
    return path


def _generate_clean_id(title: str) -> str:
    """Generate a clean kebab-case ID from a title.

    Unlike ``_generate_item_id``, this produces IDs without the ``ri-``
    prefix or numeric section prefixes — matching OpenSpec change-id
    conventions.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    # Remove leading numeric prefixes (e.g., "1-1-" from "§1.1")
    slug = re.sub(r"^[\d]+-(?:[\d]+-)*", "", slug)
    # Truncate to reasonable length
    result = slug[:60].rstrip("-")
    return result if result else "unnamed-item"


# ---------------------------------------------------------------------------
# Main decomposition entry point
# ---------------------------------------------------------------------------
def decompose(proposal_text: str, source_path: str) -> Roadmap:
    """Decompose a markdown proposal into a Roadmap with candidate items.

    Args:
        proposal_text: Full markdown text of the proposal.
        source_path: Path/identifier for the source proposal (stored in roadmap metadata).

    Returns:
        A Roadmap object with candidate items and dependency DAG.

    Raises:
        ValueError: If the proposal fails validation.
    """
    errors = validate_proposal(proposal_text)
    if errors:
        raise ValueError(f"Proposal validation failed: {'; '.join(errors)}")

    # Step 1: Parse structure
    sections = _parse_sections(proposal_text)
    sections = _classify_sections(sections)

    # Step 2: Extract items from capability sections
    items = _sections_to_items(sections)

    if not items:
        raise ValueError(
            "No decomposable items found — proposal must contain "
            "headed sections describing capabilities or features"
        )

    # Step 3: Validate sizes (merge/split)
    items = validate_item_sizes(items)

    # Step 4: Build dependency DAG
    items = build_dependency_dag(items)

    # Build roadmap ID from source path
    slug = re.sub(r"[^a-z0-9]+", "-", Path(source_path).stem.lower()).strip("-")
    roadmap_id = f"roadmap-{slug}"

    roadmap = Roadmap(
        schema_version=1,
        roadmap_id=roadmap_id,
        source_proposal=source_path,
        items=items,
        created_at=datetime.now(timezone.utc).isoformat(),
        status=RoadmapStatus.PLANNING,
    )

    # Final safety check
    if roadmap.has_cycle():
        raise RuntimeError("BUG: dependency DAG contains cycles after break_cycles()")

    return roadmap
