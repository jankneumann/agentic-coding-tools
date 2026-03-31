"""Tests for TelegramChannel (mocked httpx)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.event_bus import CoordinatorEvent
from src.notifications.telegram import TelegramChannel


def _make_channel(http_client: httpx.AsyncClient | None = None) -> TelegramChannel:
    return TelegramChannel(
        bot_token="123456:ABC-DEF",
        chat_id="@testchannel",
        http_client=http_client,
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


class TestTelegramChannel:
    async def test_send_calls_telegram_api(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        channel = _make_channel(http_client=mock_client)
        event = _make_event()

        result = await channel.send(event)

        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "sendMessage" in call_args.args[0]
        assert "bot123456:ABC-DEF" in call_args.args[0]

    async def test_send_formats_markdown(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        channel = _make_channel(http_client=mock_client)
        event = _make_event()

        await channel.send(event)

        call_kwargs = mock_client.post.call_args.kwargs
        payload = call_kwargs["json"]
        assert payload["parse_mode"] == "MarkdownV2"
        assert "*approval\\.submitted*" in payload["text"]
        assert "`agent\\-1`" in payload["text"]

    async def test_test_method_calls_getme(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)

        channel = _make_channel(http_client=mock_client)

        result = await channel.test()

        assert result is True
        mock_client.get.assert_called_once()
        assert "getMe" in mock_client.get.call_args.args[0]

    async def test_connection_error_returns_false(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        channel = _make_channel(http_client=mock_client)

        result = await channel.test()

        assert result is False
