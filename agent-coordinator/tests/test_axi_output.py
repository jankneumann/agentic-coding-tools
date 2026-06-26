"""Tests for the shared AXI list-output helpers used by the CLI and HTTP API."""

from __future__ import annotations

from src.axi_output import list_envelope, probe_truncation, truncation_hint


class TestProbeTruncation:
    def test_detects_truncation_when_over_limit(self):
        # Caller fetched limit+1 (=4) rows for a limit of 3.
        trimmed, truncated = probe_truncation([1, 2, 3, 4], 3)
        assert truncated is True
        assert trimmed == [1, 2, 3]

    def test_exact_limit_is_not_truncated(self):
        trimmed, truncated = probe_truncation([1, 2, 3], 3)
        assert truncated is False
        assert trimmed == [1, 2, 3]

    def test_under_limit_is_not_truncated(self):
        trimmed, truncated = probe_truncation([1, 2], 3)
        assert truncated is False
        assert trimmed == [1, 2]


class TestTruncationHint:
    def test_hint_mentions_limit(self):
        assert "limit" in truncation_hint(5)


class TestListEnvelope:
    def test_preserves_named_key(self):
        """HTTP envelope keeps the named array key for backward compat."""
        env = list_envelope("features", [{"feature_id": "a"}])
        assert env["features"] == [{"feature_id": "a"}]
        assert env["count"] == 1
        assert env["truncated"] is False

    def test_empty_is_definitive(self):
        env = list_envelope("entries", [])
        assert env["count"] == 0
        assert env["entries"] == []
        assert env["truncated"] is False

    def test_truncated_adds_hint(self):
        env = list_envelope("entries", [1, 2, 3], limit=3, truncated=True)
        assert env["truncated"] is True
        assert "hint" in env
        assert "limit" in env["hint"]

    def test_not_truncated_has_no_hint(self):
        env = list_envelope("entries", [1, 2], limit=3, truncated=False)
        assert "hint" not in env

    def test_next_steps_included_when_provided(self):
        env = list_envelope(
            "features", [{"x": 1}], next_steps=["GET /features/{feature_id}"]
        )
        assert env["next_steps"] == ["GET /features/{feature_id}"]

    def test_next_steps_omitted_when_absent(self):
        env = list_envelope("features", [{"x": 1}])
        assert "next_steps" not in env
