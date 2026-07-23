"""Tests for the Antigravity (agy) CLI transcript adapter.

Antigravity is Claude-shaped (E7): the adapter inherits Claude Code's JSONL
discovery/normalization and only overrides the harness id + data directory.

Covers:
- Session discovery from a fixture project directory
- JSONL parsing of summary/human/assistant/tool_result records
- Correct mapping of user, assistant, tool events
- Correct harness stamping (antigravity_cli, not claude_code_cli)
- Fail-soft when source path missing
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "antigravity_cli"
sys.path.insert(0, str(SCRIPTS_DIR))


def _seed(tmp_path: Path) -> Path:
    """Materialize the fixture under a <project>/<session>.jsonl layout."""
    project = tmp_path / "-Users-me-proj"
    project.mkdir(parents=True)
    fixture = FIXTURES_DIR / "sess-agy-001.jsonl"
    (project / "sess-agy-001.jsonl").write_text(fixture.read_text())
    return tmp_path


class TestAntigravityCLIDiscovery:
    def test_discovers_sessions_from_fixture_dir(self, tmp_path: Path) -> None:
        from adapters.antigravity_cli import AntigravityCLIAdapter

        _seed(tmp_path)
        adapter = AntigravityCLIAdapter(base_dir=str(tmp_path))
        sessions = adapter.discover_sessions()
        assert len(sessions) >= 1
        assert sessions[0].harness == "antigravity_cli"

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        from adapters.antigravity_cli import AntigravityCLIAdapter

        adapter = AntigravityCLIAdapter(base_dir=str(tmp_path / "nonexistent"))
        assert adapter.discover_sessions() == []


class TestAntigravityCLINormalization:
    @pytest.fixture()
    def adapter(self, tmp_path: Path) -> "AntigravityCLIAdapter":
        from adapters.antigravity_cli import AntigravityCLIAdapter

        _seed(tmp_path)
        return AntigravityCLIAdapter(base_dir=str(tmp_path))

    def test_normalizes_fixture_session(self, adapter: "AntigravityCLIAdapter") -> None:
        events = adapter.normalize_session("sess-agy-001")
        assert len(events) > 0

    def test_user_events_parsed(self, adapter: "AntigravityCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-agy-001")
        assert [e for e in events if e.role == EventRole.USER]

    def test_assistant_events_parsed(self, adapter: "AntigravityCLIAdapter") -> None:
        from normalize import EventRole

        events = adapter.normalize_session("sess-agy-001")
        assert [e for e in events if e.role == EventRole.ASSISTANT]

    def test_tool_use_parsed(self, adapter: "AntigravityCLIAdapter") -> None:
        from normalize import ContentType

        events = adapter.normalize_session("sess-agy-001")
        assert any(
            block.type == ContentType.TOOL_USE and block.tool_name
            for e in events
            for block in e.content
        )

    def test_tool_results_parsed(self, adapter: "AntigravityCLIAdapter") -> None:
        from normalize import ContentType

        events = adapter.normalize_session("sess-agy-001")
        assert any(
            block.type == ContentType.TOOL_RESULT
            for e in events
            for block in e.content
        )

    def test_thinking_parsed(self, adapter: "AntigravityCLIAdapter") -> None:
        from normalize import ContentType

        events = adapter.normalize_session("sess-agy-001")
        assert any(
            block.type == ContentType.THINKING
            for e in events
            for block in e.content
        )

    def test_harness_set_correctly(self, adapter: "AntigravityCLIAdapter") -> None:
        events = adapter.normalize_session("sess-agy-001")
        assert events
        for event in events:
            assert event.harness == "antigravity_cli"

    def test_nonexistent_session_returns_empty(
        self, adapter: "AntigravityCLIAdapter"
    ) -> None:
        assert adapter.normalize_session("nonexistent") == []
