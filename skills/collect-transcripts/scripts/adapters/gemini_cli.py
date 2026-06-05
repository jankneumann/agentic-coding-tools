"""Gemini CLI transcript adapter.

Reads session transcripts from
``~/.gemini/tmp/<project_hash>/chats/session-<timestamp>-<short_id>.json``
(JSONL despite the ``.json`` extension).

Schema (from ``chatRecordingService.ts``):
- Initial metadata record: sessionId, projectHash, startTime, lastUpdated,
  kind (main|subagent), messages
- Per-message MessageRecord: id, timestamp, type (user|gemini), content
  (Google GenAI Part union: text, functionCall, functionResponse),
  toolCalls, model, tokens
- Update operations: ``$set`` and ``$rewindTo``

Tool calls in ``toolCalls[]`` have displayName, description, args, result.
Content follows Google GenAI Part union (text | functionCall |
functionResponse | inlineData).
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


class GeminiCLIAdapter(AdapterBase):
    """Adapter for Gemini CLI session transcripts.

    Parameters
    ----------
    base_dir:
        Override for the Gemini data directory.  Defaults to
        ``~/.gemini/tmp``.
    """

    HARNESS_ID = "gemini_cli"
    SCHEMA_VERSION = "chatRecordingService-v1"

    def __init__(self, base_dir: str | None = None) -> None:
        if base_dir is not None:
            self._base_dir = Path(base_dir)
        else:
            self._base_dir = Path.home() / ".gemini" / "tmp"

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_sessions(self) -> list[SessionSummary]:
        if not self._base_dir.exists():
            self._warn_unavailable(f"directory not found: {self._base_dir}")
            return []

        sessions: list[SessionSummary] = []
        # Pattern: <project_hash>/chats/session-*.json
        for json_file in self._base_dir.glob("*/chats/session-*.json"):
            session_id = ""
            start_time = ""
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        header = json.loads(first_line)
                        session_id = header.get("sessionId", json_file.stem)
                        start_time = header.get("startTime", "")
            except (json.JSONDecodeError, OSError):
                session_id = json_file.stem

            sessions.append(
                SessionSummary(
                    session_id=session_id,
                    harness=self.HARNESS_ID,
                    source_path=str(json_file),
                    start_time=start_time,
                    metadata={"project_hash": json_file.parent.parent.name},
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

            # Skip metadata header (has sessionId, projectHash, messages=[])
            if "sessionId" in raw and "messages" in raw:
                continue

            # Skip $set and $rewindTo operations
            if "$set" in raw or "$rewindTo" in raw:
                continue

            # Parse message records
            if "id" in raw and "type" in raw:
                event = self._parse_message_record(raw, session_id, seq)
                if event:
                    events.append(event)
                    seq += 1

        return events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_session_file(self, session_id: str) -> Path | None:
        """Find the session file for a given session ID."""
        if not self._base_dir.exists():
            return None

        # Search by glob patterns
        candidates: list[Path] = []

        # Try matching session ID in filenames
        for f in self._base_dir.glob(f"*/chats/*{session_id}*.json"):
            candidates.append(f)

        if not candidates:
            # Scan headers for matching sessionId
            for f in self._base_dir.glob("*/chats/session-*.json"):
                try:
                    first_line = f.read_text(encoding="utf-8").split("\n", 1)[0]
                    header = json.loads(first_line)
                    if header.get("sessionId") == session_id:
                        candidates.append(f)
                        break
                except (json.JSONDecodeError, OSError):
                    continue

        return candidates[0] if candidates else None

    def _parse_message_record(
        self,
        raw: dict[str, Any],
        session_id: str,
        seq: int,
    ) -> NormalizedEvent | None:
        msg_type = raw.get("type", "")
        msg_id = raw.get("id", "")
        timestamp = raw.get("timestamp", "")
        model = raw.get("model", "")

        # Determine role
        if msg_type == "user":
            role = EventRole.USER
        elif msg_type == "gemini":
            role = EventRole.ASSISTANT
        else:
            return None

        content_blocks: list[ContentBlock] = []

        # Parse content field (Google GenAI Part union)
        raw_content = raw.get("content", {})
        if isinstance(raw_content, dict):
            # Simple text content
            if "text" in raw_content:
                content_blocks.append(
                    ContentBlock(type=ContentType.TEXT, text=raw_content["text"])
                )
            # Function call content
            if "functionCall" in raw_content:
                fc = raw_content["functionCall"]
                content_blocks.append(
                    ContentBlock(
                        type=ContentType.TOOL_USE,
                        tool_name=fc.get("name", ""),
                        tool_input=fc.get("args", {}),
                        tool_use_id=msg_id,
                    )
                )
            # Function response content
            if "functionResponse" in raw_content:
                fr = raw_content["functionResponse"]
                content_blocks.append(
                    ContentBlock(
                        type=ContentType.TOOL_RESULT,
                        text=json.dumps(fr.get("response", {})),
                        tool_use_id=msg_id,
                    )
                )
        elif isinstance(raw_content, str):
            content_blocks.append(
                ContentBlock(type=ContentType.TEXT, text=raw_content)
            )

        # Parse displayContent if no content blocks yet
        if not content_blocks:
            display = raw.get("displayContent", "")
            if display:
                content_blocks.append(
                    ContentBlock(type=ContentType.TEXT, text=display)
                )

        # Parse toolCalls array (Gemini-specific)
        tool_calls = raw.get("toolCalls", [])
        for tc in tool_calls:
            display_name = tc.get("displayName", "")
            args = tc.get("args", {})
            result = tc.get("result", "")
            tc_id = f"{msg_id}-tc-{display_name}"

            content_blocks.append(
                ContentBlock(
                    type=ContentType.TOOL_USE,
                    tool_name=display_name,
                    tool_input=args if isinstance(args, dict) else {"raw": args},
                    tool_use_id=tc_id,
                )
            )
            if result:
                content_blocks.append(
                    ContentBlock(
                        type=ContentType.TOOL_RESULT,
                        text=str(result),
                        tool_use_id=tc_id,
                    )
                )

        # Parse thoughts (Gemini thinking)
        thoughts = raw.get("thoughts", "")
        if thoughts:
            content_blocks.insert(
                0,
                ContentBlock(type=ContentType.THINKING, text=thoughts),
            )

        if not content_blocks:
            return None

        # Parse token usage
        usage = None
        tokens = raw.get("tokens", {})
        if tokens:
            from normalize import TokenUsage

            usage = TokenUsage(
                input_tokens=tokens.get("input", 0),
                output_tokens=tokens.get("output", 0),
            )

        return NormalizedEvent(
            event_id=msg_id,
            session_id=session_id,
            timestamp=timestamp,
            sequence_number=seq,
            role=role,
            content=content_blocks,
            usage=usage,
            harness=self.HARNESS_ID,
            model=model,
        )
