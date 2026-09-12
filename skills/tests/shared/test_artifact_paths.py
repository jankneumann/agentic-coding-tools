"""Tests for skills/shared/artifact_paths.py — the run-id format and
archive-not-delete retention shared by `prioritize-proposals` and
`audit-choices` (design D2, D3).

Imported with the skills root on `sys.path`, matching how every real
caller reaches the package (D2's import bootstrap).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills"))

from shared.artifact_paths import (  # noqa: E402
    ARCHIVE_DIRNAME,
    DEFAULT_RETAIN,
    RUN_ID_RE,
    RetentionResult,
    apply_retention,
    build_run_id,
    list_active_runs,
    parse_run_id,
)


class TestBuildRunId:
    def test_combines_utc_date_time_and_short_sha(self):
        now = datetime(2026, 6, 10, 14, 30, 52, tzinfo=timezone.utc)
        head_sha = "a93fe59a8b1c2d3e4f5"
        assert build_run_id(now, head_sha) == "2026-06-10-143052-a93fe59"

    def test_requires_utc_timezone(self):
        now_naive = datetime(2026, 6, 10, 14, 30, 52)
        with pytest.raises(ValueError):
            build_run_id(now_naive, "a93fe59")

    def test_rejects_short_sha(self):
        now = datetime(2026, 6, 10, 14, 30, 52, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            build_run_id(now, "abc")


class TestParseRunId:
    def test_round_trips_through_build_run_id(self):
        now = datetime(2026, 9, 12, 3, 0, 0, tzinfo=timezone.utc)
        run_id = build_run_id(now, "abc1234567")
        assert parse_run_id(run_id) == ("2026-09-12", "030000", "abc1234")

    def test_handles_legacy_suffix(self):
        assert parse_run_id("2026-05-04-legacy") == ("2026-05-04", "", "legacy")

    def test_collision_suffixed_id_parses_and_returns_its_suffix(self):
        # The un-extended regex rejects this, which would make
        # list_active_runs skip exactly the directories D8's collision
        # guard creates and let the standalone-audit tree grow unbounded
        # while the bounding scenario still passed.
        result = parse_run_id("2026-09-12-030000-abc1234-2")
        assert result[:3] == ("2026-09-12", "030000", "abc1234")
        assert result[3] == "2"

    def test_bare_date_returns_empty_middle_and_sha(self):
        assert parse_run_id("2026-06-10") == ("2026-06-10", "", "")

    def test_rejects_non_dated_name(self):
        with pytest.raises(ValueError):
            parse_run_id("not-a-run-id")


class TestRunIdRe:
    def test_matches_collision_suffixed_id(self):
        assert RUN_ID_RE.match("2026-09-12-030000-abc1234-2")

    def test_rejects_garbage(self):
        assert RUN_ID_RE.match("garbage") is None


def _make_run(base: Path, run_id: str, body: str = "x") -> Path:
    d = base / run_id
    d.mkdir(parents=True)
    (d / "report.md").write_text(body)
    return d


class TestApplyRetention:
    def test_default_retain_is_30(self):
        assert DEFAULT_RETAIN == 30

    def test_archive_dirname(self):
        assert ARCHIVE_DIRNAME == "archive"

    def test_archives_oldest_rather_than_deleting(self, tmp_path: Path):
        base = tmp_path / "runs"
        base.mkdir()
        for i in range(31):
            _make_run(base, f"2026-06-{i + 1:02d}-100000-{i:07x}")
        result = apply_retention(base, retain=30)
        assert isinstance(result, RetentionResult)
        assert result.archived_count == 1
        assert result.active_count == 30
        archived = list((base / ARCHIVE_DIRNAME).iterdir())
        assert len(archived) == 1
        assert archived[0].name == "2026-06-01-100000-0000000"
        # Moved, not deleted.
        assert not (base / "2026-06-01-100000-0000000").exists()

    def test_rejects_retain_below_one(self, tmp_path: Path):
        base = tmp_path / "runs"
        base.mkdir()
        with pytest.raises(ValueError):
            apply_retention(base, retain=0)
        with pytest.raises(ValueError):
            apply_retention(base, retain=-1)

    def test_under_limit_is_untouched(self, tmp_path: Path):
        base = tmp_path / "runs"
        base.mkdir()
        for i in range(5):
            _make_run(base, f"2026-06-{i + 1:02d}-100000-{i:07x}")
        result = apply_retention(base, retain=30)
        assert result.archived_count == 0
        assert result.active_count == 5
        assert not (base / ARCHIVE_DIRNAME).exists()

    def test_list_active_runs_skips_archive_and_non_run_names(self, tmp_path: Path):
        base = tmp_path / "runs"
        base.mkdir()
        _make_run(base, "2026-06-10-100000-aaaaaaa")
        (base / "latest.md").write_text("hi")
        (base / "latest.json").write_text("{}")
        (base / ARCHIVE_DIRNAME).mkdir()
        _make_run(base / ARCHIVE_DIRNAME, "2025-01-01-000000-ccccccc")
        active = list_active_runs(base)
        names = {p.name for p in active}
        assert names == {"2026-06-10-100000-aaaaaaa"}

    def test_list_active_runs_missing_base_returns_empty(self, tmp_path: Path):
        assert list_active_runs(tmp_path / "does-not-exist") == []
