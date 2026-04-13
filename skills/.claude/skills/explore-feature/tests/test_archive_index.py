"""Tests for archive normalization, exemplar scoring, and scenario-seed extraction.

Covers spec scenarios:
- software-factory-tooling.1.1: Archive miner indexes completed change
- software-factory-tooling.1.2: Missing optional artifact does not fail indexing
- software-factory-tooling.1.3: Index preserves change-level references
- software-factory-tooling.1.4: Incremental indexing skips already-indexed changes
- software-factory-tooling.2.1: Scenario seed extracted from archived change
- software-factory-tooling.2.2: Repair pattern extracted from rework history
- software-factory-tooling.2.3: Low-signal exemplar is demoted

Design decisions: D5 (process analysis), D6 (deterministic normalization)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from archive_index import (
    ArchiveEntry,
    ArchiveIndex,
    index_archive,
    load_archive_index,
    write_archive_index,
)
from exemplar_registry import (
    ExemplarRegistry,
    extract_exemplars,
    load_exemplar_registry,
    write_exemplar_registry,
)

# ── Archive helpers ─────────────────────────────────────────────��─


def _create_archived_change(
    archive_dir: Path,
    change_id: str,
    *,
    with_proposal: bool = True,
    with_tasks: bool = True,
    with_validation: bool = False,
    with_session_log: bool = False,
    with_process_analysis: bool = False,
    with_specs: list[str] | None = None,
    task_count: int = 3,
) -> Path:
    """Helper to create a mock archived change directory."""
    change_dir = archive_dir / change_id
    change_dir.mkdir(parents=True, exist_ok=True)

    if with_proposal:
        (change_dir / "proposal.md").write_text(
            f"# Proposal: {change_id.replace('-', ' ').title()}\n\n"
            f"**Change ID**: `{change_id}`\n"
        )

    if with_tasks:
        tasks = "\n".join(f"- [x] Task {i}" for i in range(1, task_count + 1))
        (change_dir / "tasks.md").write_text(f"# Tasks\n\n{tasks}\n")

    if with_validation:
        (change_dir / "validation-report.md").write_text("## Smoke Tests\n\n**Status**: pass\n")

    if with_session_log:
        (change_dir / "session-log.md").write_text("## Phase: Implementation\n")

    if with_process_analysis:
        (change_dir / "process-analysis.md").write_text("# Process Analysis\n")
        (change_dir / "process-analysis.json").write_text('{"change_id": "' + change_id + '"}')

    if with_specs:
        specs_dir = change_dir / "specs"
        for cap in with_specs:
            cap_dir = specs_dir / cap
            cap_dir.mkdir(parents=True, exist_ok=True)
            (cap_dir / "spec.md").write_text(
                f"### Requirement: {cap} Feature\n\n"
                f"#### Scenario: {cap} works\n"
            )

    return change_dir


# ── Archive indexing ──────────────────────────────────────────────


class TestArchiveIndexing:
    """Test archive miner indexing."""

    def test_indexes_completed_change(self, tmp_path: Path) -> None:
        """software-factory-tooling.1.1: Index completed change."""
        archive_dir = tmp_path / "archive"
        _create_archived_change(
            archive_dir,
            "test-change-1",
            with_specs=["gen-eval-framework"],
            with_validation=True,
            with_session_log=True,
        )

        index = index_archive(archive_dir)
        assert len(index.entries) == 1
        assert index.entries[0].change_id == "test-change-1"
        assert index.entries[0].has_validation is True
        assert "gen-eval-framework" in index.entries[0].spec_capabilities

    def test_missing_artifact_does_not_fail(self, tmp_path: Path) -> None:
        """software-factory-tooling.1.2: Missing artifact doesn't fail."""
        archive_dir = tmp_path / "archive"
        _create_archived_change(
            archive_dir,
            "minimal-change",
            with_proposal=True,
            with_tasks=False,
            with_validation=False,
        )

        index = index_archive(archive_dir)
        assert len(index.entries) == 1
        assert "tasks.md" in index.entries[0].artifacts_absent

    def test_preserves_change_references(self, tmp_path: Path) -> None:
        """software-factory-tooling.1.3: Preserves change-level refs."""
        archive_dir = tmp_path / "archive"
        _create_archived_change(
            archive_dir,
            "referenced-change",
            with_specs=["skill-workflow", "gen-eval-framework"],
            task_count=5,
        )

        index = index_archive(archive_dir)
        entry = index.entries[0]
        assert entry.change_id == "referenced-change"
        assert len(entry.spec_capabilities) == 2
        assert entry.task_count == 5

    def test_incremental_indexing(self, tmp_path: Path) -> None:
        """software-factory-tooling.1.4: Incremental skips already-indexed."""
        archive_dir = tmp_path / "archive"
        _create_archived_change(archive_dir, "old-change")
        _create_archived_change(archive_dir, "new-change")

        # First index
        index1 = index_archive(archive_dir)
        assert len(index1.entries) == 2

        # Add one more change
        _create_archived_change(archive_dir, "newer-change")

        # Incremental index
        index2 = index_archive(archive_dir, existing_index=index1)
        assert len(index2.entries) == 3
        new_ids = {e.change_id for e in index2.entries}
        assert "newer-change" in new_ids

    def test_empty_archive(self, tmp_path: Path) -> None:
        index = index_archive(tmp_path / "nonexistent")
        assert len(index.entries) == 0

    def test_title_extraction(self, tmp_path: Path) -> None:
        archive_dir = tmp_path / "archive"
        _create_archived_change(archive_dir, "add-cool-feature")

        index = index_archive(archive_dir)
        assert "Add Cool Feature" in index.entries[0].title


# ── Archive index IO ────────────────────────────────────────────���─


class TestArchiveIndexIO:
    """Test archive index serialization."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        index = ArchiveIndex(
            entries=[
                ArchiveEntry(
                    change_id="test-1",
                    title="Test",
                    artifacts_present=["proposal.md"],
                    spec_capabilities=["gen-eval"],
                    task_count=3,
                )
            ]
        )
        path = tmp_path / "index.json"
        write_archive_index(index, path)

        loaded = load_archive_index(path)
        assert len(loaded.entries) == 1
        assert loaded.entries[0].change_id == "test-1"

    def test_load_missing(self, tmp_path: Path) -> None:
        loaded = load_archive_index(tmp_path / "missing.json")
        assert len(loaded.entries) == 0


# ── Exemplar extraction ──────────────────────────────────────────


class TestExemplarExtraction:
    """Test exemplar registry generation from archive index."""

    @pytest.fixture
    def rich_index(self) -> ArchiveIndex:
        return ArchiveIndex(
            entries=[
                ArchiveEntry(
                    change_id="validated-change",
                    title="Validated Feature",
                    artifacts_present=["proposal.md", "tasks.md", "validation-report.md", "session-log.md"],
                    spec_capabilities=["gen-eval-framework"],
                    task_count=8,
                    requirement_count=3,
                    has_validation=True,
                    has_session_log=True,
                ),
                ArchiveEntry(
                    change_id="minimal-change",
                    title="Quick Fix",
                    artifacts_present=["proposal.md"],
                    artifacts_absent=["tasks.md", "validation-report.md", "session-log.md"],
                    spec_capabilities=[],
                    task_count=1,
                    has_validation=False,
                ),
            ]
        )

    def test_scenario_seed_extracted(self, rich_index: ArchiveIndex) -> None:
        """software-factory-tooling.2.1: Scenario seed from archive."""
        registry = extract_exemplars(rich_index)
        seeds = registry.by_type("scenario_seed")
        assert len(seeds) >= 1
        assert any("gen-eval-framework" in s.tags for s in seeds)

    def test_repair_pattern_extracted(self, rich_index: ArchiveIndex) -> None:
        """software-factory-tooling.2.2: Repair pattern from rework."""
        registry = extract_exemplars(rich_index)
        repairs = registry.by_type("repair_pattern")
        assert len(repairs) >= 1
        assert repairs[0].source_change_id == "validated-change"

    def test_low_signal_exemplar_demoted(self, rich_index: ArchiveIndex) -> None:
        """software-factory-tooling.2.3: Low-signal demoted."""
        registry = extract_exemplars(rich_index)
        # Minimal change should have low confidence
        preferred = registry.preferred(min_confidence=0.5)
        minimal_preferred = [
            e for e in preferred if e.source_change_id == "minimal-change"
        ]
        assert len(minimal_preferred) == 0

    def test_implementation_pattern_for_complex_changes(self, rich_index: ArchiveIndex) -> None:
        registry = extract_exemplars(rich_index)
        impls = registry.by_type("implementation_pattern")
        assert len(impls) >= 1
        assert impls[0].source_change_id == "validated-change"

    def test_empty_index(self) -> None:
        registry = extract_exemplars(ArchiveIndex())
        assert len(registry.exemplars) == 0


# ── Exemplar registry IO ─────────────────────────────────────────


class TestExemplarRegistryIO:
    """Test exemplar registry serialization."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        from exemplar_registry import Exemplar

        registry = ExemplarRegistry(
            exemplars=[
                Exemplar(
                    exemplar_id="test-1",
                    type="scenario_seed",
                    source_change_id="change-1",
                    title="Test",
                    confidence=0.8,
                )
            ]
        )
        path = tmp_path / "exemplars.json"
        write_exemplar_registry(registry, path)

        loaded = load_exemplar_registry(path)
        assert len(loaded.exemplars) == 1
        assert loaded.exemplars[0].confidence == 0.8
