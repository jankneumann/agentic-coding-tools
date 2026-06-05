"""Tests for normalized event schema and round-trip serialization.

Covers:
- NormalizedEvent round-trip (to_dict -> from_dict)
- ContentBlock round-trip for each ContentType
- TokenUsage round-trip
- JSONL serialization / deserialization
- SessionSummary fields
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Path setup
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestContentBlock:
    """Content block round-trip tests."""

    def test_text_block_round_trip(self) -> None:
        from normalize import ContentBlock, ContentType

        block = ContentBlock(type=ContentType.TEXT, text="Hello world")
        d = block.to_dict()
        restored = ContentBlock.from_dict(d)
        assert restored.type == ContentType.TEXT
        assert restored.text == "Hello world"

    def test_thinking_block_round_trip(self) -> None:
        from normalize import ContentBlock, ContentType

        block = ContentBlock(type=ContentType.THINKING, text="Let me think...")
        d = block.to_dict()
        restored = ContentBlock.from_dict(d)
        assert restored.type == ContentType.THINKING
        assert restored.text == "Let me think..."

    def test_tool_use_block_round_trip(self) -> None:
        from normalize import ContentBlock, ContentType

        block = ContentBlock(
            type=ContentType.TOOL_USE,
            tool_name="Read",
            tool_input={"file_path": "/foo.py"},
            tool_use_id="tu-001",
        )
        d = block.to_dict()
        assert d["tool_name"] == "Read"
        assert d["tool_input"] == {"file_path": "/foo.py"}
        assert d["tool_use_id"] == "tu-001"

        restored = ContentBlock.from_dict(d)
        assert restored.type == ContentType.TOOL_USE
        assert restored.tool_name == "Read"
        assert restored.tool_input == {"file_path": "/foo.py"}
        assert restored.tool_use_id == "tu-001"

    def test_tool_result_block_round_trip(self) -> None:
        from normalize import ContentBlock, ContentType

        block = ContentBlock(
            type=ContentType.TOOL_RESULT,
            text="File contents here",
            tool_use_id="tu-001",
            is_error=False,
        )
        d = block.to_dict()
        restored = ContentBlock.from_dict(d)
        assert restored.type == ContentType.TOOL_RESULT
        assert restored.tool_use_id == "tu-001"
        assert restored.is_error is False
        assert restored.text == "File contents here"

    def test_tool_result_error_block(self) -> None:
        from normalize import ContentBlock, ContentType

        block = ContentBlock(
            type=ContentType.TOOL_RESULT,
            text="Error: file not found",
            tool_use_id="tu-002",
            is_error=True,
        )
        d = block.to_dict()
        restored = ContentBlock.from_dict(d)
        assert restored.is_error is True

    def test_unknown_type_defaults(self) -> None:
        from normalize import ContentBlock, ContentType

        restored = ContentBlock.from_dict({"type": "unknown"})
        assert restored.type == ContentType.UNKNOWN


class TestTokenUsage:
    """Token usage round-trip tests."""

    def test_round_trip(self) -> None:
        from normalize import TokenUsage

        usage = TokenUsage(
            input_tokens=500,
            output_tokens=200,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=100,
        )
        d = usage.to_dict()
        restored = TokenUsage.from_dict(d)
        assert restored.input_tokens == 500
        assert restored.output_tokens == 200
        assert restored.cache_read_input_tokens == 100

    def test_defaults_to_zero(self) -> None:
        from normalize import TokenUsage

        usage = TokenUsage.from_dict({})
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0


class TestNormalizedEvent:
    """Normalized event round-trip tests."""

    def test_full_round_trip(self) -> None:
        from normalize import (
            ContentBlock,
            ContentType,
            EventRole,
            NormalizedEvent,
            TokenUsage,
        )

        event = NormalizedEvent(
            event_id="evt-001",
            session_id="sess-123",
            timestamp="2026-05-01T10:00:00Z",
            sequence_number=1,
            role=EventRole.ASSISTANT,
            content=[
                ContentBlock(type=ContentType.TEXT, text="Hello"),
                ContentBlock(
                    type=ContentType.TOOL_USE,
                    tool_name="Read",
                    tool_input={"file_path": "/x.py"},
                    tool_use_id="tu-001",
                ),
            ],
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            harness="claude_code_cli",
            model="claude-opus-4-6",
            version="1.0.42",
            metadata={"cwd": "/proj"},
        )
        d = event.to_dict()
        restored = NormalizedEvent.from_dict(d)
        assert restored.event_id == "evt-001"
        assert restored.session_id == "sess-123"
        assert restored.role == EventRole.ASSISTANT
        assert len(restored.content) == 2
        assert restored.content[0].type == ContentType.TEXT
        assert restored.content[1].tool_name == "Read"
        assert restored.usage is not None
        assert restored.usage.input_tokens == 100
        assert restored.harness == "claude_code_cli"
        assert restored.model == "claude-opus-4-6"
        assert restored.metadata == {"cwd": "/proj"}

    def test_user_event_no_usage(self) -> None:
        from normalize import (
            ContentBlock,
            ContentType,
            EventRole,
            NormalizedEvent,
        )

        event = NormalizedEvent(
            event_id="evt-001",
            session_id="sess-123",
            role=EventRole.USER,
            content=[ContentBlock(type=ContentType.TEXT, text="Do something")],
        )
        d = event.to_dict()
        assert "usage" not in d
        restored = NormalizedEvent.from_dict(d)
        assert restored.usage is None

    def test_jsonl_round_trip(self) -> None:
        from normalize import (
            ContentBlock,
            ContentType,
            EventRole,
            NormalizedEvent,
        )

        event = NormalizedEvent(
            event_id="evt-001",
            session_id="sess-123",
            role=EventRole.USER,
            content=[ContentBlock(type=ContentType.TEXT, text="Hi")],
            harness="codex_cli",
        )
        line = event.to_jsonl_line()
        assert "\n" not in line
        restored = NormalizedEvent.from_jsonl_line(line)
        assert restored.event_id == "evt-001"
        assert restored.harness == "codex_cli"

    def test_tool_event_role(self) -> None:
        from normalize import EventRole, NormalizedEvent

        event = NormalizedEvent(role=EventRole.TOOL)
        d = event.to_dict()
        assert d["role"] == "tool"
        restored = NormalizedEvent.from_dict(d)
        assert restored.role == EventRole.TOOL


class TestSessionSummary:
    """Session summary field tests."""

    def test_basic_fields(self) -> None:
        from normalize import SessionSummary

        summary = SessionSummary(
            session_id="sess-001",
            harness="claude_code_cli",
            source_path="/path/to/session.jsonl",
            start_time="2026-05-01T10:00:00Z",
            event_count=10,
        )
        assert summary.session_id == "sess-001"
        assert summary.harness == "claude_code_cli"
        assert summary.event_count == 10

    def test_metadata_defaults_empty(self) -> None:
        from normalize import SessionSummary

        summary = SessionSummary(session_id="s1", harness="test")
        assert summary.metadata == {}
