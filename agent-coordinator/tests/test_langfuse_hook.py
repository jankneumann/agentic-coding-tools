"""Tests for the Langfuse Claude Code Stop hook (scripts/langfuse_hook.py)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def hook_module():
    """Import the hook script as a module."""
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        if "langfuse_hook" in sys.modules:
            del sys.modules["langfuse_hook"]
        mod = importlib.import_module("langfuse_hook")
        yield mod
    finally:
        sys.path.pop(0)
        if "langfuse_hook" in sys.modules:
            del sys.modules["langfuse_hook"]


class TestSanitize:
    def test_redacts_api_keys(self, hook_module):
        text = "key: sk-abcdefghijklmnopqrstuvwxyz123456"
        result = hook_module.sanitize(text)
        assert "SK-REDACTED" in result
        assert "sk-abcdefghijklmnop" not in result

    def test_redacts_bearer_tokens(self, hook_module):
        text = "Authorization: Bearer eyJhbGciOi.token.here"
        result = hook_module.sanitize(text)
        assert "Bearer REDACTED" in result

    def test_redacts_password_patterns(self, hook_module):
        text = "password=super_secret_123"
        result = hook_module.sanitize(text)
        assert "super_secret_123" not in result

    def test_redacts_langfuse_keys(self, hook_module):
        # Standalone Langfuse key (not in a key=value context)
        text = "using key pk-lf-local-coding-agents for tracing"
        result = hook_module.sanitize(text)
        assert "pk-lf-local" not in result
        assert "LF-KEY-REDACTED" in result

    def test_redacts_langfuse_secret_in_env(self, hook_module):
        # Langfuse key inside a key=value pair — either specific or generic pattern redacts it
        text = "LANGFUSE_SECRET_KEY=sk-lf-local-coding-agents"
        result = hook_module.sanitize(text)
        assert "sk-lf-local-coding-agents" not in result

    def test_redacts_jwt_tokens(self, hook_module):
        # JWT outside a key=value context
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        )
        result = hook_module.sanitize(f"header: {jwt}")
        assert "eyJhbGciOi" not in result
        assert "JWT-REDACTED" in result

    def test_preserves_normal_text(self, hook_module):
        text = "This is a normal message about code"
        assert hook_module.sanitize(text) == text


class TestGroupIntoTurns:
    def test_empty_input(self, hook_module):
        assert hook_module.group_into_turns([]) == []

    def test_single_turn(self, hook_module):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!", "model": "claude-3"},
        ]
        turns = hook_module.group_into_turns(messages)
        assert len(turns) == 1
        assert turns[0]["user_message"] == "Hello"
        assert turns[0]["assistant_messages"] == ["Hi there!"]
        assert turns[0]["model"] == "claude-3"

    def test_multiple_turns(self, hook_module):
        messages = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Second"},
            {"role": "assistant", "content": "Response 2"},
        ]
        turns = hook_module.group_into_turns(messages)
        assert len(turns) == 2
        assert turns[0]["user_message"] == "First"
        assert turns[1]["user_message"] == "Second"

    def test_tool_calls(self, hook_module):
        messages = [
            {"role": "user", "content": "Read the file"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me read that."},
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"path": "/test.py"},
                    },
                ],
            },
            {
                "role": "tool",
                "tool_use_id": "tool-1",
                "content": "file contents here",
            },
        ]
        turns = hook_module.group_into_turns(messages)
        assert len(turns) == 1
        assert len(turns[0]["tool_calls"]) == 1
        assert turns[0]["tool_calls"][0]["name"] == "Read"
        assert turns[0]["tool_calls"][0]["output"] == "file contents here"

    def test_content_blocks(self, hook_module):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Part 1"},
                    {"type": "text", "text": "Part 2"},
                ],
            },
            {"role": "assistant", "content": "OK"},
        ]
        turns = hook_module.group_into_turns(messages)
        assert "Part 1\nPart 2" == turns[0]["user_message"]


class TestExtractText:
    def test_string_content(self, hook_module):
        assert hook_module._extract_text({"content": "hello"}) == "hello"

    def test_list_content(self, hook_module):
        msg = {"content": [{"type": "text", "text": "hello"}]}
        assert hook_module._extract_text(msg) == "hello"

    def test_empty_content(self, hook_module):
        assert hook_module._extract_text({"content": ""}) == ""


class TestTruncate:
    def test_short_text(self, hook_module):
        assert hook_module._truncate("short", 100) == "short"

    def test_long_text(self, hook_module):
        result = hook_module._truncate("a" * 200, 50)
        assert len(result) == 50
        assert result.endswith("...")


class TestParseTranscriptLines:
    def test_reads_from_offset(self, hook_module, tmp_path):
        transcript = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"role": "user", "content": "msg1"}),
            json.dumps({"role": "assistant", "content": "resp1"}),
            json.dumps({"role": "user", "content": "msg2"}),
        ]
        transcript.write_text("\n".join(lines) + "\n")

        # Skip first 2 lines
        messages, lines_consumed = hook_module.parse_transcript_lines(transcript, 2)
        assert len(messages) == 1
        assert messages[0]["content"] == "msg2"
        assert lines_consumed == 1

    def test_handles_missing_file(self, hook_module, tmp_path):
        missing = tmp_path / "nonexistent.jsonl"
        messages, lines_consumed = hook_module.parse_transcript_lines(missing, 0)
        assert messages == []
        assert lines_consumed == 0

    def test_skips_invalid_json(self, hook_module, tmp_path):
        transcript = tmp_path / "test.jsonl"
        transcript.write_text('{"valid": true}\nnot json\n{"also": "valid"}\n')
        messages, lines_consumed = hook_module.parse_transcript_lines(transcript, 0)
        assert len(messages) == 2
        assert lines_consumed == 3  # all 3 lines read, 1 was invalid JSON


class TestStateManagement:
    def test_load_save_roundtrip(self, hook_module, tmp_path, monkeypatch):
        monkeypatch.setattr(hook_module, "STATE_DIR", tmp_path)
        session_id = "test-session-123"

        # Initial load returns defaults
        state = hook_module.load_state(session_id)
        assert state["last_line"] == 0
        assert state["trace_count"] == 0

        # Save and reload
        state["last_line"] = 42
        state["trace_count"] = 5
        hook_module.save_state(session_id, state)

        reloaded = hook_module.load_state(session_id)
        assert reloaded["last_line"] == 42
        assert reloaded["trace_count"] == 5
