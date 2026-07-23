"""Tests for the Pi CLI transcript adapter.

Pi's --mode json output is an NDJSON event stream (E8). The adapter
materializes terminal message events (message_end) into NormalizedEvents and
ignores the streaming message_start/message_update deltas.

Covers:
- Session discovery from fixture NDJSON files
- Event-stream parsing of session/message_end records
- Correct mapping of user, assistant, tool events
- thinking blocks captured; streaming deltas not double-counted
- Model capture (moonshotai/kimi-k3)
- Fail-soft when source path missing
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "pi_cli"
sys.path.insert(0, str(SCRIPTS_DIR))

_FIXTURE = "session-2026-05-01T10-00-pi0001.ndjson"


def _seed(tmp_path: Path) -> Path:
    (tmp_path / _FIXTURE).write_text((FIXTURES_DIR / _FIXTURE).read_text())
    return tmp_path


class TestPiCLIDiscovery:
    def test_discovers_sessions_from_fixture_dir(self, tmp_path: Path) -> None:
        from adapters.pi_cli import PiCLIAdapter

        _seed(tmp_path)
        adapter = PiCLIAdapter(base_dir=str(tmp_path))
        sessions = adapter.discover_sessions()
        assert len(sessions) >= 1
        assert sessions[0].harness == "pi_cli"
        assert sessions[0].session_id == "sess-pi-001"

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        from adapters.pi_cli import PiCLIAdapter

        adapter = PiCLIAdapter(base_dir=str(tmp_path / "nonexistent"))
        assert adapter.discover_sessions() == []


class TestPiCLINormalization:
    @pytest.fixture()
    def adapter(self, tmp_path: Path) -> "PiCLIAdapter":
        from adapters.pi_cli import PiCLIAdapter

        _seed(tmp_path)
        return PiCLIAdapter(base_dir=str(tmp_path))

    def test_normalizes_fixture_session(self, adapter: "PiCLIAdapter") -> None:
        assert adapter.normalize_session("sess-pi-001")

    def test_user_events_parsed(self, adapter: "PiCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-pi-001")
        assert [e for e in events if e.role == EventRole.USER]

    def test_assistant_events_parsed(self, adapter: "PiCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-pi-001")
        assert [e for e in events if e.role == EventRole.ASSISTANT]

    def test_tool_use_parsed(self, adapter: "PiCLIAdapter") -> None:
        from normalize import ContentType

        events = adapter.normalize_session("sess-pi-001")
        assert any(
            block.type == ContentType.TOOL_USE and block.tool_name
            for e in events
            for block in e.content
        )

    def test_tool_results_parsed(self, adapter: "PiCLIAdapter") -> None:
        from normalize import ContentType

        events = adapter.normalize_session("sess-pi-001")
        assert any(
            block.type == ContentType.TOOL_RESULT
            for e in events
            for block in e.content
        )

    def test_thinking_parsed(self, adapter: "PiCLIAdapter") -> None:
        from normalize import ContentType

        events = adapter.normalize_session("sess-pi-001")
        assert any(
            block.type == ContentType.THINKING
            for e in events
            for block in e.content
        )

    def test_streaming_deltas_not_double_counted(self, adapter: "PiCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-pi-001")
        # The fixture streams m-002 via message_start/update/end; only the
        # terminal message_end must be materialized once.
        assistant = [e for e in events if e.role == EventRole.ASSISTANT]
        assert len(assistant) == 2

    def test_harness_set_correctly(self, adapter: "PiCLIAdapter") -> None:
        events = adapter.normalize_session("sess-pi-001")
        assert events
        for event in events:
            assert event.harness == "pi_cli"

    def test_model_captured(self, adapter: "PiCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-pi-001")
        models = [e.model for e in events if e.role == EventRole.ASSISTANT and e.model]
        assert any("kimi" in m for m in models)

    def test_nonexistent_session_returns_empty(self, adapter: "PiCLIAdapter") -> None:
        assert adapter.normalize_session("nonexistent") == []
