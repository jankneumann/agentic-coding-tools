"""Tests for the Codex CLI transcript adapter.

Covers:
- Session discovery from rollout files
- JSONL parsing of RolloutLine variants (SessionMeta, EventMsg, ResponseItem)
- Correct mapping of user, assistant, tool_use, tool_result, reasoning events
- Fail-soft when source path missing
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "codex_cli"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestCodexCLIDiscovery:
    """Test session discovery from the Codex CLI source."""

    def test_discovers_sessions_from_fixture_dir(self, tmp_path: Path) -> None:
        from adapters.codex_cli import CodexCLIAdapter

        # Create mock Codex sessions directory structure
        sess_dir = tmp_path / "sessions" / "2026" / "05" / "01"
        sess_dir.mkdir(parents=True)
        fixture = FIXTURES_DIR / "rollout-1714560000-sess-xyz789.jsonl"
        (sess_dir / "rollout-1714560000-sess-xyz789.jsonl").write_text(
            fixture.read_text()
        )

        adapter = CodexCLIAdapter(base_dir=str(tmp_path / "sessions"))
        sessions = adapter.discover_sessions()
        assert len(sessions) >= 1

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        from adapters.codex_cli import CodexCLIAdapter

        adapter = CodexCLIAdapter(base_dir=str(tmp_path / "nonexistent"))
        sessions = adapter.discover_sessions()
        assert sessions == []


class TestCodexCLINormalization:
    """Test normalization of Codex CLI JSONL to NormalizedEvent."""

    @pytest.fixture()
    def adapter(self, tmp_path: Path) -> "CodexCLIAdapter":
        from adapters.codex_cli import CodexCLIAdapter

        sess_dir = tmp_path / "sessions" / "2026" / "05" / "01"
        sess_dir.mkdir(parents=True)
        fixture = FIXTURES_DIR / "rollout-1714560000-sess-xyz789.jsonl"
        (sess_dir / "rollout-1714560000-sess-xyz789.jsonl").write_text(
            fixture.read_text()
        )

        return CodexCLIAdapter(base_dir=str(tmp_path / "sessions"))

    def test_normalizes_fixture_session(self, adapter: "CodexCLIAdapter") -> None:
        events = adapter.normalize_session("sess-xyz789")
        assert len(events) > 0

    def test_user_events_parsed(self, adapter: "CodexCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-xyz789")
        user_events = [e for e in events if e.role == EventRole.USER]
        assert len(user_events) >= 1

    def test_assistant_messages_parsed(self, adapter: "CodexCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-xyz789")
        assistant_events = [e for e in events if e.role == EventRole.ASSISTANT]
        assert len(assistant_events) >= 1

    def test_function_call_mapped_to_tool_use(self, adapter: "CodexCLIAdapter") -> None:
        from normalize import ContentType, EventRole

        events = adapter.normalize_session("sess-xyz789")
        tool_use_events = [
            e
            for e in events
            if e.role == EventRole.ASSISTANT
            and any(c.type == ContentType.TOOL_USE for c in e.content)
        ]
        assert len(tool_use_events) >= 1
        tool_block = next(
            c for c in tool_use_events[0].content if c.type == ContentType.TOOL_USE
        )
        assert tool_block.tool_name == "write_file"

    def test_function_call_output_mapped_to_tool_result(
        self, adapter: "CodexCLIAdapter"
    ) -> None:
        from normalize import ContentType, EventRole

        events = adapter.normalize_session("sess-xyz789")
        tool_result_events = [
            e
            for e in events
            if e.role == EventRole.TOOL
            and any(c.type == ContentType.TOOL_RESULT for c in e.content)
        ]
        assert len(tool_result_events) >= 1

    def test_reasoning_mapped_to_thinking(self, adapter: "CodexCLIAdapter") -> None:
        from normalize import ContentType, EventRole

        events = adapter.normalize_session("sess-xyz789")
        thinking_events = [
            e
            for e in events
            if any(c.type == ContentType.THINKING for c in e.content)
        ]
        assert len(thinking_events) >= 1

    def test_harness_set_correctly(self, adapter: "CodexCLIAdapter") -> None:
        events = adapter.normalize_session("sess-xyz789")
        for event in events:
            assert event.harness == "codex_cli"

    def test_nonexistent_session_returns_empty(
        self, adapter: "CodexCLIAdapter"
    ) -> None:
        events = adapter.normalize_session("nonexistent")
        assert events == []

    def test_extract_session_id_from_filename(self) -> None:
        from adapters.codex_cli import CodexCLIAdapter

        assert CodexCLIAdapter._extract_session_id(
            "rollout-1714560000-sess-xyz789.jsonl"
        ) == "sess-xyz789"
