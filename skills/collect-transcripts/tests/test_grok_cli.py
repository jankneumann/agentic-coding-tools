"""Tests for the Grok CLI transcript adapter.

Covers:
- Session discovery from fixture files
- JSONL parsing of metadata header + message records
- Correct mapping of user, assistant, tool events
- grok reasoning mapped to thinking blocks
- Model capture (grok-4.5)
- Fail-soft when source path missing
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "grok_cli"
sys.path.insert(0, str(SCRIPTS_DIR))

_FIXTURE = "session-2026-05-01T10-00-grok01.jsonl"


def _seed(tmp_path: Path) -> Path:
    (tmp_path / _FIXTURE).write_text((FIXTURES_DIR / _FIXTURE).read_text())
    return tmp_path


class TestGrokCLIDiscovery:
    def test_discovers_sessions_from_fixture_dir(self, tmp_path: Path) -> None:
        from adapters.grok_cli import GrokCLIAdapter

        _seed(tmp_path)
        adapter = GrokCLIAdapter(base_dir=str(tmp_path))
        sessions = adapter.discover_sessions()
        assert len(sessions) >= 1
        assert sessions[0].harness == "grok_cli"

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        from adapters.grok_cli import GrokCLIAdapter

        adapter = GrokCLIAdapter(base_dir=str(tmp_path / "nonexistent"))
        assert adapter.discover_sessions() == []


class TestGrokCLINormalization:
    @pytest.fixture()
    def adapter(self, tmp_path: Path) -> "GrokCLIAdapter":
        from adapters.grok_cli import GrokCLIAdapter

        _seed(tmp_path)
        return GrokCLIAdapter(base_dir=str(tmp_path))

    def test_normalizes_fixture_session(self, adapter: "GrokCLIAdapter") -> None:
        assert adapter.normalize_session("sess-grok-001")

    def test_user_events_parsed(self, adapter: "GrokCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-grok-001")
        assert [e for e in events if e.role == EventRole.USER]

    def test_assistant_events_parsed(self, adapter: "GrokCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-grok-001")
        assert [e for e in events if e.role == EventRole.ASSISTANT]

    def test_tool_use_parsed(self, adapter: "GrokCLIAdapter") -> None:
        from normalize import ContentType

        events = adapter.normalize_session("sess-grok-001")
        assert any(
            block.type == ContentType.TOOL_USE and block.tool_name
            for e in events
            for block in e.content
        )

    def test_tool_results_parsed(self, adapter: "GrokCLIAdapter") -> None:
        from normalize import ContentType

        events = adapter.normalize_session("sess-grok-001")
        assert any(
            block.type == ContentType.TOOL_RESULT
            for e in events
            for block in e.content
        )

    def test_reasoning_mapped_to_thinking(self, adapter: "GrokCLIAdapter") -> None:
        from normalize import ContentType

        events = adapter.normalize_session("sess-grok-001")
        assert any(
            block.type == ContentType.THINKING
            for e in events
            for block in e.content
        )

    def test_harness_set_correctly(self, adapter: "GrokCLIAdapter") -> None:
        events = adapter.normalize_session("sess-grok-001")
        assert events
        for event in events:
            assert event.harness == "grok_cli"

    def test_model_captured(self, adapter: "GrokCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-grok-001")
        models = [e.model for e in events if e.role == EventRole.ASSISTANT and e.model]
        assert any("grok" in m for m in models)

    def test_nonexistent_session_returns_empty(self, adapter: "GrokCLIAdapter") -> None:
        assert adapter.normalize_session("nonexistent") == []
