"""Generic webhook notification channel."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

import httpx

from src.event_bus import CoordinatorEvent

logger = logging.getLogger(__name__)


class WebhookChannel:
    """Generic HTTP POST webhook notification channel.

    Implements the NotificationChannel protocol.
    """

    channel_id: str = "webhook"

    def __init__(
        self,
        webhook_url: str,
        webhook_secret: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self._client = http_client

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def send(self, event: CoordinatorEvent) -> bool:
        """POST JSON payload with event data to the webhook URL."""
        payload = {
            "event_type": event.event_type,
            "channel": event.channel,
            "entity_id": event.entity_id,
            "agent_id": event.agent_id,
            "urgency": event.urgency,
            "summary": event.summary,
            "timestamp": event.timestamp,
            "change_id": event.change_id,
            "context": event.context,
        }
        body = json.dumps(payload)
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if self.webhook_secret:
            signature = hmac.new(
                self.webhook_secret.encode(),
                body.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        try:
            response = await self.client.post(
                self.webhook_url,
                content=body,
                headers=headers,
            )
            response.raise_for_status()
            logger.info(
                "Webhook: sent %s notification for %s",
                event.event_type,
                event.entity_id,
            )
            return True
        except Exception as exc:
            logger.error("Webhook: failed to send: %s", exc)
            return False

    async def test(self) -> bool:
        """POST a test event and check for 2xx response."""
        payload = {"event_type": "test", "summary": "Webhook connectivity test"}
        body = json.dumps(payload)
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if self.webhook_secret:
            signature = hmac.new(
                self.webhook_secret.encode(),
                body.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        try:
            response = await self.client.post(
                self.webhook_url,
                content=body,
                headers=headers,
            )
            response.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("Webhook: connection test failed: %s", exc)
            return False

    def supports_reply(self) -> bool:
        return False


def get_webhook_channel() -> WebhookChannel:
    """Factory: create WebhookChannel from environment variables."""
    return WebhookChannel(
        webhook_url=os.environ["WEBHOOK_URL"],
        webhook_secret=os.environ.get("WEBHOOK_SECRET"),
    )
