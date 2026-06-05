"""Codex CLI transcript adapter.

Reads session transcripts from
``$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<timestamp>-<session-id>.jsonl``
(default ``$CODEX_HOME`` = ``~/.codex``).

Schema: JSONL one ``RolloutLine`` per line.  Each line is a ``RolloutItem``
enum variant:
- ``SessionMeta`` — header with session_id, source, timestamp, model_provider
- ``EventMsg`` — UI replay events including ``UserMessage``
- ``ResponseItem`` — full Responses-API turn: message, function_call,
  function_call_output, reasoning

Note: ``~/.codex/history.jsonl`` is command history only, NOT the rollout
transcript.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from adapters.base import AdapterBase
from normalize import (
    ContentBlock,
    ContentType,
    EventRole,
    NormalizedEvent,
    SessionSummary,
)

logger = logging.getLogger(__name__)


class CodexCLIAdapter(AdapterBase):
    """Adapter for Codex CLI session transcripts.

    Parameters
    ----------
    base_dir:
        Override for the sessions directory.  Defaults to
        ``$CODEX_HOME/sessions`` or ``~/.codex/sessions``.
    """

    HARNESS_ID = "codex_cli"
    SCHEMA_VERSION = "rollout-v1"

    def __init__(self, base_dir: str | None = None) -> None:
        if base_dir is not None:
            self._base_dir = Path(base_dir)
        else:
            codex_home = os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
            self._base_dir = Path(codex_home) / "sessions"

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_sessions(self) -> list[SessionSummary]:
        if not self._base_dir.exists():
            self._warn_unavailable(f"directory not found: {self._base_dir}")
            return []

        sessions: list[SessionSummary] = []
        # Pattern: YYYY/MM/DD/rollout-<timestamp>-<session-id>.jsonl
        for jsonl_file in self._base_dir.glob("*/*/*/*rollout-*.jsonl"):
            session_id = self._extract_session_id(jsonl_file.name)

            # Read first line for metadata
            start_time = ""
            try:
                with open(jsonl_file, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        header = json.loads(first_line)
                        start_time = header.get("timestamp", "")
            except (json.JSONDecodeError, OSError):
                pass

            sessions.append(
                SessionSummary(
                    session_id=session_id,
                    harness=self.HARNESS_ID,
                    source_path=str(jsonl_file),
                    start_time=start_time,
                )
            )

        return sessions

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def normalize_session(self, session_id: str) -> list[NormalizedEvent]:
        source_file = self._find_session_file(session_id)
        if source_file is None:
            self._warn_parse_error(session_id, "session file not found")
            return []

        try:
            lines = source_file.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            self._warn_parse_error(session_id, str(exc))
            return []

        events: list[NormalizedEvent] = []
        seq = 0
        model = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue

            line_type = raw.get("type", "")

            if line_type == "session_meta":
                model = raw.get("model", "")
                continue

            if line_type == "event_msg":
                event = self._parse_event_msg(raw, session_id, seq, model)
                if event:
                    events.append(event)
                    seq += 1

            elif line_type == "response_item":
                event = self._parse_response_item(raw, session_id, seq, model)
                if event:
                    events.append(event)
                    seq += 1

        return events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_session_id(filename: str) -> str:
        """Extract session ID from rollout filename.

        Format: rollout-<timestamp>-<session-id>.jsonl
        """
        stem = filename.replace(".jsonl", "")
        parts = stem.split("-", 2)
        if len(parts) >= 3:
            return parts[2]
        return stem

    def _find_session_file(self, session_id: str) -> Path | None:
        """Find the JSONL file for a given session ID."""
        if not self._base_dir.exists():
            return None

        candidates = list(self._base_dir.glob(f"*/*/*/rollout-*-{session_id}.jsonl"))
        if not candidates:
            # Also try direct match
            candidates = list(self._base_dir.glob(f"**/{session_id}.jsonl"))
        return candidates[0] if candidates else None

    def _parse_event_msg(
        self,
        raw: dict[str, Any],
        session_id: str,
        seq: int,
        model: str,
    ) -> NormalizedEvent | None:
        event_type = raw.get("event_type", "")
        content_text = raw.get("content", "")

        if event_type == "UserMessage" or event_type == "user_message":
            return NormalizedEvent(
                event_id=f"evt-{seq}",
                session_id=session_id,
                sequence_number=seq,
                role=EventRole.USER,
                content=[ContentBlock(type=ContentType.TEXT, text=content_text)],
                harness=self.HARNESS_ID,
                model=model,
            )

        # Other event types we map as system/metadata events
        if content_text:
            return NormalizedEvent(
                event_id=f"evt-{seq}",
                session_id=session_id,
                sequence_number=seq,
                role=EventRole.SYSTEM,
                content=[ContentBlock(type=ContentType.TEXT, text=content_text)],
                harness=self.HARNESS_ID,
                model=model,
                metadata={"event_type": event_type},
            )

        return None

    def _parse_response_item(
        self,
        raw: dict[str, Any],
        session_id: str,
        seq: int,
        model: str,
    ) -> NormalizedEvent | None:
        item_type = raw.get("item_type", "")

        if item_type == "message":
            role_str = raw.get("role", "assistant")
            role = EventRole.USER if role_str == "user" else EventRole.ASSISTANT
            content = raw.get("content", "")
            return NormalizedEvent(
                event_id=f"evt-{seq}",
                session_id=session_id,
                sequence_number=seq,
                role=role,
                content=[ContentBlock(type=ContentType.TEXT, text=content)],
                harness=self.HARNESS_ID,
                model=model,
            )

        if item_type == "function_call":
            name = raw.get("name", "")
            arguments = raw.get("arguments", "{}")
            call_id = raw.get("call_id", "")
            # Parse arguments if it's a JSON string
            try:
                args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
            except json.JSONDecodeError:
                args_dict = {"raw": arguments}

            return NormalizedEvent(
                event_id=f"evt-{seq}",
                session_id=session_id,
                sequence_number=seq,
                role=EventRole.ASSISTANT,
                content=[
                    ContentBlock(
                        type=ContentType.TOOL_USE,
                        tool_name=name,
                        tool_input=args_dict,
                        tool_use_id=call_id,
                    )
                ],
                harness=self.HARNESS_ID,
                model=model,
            )

        if item_type == "function_call_output":
            call_id = raw.get("call_id", "")
            output = raw.get("output", "")
            return NormalizedEvent(
                event_id=f"evt-{seq}",
                session_id=session_id,
                sequence_number=seq,
                role=EventRole.TOOL,
                content=[
                    ContentBlock(
                        type=ContentType.TOOL_RESULT,
                        text=output,
                        tool_use_id=call_id,
                    )
                ],
                harness=self.HARNESS_ID,
                model=model,
            )

        if item_type == "reasoning":
            content = raw.get("content", "")
            return NormalizedEvent(
                event_id=f"evt-{seq}",
                session_id=session_id,
                sequence_number=seq,
                role=EventRole.ASSISTANT,
                content=[ContentBlock(type=ContentType.THINKING, text=content)],
                harness=self.HARNESS_ID,
                model=model,
            )

        return None
