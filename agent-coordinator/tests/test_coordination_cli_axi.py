"""Tests for the AXI-aligned list output helpers in coordination_cli.

These cover the agent-ergonomics contract added per the AXI design principles:
definitive empty states (``count``), explicit truncation markers
(``truncated`` + ``hint``), and contextual disclosure (``next_steps``). The
helpers are pure output functions — no database is required.
"""

from __future__ import annotations

import json

from src.coordination_cli import _emit_list, _probe_truncation


def _capture(capsys) -> dict:
    """Read captured stdout and parse it as the JSON envelope."""
    out = capsys.readouterr().out
    return json.loads(out)


class TestEmitListEnvelope:
    def test_non_empty_list_wraps_in_envelope(self, capsys):
        items = [{"feature_id": "a"}, {"feature_id": "b"}]
        _emit_list(items, json_mode=True)
        env = _capture(capsys)
        assert env["count"] == 2
        assert env["truncated"] is False
        assert env["items"] == items

    def test_empty_list_is_definitive(self, capsys):
        """A definitive empty state — count 0 — not an ambiguous bare ``[]``."""
        _emit_list([], json_mode=True)
        env = _capture(capsys)
        assert env["count"] == 0
        assert env["truncated"] is False
        assert env["items"] == []

    def test_next_steps_included_when_provided(self, capsys):
        _emit_list(
            [{"x": 1}],
            json_mode=True,
            next_steps=["coordination-cli feature show --feature-id <id>"],
        )
        env = _capture(capsys)
        assert env["next_steps"] == [
            "coordination-cli feature show --feature-id <id>"
        ]

    def test_next_steps_omitted_when_absent(self, capsys):
        _emit_list([{"x": 1}], json_mode=True)
        env = _capture(capsys)
        assert "next_steps" not in env

    def test_truncated_adds_hint(self, capsys):
        items = [{"i": n} for n in range(5)]
        _emit_list(items, json_mode=True, limit=5, truncated=True)
        env = _capture(capsys)
        assert env["truncated"] is True
        assert "hint" in env
        assert "--limit" in env["hint"]

    def test_not_truncated_has_no_hint(self, capsys):
        _emit_list([{"i": 1}], json_mode=True, limit=5, truncated=False)
        env = _capture(capsys)
        assert "hint" not in env

    def test_human_readable_renders_count_and_steps(self, capsys):
        _emit_list(
            [{"feature_id": "a"}],
            json_mode=False,
            next_steps=["do the next thing"],
        )
        out = capsys.readouterr().out
        assert "1 result(s)" in out
        assert "next steps:" in out
        assert "do the next thing" in out


class TestProbeTruncation:
    def test_detects_truncation_when_over_limit(self):
        # Caller fetched limit+1 (=4) rows for a limit of 3.
        rows = [1, 2, 3, 4]
        trimmed, truncated = _probe_truncation(rows, 3)
        assert truncated is True
        assert trimmed == [1, 2, 3]

    def test_exact_limit_is_not_truncated(self):
        # Exactly ``limit`` rows exist — the +1 sentinel was never returned.
        rows = [1, 2, 3]
        trimmed, truncated = _probe_truncation(rows, 3)
        assert truncated is False
        assert trimmed == [1, 2, 3]

    def test_under_limit_is_not_truncated(self):
        rows = [1, 2]
        trimmed, truncated = _probe_truncation(rows, 3)
        assert truncated is False
        assert trimmed == [1, 2]
