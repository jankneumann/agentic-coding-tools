"""Learning-log read/write helpers with progressive disclosure.

Manages the root index (learning-log.md) and per-item entries (learnings/<item-id>.md).
"""

from __future__ import annotations

import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from models import LearningEntry  # type: ignore[import-untyped]
from sanitizer import sanitize_dict  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

COMPACTION_THRESHOLD = 50
RECENCY_WINDOW = 3


def write_entry(workspace: Path, entry: LearningEntry) -> Path:
    """Write a learning entry to learnings/<item-id>.md with sanitized frontmatter."""
    learnings_dir = workspace / "learnings"
    learnings_dir.mkdir(exist_ok=True)

    entry_path = learnings_dir / f"{entry.item_id}.md"
    sanitized = sanitize_dict(entry.to_dict())

    frontmatter = yaml.dump(sanitized, default_flow_style=False, sort_keys=False)
    body = _build_narrative(entry)

    content = f"---\n{frontmatter}---\n\n{body}\n"
    entry_path.write_text(content)

    _update_index(workspace, entry)
    logger.info("Learning entry written: %s", entry.item_id)
    return entry_path


def _build_narrative(entry: LearningEntry) -> str:
    """Build a markdown narrative body from entry data."""
    sections: list[str] = [f"# Learning: {entry.item_id}"]

    if entry.decisions:
        sections.append("\n## Decisions")
        for dec in entry.decisions:
            sections.append(f"- **{dec.title}**: {dec.outcome}")
            if dec.alternatives_rejected:
                for alt in dec.alternatives_rejected:
                    sections.append(f"  - Rejected: {alt}")

    if entry.blockers:
        sections.append("\n## Blockers")
        for b in entry.blockers:
            sections.append(f"- {b.description} → {b.resolution}")

    if entry.deviations:
        sections.append("\n## Deviations")
        for dv in entry.deviations:
            sections.append(f"- Plan: {dv.from_plan} → Actual: {dv.actual} (reason: {dv.reason})")

    if entry.recommendations:
        sections.append("\n## Recommendations")
        for rec in entry.recommendations:
            sections.append(f"- {rec}")

    return "\n".join(sections)


def _update_index(workspace: Path, entry: LearningEntry) -> None:
    """Update the root learning-log.md index with a one-line entry."""
    index_path = workspace / "learning-log.md"

    if not index_path.exists():
        index_path.write_text("# Learning Log\n\n| Item | Status | Summary |\n|------|--------|--------|\n")

    existing = index_path.read_text()
    raw_summary = entry.decisions[0].outcome[:80] if entry.decisions else "No decisions recorded"
    summary = raw_summary.replace("|", "\\|")
    phase_str = entry.phase.value if entry.phase else "unknown"
    line = f"| {entry.item_id} | {phase_str} | {summary} |\n"

    # Replace existing line for this item, or append
    pattern = re.compile(rf"^\| {re.escape(entry.item_id)} \|.*$", re.MULTILINE)
    if pattern.search(existing):
        updated = pattern.sub(line.rstrip(), existing)
    else:
        updated = existing.rstrip() + "\n" + line

    index_path.write_text(updated)


def read_entry(workspace: Path, item_id: str) -> dict[str, Any] | None:
    """Read a learning entry's frontmatter as a dict."""
    entry_path = workspace / "learnings" / f"{item_id}.md"
    if not entry_path.exists():
        return None

    content = entry_path.read_text()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1])  # type: ignore[no-any-return]
    return None


def read_index(workspace: Path) -> list[str]:
    """Read the learning-log.md index and return item IDs in order."""
    index_path = workspace / "learning-log.md"
    if not index_path.exists():
        return []

    content = index_path.read_text()
    item_ids: list[str] = []
    for line in content.splitlines():
        if line.startswith("| ") and not line.startswith("| Item") and not line.startswith("|---"):
            parts = line.split("|")
            if len(parts) >= 2:
                item_id = parts[1].strip()
                if item_id:
                    item_ids.append(item_id)
    return item_ids


def select_relevant_entries(
    workspace: Path,
    target_item_depends_on: list[str],
    recency_window: int = RECENCY_WINDOW,
) -> list[dict[str, Any]]:
    """Select learning entries relevant to the target item.

    Loads direct dependency entries plus the most recent N entries,
    bounding context assembly to O(k) not O(n).
    """
    all_ids = read_index(workspace)
    relevant_ids = set(target_item_depends_on) | set(all_ids[-recency_window:])

    entries: list[dict[str, Any]] = []
    for item_id in relevant_ids:
        entry = read_entry(workspace, item_id)
        if entry:
            entries.append(entry)
    return entries


def needs_compaction(workspace: Path) -> bool:
    """Check if the learning log index exceeds the compaction threshold."""
    return len(read_index(workspace)) > COMPACTION_THRESHOLD


def compact(workspace: Path, active_item_ids: set[str]) -> int:
    """Compact older entries into _archive.md, preserving active items.

    Returns number of entries archived.
    """
    all_ids = read_index(workspace)
    if len(all_ids) <= COMPACTION_THRESHOLD:
        return 0

    learnings_dir = workspace / "learnings"
    archive_path = learnings_dir / "_archive.md"

    # Entries to keep: active items + recent window
    keep_ids = active_item_ids | set(all_ids[-RECENCY_WINDOW:])
    archive_ids = [i for i in all_ids if i not in keep_ids]

    if not archive_ids:
        return 0

    # Build archive summary
    summaries: list[str] = []
    if archive_path.exists():
        summaries.append(archive_path.read_text().rstrip())
    else:
        summaries.append("# Archived Learning Entries\n")

    summaries.append(f"\n## Archive batch ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})\n")

    for item_id in archive_ids:
        entry = read_entry(workspace, item_id)
        if entry:
            decisions = entry.get("decisions", [])
            summary = decisions[0].get("outcome", "")[:100] if decisions else ""
            summaries.append(f"- **{item_id}**: {summary}")
            # Remove individual entry file
            entry_file = learnings_dir / f"{item_id}.md"
            if entry_file.exists():
                entry_file.unlink()

    archive_path.write_text("\n".join(summaries) + "\n")

    # Rebuild index with only kept entries
    index_path = workspace / "learning-log.md"
    kept_lines = ["# Learning Log\n", "\n| Item | Status | Summary |\n", "|------|--------|--------|\n"]
    content = index_path.read_text()
    for line in content.splitlines():
        if line.startswith("| ") and not line.startswith("| Item") and not line.startswith("|---"):
            parts = line.split("|")
            if len(parts) >= 2:
                item_id = parts[1].strip()
                if item_id in keep_ids:
                    kept_lines.append(line + "\n")
    index_path.write_text("".join(kept_lines))

    logger.info("Compacted %d entries into archive", len(archive_ids))
    return len(archive_ids)
