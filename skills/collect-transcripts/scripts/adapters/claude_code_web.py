"""Claude Code web adapter (CLI bridge).

Invokes ``claude --teleport <session-id>`` to pull a cloud session onto
local disk, then delegates to the ``claude_code_cli`` adapter.

Fails soft if:
- ``claude`` CLI is not on PATH
- ``--teleport`` exits non-zero
- No session ID is supplied

Discovery: session ID is available in ``CLAUDE_CODE_REMOTE_SESSION_ID``
env var (with ``cse_`` prefix; URL form uses ``session_`` prefix).
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
from adapters.claude_code_cli import ClaudeCodeCLIAdapter
from normalize import NormalizedEvent, SessionSummary

logger = logging.getLogger(__name__)


class ClaudeCodeWebAdapter(AdapterBase):
    """Adapter for Claude Code web sessions via CLI bridge.

    Uses ``claude --teleport <session-id>`` to materialize cloud sessions
    as local JSONL files, then delegates parsing to ClaudeCodeCLIAdapter.
    """

    HARNESS_ID = "claude_code_web"
    SCHEMA_VERSION = "1.0"

    def __init__(
        self,
        *,
        session_ids: list[str] | None = None,
        base_dir: str | None = None,
    ) -> None:
        """
        Parameters
        ----------
        session_ids:
            Explicit session IDs to teleport.  If not provided, attempts
            to read from CLAUDE_CODE_REMOTE_SESSION_ID env var.
        base_dir:
            Override for the Claude projects directory.
        """
        self._session_ids = session_ids or []
        self._base_dir = base_dir

        # Try to discover session ID from environment
        if not self._session_ids:
            env_id = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID", "")
            if env_id:
                self._session_ids.append(env_id)

    def _cli_available(self) -> bool:
        """Check if claude CLI is on PATH."""
        return shutil.which("claude") is not None

    def _teleport_session(self, session_id: str) -> bool:
        """Invoke claude --teleport to pull a session to local disk.

        Returns True if successful, False otherwise.
        """
        try:
            result = subprocess.run(
                ["claude", "--teleport", session_id],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.warning(
                    "claude --teleport %s failed (rc=%d): %s",
                    session_id,
                    result.returncode,
                    result.stderr.strip(),
                )
                return False
            return True
        except FileNotFoundError:
            self._warn_unavailable("claude CLI not found on PATH")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("claude --teleport %s timed out", session_id)
            return False
        except OSError as exc:
            self._warn_unavailable(str(exc))
            return False

    def discover_sessions(self) -> list[SessionSummary]:
        if not self._cli_available():
            self._warn_unavailable("claude CLI not found on PATH")
            return []

        if not self._session_ids:
            self._warn_unavailable(
                "no session IDs provided and CLAUDE_CODE_REMOTE_SESSION_ID not set"
            )
            return []

        sessions: list[SessionSummary] = []
        for sid in self._session_ids:
            sessions.append(
                SessionSummary(
                    session_id=sid,
                    harness=self.HARNESS_ID,
                    metadata={"source": "cloud-teleport"},
                )
            )
        return sessions

    def normalize_session(self, session_id: str) -> list[NormalizedEvent]:
        if not self._cli_available():
            self._warn_unavailable("claude CLI not found on PATH")
            return []

        # Teleport the session to local disk
        if not self._teleport_session(session_id):
            return []

        # Delegate to the CLI adapter
        cli_adapter = ClaudeCodeCLIAdapter(base_dir=self._base_dir)
        events = cli_adapter.normalize_session(session_id)

        # Re-tag the harness as web
        for event in events:
            event.harness = self.HARNESS_ID

        return events
