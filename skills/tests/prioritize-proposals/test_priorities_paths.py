"""Tests for priorities_paths.py — run-id and path construction."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills" / "prioritize-proposals" / "scripts"))

from priorities_paths import (  # noqa: E402
    build_paths,
    build_run_id,
    parse_run_id,
)


class TestBuildRunId:
    def test_combines_utc_date_time_and_short_sha(self):
        now = datetime(2026, 6, 10, 14, 30, 52, tzinfo=timezone.utc)
        head_sha = "a93fe59a8b1c2d3e4f5"
        assert build_run_id(now, head_sha) == "2026-06-10-143052-a93fe59"

    def test_uses_first_7_chars_of_sha(self):
        now = datetime(2026, 6, 10, 14, 30, 52, tzinfo=timezone.utc)
        head_sha = "abcdef1234567890"
        assert build_run_id(now, head_sha) == "2026-06-10-143052-abcdef1"

    def test_pads_single_digit_time_components(self):
        now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        head_sha = "0000000abc"
        assert build_run_id(now, head_sha) == "2026-01-02-030405-0000000"

    def test_requires_utc_timezone(self):
        # Naive datetime should raise — UTC is mandatory for stability.
        now_naive = datetime(2026, 6, 10, 14, 30, 52)
        head_sha = "a93fe59"
        try:
            build_run_id(now_naive, head_sha)
        except ValueError as e:
            assert "UTC" in str(e) or "timezone" in str(e)
        else:
            raise AssertionError("expected ValueError for naive datetime")

    def test_rejects_short_sha(self):
        now = datetime(2026, 6, 10, 14, 30, 52, tzinfo=timezone.utc)
        try:
            build_run_id(now, "abc")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for sha shorter than 7 chars")


class TestBuildPaths:
    def test_returns_named_paths_for_run_id(self):
        base = Path("/tmp/repo/openspec/priorities")
        run_id = "2026-06-10-143052-a93fe59"
        result = build_paths(base, run_id)
        assert result.dated_dir == base / run_id
        assert result.report_md == base / run_id / "report.md"
        assert result.report_json == base / run_id / "report.json"
        assert result.latest_md == base / "latest.md"
        assert result.latest_json == base / "latest.json"
        assert result.archive_dir == base / "archive"

    def test_archive_destination_preserves_run_id(self):
        base = Path("/tmp/repo/openspec/priorities")
        run_id = "2026-06-10-143052-a93fe59"
        result = build_paths(base, run_id)
        assert result.archive_destination == base / "archive" / run_id


class TestParseRunId:
    def test_extracts_components(self):
        date, hms, sha = parse_run_id("2026-06-10-143052-a93fe59")
        assert date == "2026-06-10"
        assert hms == "143052"
        assert sha == "a93fe59"

    def test_handles_legacy_suffix(self):
        # Legacy directory uses a non-standard suffix; parse should still succeed.
        date, hms, sha = parse_run_id("2026-05-04-legacy")
        assert date == "2026-05-04"
        # legacy directories don't have HHMMSS or sha — both return ""
        assert hms == ""
        assert sha == "legacy"

    def test_rejects_non_dated_name(self):
        try:
            parse_run_id("not-a-priorities-run")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for non-dated directory name")
