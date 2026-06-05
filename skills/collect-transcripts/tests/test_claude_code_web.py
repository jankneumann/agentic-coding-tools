"""Tests for the Claude Code web adapter (CLI bridge).

Covers:
- Fail-soft when claude CLI not on PATH
- Fail-soft when no session IDs provided
- Discovers sessions from explicit IDs
- Discovers sessions from env var
- Teleport failure is handled gracefully
- Delegates to CLI adapter after teleport
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestClaudeCodeWebDiscovery:
    """Test session discovery for web adapter."""

    def test_returns_empty_when_cli_missing(self) -> None:
        from adapters.claude_code_web import ClaudeCodeWebAdapter

        with patch("shutil.which", return_value=None):
            adapter = ClaudeCodeWebAdapter(session_ids=["sess-001"])
            sessions = adapter.discover_sessions()
            assert sessions == []

    def test_returns_empty_when_no_session_ids(self) -> None:
        from adapters.claude_code_web import ClaudeCodeWebAdapter

        with patch("shutil.which", return_value="/usr/bin/claude"):
            with patch.dict("os.environ", {}, clear=True):
                adapter = ClaudeCodeWebAdapter()
                sessions = adapter.discover_sessions()
                assert sessions == []

    def test_discovers_explicit_session_ids(self) -> None:
        from adapters.claude_code_web import ClaudeCodeWebAdapter

        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeWebAdapter(session_ids=["sess-001", "sess-002"])
            sessions = adapter.discover_sessions()
            assert len(sessions) == 2
            assert sessions[0].session_id == "sess-001"
            assert sessions[0].harness == "claude_code_web"

    def test_discovers_from_env_var(self) -> None:
        from adapters.claude_code_web import ClaudeCodeWebAdapter

        with patch("shutil.which", return_value="/usr/bin/claude"):
            with patch.dict(
                "os.environ",
                {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_test123"},
            ):
                adapter = ClaudeCodeWebAdapter()
                sessions = adapter.discover_sessions()
                assert len(sessions) == 1
                assert sessions[0].session_id == "cse_test123"


class TestClaudeCodeWebNormalization:
    """Test normalization via CLI bridge."""

    def test_returns_empty_when_cli_missing(self) -> None:
        from adapters.claude_code_web import ClaudeCodeWebAdapter

        with patch("shutil.which", return_value=None):
            adapter = ClaudeCodeWebAdapter(session_ids=["sess-001"])
            events = adapter.normalize_session("sess-001")
            assert events == []

    def test_returns_empty_on_teleport_failure(self) -> None:
        from adapters.claude_code_web import ClaudeCodeWebAdapter

        with patch("shutil.which", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, stderr="Authentication required"
                )
                adapter = ClaudeCodeWebAdapter(session_ids=["sess-001"])
                events = adapter.normalize_session("sess-001")
                assert events == []

    def test_delegates_to_cli_adapter_after_teleport(self, tmp_path: Path) -> None:
        from adapters.claude_code_web import ClaudeCodeWebAdapter

        # Set up a mock teleported session on disk
        proj_dir = tmp_path / ".claude" / "projects" / "-Users-me-proj"
        proj_dir.mkdir(parents=True)
        fixture = (
            Path(__file__).parent / "fixtures" / "claude_code_cli" / "session-abc123.jsonl"
        )
        (proj_dir / "session-abc123.jsonl").write_text(fixture.read_text())

        with patch("shutil.which", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                adapter = ClaudeCodeWebAdapter(
                    session_ids=["abc123"],
                    base_dir=str(tmp_path / ".claude" / "projects"),
                )
                events = adapter.normalize_session("abc123")
                assert len(events) > 0
                # Should be tagged as web, not CLI
                assert events[0].harness == "claude_code_web"

    def test_handles_teleport_timeout(self) -> None:
        import subprocess as sp

        from adapters.claude_code_web import ClaudeCodeWebAdapter

        with patch("shutil.which", return_value="/usr/bin/claude"):
            with patch("subprocess.run", side_effect=sp.TimeoutExpired("claude", 120)):
                adapter = ClaudeCodeWebAdapter(session_ids=["sess-001"])
                events = adapter.normalize_session("sess-001")
                assert events == []
