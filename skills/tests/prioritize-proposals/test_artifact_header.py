"""Tests for artifact_header.py — mandatory codeviz-aligned header."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills" / "prioritize-proposals" / "scripts"))

from artifact_header import GENERATOR, SCHEMA_VERSION, make_header, wrap_report  # noqa: E402


class TestMakeHeader:
    def test_all_six_required_fields_present(self):
        now = datetime(2026, 6, 10, 14, 30, 52, tzinfo=timezone.utc)
        header = make_header(
            now=now,
            git_sha="a93fe59a8b1c2d3e4f5060708090a0b0c0d0e0f0",
            run_id="2026-06-10-143052-a93fe59",
        )
        for field in (
            "schema_version",
            "generated_at",
            "git_sha",
            "generator",
            "run_id",
            "event_kind",
        ):
            assert field in header, f"missing required field: {field}"

    def test_schema_version_is_integer_one(self):
        header = make_header(
            now=datetime(2026, 6, 10, tzinfo=timezone.utc),
            git_sha="a" * 40,
            run_id="2026-06-10-000000-aaaaaaa",
        )
        assert header["schema_version"] == SCHEMA_VERSION == 1

    def test_generated_at_is_iso8601_utc(self):
        now = datetime(2026, 6, 10, 14, 30, 52, tzinfo=timezone.utc)
        header = make_header(
            now=now,
            git_sha="a" * 40,
            run_id="2026-06-10-143052-aaaaaaa",
        )
        assert header["generated_at"] == "2026-06-10T14:30:52Z"
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", header["generated_at"])

    def test_git_sha_is_full_40_chars(self):
        header = make_header(
            now=datetime(2026, 6, 10, tzinfo=timezone.utc),
            git_sha="a93fe59a8b1c2d3e4f5060708090a0b0c0d0e0f0",
            run_id="2026-06-10-000000-a93fe59",
        )
        assert len(header["git_sha"]) == 40
        assert header["git_sha"] == "a93fe59a8b1c2d3e4f5060708090a0b0c0d0e0f0"

    def test_generator_format(self):
        header = make_header(
            now=datetime(2026, 6, 10, tzinfo=timezone.utc),
            git_sha="a" * 40,
            run_id="2026-06-10-000000-aaaaaaa",
        )
        assert header["generator"] == GENERATOR
        assert header["generator"].startswith("prioritize-proposals@")

    def test_event_kind_constant(self):
        header = make_header(
            now=datetime(2026, 6, 10, tzinfo=timezone.utc),
            git_sha="a" * 40,
            run_id="2026-06-10-000000-aaaaaaa",
        )
        assert header["event_kind"] == "priorities-report"

    def test_rejects_short_git_sha(self):
        try:
            make_header(
                now=datetime(2026, 6, 10, tzinfo=timezone.utc),
                git_sha="abc",
                run_id="2026-06-10-000000-aaaaaaa",
            )
        except ValueError as e:
            assert "40" in str(e)
        else:
            raise AssertionError("expected ValueError for short SHA")

    def test_rejects_naive_datetime(self):
        try:
            make_header(
                now=datetime(2026, 6, 10),
                git_sha="a" * 40,
                run_id="2026-06-10-000000-aaaaaaa",
            )
        except ValueError as e:
            assert "UTC" in str(e) or "timezone" in str(e)
        else:
            raise AssertionError("expected ValueError for naive datetime")


class TestWrapReport:
    def test_wraps_existing_dict_under_report_key(self):
        body = {"top_recommendation": "execute-foo", "items": []}
        header = make_header(
            now=datetime(2026, 6, 10, tzinfo=timezone.utc),
            git_sha="a" * 40,
            run_id="2026-06-10-000000-aaaaaaa",
        )
        wrapped = wrap_report(header, body)
        assert wrapped["_header"] == header
        assert wrapped["report"] == body

    def test_does_not_mutate_body(self):
        body = {"top_recommendation": "execute-foo"}
        header = make_header(
            now=datetime(2026, 6, 10, tzinfo=timezone.utc),
            git_sha="a" * 40,
            run_id="2026-06-10-000000-aaaaaaa",
        )
        wrap_report(header, body)
        assert body == {"top_recommendation": "execute-foo"}
        assert "_header" not in body
