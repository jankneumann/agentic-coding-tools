"""Grok CLI transcript adapter.

Reads session transcripts from
``~/.grok/sessions/session-<timestamp>-<short_id>.jsonl`` (JSONL — one record
per line).

Schema:
- Initial metadata record: ``sessionId``, ``startTime``, ``model``.
- Per-message record: ``id``, ``timestamp``, ``role`` (user|assistant|tool),
  ``content`` (string, or a list of blocks: ``text`` / ``tool_use`` /
  ``tool_result``), optional ``reasoning`` (grok thinking), ``model``, and
  ``tokens`` (``{input, output}``).

grok exposes a single model (``grok-4.5``, E5) whose reasoning effort is a
dispatch-time flag rather than a distinct slug, so the recorded ``model`` is
typically ``grok-4.5``.
"""

from __future__ import annotations

import json
import logging
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
    TokenUsage,
)

logger = logging.getLogger(__name__)

_ROLE_MAP = {
    "user": EventRole.USER,
    "assistant": EventRole.ASSISTANT,
    "tool": EventRole.TOOL,
}


class GrokCLIAdapter(AdapterBase):
    """Adapter for Grok CLI session transcripts.

    Parameters
    ----------
    base_dir:
        Override for the Grok sessions directory.  Defaults to
        ``~/.grok/sessions``.
    """

    HARNESS_ID = "grok_cli"
    SCHEMA_VERSION = "grok-session-v1"

    def __init__(self, base_dir: str | None = None) -> None:
        if base_dir is not None:
            self._base_dir = Path(base_dir)
        else:
            self._base_dir = Path.home() / ".grok" / "sessions"

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_sessions(self) -> list[SessionSummary]:
        if not self._base_dir.exists():
            self._warn_unavailable(f"directory not found: {self._base_dir}")
            return []

        sessions: list[SessionSummary] = []
        for jsonl_file in self._base_dir.glob("session-*.jsonl"):
            session_id = jsonl_file.stem
            start_time = ""
            try:
                with open(jsonl_file, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        header = json.loads(first_line)
                        session_id = header.get("sessionId", jsonl_file.stem)
                        start_time = header.get("startTime", "")
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

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Skip the metadata header (sessionId present, no role).
            if "sessionId" in raw and "role" not in raw:
                continue

            if "role" in raw:
                event = self._parse_message_record(raw, session_id, seq)
                if event is not None:
                    events.append(event)
                    seq += 1

        return events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_session_file(self, session_id: str) -> Path | None:
        if not self._base_dir.exists():
            return None

        candidates = [
            *self._base_dir.glob(f"*{session_id}*.jsonl"),
        ]
        if candidates:
            return candidates[0]

        # Fall back to scanning headers for a matching sessionId.
        for f in self._base_dir.glob("session-*.jsonl"):
            try:
                first_line = f.read_text(encoding="utf-8").split("\n", 1)[0]
                header = json.loads(first_line)
                if header.get("sessionId") == session_id:
                    return f
            except (json.JSONDecodeError, OSError):
                continue
        return None

    def _parse_message_record(
        self,
        raw: dict[str, Any],
        session_id: str,
        seq: int,
    ) -> NormalizedEvent | None:
        role = _ROLE_MAP.get(raw.get("role", ""))
        if role is None:
            return None

        content_blocks: list[ContentBlock] = []

        # grok reasoning (thinking) comes first when present.
        reasoning = raw.get("reasoning", "")
        if reasoning:
            content_blocks.append(
                ContentBlock(type=ContentType.THINKING, text=str(reasoning))
            )

        raw_content = raw.get("content", "")
        if isinstance(raw_content, str):
            if raw_content:
                content_blocks.append(
                    ContentBlock(type=ContentType.TEXT, text=raw_content)
                )
        elif isinstance(raw_content, list):
            for block in raw_content:
                parsed = self._parse_content_block(block)
                if parsed is not None:
                    content_blocks.append(parsed)

        if not content_blocks:
            return None

        usage = None
        tokens = raw.get("tokens", {})
        if tokens:
            usage = TokenUsage(
                input_tokens=tokens.get("input", 0),
                output_tokens=tokens.get("output", 0),
            )

        return NormalizedEvent(
            event_id=str(raw.get("id", "")),
            session_id=session_id,
            timestamp=raw.get("timestamp", ""),
            sequence_number=seq,
            role=role,
            content=content_blocks,
            usage=usage,
            harness=self.HARNESS_ID,
            model=raw.get("model", ""),
        )

    @staticmethod
    def _parse_content_block(block: Any) -> ContentBlock | None:
        if isinstance(block, str):
            return ContentBlock(type=ContentType.TEXT, text=block)
        if not isinstance(block, dict):
            return None

        block_type = block.get("type", "")
        if block_type == "text":
            return ContentBlock(type=ContentType.TEXT, text=block.get("text", ""))
        if block_type == "thinking":
            return ContentBlock(
                type=ContentType.THINKING,
                text=block.get("text", block.get("thinking", "")),
            )
        if block_type == "tool_use":
            tool_input = block.get("input", {})
            return ContentBlock(
                type=ContentType.TOOL_USE,
                tool_name=block.get("name", ""),
                tool_input=tool_input if isinstance(tool_input, dict) else {"raw": tool_input},
                tool_use_id=block.get("id", ""),
            )
        if block_type == "tool_result":
            content = block.get("content", block.get("text", ""))
            return ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=content if isinstance(content, str) else json.dumps(content),
                tool_use_id=block.get("tool_use_id", ""),
                is_error=block.get("is_error", False),
            )
        return ContentBlock(type=ContentType.UNKNOWN, text=str(block))
