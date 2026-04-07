"""Archive miner for completed OpenSpec changes.

Indexes archived changes into a normalized archive-intelligence index.
Supports incremental indexing — already-indexed changes are skipped.

Design Decision D6: First pass uses deterministic normalization.
Advanced retrieval/embedding can be layered on later.

Inputs (when present):
- proposal.md, design.md, tasks.md
- spec deltas (specs/**/*.md)
- change-context.md, validation-report.md
- session-log.md, process-analysis.md/json
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ArchiveEntry:
    """Normalized index entry for a single archived change."""

    change_id: str
    title: str = ""
    status: str = "archived"
    artifacts_present: list[str] = field(default_factory=list)
    artifacts_absent: list[str] = field(default_factory=list)
    spec_capabilities: list[str] = field(default_factory=list)
    task_count: int = 0
    requirement_count: int = 0
    has_validation: bool = False
    has_process_analysis: bool = False
    has_session_log: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "title": self.title,
            "status": self.status,
            "artifacts_present": self.artifacts_present,
            "artifacts_absent": self.artifacts_absent,
            "spec_capabilities": self.spec_capabilities,
            "task_count": self.task_count,
            "requirement_count": self.requirement_count,
            "has_validation": self.has_validation,
            "has_process_analysis": self.has_process_analysis,
            "has_session_log": self.has_session_log,
            "metadata": self.metadata,
        }


@dataclass
class ArchiveIndex:
    """Full archive-intelligence index over all archived changes."""

    version: int = 1
    entries: list[ArchiveEntry] = field(default_factory=list)

    @property
    def indexed_ids(self) -> set[str]:
        return {e.change_id for e in self.entries}

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "total_changes": len(self.entries),
            "entries": [e.to_dict() for e in self.entries],
        }


# Known artifact files to check in each archived change
KNOWN_ARTIFACTS = [
    "proposal.md",
    "design.md",
    "tasks.md",
    "change-context.md",
    "validation-report.md",
    "session-log.md",
    "process-analysis.md",
    "process-analysis.json",
    "rework-report.json",
    "work-packages.yaml",
]


def index_archive(
    archive_dir: Path,
    existing_index: ArchiveIndex | None = None,
) -> ArchiveIndex:
    """Index all archived OpenSpec changes.

    Scans the archive directory for change directories and normalizes
    their artifacts into index entries. Supports incremental indexing.

    Args:
        archive_dir: Path to openspec/changes/archive/.
        existing_index: If provided, skip already-indexed changes.

    Returns:
        ArchiveIndex with entries for all changes.
    """
    if not archive_dir.exists():
        logger.warning("Archive directory not found: %s", archive_dir)
        return existing_index or ArchiveIndex()

    already_indexed = existing_index.indexed_ids if existing_index else set()
    entries = list(existing_index.entries) if existing_index else []

    change_dirs = sorted(
        d for d in archive_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    new_count = 0
    for change_dir in change_dirs:
        change_id = change_dir.name
        if change_id in already_indexed:
            continue

        entry = _index_single_change(change_dir)
        if entry:
            entries.append(entry)
            new_count += 1

    if new_count > 0:
        logger.info("Indexed %d new archived changes", new_count)

    return ArchiveIndex(entries=entries)


def write_archive_index(index: ArchiveIndex, path: Path) -> None:
    """Write archive index as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(index.to_dict(), f, indent=2)


def load_archive_index(path: Path) -> ArchiveIndex:
    """Load existing archive index from JSON."""
    if not path.exists():
        return ArchiveIndex()

    with open(path) as f:
        data = json.load(f)

    entries = []
    for e_data in data.get("entries", []):
        entries.append(
            ArchiveEntry(
                change_id=e_data["change_id"],
                title=e_data.get("title", ""),
                artifacts_present=e_data.get("artifacts_present", []),
                artifacts_absent=e_data.get("artifacts_absent", []),
                spec_capabilities=e_data.get("spec_capabilities", []),
                task_count=e_data.get("task_count", 0),
                requirement_count=e_data.get("requirement_count", 0),
                has_validation=e_data.get("has_validation", False),
                has_process_analysis=e_data.get("has_process_analysis", False),
                has_session_log=e_data.get("has_session_log", False),
                metadata=e_data.get("metadata", {}),
            )
        )

    return ArchiveIndex(
        version=data.get("version", 1),
        entries=entries,
    )


def _index_single_change(change_dir: Path) -> ArchiveEntry | None:
    """Index a single archived change directory."""
    change_id = change_dir.name

    present: list[str] = []
    absent: list[str] = []
    for artifact in KNOWN_ARTIFACTS:
        if (change_dir / artifact).exists():
            present.append(artifact)
        else:
            absent.append(artifact)

    # Extract title from proposal.md
    title = ""
    proposal_path = change_dir / "proposal.md"
    if proposal_path.exists():
        try:
            first_line = proposal_path.read_text().split("\n", 1)[0]
            title_match = re.match(r"#\s+(?:Proposal:\s+)?(.+)", first_line)
            if title_match:
                title = title_match.group(1).strip()
        except Exception as e:
            logger.warning("Failed to read proposal for %s: %s", change_id, e)

    # Count tasks
    task_count = 0
    tasks_path = change_dir / "tasks.md"
    if tasks_path.exists():
        try:
            content = tasks_path.read_text()
            task_count = len(re.findall(r"- \[.\]", content))
        except Exception:
            pass

    # Count spec requirements
    requirement_count = 0
    specs_dir = change_dir / "specs"
    spec_capabilities: list[str] = []
    if specs_dir.is_dir():
        for spec_dir in sorted(specs_dir.iterdir()):
            if spec_dir.is_dir():
                spec_capabilities.append(spec_dir.name)
                spec_file = spec_dir / "spec.md"
                if spec_file.exists():
                    try:
                        content = spec_file.read_text()
                        requirement_count += len(
                            re.findall(r"###\s+Requirement:", content)
                        )
                    except Exception:
                        pass

    return ArchiveEntry(
        change_id=change_id,
        title=title,
        artifacts_present=present,
        artifacts_absent=absent,
        spec_capabilities=spec_capabilities,
        task_count=task_count,
        requirement_count=requirement_count,
        has_validation="validation-report.md" in present,
        has_process_analysis="process-analysis.md" in present or "process-analysis.json" in present,
        has_session_log="session-log.md" in present,
    )
