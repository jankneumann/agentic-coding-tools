"""Tests for the Claude Code CLI transcript adapter.

Covers:
- Session discovery from fixture files
- JSONL parsing and normalization to NormalizedEvent
- Correct mapping of user, assistant, tool_use, tool_result events
- Fail-soft when source path missing
- Round-trip: fixture -> normalize -> to_dict -> from_dict
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "claude_code_cli"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestClaudeCodeCLIDiscovery:
    """Test session discovery from the Claude Code CLI source."""

    def test_discovers_sessions_from_fixture_dir(self, tmp_path: Path) -> None:
        from adapters.claude_code_cli import ClaudeCodeCLIAdapter

        # Create a mock Claude projects directory
        proj_dir = tmp_path / ".claude" / "projects" / "-Users-me-proj"
        proj_dir.mkdir(parents=True)
        fixture = FIXTURES_DIR / "session-abc123.jsonl"
        (proj_dir / "session-abc123.jsonl").write_text(fixture.read_text())

        adapter = ClaudeCodeCLIAdapter(base_dir=str(tmp_path / ".claude" / "projects"))
        sessions = adapter.discover_sessions()
        assert len(sessions) >= 1
        assert any(s.session_id == "abc123" for s in sessions)

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        from adapters.claude_code_cli import ClaudeCodeCLIAdapter

        adapter = ClaudeCodeCLIAdapter(
            base_dir=str(tmp_path / "nonexistent" / ".claude" / "projects")
        )
        sessions = adapter.discover_sessions()
        assert sessions == []

    def test_returns_empty_when_no_jsonl_files(self, tmp_path: Path) -> None:
        from adapters.claude_code_cli import ClaudeCodeCLIAdapter

        proj_dir = tmp_path / ".claude" / "projects" / "-Users-me-proj"
        proj_dir.mkdir(parents=True)
        # No .jsonl files created

        adapter = ClaudeCodeCLIAdapter(base_dir=str(tmp_path / ".claude" / "projects"))
        sessions = adapter.discover_sessions()
        assert sessions == []


class TestClaudeCodeCLINormalization:
    """Test normalization of Claude Code CLI JSONL to NormalizedEvent."""

    @pytest.fixture()
    def adapter(self, tmp_path: Path) -> "ClaudeCodeCLIAdapter":
        from adapters.claude_code_cli import ClaudeCodeCLIAdapter

        proj_dir = tmp_path / ".claude" / "projects" / "-Users-me-proj"
        proj_dir.mkdir(parents=True)
        fixture = FIXTURES_DIR / "session-abc123.jsonl"
        (proj_dir / "session-abc123.jsonl").write_text(fixture.read_text())

        return ClaudeCodeCLIAdapter(base_dir=str(tmp_path / ".claude" / "projects"))

    def test_normalizes_fixture_session(self, adapter: "ClaudeCodeCLIAdapter") -> None:
        events = adapter.normalize_session("abc123")
        # The fixture has: summary (skipped), 2 user, 3 assistant, 2 tool_result
        # But we combine tool_result with the tool event — they become separate events
        assert len(events) > 0

    def test_user_events_have_user_role(self, adapter: "ClaudeCodeCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("abc123")
        user_events = [e for e in events if e.role == EventRole.USER]
        assert len(user_events) >= 1
        assert user_events[0].content[0].text == "Fix the failing test in src/foo.py"

    def test_assistant_events_have_content_blocks(
        self, adapter: "ClaudeCodeCLIAdapter"
    ) -> None:
        from normalize import ContentType, EventRole

        events = adapter.normalize_session("abc123")
        assistant_events = [e for e in events if e.role == EventRole.ASSISTANT]
        assert len(assistant_events) >= 1
        # First assistant event should have thinking + text + tool_use
        first_assistant = assistant_events[0]
        types = {c.type for c in first_assistant.content}
        assert ContentType.THINKING in types
        assert ContentType.TEXT in types
        assert ContentType.TOOL_USE in types

    def test_tool_use_blocks_have_name_and_input(
        self, adapter: "ClaudeCodeCLIAdapter"
    ) -> None:
        from normalize import ContentType, EventRole

        events = adapter.normalize_session("abc123")
        assistant_events = [e for e in events if e.role == EventRole.ASSISTANT]
        for event in assistant_events:
            for block in event.content:
                if block.type == ContentType.TOOL_USE:
                    assert block.tool_name != ""
                    assert block.tool_use_id != ""

    def test_tool_result_events_mapped(
        self, adapter: "ClaudeCodeCLIAdapter"
    ) -> None:
        from normalize import ContentType, EventRole

        events = adapter.normalize_session("abc123")
        tool_events = [e for e in events if e.role == EventRole.TOOL]
        assert len(tool_events) >= 1
        # Tool results should have tool_result content blocks
        for event in tool_events:
            assert any(c.type == ContentType.TOOL_RESULT for c in event.content)

    def test_usage_populated_on_assistant_events(
        self, adapter: "ClaudeCodeCLIAdapter"
    ) -> None:
        from normalize import EventRole

        events = adapter.normalize_session("abc123")
        assistant_events = [e for e in events if e.role == EventRole.ASSISTANT]
        # At least one assistant event should have usage
        events_with_usage = [e for e in assistant_events if e.usage is not None]
        assert len(events_with_usage) >= 1
        assert events_with_usage[0].usage.input_tokens > 0

    def test_harness_set_correctly(self, adapter: "ClaudeCodeCLIAdapter") -> None:
        events = adapter.normalize_session("abc123")
        for event in events:
            assert event.harness == "claude_code_cli"

    def test_session_id_set_correctly(self, adapter: "ClaudeCodeCLIAdapter") -> None:
        events = adapter.normalize_session("abc123")
        for event in events:
            assert event.session_id == "abc123"

    def test_events_have_sequential_numbers(
        self, adapter: "ClaudeCodeCLIAdapter"
    ) -> None:
        events = adapter.normalize_session("abc123")
        numbers = [e.sequence_number for e in events]
        assert numbers == sorted(numbers)
        assert numbers[0] == 0 or numbers[0] == 1

    def test_round_trip_through_dict(self, adapter: "ClaudeCodeCLIAdapter") -> None:
        """Verify events survive to_dict -> from_dict round-trip."""
        from normalize import NormalizedEvent

        events = adapter.normalize_session("abc123")
        for event in events:
            d = event.to_dict()
            restored = NormalizedEvent.from_dict(d)
            assert restored.event_id == event.event_id
            assert restored.role == event.role
            assert len(restored.content) == len(event.content)

    def test_nonexistent_session_returns_empty(
        self, adapter: "ClaudeCodeCLIAdapter"
    ) -> None:
        events = adapter.normalize_session("nonexistent-session-id")
        assert events == []
