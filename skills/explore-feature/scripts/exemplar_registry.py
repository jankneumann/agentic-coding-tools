"""Exemplar registry derived from archive-intelligence index.

Extracts reusable exemplars from archived changes: scenario seeds,
repair patterns, DTU edge cases, and implementation patterns.
Exposes confidence metadata so downstream tools prefer higher-signal
exemplars.

Design Decision D6: Uses deterministic normalization before any
advanced retrieval or embedding-based ranking.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from .archive_index import ArchiveEntry, ArchiveIndex
except ImportError:
    from archive_index import ArchiveEntry, ArchiveIndex  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# Minimum artifacts for an exemplar to be considered high-signal
HIGH_SIGNAL_ARTIFACTS = {"proposal.md", "tasks.md", "validation-report.md"}


@dataclass
class Exemplar:
    """A reusable exemplar extracted from an archived change."""

    exemplar_id: str
    type: str  # scenario_seed, repair_pattern, dtu_edge_case, implementation_pattern
    source_change_id: str
    title: str = ""
    description: str = ""
    confidence: float = 0.0  # 0.0 to 1.0
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exemplar_id": self.exemplar_id,
            "type": self.type,
            "source_change_id": self.source_change_id,
            "title": self.title,
            "description": self.description,
            "confidence": self.confidence,
            "tags": self.tags,
            "metadata": self.metadata,
        }


@dataclass
class ExemplarRegistry:
    """Collection of reusable exemplars from archived changes."""

    version: int = 1
    exemplars: list[Exemplar] = field(default_factory=list)

    def by_type(self, exemplar_type: str) -> list[Exemplar]:
        return [e for e in self.exemplars if e.type == exemplar_type]

    def preferred(self, min_confidence: float = 0.5) -> list[Exemplar]:
        return [e for e in self.exemplars if e.confidence >= min_confidence]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "total_exemplars": len(self.exemplars),
            "by_type": {
                t: len(self.by_type(t))
                for t in {"scenario_seed", "repair_pattern", "dtu_edge_case", "implementation_pattern"}
            },
            "exemplars": [e.to_dict() for e in self.exemplars],
        }


def extract_exemplars(index: ArchiveIndex) -> ExemplarRegistry:
    """Extract exemplars from an archive index.

    Processes each indexed change to derive scenario seeds,
    repair patterns, and implementation patterns.

    Args:
        index: Archive-intelligence index to mine.

    Returns:
        ExemplarRegistry with extracted exemplars.
    """
    exemplars: list[Exemplar] = []

    for entry in index.entries:
        confidence = _compute_confidence(entry)

        # Scenario seed: every archived change with specs is a seed source
        if entry.spec_capabilities:
            for cap in entry.spec_capabilities:
                exemplars.append(
                    Exemplar(
                        exemplar_id=f"seed-{entry.change_id}-{cap}",
                        type="scenario_seed",
                        source_change_id=entry.change_id,
                        title=f"Scenarios from {cap} ({entry.title})",
                        description=f"Spec capability {cap} from archived change {entry.change_id}",
                        confidence=confidence,
                        tags=[cap, "archived"],
                        metadata={"capability": cap, "requirement_count": entry.requirement_count},
                    )
                )

        # Repair pattern: changes with validation AND session log suggest rework happened
        if entry.has_validation and entry.has_session_log:
            exemplars.append(
                Exemplar(
                    exemplar_id=f"repair-{entry.change_id}",
                    type="repair_pattern",
                    source_change_id=entry.change_id,
                    title=f"Repair pattern from {entry.title}",
                    description=f"Change went through validation and iteration ({entry.task_count} tasks)",
                    confidence=confidence,
                    tags=["validated", "iterated"],
                    metadata={"task_count": entry.task_count},
                )
            )

        # Implementation pattern: changes with many tasks and complete artifacts
        if entry.task_count >= 5 and len(entry.artifacts_present) >= 4:
            exemplars.append(
                Exemplar(
                    exemplar_id=f"impl-{entry.change_id}",
                    type="implementation_pattern",
                    source_change_id=entry.change_id,
                    title=f"Implementation exemplar: {entry.title}",
                    description=f"Complex change with {entry.task_count} tasks and {len(entry.artifacts_present)} artifacts",
                    confidence=confidence,
                    tags=["complex", "complete"],
                    metadata={
                        "task_count": entry.task_count,
                        "artifact_count": len(entry.artifacts_present),
                    },
                )
            )

    return ExemplarRegistry(exemplars=exemplars)


def write_exemplar_registry(registry: ExemplarRegistry, path: Path) -> None:
    """Write exemplar registry as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(registry.to_dict(), f, indent=2)


def load_exemplar_registry(path: Path) -> ExemplarRegistry:
    """Load exemplar registry from JSON."""
    if not path.exists():
        return ExemplarRegistry()

    with open(path) as f:
        data = json.load(f)

    exemplars = []
    for e_data in data.get("exemplars", []):
        exemplars.append(
            Exemplar(
                exemplar_id=e_data["exemplar_id"],
                type=e_data["type"],
                source_change_id=e_data["source_change_id"],
                title=e_data.get("title", ""),
                description=e_data.get("description", ""),
                confidence=e_data.get("confidence", 0.0),
                tags=e_data.get("tags", []),
                metadata=e_data.get("metadata", {}),
            )
        )

    return ExemplarRegistry(
        version=data.get("version", 1),
        exemplars=exemplars,
    )


def _compute_confidence(entry: ArchiveEntry) -> float:
    """Compute exemplar confidence from artifact completeness."""
    present_set = set(entry.artifacts_present)

    # High-signal artifacts contribute most
    high_signal_count = len(HIGH_SIGNAL_ARTIFACTS & present_set)
    high_signal_ratio = high_signal_count / len(HIGH_SIGNAL_ARTIFACTS)

    # Total artifact coverage
    total_coverage = len(entry.artifacts_present) / max(
        len(entry.artifacts_present) + len(entry.artifacts_absent), 1
    )

    # Weighted score: 60% high-signal, 40% total coverage
    score = 0.6 * high_signal_ratio + 0.4 * total_coverage

    return round(score, 3)
