"""Codex web adapter (CLI bridge).

Invokes ``codex cloud`` to pull cloud-task transcripts onto local disk
(where they land as standard rollout JSONL), then delegates to the
``codex_cli`` adapter.

Fails soft if:
- ``codex`` CLI is not on PATH
- ``codex cloud`` is not authenticated
- No sessions are returned
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from adapters.base import AdapterBase
from adapters.codex_cli import CodexCLIAdapter
from normalize import NormalizedEvent, SessionSummary

logger = logging.getLogger(__name__)


class CodexWebAdapter(AdapterBase):
    """Adapter for Codex web/cloud sessions via CLI bridge.

    Uses ``codex cloud`` to pull cloud-task transcripts to local disk,
    then delegates parsing to CodexCLIAdapter.
    """

    HARNESS_ID = "codex_web"
    SCHEMA_VERSION = "rollout-v1"

    def __init__(
        self,
        *,
        base_dir: str | None = None,
    ) -> None:
        """
        Parameters
        ----------
        base_dir:
            Override for the Codex sessions directory.
        """
        self._base_dir = base_dir

    def _cli_available(self) -> bool:
        """Check if codex CLI is on PATH."""
        return shutil.which("codex") is not None

    def _pull_cloud_sessions(self) -> bool:
        """Invoke codex cloud to pull sessions to local disk.

        Returns True if successful, False otherwise.
        """
        try:
            result = subprocess.run(
                ["codex", "cloud"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.warning(
                    "codex cloud failed (rc=%d): %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return False
            return True
        except FileNotFoundError:
            self._warn_unavailable("codex CLI not found on PATH")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("codex cloud timed out")
            return False
        except OSError as exc:
            self._warn_unavailable(str(exc))
            return False

    def discover_sessions(self) -> list[SessionSummary]:
        if not self._cli_available():
            self._warn_unavailable("codex CLI not found on PATH")
            return []

        # Pull cloud sessions first
        if not self._pull_cloud_sessions():
            return []

        # Delegate discovery to CLI adapter
        cli_adapter = CodexCLIAdapter(base_dir=self._base_dir)
        sessions = cli_adapter.discover_sessions()

        # Re-tag as web
        for s in sessions:
            s.harness = self.HARNESS_ID

        return sessions

    def normalize_session(self, session_id: str) -> list[NormalizedEvent]:
        if not self._cli_available():
            self._warn_unavailable("codex CLI not found on PATH")
            return []

        # Pull cloud sessions
        self._pull_cloud_sessions()

        # Delegate to CLI adapter
        cli_adapter = CodexCLIAdapter(base_dir=self._base_dir)
        events = cli_adapter.normalize_session(session_id)

        # Re-tag as web
        for event in events:
            event.harness = self.HARNESS_ID

        return events
