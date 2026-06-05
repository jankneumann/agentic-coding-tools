"""Tests for the Codex web adapter (CLI bridge).

Covers:
- Fail-soft when codex CLI not on PATH
- Fail-soft on cloud pull failure
- Delegates to CLI adapter after cloud pull
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestCodexWebDiscovery:
    """Test session discovery for web adapter."""

    def test_returns_empty_when_cli_missing(self) -> None:
        from adapters.codex_web import CodexWebAdapter

        with patch("shutil.which", return_value=None):
            adapter = CodexWebAdapter()
            sessions = adapter.discover_sessions()
            assert sessions == []

    def test_returns_empty_on_cloud_pull_failure(self) -> None:
        from adapters.codex_web import CodexWebAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, stderr="Not authenticated"
                )
                adapter = CodexWebAdapter()
                sessions = adapter.discover_sessions()
                assert sessions == []


class TestCodexWebNormalization:
    """Test normalization via CLI bridge."""

    def test_returns_empty_when_cli_missing(self) -> None:
        from adapters.codex_web import CodexWebAdapter

        with patch("shutil.which", return_value=None):
            adapter = CodexWebAdapter()
            events = adapter.normalize_session("sess-001")
            assert events == []

    def test_delegates_to_cli_adapter_after_cloud_pull(
        self, tmp_path: Path
    ) -> None:
        from adapters.codex_web import CodexWebAdapter

        # Set up mock pulled session
        fixtures = Path(__file__).parent / "fixtures" / "codex_cli"
        sess_dir = tmp_path / "sessions" / "2026" / "05" / "01"
        sess_dir.mkdir(parents=True)
        (sess_dir / "rollout-1714560000-sess-xyz789.jsonl").write_text(
            (fixtures / "rollout-1714560000-sess-xyz789.jsonl").read_text()
        )

        with patch("shutil.which", return_value="/usr/bin/codex"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                adapter = CodexWebAdapter(
                    base_dir=str(tmp_path / "sessions")
                )
                events = adapter.normalize_session("sess-xyz789")
                assert len(events) > 0
                assert events[0].harness == "codex_web"
