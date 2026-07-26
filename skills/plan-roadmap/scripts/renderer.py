"""Roadmap renderer — YAML to enriched structured markdown.

Produces a human-readable markdown view of ``roadmap.yaml`` with
``<!-- GENERATED: begin/end -->`` markers around auto-generated
sections.  Human-authored prose outside markers is preserved across
re-renders.

This is the maintenance direction of the plan-roadmap lifecycle:
  Ingestion:    proposal.md  →  roadmap.yaml   (decomposer)
  Maintenance:  roadmap.yaml →  roadmap.md     (renderer)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from models import (  # type: ignore[import-untyped]
    Roadmap,
)

# ---------------------------------------------------------------------------
# Generated-block markers
# ---------------------------------------------------------------------------
_GEN_BEGIN = "<!-- GENERATED: begin {name} -->"
_GEN_END = "<!-- GENERATED: end {name} -->"
_GEN_BEGIN_RE = re.compile(r"<!-- GENERATED: begin (\S+) -->")
_GEN_END_RE = re.compile(r"<!-- GENERATED: end (\S+) -->")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def render_roadmap(
    roadmap: Roadmap,
    source_proposal_text: str | None = None,
    existing_md: str | None = None,
) -> str:
    """Render a roadmap to structured markdown with generated-block markers.

    Args:
        roadmap: The roadmap to render.
        source_proposal_text: Optional original proposal text for
            context enrichment.
        existing_md: If provided, preserves human-authored sections
            (everything outside ``<!-- GENERATED: begin/end -->`` markers).
            This enables round-trip safety.

    Returns:
        Complete markdown string.
    """
    # Extract human-authored sections from existing markdown
    human_sections = _extract_human_sections(existing_md) if existing_md else {}

    parts: list[str] = []

    # Title
    parts.append(f"# Roadmap: {roadmap.roadmap_id}\n")

    # Human intro (preserved across re-renders)
    if "intro" in human_sections:
        parts.append(human_sections["intro"])
    else:
        parts.append(
            f"> Source: `{roadmap.source_proposal}` | "
            f"Status: **{roadmap.status.value}** | "
            f"Items: {len(roadmap.items)}\n"
        )

    # Phase table (generated)
    parts.append(_gen_block("phase-table", _render_phase_table(roadmap)))

    # Dependency DAG (generated)
    parts.append(_gen_block("dependency-dag", _render_dag(roadmap)))

    # Human cross-cutting themes (preserved)
    if "themes" in human_sections:
        parts.append("\n## Cross-Cutting Themes\n")
        parts.append(human_sections["themes"])

    # Per-item details (generated)
    parts.append(_gen_block("item-details", _render_item_details(roadmap)))

    # Human out-of-scope (preserved)
    if "out-of-scope" in human_sections:
        parts.append("\n## Out of Scope\n")
        parts.append(human_sections["out-of-scope"])

    # Human any other content (preserved)
    if "other" in human_sections:
        parts.append(human_sections["other"])

    return "\n".join(parts) + "\n"


def check_roadmap_sync(yaml_path: Path, md_path: Path) -> list[str]:
    """Check if roadmap.md is up-to-date with roadmap.yaml.

    Re-renders the generated sections from current YAML and compares
    against the generated sections in the existing markdown.  Returns
    a list of drift messages (empty = in sync).
    """
    import yaml as yaml_mod
    from models import Roadmap as RoadmapCls  # type: ignore[import-untyped]

    if not yaml_path.exists():
        return [f"YAML file not found: {yaml_path}"]
    if not md_path.exists():
        return [f"Markdown file not found: {md_path}"]

    roadmap = RoadmapCls.from_dict(yaml_mod.safe_load(yaml_path.read_text()))
    existing_md = md_path.read_text()

    # Extract generated blocks from existing markdown
    existing_blocks = _extract_generated_blocks(existing_md)

    # Render fresh generated blocks
    fresh_table = _render_phase_table(roadmap)
    fresh_dag = _render_dag(roadmap)
    fresh_details = _render_item_details(roadmap)

    drifts: list[str] = []

    if "phase-table" not in existing_blocks:
        drifts.append("Missing generated block: phase-table")
    elif existing_blocks["phase-table"].strip() != fresh_table.strip():
        drifts.append("Drift in phase-table: YAML and markdown differ")

    if "dependency-dag" not in existing_blocks:
        drifts.append("Missing generated block: dependency-dag")
    elif existing_blocks["dependency-dag"].strip() != fresh_dag.strip():
        drifts.append("Drift in dependency-dag: YAML and markdown differ")

    if "item-details" not in existing_blocks:
        drifts.append("Missing generated block: item-details")
    elif existing_blocks["item-details"].strip() != fresh_details.strip():
        drifts.append("Drift in item-details: YAML and markdown differ")

    return drifts


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def _render_phase_table(roadmap: Roadmap) -> str:
    """Render the phase/item summary table."""
    lines = [
        "## Phase Table\n",
        "| Priority | Item | Effort | Status | Dependencies |",
        "|----------|------|--------|--------|--------------|",
    ]
    for item in sorted(roadmap.items, key=lambda i: i.priority):
        deps = ", ".join(item.depends_on) if item.depends_on else "-"
        lines.append(
            f"| {item.priority} | {item.title} | {item.effort.value} "
            f"| {item.status.value} | {deps} |"
        )
    return "\n".join(lines)


def _render_dag(roadmap: Roadmap) -> str:
    """Render the dependency DAG as a mermaid graph."""
    lines = ["## Dependency Graph\n", "```mermaid", "graph TD"]

    for item in roadmap.items:
        # Node
        label = item.title[:40]
        lines.append(f"    {item.item_id}[\"{label}\"]")

    for item in roadmap.items:
        for dep_id in item.depends_on:
            # Edge annotation from dep_edges if available
            annotation = ""
            for edge in item.dep_edges:
                if edge.id == dep_id:
                    annotation = f"|{edge.source.value}|"
                    break
            lines.append(f"    {dep_id} -->{annotation} {item.item_id}")

    lines.append("```")
    return "\n".join(lines)


def _render_item_details(roadmap: Roadmap) -> str:
    """Render per-item detail sections."""
    sections: list[str] = ["## Item Details\n"]

    for item in sorted(roadmap.items, key=lambda i: i.priority):
        sections.append(f"### {item.item_id}: {item.title}\n")
        sections.append(f"- **Status**: {item.status.value}")
        sections.append(f"- **Priority**: {item.priority}")
        sections.append(f"- **Effort**: {item.effort.value}")

        if item.change_id:
            sections.append(f"- **Change ID**: {item.change_id}")

        if item.depends_on:
            deps_str = ", ".join(f"`{d}`" for d in item.depends_on)
            sections.append(f"- **Depends on**: {deps_str}")

        if item.scope:
            scope_parts = []
            if item.scope.write_allow:
                scope_parts.append(f"write: {', '.join(item.scope.write_allow)}")
            if item.scope.read_allow:
                scope_parts.append(f"read: {', '.join(item.scope.read_allow)}")
            if item.scope.lock_keys:
                scope_parts.append(f"locks: {', '.join(item.scope.lock_keys)}")
            sections.append(f"- **Scope**: {'; '.join(scope_parts)}")

        if item.description:
            sections.append(f"\n{item.description}")

        if item.acceptance_outcomes:
            sections.append("\n**Acceptance outcomes**:")
            for outcome in item.acceptance_outcomes:
                sections.append(f"- [ ] {outcome}")

        if item.dep_edges:
            sections.append("\n**Dependency rationale**:")
            for edge in item.dep_edges:
                conf = f" ({edge.confidence})" if edge.confidence else ""
                sections.append(
                    f"- `{edge.id}` [{edge.source.value}{conf}]: {edge.rationale}"
                )

        sections.append("")  # blank line between items

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Generated-block helpers
# ---------------------------------------------------------------------------
def _gen_block(name: str, content: str) -> str:
    """Wrap content in generated-block markers."""
    begin = _GEN_BEGIN.format(name=name)
    end = _GEN_END.format(name=name)
    return f"\n{begin}\n{content}\n{end}\n"


def _extract_generated_blocks(md: str) -> dict[str, str]:
    """Extract content within generated-block markers."""
    blocks: dict[str, str] = {}
    lines = md.split("\n")
    current_name: str | None = None
    current_lines: list[str] = []

    for line in lines:
        begin_match = _GEN_BEGIN_RE.search(line)
        end_match = _GEN_END_RE.search(line)

        if begin_match:
            current_name = begin_match.group(1)
            current_lines = []
        elif end_match and current_name:
            blocks[current_name] = "\n".join(current_lines)
            current_name = None
        elif current_name is not None:
            current_lines.append(line)

    return blocks


def _extract_human_sections(md: str) -> dict[str, str]:
    """Extract human-authored content from existing markdown.

    Returns sections that are OUTSIDE generated-block markers.
    """
    sections: dict[str, str] = {}
    lines = md.split("\n")
    in_generated = False
    current_section = "intro"
    section_lines: dict[str, list[str]] = {"intro": []}

    for line in lines:
        if _GEN_BEGIN_RE.search(line):
            in_generated = True
            continue
        if _GEN_END_RE.search(line):
            in_generated = False
            continue
        if in_generated:
            continue

        # Track section boundaries
        if line.startswith("## Cross-Cutting Themes"):
            current_section = "themes"
            section_lines.setdefault("themes", [])
            continue
        elif line.startswith("## Out of Scope"):
            current_section = "out-of-scope"
            section_lines.setdefault("out-of-scope", [])
            continue
        elif line.startswith("# "):
            continue  # skip title line

        section_lines.setdefault(current_section, []).append(line)

    for name, slines in section_lines.items():
        content = "\n".join(slines).strip()
        if content:
            sections[name] = content

    return sections
