"""Pi CLI transcript adapter.

Reads session transcripts from
``~/.pi/sessions/session-<timestamp>-<short_id>.ndjson``.

Pi's ``--mode json`` output is an **NDJSON event stream** (design.md §
Empirical CLI findings, E8): one JSON object per line, with event ``type`` in
``{session, agent_start, turn_start, message_start, message_update,
message_end, turn_end, agent_end, agent_settled}``. Message content lives on
``message_end`` events under ``content[]`` where each block carries a ``type``
(``text`` / ``thinking`` / ``tool_use`` / ``tool_result``). The final assistant
answer is the last ``message_end`` assistant text block.

Only terminal message events (``message_end``) are materialized; the
``message_start`` / ``message_update`` deltas for the same message are ignored
so a streamed message is not double-counted.
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
    "system": EventRole.SYSTEM,
}


class PiCLIAdapter(AdapterBase):
    """Adapter for Pi CLI NDJSON session transcripts.

    Parameters
    ----------
    base_dir:
        Override for the Pi sessions directory.  Defaults to
        ``~/.pi/sessions``.
    """

    HARNESS_ID = "pi_cli"
    SCHEMA_VERSION = "pi-ndjson-v1"

    def __init__(self, base_dir: str | None = None) -> None:
        if base_dir is not None:
            self._base_dir = Path(base_dir)
        else:
            self._base_dir = Path.home() / ".pi" / "sessions"

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_sessions(self) -> list[SessionSummary]:
        if not self._base_dir.exists():
            self._warn_unavailable(f"directory not found: {self._base_dir}")
            return []

        sessions: list[SessionSummary] = []
        for ndjson_file in self._base_dir.glob("session-*.ndjson"):
            session_id = ndjson_file.stem
            start_time = ""
            model = ""
            try:
                with open(ndjson_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        rec = json.loads(line)
                        if rec.get("type") == "session":
                            session_id = rec.get("sessionId", ndjson_file.stem)
                            start_time = rec.get("startTime", "")
                            model = rec.get("model", "")
                            break
            except (json.JSONDecodeError, OSError):
                pass

            sessions.append(
                SessionSummary(
                    session_id=session_id,
                    harness=self.HARNESS_ID,
                    source_path=str(ndjson_file),
                    start_time=start_time,
                    metadata={"model": model} if model else {},
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

        session_model = ""
        events: list[NormalizedEvent] = []
        seq = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = rec.get("type", "")

            if etype == "session":
                session_model = rec.get("model", "")
                continue

            # Only terminal message events carry the settled content[].
            if etype == "message_end":
                event = self._parse_message_end(rec, session_id, seq, session_model)
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

        candidates = [*self._base_dir.glob(f"*{session_id}*.ndjson")]
        if candidates:
            return candidates[0]

        for f in self._base_dir.glob("session-*.ndjson"):
            try:
                with open(f, "r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        rec = json.loads(line)
                        if rec.get("type") == "session" and rec.get("sessionId") == session_id:
                            return f
                        break
            except (json.JSONDecodeError, OSError):
                continue
        return None

    def _parse_message_end(
        self,
        rec: dict[str, Any],
        session_id: str,
        seq: int,
        session_model: str,
    ) -> NormalizedEvent | None:
        # Real ``pi --mode json`` message_end records nest role/content/usage/
        # model under a ``message`` object; older flat records keep them at the
        # top level. Unwrap so both shapes normalize.
        payload = rec.get("message", rec)
        if not isinstance(payload, dict):
            payload = rec

        role = _ROLE_MAP.get(payload.get("role", ""))
        if role is None:
            return None

        content_blocks: list[ContentBlock] = []
        raw_content = payload.get("content", [])
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
        tokens = payload.get("usage", payload.get("tokens", {}))
        if tokens:
            usage = TokenUsage(
                input_tokens=tokens.get("input", tokens.get("input_tokens", 0)),
                output_tokens=tokens.get("output", tokens.get("output_tokens", 0)),
            )

        return NormalizedEvent(
            event_id=str(
                payload.get("id", payload.get("messageId", payload.get("responseId", "")))
            ),
            session_id=session_id,
            timestamp=payload.get("timestamp", ""),
            sequence_number=seq,
            role=role,
            content=content_blocks,
            usage=usage,
            harness=self.HARNESS_ID,
            model=payload.get("model", session_model),
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
            tool_input = block.get("input", block.get("arguments", {}))
            return ContentBlock(
                type=ContentType.TOOL_USE,
                tool_name=block.get("name", ""),
                tool_input=tool_input if isinstance(tool_input, dict) else {"raw": tool_input},
                tool_use_id=block.get("id", block.get("tool_use_id", "")),
            )
        if block_type == "tool_result":
            content = block.get("content", block.get("text", ""))
            return ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=content if isinstance(content, str) else json.dumps(content),
                tool_use_id=block.get("tool_use_id", block.get("id", "")),
                is_error=block.get("is_error", False),
            )
        return ContentBlock(type=ContentType.UNKNOWN, text=str(block))
