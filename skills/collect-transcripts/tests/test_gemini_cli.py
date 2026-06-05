"""Tests for the Gemini CLI transcript adapter.

Covers:
- Session discovery from fixture files
- JSONL parsing of metadata, MessageRecord, tool calls
- Correct mapping of user, gemini (assistant), tool events
- Handling of $set/$rewindTo operations (skipped)
- Fail-soft when source path missing
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "gemini_cli"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestGeminiCLIDiscovery:
    """Test session discovery from the Gemini CLI source."""

    def test_discovers_sessions_from_fixture_dir(self, tmp_path: Path) -> None:
        from adapters.gemini_cli import GeminiCLIAdapter

        # Create mock Gemini directory structure
        chats_dir = tmp_path / "abc123hash" / "chats"
        chats_dir.mkdir(parents=True)
        fixture = FIXTURES_DIR / "session-2026-05-01T10-00-abcdef.json"
        (chats_dir / "session-2026-05-01T10-00-abcdef.json").write_text(
            fixture.read_text()
        )

        adapter = GeminiCLIAdapter(base_dir=str(tmp_path))
        sessions = adapter.discover_sessions()
        assert len(sessions) >= 1
        assert sessions[0].harness == "gemini_cli"

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        from adapters.gemini_cli import GeminiCLIAdapter

        adapter = GeminiCLIAdapter(base_dir=str(tmp_path / "nonexistent"))
        sessions = adapter.discover_sessions()
        assert sessions == []


class TestGeminiCLINormalization:
    """Test normalization of Gemini CLI JSONL to NormalizedEvent."""

    @pytest.fixture()
    def adapter(self, tmp_path: Path) -> "GeminiCLIAdapter":
        from adapters.gemini_cli import GeminiCLIAdapter

        chats_dir = tmp_path / "abc123hash" / "chats"
        chats_dir.mkdir(parents=True)
        fixture = FIXTURES_DIR / "session-2026-05-01T10-00-abcdef.json"
        (chats_dir / "session-2026-05-01T10-00-abcdef.json").write_text(
            fixture.read_text()
        )

        return GeminiCLIAdapter(base_dir=str(tmp_path))

    def test_normalizes_fixture_session(self, adapter: "GeminiCLIAdapter") -> None:
        events = adapter.normalize_session("sess-gem-001")
        assert len(events) > 0

    def test_user_events_parsed(self, adapter: "GeminiCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-gem-001")
        user_events = [e for e in events if e.role == EventRole.USER]
        assert len(user_events) >= 1

    def test_assistant_events_parsed(self, adapter: "GeminiCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-gem-001")
        assistant_events = [e for e in events if e.role == EventRole.ASSISTANT]
        assert len(assistant_events) >= 1

    def test_tool_calls_parsed(self, adapter: "GeminiCLIAdapter") -> None:
        from normalize import ContentType

        events = adapter.normalize_session("sess-gem-001")
        tool_use_found = False
        for event in events:
            for block in event.content:
                if block.type == ContentType.TOOL_USE:
                    assert block.tool_name != ""
                    tool_use_found = True
        assert tool_use_found

    def test_tool_results_parsed(self, adapter: "GeminiCLIAdapter") -> None:
        from normalize import ContentType

        events = adapter.normalize_session("sess-gem-001")
        tool_result_found = False
        for event in events:
            for block in event.content:
                if block.type == ContentType.TOOL_RESULT:
                    tool_result_found = True
        assert tool_result_found

    def test_harness_set_correctly(self, adapter: "GeminiCLIAdapter") -> None:
        events = adapter.normalize_session("sess-gem-001")
        for event in events:
            assert event.harness == "gemini_cli"

    def test_model_captured(self, adapter: "GeminiCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-gem-001")
        assistant_events = [e for e in events if e.role == EventRole.ASSISTANT]
        # At least one should have model info
        models = [e.model for e in assistant_events if e.model]
        assert any("gemini" in m for m in models)

    def test_nonexistent_session_returns_empty(
        self, adapter: "GeminiCLIAdapter"
    ) -> None:
        events = adapter.normalize_session("nonexistent")
        assert events == []

    def test_skips_metadata_header(self, adapter: "GeminiCLIAdapter") -> None:
        """Metadata header (with sessionId + messages) should not be an event."""
        from normalize import EventRole

        events = adapter.normalize_session("sess-gem-001")
        # None of the events should have the raw metadata shape
        for event in events:
            assert event.role in (EventRole.USER, EventRole.ASSISTANT, EventRole.TOOL)
