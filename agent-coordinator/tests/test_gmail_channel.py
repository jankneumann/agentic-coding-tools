"""Tests for GmailChannel (mocked aiosmtplib)."""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_bus import CoordinatorEvent
from src.notifications.gmail import GmailChannel, _thread_message_id


def _make_channel() -> GmailChannel:
    return GmailChannel(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_user="user@gmail.com",
        smtp_password="secret",
        sender_email="sender@gmail.com",
        recipient_email="recipient@gmail.com",
    )


def _make_event(
    event_type: str = "approval.submitted",
    change_id: str | None = "change-123",
) -> CoordinatorEvent:
    return CoordinatorEvent(
        event_type=event_type,
        channel="coordinator_approval",
        entity_id="entity-1",
        agent_id="agent-1",
        urgency="high",
        summary="Please approve this change",
        change_id=change_id,
    )


class TestGmailChannel:
    @patch("src.notifications.gmail.store_token", new_callable=AsyncMock)
    @patch("src.notifications.gmail.aiosmtplib.send", new_callable=AsyncMock)
    @patch("src.notifications.gmail.generate_token", return_value="abc12345")
    async def test_send_constructs_email_with_correct_headers(
        self, mock_token, mock_send, mock_store
    ):
        channel = _make_channel()
        event = _make_event()

        result = await channel.send(event)

        assert result is True
        mock_store.assert_called_once()
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][0]

        assert msg["X-Coordinator-Token"] == "abc12345"
        assert msg["X-Coordinator-Event"] == "approval.submitted"
        assert msg["X-Coordinator-Change-Id"] == "change-123"
        assert msg["From"] == "sender@gmail.com"
        assert msg["To"] == "recipient@gmail.com"

    @patch("src.notifications.gmail.store_token", new_callable=AsyncMock)
    @patch("src.notifications.gmail.aiosmtplib.send", new_callable=AsyncMock)
    @patch("src.notifications.gmail.generate_token", return_value="tok98765")
    async def test_send_includes_token_in_subject(self, mock_token, mock_send, mock_store):
        channel = _make_channel()
        event = _make_event()

        await channel.send(event)

        msg = mock_send.call_args[0][0]
        assert "[#tok98765]" in msg["Subject"]

    @patch("src.notifications.gmail.store_token", new_callable=AsyncMock)
    @patch("src.notifications.gmail.aiosmtplib.send", new_callable=AsyncMock)
    @patch("src.notifications.gmail.generate_token", return_value="threadtk")
    async def test_send_threads_by_change_id(self, mock_token, mock_send, mock_store):
        channel = _make_channel()
        event = _make_event(change_id="feature-xyz")

        await channel.send(event)

        msg = mock_send.call_args[0][0]
        expected_thread_id = _thread_message_id("feature-xyz", "sender@gmail.com")
        assert msg["In-Reply-To"] == expected_thread_id
        assert msg["References"] == expected_thread_id

    @patch("src.notifications.gmail.store_token", new_callable=AsyncMock)
    @patch("src.notifications.gmail.aiosmtplib.send", new_callable=AsyncMock)
    @patch("src.notifications.gmail.generate_token", return_value="nothread")
    async def test_send_no_threading_without_change_id(self, mock_token, mock_send, mock_store):
        channel = _make_channel()
        event = _make_event(change_id=None)

        await channel.send(event)

        msg = mock_send.call_args[0][0]
        assert msg["In-Reply-To"] is None
        assert msg["References"] is None

    async def test_test_method_returns_false_on_connection_error(self):
        channel = _make_channel()

        with patch("src.notifications.gmail.aiosmtplib.SMTP") as MockSMTP:
            instance = MockSMTP.return_value
            instance.connect = AsyncMock(side_effect=ConnectionRefusedError("refused"))

            result = await channel.test()
            assert result is False
