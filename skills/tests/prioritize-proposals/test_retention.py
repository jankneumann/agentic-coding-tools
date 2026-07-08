"""Tests for retention.py — archive-not-delete retention scan."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills" / "prioritize-proposals" / "scripts"))

from retention import apply_retention, list_active_runs  # noqa: E402


def _make_run(base: Path, run_id: str, body: str = "x") -> Path:
    d = base / run_id
    d.mkdir(parents=True)
    (d / "report.md").write_text(body)
    return d


@pytest.fixture
def priorities_dir(tmp_path: Path) -> Path:
    p = tmp_path / "priorities"
    p.mkdir()
    return p


class TestListActiveRuns:
    def test_returns_dated_dirs_only(self, priorities_dir: Path):
        _make_run(priorities_dir, "2026-06-10-100000-aaaaaaa")
        _make_run(priorities_dir, "2026-06-09-120000-bbbbbbb")
        (priorities_dir / "latest.md").write_text("hi")
        (priorities_dir / "latest.json").write_text("{}")
        (priorities_dir / "archive").mkdir()
        _make_run(priorities_dir / "archive", "2025-01-01-000000-ccccccc")
        active = list_active_runs(priorities_dir)
        names = {p.name for p in active}
        assert names == {"2026-06-10-100000-aaaaaaa", "2026-06-09-120000-bbbbbbb"}

    def test_returns_chronological_order(self, priorities_dir: Path):
        _make_run(priorities_dir, "2026-06-10-100000-aaaaaaa")
        _make_run(priorities_dir, "2026-06-08-090000-ccccccc")
        _make_run(priorities_dir, "2026-06-09-120000-bbbbbbb")
        active = list_active_runs(priorities_dir)
        names = [p.name for p in active]
        assert names == [
            "2026-06-08-090000-ccccccc",
            "2026-06-09-120000-bbbbbbb",
            "2026-06-10-100000-aaaaaaa",
        ]

    def test_includes_legacy_entry(self, priorities_dir: Path):
        _make_run(priorities_dir, "2026-05-04-legacy")
        _make_run(priorities_dir, "2026-06-10-100000-aaaaaaa")
        active = list_active_runs(priorities_dir)
        names = [p.name for p in active]
        # legacy sorts before HHMMSS-keyed entries on the same day; here different day:
        assert "2026-05-04-legacy" in names
        assert "2026-06-10-100000-aaaaaaa" in names


class TestApplyRetention:
    def test_keeps_30_by_default(self, priorities_dir: Path):
        # Make 31 entries on distinct timestamps
        for i in range(31):
            _make_run(priorities_dir, f"2026-06-10-{i:06d}-aaaaaaa")
        result = apply_retention(priorities_dir, retain=30)
        active = list_active_runs(priorities_dir)
        assert len(active) == 30
        # The oldest (000000) was archived
        archived = list((priorities_dir / "archive").iterdir())
        assert len(archived) == 1
        assert archived[0].name == "2026-06-10-000000-aaaaaaa"
        assert result.archived_count == 1
        assert result.active_count == 30

    def test_custom_retain_5(self, priorities_dir: Path):
        for i in range(11):
            _make_run(priorities_dir, f"2026-06-10-{i:06d}-aaaaaaa")
        result = apply_retention(priorities_dir, retain=5)
        active = list_active_runs(priorities_dir)
        assert len(active) == 5
        archived = list((priorities_dir / "archive").iterdir())
        assert len(archived) == 6
        assert result.archived_count == 6

    def test_archive_accumulates_across_calls(self, priorities_dir: Path):
        # First call: 4 entries archived
        for i in range(7):
            _make_run(priorities_dir, f"2026-06-10-{i:06d}-aaaaaaa")
        apply_retention(priorities_dir, retain=3)
        assert len(list((priorities_dir / "archive").iterdir())) == 4

        # Second call: 3 more entries archived; archive preserves the previous 4
        for i in range(7, 12):
            _make_run(priorities_dir, f"2026-06-11-{i:06d}-bbbbbbb")
        apply_retention(priorities_dir, retain=3)
        archived = list((priorities_dir / "archive").iterdir())
        assert len(archived) == 4 + 5

    def test_archive_never_deletes(self, priorities_dir: Path):
        # Make a long-existing archive entry
        archive = priorities_dir / "archive"
        archive.mkdir()
        old_archived = archive / "2024-01-01-000000-deadbee"
        old_archived.mkdir()
        (old_archived / "report.md").write_text("ancient")
        # Run retention with normal active entries
        for i in range(5):
            _make_run(priorities_dir, f"2026-06-10-{i:06d}-aaaaaaa")
        apply_retention(priorities_dir, retain=3)
        # The ancient archived entry must still exist
        assert old_archived.exists()
        assert (old_archived / "report.md").read_text() == "ancient"

    def test_archive_subdir_excluded_from_active_count(self, priorities_dir: Path):
        archive = priorities_dir / "archive"
        archive.mkdir()
        for i in range(50):
            _make_run(archive, f"2025-01-01-{i:06d}-archive")
        for i in range(3):
            _make_run(priorities_dir, f"2026-06-10-{i:06d}-aaaaaaa")
        result = apply_retention(priorities_dir, retain=30)
        # Only 3 active entries — well under retain=30, so nothing archived
        assert result.archived_count == 0
        assert result.active_count == 3

    def test_no_op_when_under_threshold(self, priorities_dir: Path):
        for i in range(5):
            _make_run(priorities_dir, f"2026-06-10-{i:06d}-aaaaaaa")
        result = apply_retention(priorities_dir, retain=30)
        assert result.archived_count == 0
        assert result.active_count == 5

    def test_rejects_zero_or_negative_retain(self, priorities_dir: Path):
        with pytest.raises(ValueError):
            apply_retention(priorities_dir, retain=0)
        with pytest.raises(ValueError):
            apply_retention(priorities_dir, retain=-1)
