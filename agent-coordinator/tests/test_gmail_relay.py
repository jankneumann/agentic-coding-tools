"""Tests for the Gmail relay: reply parsing, sender validation, and routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.notifications.relay import (
    clean_reply_body,
    extract_token,
    parse_reply,
    route_reply,
    validate_sender,
)

# --- extract_token ---


class TestExtractToken:
    def test_extract_token_from_subject(self) -> None:
        assert extract_token("Re: Approval needed [#AbCd1234]") == "AbCd1234"

    def test_extract_token_12_char(self) -> None:
        assert extract_token("Subject [#AbCdEfGh1234]") == "AbCdEfGh1234"

    def test_extract_token_start_of_subject(self) -> None:
        assert extract_token("[#Token123] Approval request") == "Token123"

    def test_extract_token_missing_returns_none(self) -> None:
        assert extract_token("Re: Just a normal subject") is None

    def test_extract_token_too_short(self) -> None:
        assert extract_token("[#Short]") is None

    def test_extract_token_too_long(self) -> None:
        assert extract_token("[#ThisTokenIsTooLong]") is None

    def test_extract_token_no_hash(self) -> None:
        assert extract_token("[AbCd1234]") is None


# --- parse_reply ---


class TestParseReply:
    def test_parse_reply_approved(self) -> None:
        assert parse_reply("approved") == ("approval", "approved")

    def test_parse_reply_approve(self) -> None:
        assert parse_reply("approve") == ("approval", "approved")

    def test_parse_reply_yes(self) -> None:
        assert parse_reply("Yes") == ("approval", "approved")

    def test_parse_reply_yes_uppercase(self) -> None:
        assert parse_reply("YES") == ("approval", "approved")

    def test_parse_reply_approved_uppercase(self) -> None:
        assert parse_reply("APPROVE") == ("approval", "approved")

    def test_parse_reply_denied(self) -> None:
        assert parse_reply("denied") == ("approval", "denied")

    def test_parse_reply_deny(self) -> None:
        assert parse_reply("deny") == ("approval", "denied")

    def test_parse_reply_no(self) -> None:
        assert parse_reply("no") == ("approval", "denied")

    def test_parse_reply_resolved(self) -> None:
        assert parse_reply("resolved") == ("gate_check", None)

    def test_parse_reply_skip(self) -> None:
        assert parse_reply("skip") == ("phase_skip", None)

    def test_parse_reply_freetext_guidance(self) -> None:
        cmd_type, cmd_value = parse_reply("Please focus on the API layer first")
        assert cmd_type == "guidance"
        assert cmd_value == "Please focus on the API layer first"

    def test_parse_reply_strips_punctuation(self) -> None:
        assert parse_reply("Approved!") == ("approval", "approved")

    def test_parse_reply_strips_punctuation_question(self) -> None:
        assert parse_reply("Approved?") == ("approval", "approved")

    def test_parse_reply_multiline_guidance_context(self) -> None:
        body = "approved\nBut please also check the edge cases"
        cmd_type, cmd_value = parse_reply(body)
        # First word is the command
        assert cmd_type == "approval"
        assert cmd_value == "approved"

    def test_parse_reply_empty_body(self) -> None:
        cmd_type, _ = parse_reply("")
        assert cmd_type == "guidance"


# --- validate_sender ---


class TestValidateSender:
    def test_validate_sender_case_insensitive(self) -> None:
        assert validate_sender("User@Example.COM", "user@example.com") is True

    def test_validate_sender_in_list(self) -> None:
        assert validate_sender("a@b.com", "x@y.com, a@b.com, c@d.com") is True

    def test_validate_sender_rejects_unlisted(self) -> None:
        assert validate_sender("evil@hacker.com", "user@example.com") is False

    def test_validate_sender_empty_allowlist(self) -> None:
        assert validate_sender("user@example.com", "") is False

    def test_validate_sender_whitespace_handling(self) -> None:
        assert validate_sender("a@b.com", "  a@b.com  ,  c@d.com  ") is True


# --- clean_reply_body ---


class TestCleanReplyBody:
    def test_clean_reply_body_strips_quoted_text(self) -> None:
        body = "Approved\n\n> On Monday, someone wrote:\n> Some quoted text"
        result = clean_reply_body(body)
        assert "Approved" in result
        assert "Some quoted text" not in result

    def test_clean_reply_body_strips_signature(self) -> None:
        body = "Approved\n\n-- \nJohn Doe\nCEO"
        result = clean_reply_body(body)
        assert "Approved" in result
        assert "John Doe" not in result

    def test_clean_reply_body_strips_on_wrote(self) -> None:
        body = "Looks good\n\nOn 2026-03-29 User wrote:\noriginal message"
        result = clean_reply_body(body)
        assert "Looks good" in result
        assert "original message" not in result

    def test_clean_reply_body_plain(self) -> None:
        body = "Just a simple reply"
        assert clean_reply_body(body) == "Just a simple reply"


# --- route_reply ---


class TestRouteReply:
    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.rpc = AsyncMock(return_value={})
        db.query = AsyncMock(return_value=[])
        db.insert = AsyncMock(return_value={})
        db.update = AsyncMock(return_value=[])
        return db

    @pytest.fixture
    def token_data(self) -> dict:
        return {
            "token": "AbCd1234",
            "entity_id": "req-123",
            "change_id": "change-456",
            "event_type": "approval.requested",
        }

    async def test_route_reply_approval(self, mock_db: AsyncMock, token_data: dict) -> None:
        # Mock the approval service decide_request
        mock_request = MagicMock()
        mock_request.status = "approved"

        with patch("src.approval.ApprovalService") as mock_approval_svc:
            instance = mock_approval_svc.return_value
            instance.decide_request = AsyncMock(return_value=mock_request)

            result = await route_reply("approval", "approved", token_data, mock_db)

        assert result["status"] == "routed"
        assert result["command_type"] == "approval"
        assert result["decision"] == "approved"

    async def test_route_reply_approval_denied(
        self, mock_db: AsyncMock, token_data: dict
    ) -> None:
        mock_request = MagicMock()
        mock_request.status = "denied"

        with patch("src.approval.ApprovalService") as mock_approval_svc:
            instance = mock_approval_svc.return_value
            instance.decide_request = AsyncMock(return_value=mock_request)

            result = await route_reply("approval", "denied", token_data, mock_db)

        assert result["status"] == "routed"
        assert result["decision"] == "denied"

    async def test_route_reply_approval_not_found(
        self, mock_db: AsyncMock, token_data: dict
    ) -> None:
        with patch("src.approval.ApprovalService") as mock_approval_svc:
            instance = mock_approval_svc.return_value
            instance.decide_request = AsyncMock(return_value=None)

            result = await route_reply("approval", "approved", token_data, mock_db)

        assert result["status"] == "not_found"

    async def test_route_reply_gate_check(self, mock_db: AsyncMock, token_data: dict) -> None:
        result = await route_reply("gate_check", None, token_data, mock_db)

        assert result["status"] == "routed"
        assert result["command_type"] == "gate_check"
        mock_db.rpc.assert_called_once()

    async def test_route_reply_phase_skip(self, mock_db: AsyncMock, token_data: dict) -> None:
        result = await route_reply("phase_skip", None, token_data, mock_db)

        assert result["status"] == "routed"
        assert result["command_type"] == "phase_skip"

    async def test_route_reply_guidance(self, mock_db: AsyncMock, token_data: dict) -> None:
        mock_mem_result = MagicMock()
        mock_mem_result.success = True
        mock_mem_result.memory_id = "mem-789"

        with patch("src.memory.MemoryService") as mock_mem_svc:
            instance = mock_mem_svc.return_value
            instance.remember = AsyncMock(return_value=mock_mem_result)

            result = await route_reply(
                "guidance", "Focus on API layer", token_data, mock_db
            )

        assert result["status"] == "routed"
        assert result["command_type"] == "guidance"
        assert result["memory_result"]["success"] is True

    async def test_route_reply_unknown_command(
        self, mock_db: AsyncMock, token_data: dict
    ) -> None:
        result = await route_reply("unknown_type", None, token_data, mock_db)
        assert result["status"] == "unknown_command"
