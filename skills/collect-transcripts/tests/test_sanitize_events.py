"""Tests for transcript-specific sanitization.

Covers:
- Tool-call argument blobs are sanitized (secrets in tool_input)
- Tool-result output text is sanitized
- Metadata is sanitized
- Existing session-log redaction rules still apply (secrets, entropy, paths)
- Clean events pass through unchanged
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestSanitizeContentBlock:
    """Test sanitization of individual content blocks."""

    def test_text_block_redacts_api_key(self) -> None:
        from normalize import ContentBlock, ContentType
        from sanitize_events import sanitize_content_block

        block = ContentBlock(
            type=ContentType.TEXT,
            text="Use this key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890",
        )
        sanitized, redactions = sanitize_content_block(block)
        assert "sk-ant-" not in sanitized.text
        assert "[REDACTED:" in sanitized.text
        assert len(redactions) >= 1

    def test_tool_input_redacts_secret(self) -> None:
        from normalize import ContentBlock, ContentType
        from sanitize_events import sanitize_content_block

        block = ContentBlock(
            type=ContentType.TOOL_USE,
            tool_name="Bash",
            tool_input={
                "command": "export API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
            },
            tool_use_id="tu-001",
        )
        sanitized, redactions = sanitize_content_block(block)
        # The serialized tool_input should not contain the key
        import json
        input_str = json.dumps(sanitized.tool_input)
        assert "sk-ant-" not in input_str
        assert len(redactions) >= 1

    def test_tool_result_redacts_connection_string(self) -> None:
        from normalize import ContentBlock, ContentType
        from sanitize_events import sanitize_content_block

        block = ContentBlock(
            type=ContentType.TOOL_RESULT,
            text="Connected to postgres://admin:secret123@db.internal.company:5432/prod",
            tool_use_id="tu-001",
        )
        sanitized, redactions = sanitize_content_block(block)
        assert "postgres://" not in sanitized.text
        assert len(redactions) >= 1

    def test_clean_text_passes_through(self) -> None:
        from normalize import ContentBlock, ContentType
        from sanitize_events import sanitize_content_block

        block = ContentBlock(
            type=ContentType.TEXT,
            text="This is normal text without any secrets.",
        )
        sanitized, redactions = sanitize_content_block(block)
        assert sanitized.text == "This is normal text without any secrets."
        assert redactions == []

    def test_preserves_block_type(self) -> None:
        from normalize import ContentBlock, ContentType
        from sanitize_events import sanitize_content_block

        block = ContentBlock(type=ContentType.THINKING, text="Let me think...")
        sanitized, _ = sanitize_content_block(block)
        assert sanitized.type == ContentType.THINKING


class TestSanitizeEvent:
    """Test sanitization of full NormalizedEvent."""

    def test_sanitizes_all_content_blocks(self) -> None:
        from normalize import ContentBlock, ContentType, EventRole, NormalizedEvent
        from sanitize_events import sanitize_event

        event = NormalizedEvent(
            event_id="evt-001",
            session_id="sess-001",
            role=EventRole.ASSISTANT,
            content=[
                ContentBlock(
                    type=ContentType.TEXT,
                    text="Here is the key: ghp_1234567890abcdefghijklmnopqrstuvwxyz12",
                ),
                ContentBlock(
                    type=ContentType.TOOL_USE,
                    tool_name="Bash",
                    tool_input={"command": "echo $AWS_SECRET_KEY"},
                    tool_use_id="tu-001",
                ),
            ],
            harness="claude_code_cli",
        )
        sanitized, redactions = sanitize_event(event)
        assert "ghp_" not in sanitized.content[0].text
        assert len(redactions) >= 1

    def test_sanitizes_metadata(self) -> None:
        from normalize import EventRole, NormalizedEvent
        from sanitize_events import sanitize_event

        event = NormalizedEvent(
            event_id="evt-001",
            role=EventRole.USER,
            metadata={"cwd": "/home/realuser/project"},
            harness="claude_code_cli",
        )
        sanitized, _ = sanitize_event(event)
        import json
        meta_str = json.dumps(sanitized.metadata)
        assert "/home/realuser/" not in meta_str

    def test_preserves_event_identity(self) -> None:
        from normalize import ContentBlock, ContentType, EventRole, NormalizedEvent
        from sanitize_events import sanitize_event

        event = NormalizedEvent(
            event_id="evt-001",
            session_id="sess-001",
            timestamp="2026-05-01T10:00:00Z",
            role=EventRole.USER,
            content=[ContentBlock(type=ContentType.TEXT, text="Hi")],
            harness="claude_code_cli",
        )
        sanitized, _ = sanitize_event(event)
        assert sanitized.event_id == "evt-001"
        assert sanitized.session_id == "sess-001"
        assert sanitized.timestamp == "2026-05-01T10:00:00Z"
        assert sanitized.harness == "claude_code_cli"


class TestSanitizeEventStream:
    """Test sanitization of event streams."""

    def test_sanitizes_full_stream(self) -> None:
        from normalize import ContentBlock, ContentType, EventRole, NormalizedEvent
        from sanitize_events import sanitize_event_stream

        events = [
            NormalizedEvent(
                event_id="e1",
                role=EventRole.USER,
                content=[ContentBlock(type=ContentType.TEXT, text="Hello")],
                harness="test",
            ),
            NormalizedEvent(
                event_id="e2",
                role=EventRole.ASSISTANT,
                content=[
                    ContentBlock(
                        type=ContentType.TEXT,
                        text="Key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890",
                    )
                ],
                harness="test",
            ),
        ]
        sanitized, redactions = sanitize_event_stream(events)
        assert len(sanitized) == 2
        assert "sk-ant-" not in sanitized[1].content[0].text
        assert len(redactions) >= 1

    def test_empty_stream_passes_through(self) -> None:
        from sanitize_events import sanitize_event_stream

        sanitized, redactions = sanitize_event_stream([])
        assert sanitized == []
        assert redactions == []
