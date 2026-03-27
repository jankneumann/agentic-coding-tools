"""Tests for extract_session_log.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from extract_session_log import (
    _format_handoffs_as_session_log,
    _parse_jsonl_messages,
    generate_self_summary_prompt,
    try_extract_from_handoffs,
)


# --- JSONL parsing ---


class TestParseJsonlMessages:
    def test_simple_messages(self) -> None:
        content = (
            '{"role": "user", "content": "Hello"}\n'
            '{"role": "assistant", "content": "Hi there"}\n'
        )
        messages = _parse_jsonl_messages(content)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

    def test_structured_content_blocks(self) -> None:
        content = json.dumps({
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Part 1"},
                {"type": "text", "text": "Part 2"},
            ]
        }) + "\n"
        messages = _parse_jsonl_messages(content)
        assert len(messages) == 1
        assert "Part 1" in messages[0]["content"]
        assert "Part 2" in messages[0]["content"]

    def test_empty_lines_skipped(self) -> None:
        content = '{"role": "user", "content": "Hello"}\n\n\n'
        messages = _parse_jsonl_messages(content)
        assert len(messages) == 1

    def test_invalid_json_skipped(self) -> None:
        content = (
            '{"role": "user", "content": "Hello"}\n'
            'not valid json\n'
            '{"role": "assistant", "content": "Hi"}\n'
        )
        messages = _parse_jsonl_messages(content)
        assert len(messages) == 2

    def test_missing_role_skipped(self) -> None:
        content = '{"content": "Hello"}\n'
        messages = _parse_jsonl_messages(content)
        assert len(messages) == 0

    def test_missing_content_skipped(self) -> None:
        content = '{"role": "user"}\n'
        messages = _parse_jsonl_messages(content)
        assert len(messages) == 0


# --- Handoff extraction ---


class TestHandoffExtraction:
    def test_extract_from_handoff_file(self) -> None:
        handoffs = [
            {
                "summary": "Planned the store-conversation-history feature",
                "agent_name": "plan-agent",
                "session_id": "sess-123",
                "decisions": [
                    "Use file-based storage",
                    "3-tier extraction strategy",
                ],
                "completed_work": ["Created proposal", "Wrote specs"],
                "next_steps": ["Implement sanitization script"],
                "created_at": "2026-03-27T10:00:00Z",
            }
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(handoffs, f)
            f.flush()

            result = try_extract_from_handoffs(
                "store-conversation-history",
                handoff_source=f.name,
            )

        assert result is not None
        assert "store-conversation-history" in result
        assert "Use file-based storage" in result
        assert "3-tier extraction strategy" in result
        assert "handoff-documents" in result

        Path(f.name).unlink()

    def test_no_relevant_handoffs(self) -> None:
        handoffs = [{"summary": "Unrelated work", "decisions": []}]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(handoffs, f)
            f.flush()

            result = try_extract_from_handoffs(
                "nonexistent-change-id",
                handoff_source=f.name,
            )

        assert result is None
        Path(f.name).unlink()

    def test_missing_handoff_file(self) -> None:
        result = try_extract_from_handoffs(
            "test-change",
            handoff_source="/nonexistent/path.json",
        )
        assert result is None


# --- Handoff formatting ---


class TestFormatHandoffs:
    def test_basic_formatting(self) -> None:
        handoffs = [
            {
                "summary": "Completed planning phase",
                "agent_name": "planner",
                "session_id": "s1",
                "decisions": ["Decision A", "Decision B"],
                "completed_work": ["Task 1"],
                "next_steps": ["Task 2"],
                "created_at": "2026-03-27",
            }
        ]
        result = _format_handoffs_as_session_log(handoffs, "test-change")
        assert "# Session Log: test-change" in result
        assert "## Key Decisions" in result
        assert "Decision A" in result
        assert "Decision B" in result
        assert "## Open Questions" in result
        assert "Task 2" in result
        assert "| Source | handoff-documents |" in result

    def test_multiple_agents(self) -> None:
        handoffs = [
            {"agent_name": "agent-1", "decisions": ["D1"], "summary": "A"},
            {"agent_name": "agent-2", "decisions": ["D2"], "summary": "B"},
        ]
        result = _format_handoffs_as_session_log(handoffs, "test")
        assert "agent-1" in result
        assert "agent-2" in result

    def test_empty_fields(self) -> None:
        handoffs = [{"summary": "Minimal handoff"}]
        result = _format_handoffs_as_session_log(handoffs, "test")
        assert "# Session Log: test" in result
        assert "No explicit decisions" in result


# --- Self-summary prompt ---


class TestSelfSummaryPrompt:
    def test_prompt_contains_change_id(self) -> None:
        prompt = generate_self_summary_prompt("my-feature")
        assert "my-feature" in prompt

    def test_prompt_has_required_sections(self) -> None:
        prompt = generate_self_summary_prompt("test")
        assert "## Summary" in prompt
        assert "## Key Decisions" in prompt
        assert "## Alternatives Considered" in prompt
        assert "## Trade-offs" in prompt
        assert "## Open Questions" in prompt
        assert "## Session Metadata" in prompt

    def test_prompt_includes_safety_warnings(self) -> None:
        prompt = generate_self_summary_prompt("test")
        assert "secrets" in prompt.lower() or "API keys" in prompt
        assert "500 lines" in prompt
