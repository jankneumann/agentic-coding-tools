"""Tests for learning-log helpers with progressive disclosure."""

from __future__ import annotations

from pathlib import Path

import pytest
from learning import (
    COMPACTION_THRESHOLD,
    compact,
    needs_compaction,
    read_entry,
    read_index,
    select_relevant_entries,
    write_entry,
)
from models import LearningDecision, LearningEntry, LearningPhase


def _make_entry(item_id: str = "ri-01", **kwargs) -> LearningEntry:
    return LearningEntry(
        schema_version=1,
        item_id=item_id,
        timestamp="2026-04-13T00:00:00Z",
        decisions=[LearningDecision(title="Decision", outcome="Chose X over Y")],
        phase=LearningPhase.IMPLEMENTATION,
        **kwargs,
    )

class TestWriteEntry:
    def test_creates_file_and_index(self, tmp_path):
        entry = _make_entry()
        path = write_entry(tmp_path, entry)

        assert path.exists()
        assert (tmp_path / "learning-log.md").exists()
        assert "ri-01" in (tmp_path / "learning-log.md").read_text()

    def test_frontmatter_parseable(self, tmp_path):
        entry = _make_entry()
        write_entry(tmp_path, entry)
        data = read_entry(tmp_path, "ri-01")
        assert data is not None
        assert data["item_id"] == "ri-01"

    def test_updates_existing_index_entry(self, tmp_path):
        entry1 = _make_entry()
        write_entry(tmp_path, entry1)

        entry2 = _make_entry(recommendations=["Updated recommendation"])
        write_entry(tmp_path, entry2)

        index = (tmp_path / "learning-log.md").read_text()
        assert index.count("ri-01") == 1  # No duplicate

class TestReadEntry:
    def test_nonexistent(self, tmp_path):
        assert read_entry(tmp_path, "nonexistent") is None

    def test_round_trip(self, tmp_path):
        entry = _make_entry(recommendations=["Test recommendation"])
        write_entry(tmp_path, entry)
        data = read_entry(tmp_path, "ri-01")
        assert data is not None
        assert data["recommendations"] == ["Test recommendation"]

class TestReadIndex:
    def test_empty(self, tmp_path):
        assert read_index(tmp_path) == []

    def test_multiple_entries(self, tmp_path):
        for i in range(3):
            write_entry(tmp_path, _make_entry(f"ri-{i:02d}"))
        ids = read_index(tmp_path)
        assert len(ids) == 3

class TestSelectRelevantEntries:
    def test_loads_dependencies(self, tmp_path):
        for i in range(5):
            write_entry(tmp_path, _make_entry(f"ri-{i:02d}"))
        entries = select_relevant_entries(tmp_path, ["ri-00", "ri-01"], recency_window=2)
        item_ids = {e["item_id"] for e in entries}
        assert "ri-00" in item_ids
        assert "ri-01" in item_ids

    def test_loads_recent_entries(self, tmp_path):
        for i in range(5):
            write_entry(tmp_path, _make_entry(f"ri-{i:02d}"))
        entries = select_relevant_entries(tmp_path, [], recency_window=2)
        item_ids = {e["item_id"] for e in entries}
        assert "ri-03" in item_ids
        assert "ri-04" in item_ids

    def test_bounded_by_window(self, tmp_path):
        for i in range(10):
            write_entry(tmp_path, _make_entry(f"ri-{i:02d}"))
        entries = select_relevant_entries(tmp_path, ["ri-00"], recency_window=2)
        assert len(entries) <= 3  # 1 dep + 2 recent

class TestCompaction:
    def test_needs_compaction(self, tmp_path):
        assert not needs_compaction(tmp_path)
        for i in range(COMPACTION_THRESHOLD + 5):
            write_entry(tmp_path, _make_entry(f"ri-{i:03d}"))
        assert needs_compaction(tmp_path)

    def test_compact_archives(self, tmp_path):
        for i in range(COMPACTION_THRESHOLD + 5):
            write_entry(tmp_path, _make_entry(f"ri-{i:03d}"))

        active_ids = {f"ri-{COMPACTION_THRESHOLD + j:03d}" for j in range(5)}
        archived = compact(tmp_path, active_ids)

        assert archived > 0
        assert (tmp_path / "learnings" / "_archive.md").exists()
        # Active entries should still have files
        for item_id in active_ids:
            assert (tmp_path / "learnings" / f"{item_id}.md").exists()

    def test_compact_no_op_when_under_threshold(self, tmp_path):
        for i in range(5):
            write_entry(tmp_path, _make_entry(f"ri-{i:02d}"))
        assert compact(tmp_path, set()) == 0
