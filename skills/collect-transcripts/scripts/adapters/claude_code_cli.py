"""Claude Code CLI transcript adapter.

Reads session transcripts from ``~/.claude/projects/<encoded-cwd>/<session-id>.jsonl``.
The ``<encoded-cwd>`` is the absolute working directory with every non-alphanumeric
character replaced by ``-`` (e.g. ``/Users/me/proj`` -> ``-Users-me-proj``).

Schema: JSONL one event per line.  Top-level ``type`` discriminates:
  - ``summary`` — session metadata header
  - ``human``   — user message
  - ``assistant`` — assistant response with content blocks
  - ``tool_result`` — tool execution result

Message content blocks use ``type`` in {text, thinking, tool_use, tool_result}.
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


class ClaudeCodeCLIAdapter(AdapterBase):
    """Adapter for Claude Code CLI session transcripts.

    Parameters
    ----------
    base_dir:
        Override for the projects directory.  Defaults to
        ``~/.claude/projects``.
    """

    HARNESS_ID = "claude_code_cli"
    SCHEMA_VERSION = "1.0"

    def __init__(self, base_dir: str | None = None) -> None:
        if base_dir is not None:
            self._base_dir = Path(base_dir)
        else:
            self._base_dir = Path.home() / ".claude" / "projects"

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_sessions(self) -> list[SessionSummary]:
        if not self._base_dir.exists():
            self._warn_unavailable(f"directory not found: {self._base_dir}")
            return []

        sessions: list[SessionSummary] = []
        for jsonl_file in self._base_dir.glob("*/*.jsonl"):
            session_id = jsonl_file.stem
            # Strip the "session-" prefix if present
            if session_id.startswith("session-"):
                session_id = session_id[len("session-"):]

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
                    metadata={"project_dir": jsonl_file.parent.name},
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
        version = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.debug("Skipping malformed line in %s: %s", session_id, exc)
                continue

            event_type = raw.get("type", "")

            if event_type == "summary":
                version = raw.get("version", "")
                continue

            if event_type == "human":
                event = self._parse_human_event(raw, session_id, seq, version)
                events.append(event)
                seq += 1

            elif event_type == "assistant":
                event = self._parse_assistant_event(raw, session_id, seq, version)
                events.append(event)
                seq += 1

            elif event_type == "tool_result":
                event = self._parse_tool_result_event(raw, session_id, seq, version)
                events.append(event)
                seq += 1

        return events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_session_file(self, session_id: str) -> Path | None:
        """Find the JSONL file for a given session ID."""
        if not self._base_dir.exists():
            return None

        # Try exact match first, then with prefix
        candidates = [
            *self._base_dir.glob(f"*/{session_id}.jsonl"),
            *self._base_dir.glob(f"*/session-{session_id}.jsonl"),
        ]
        return candidates[0] if candidates else None

    def _parse_human_event(
        self,
        raw: dict[str, Any],
        session_id: str,
        seq: int,
        version: str,
    ) -> NormalizedEvent:
        content_blocks: list[ContentBlock] = []
        message = raw.get("message", {})
        raw_content = message.get("content", [])

        if isinstance(raw_content, str):
            content_blocks.append(ContentBlock(type=ContentType.TEXT, text=raw_content))
        elif isinstance(raw_content, list):
            for block in raw_content:
                content_blocks.append(self._parse_content_block(block))

        return NormalizedEvent(
            event_id=raw.get("uuid", ""),
            session_id=session_id,
            timestamp=raw.get("timestamp", ""),
            sequence_number=seq,
            role=EventRole.USER,
            content=content_blocks,
            harness=self.HARNESS_ID,
            version=version,
            metadata={
                k: v
                for k, v in raw.items()
                if k in ("parentUuid", "cwd", "gitBranch")
            },
        )

    def _parse_assistant_event(
        self,
        raw: dict[str, Any],
        session_id: str,
        seq: int,
        version: str,
    ) -> NormalizedEvent:
        content_blocks: list[ContentBlock] = []
        message = raw.get("message", {})
        raw_content = message.get("content", [])

        if isinstance(raw_content, str):
            content_blocks.append(ContentBlock(type=ContentType.TEXT, text=raw_content))
        elif isinstance(raw_content, list):
            for block in raw_content:
                content_blocks.append(self._parse_content_block(block))

        # Parse usage
        usage = None
        raw_usage = message.get("usage", {})
        if raw_usage:
            usage = TokenUsage(
                input_tokens=raw_usage.get("input_tokens", 0),
                output_tokens=raw_usage.get("output_tokens", 0),
                cache_creation_input_tokens=raw_usage.get(
                    "cache_creation_input_tokens", 0
                ),
                cache_read_input_tokens=raw_usage.get("cache_read_input_tokens", 0),
            )

        return NormalizedEvent(
            event_id=raw.get("uuid", ""),
            session_id=session_id,
            timestamp=raw.get("timestamp", ""),
            sequence_number=seq,
            role=EventRole.ASSISTANT,
            content=content_blocks,
            usage=usage,
            harness=self.HARNESS_ID,
            version=version,
            metadata={
                k: v
                for k, v in raw.items()
                if k in ("parentUuid", "cwd", "gitBranch")
            },
        )

    def _parse_tool_result_event(
        self,
        raw: dict[str, Any],
        session_id: str,
        seq: int,
        version: str,
    ) -> NormalizedEvent:
        raw_content = raw.get("content", [])
        text = ""
        if isinstance(raw_content, str):
            text = raw_content
        elif isinstance(raw_content, list):
            text_parts = []
            for block in raw_content:
                if isinstance(block, dict):
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            text = "\n".join(text_parts)

        content_blocks = [
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=text,
                tool_use_id=raw.get("tool_use_id", ""),
                is_error=raw.get("is_error", False),
            )
        ]

        return NormalizedEvent(
            event_id=raw.get("uuid", ""),
            session_id=session_id,
            timestamp=raw.get("timestamp", ""),
            sequence_number=seq,
            role=EventRole.TOOL,
            content=content_blocks,
            harness=self.HARNESS_ID,
            version=version,
        )

    @staticmethod
    def _parse_content_block(block: dict[str, Any]) -> ContentBlock:
        """Parse a single content block from raw Claude Code CLI format."""
        block_type = block.get("type", "unknown")

        if block_type == "text":
            return ContentBlock(type=ContentType.TEXT, text=block.get("text", ""))

        if block_type == "thinking":
            return ContentBlock(
                type=ContentType.THINKING,
                text=block.get("thinking", block.get("text", "")),
            )

        if block_type == "tool_use":
            return ContentBlock(
                type=ContentType.TOOL_USE,
                tool_name=block.get("name", ""),
                tool_input=block.get("input", {}),
                tool_use_id=block.get("id", ""),
            )

        if block_type == "tool_result":
            return ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=block.get("text", ""),
                tool_use_id=block.get("tool_use_id", ""),
                is_error=block.get("is_error", False),
            )

        return ContentBlock(type=ContentType.UNKNOWN, text=str(block))
