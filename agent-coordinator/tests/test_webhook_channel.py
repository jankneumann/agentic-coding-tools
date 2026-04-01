"""Tests for WebhookChannel (mocked httpx)."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock

import httpx

from src.event_bus import CoordinatorEvent
from src.notifications.webhook import WebhookChannel


def _make_channel(
    secret: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> WebhookChannel:
    return WebhookChannel(
        webhook_url="https://example.com/webhook",
        webhook_secret=secret,
        http_client=http_client,
    )


def _make_event() -> CoordinatorEvent:
    return CoordinatorEvent(
        event_type="task.completed",
        channel="coordinator_task",
        entity_id="task-1",
        agent_id="agent-1",
        urgency="medium",
        summary="Task completed successfully",
    )


class TestWebhookChannel:
    async def test_send_posts_json_payload(self):
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

        call_kwargs = mock_client.post.call_args.kwargs
        body = call_kwargs["content"]
        payload = json.loads(body)
        assert payload["event_type"] == "task.completed"
        assert payload["agent_id"] == "agent-1"
        assert payload["summary"] == "Task completed successfully"
        assert call_kwargs["headers"]["Content-Type"] == "application/json"

    async def test_send_includes_hmac_signature(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        secret = "my-webhook-secret"
        channel = _make_channel(secret=secret, http_client=mock_client)
        event = _make_event()

        await channel.send(event)

        call_kwargs = mock_client.post.call_args.kwargs
        headers = call_kwargs["headers"]
        body = call_kwargs["content"]

        assert "X-Webhook-Signature" in headers
        expected_sig = hmac.new(
            secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        assert headers["X-Webhook-Signature"] == f"sha256={expected_sig}"

    async def test_send_without_secret_skips_signature(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        channel = _make_channel(secret=None, http_client=mock_client)
        event = _make_event()

        await channel.send(event)

        call_kwargs = mock_client.post.call_args.kwargs
        headers = call_kwargs["headers"]
        assert "X-Webhook-Signature" not in headers

    async def test_connection_error_returns_false(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        channel = _make_channel(http_client=mock_client)
        event = _make_event()

        result = await channel.send(event)

        assert result is False
