"""Telegram notification channel using the Telegram Bot API."""

from __future__ import annotations

import json
import logging
import os
import re

import httpx

from src.event_bus import CoordinatorEvent

logger = logging.getLogger(__name__)

# Telegram callback_data has a 64-byte hard limit
_MAX_CALLBACK_DATA_BYTES = 64


class TelegramChannel:
    """Outbound Telegram notification channel via Bot API.

    Implements the NotificationChannel protocol.
    """

    channel_id: str = "telegram"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._client = http_client

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"

    async def send(self, event: CoordinatorEvent) -> bool:
        """Send an event notification as a Telegram message with Markdown formatting."""
        text = self._format_message(event)
        payload: dict[str, str | object] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
        }

        # For approval events, add inline keyboard with Approve/Deny buttons
        if event.event_type.startswith("approval."):
            token = event.context.get("token", event.entity_id)
            # Truncate token to fit within Telegram's 64-byte callback_data limit
            # Reserve ~30 bytes for the JSON envelope {"action":"approve","t":""}
            max_token_len = _MAX_CALLBACK_DATA_BYTES - 30
            if len(token) > max_token_len:
                token = token[:max_token_len]
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": [
                    [
                        {
                            "text": "Approve",
                            "callback_data": json.dumps(
                                {"action": "approve", "t": token}
                            ),
                        },
                        {
                            "text": "Deny",
                            "callback_data": json.dumps(
                                {"action": "deny", "t": token}
                            ),
                        },
                    ]
                ]
            })

        try:
            response = await self.client.post(
                self._api_url("sendMessage"),
                json=payload,
            )
            response.raise_for_status()
            logger.info(
                "Telegram: sent %s notification for %s",
                event.event_type,
                event.entity_id,
            )
            return True
        except httpx.HTTPStatusError as exc:
            # Log status code only — URL contains the bot token
            logger.error(
                "Telegram: sendMessage failed with HTTP %d",
                exc.response.status_code,
            )
            return False
        except Exception as exc:
            logger.error("Telegram: failed to send message: %s", type(exc).__name__)
            return False

    async def test(self) -> bool:
        """Test connectivity by calling the getMe endpoint."""
        try:
            response = await self.client.get(self._api_url("getMe"))
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Telegram: connection test failed with HTTP %d",
                exc.response.status_code,
            )
            return False
        except Exception as exc:
            logger.warning("Telegram: connection test failed: %s", type(exc).__name__)
            return False

    def supports_reply(self) -> bool:
        return True

    @staticmethod
    def _escape_markdown(text: str) -> str:
        """Escape special characters for Telegram MarkdownV2."""
        return re.sub(r"([_*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", text)

    @classmethod
    def _format_message(cls, event: CoordinatorEvent) -> str:
        """Format a CoordinatorEvent as a MarkdownV2 message for Telegram."""
        esc = cls._escape_markdown
        urgency_icon = {"high": "\u26a0\ufe0f", "medium": "\u2139\ufe0f", "low": "\u2705"}.get(
            event.urgency, ""
        )
        lines = [
            f"{urgency_icon} *{esc(event.event_type)}*",
            f"Agent: `{esc(event.agent_id)}`",
            f"Entity: `{esc(event.entity_id)}`",
        ]
        if event.change_id:
            lines.append(f"Change: `{esc(event.change_id)}`")
        lines.append(f"\n{esc(event.summary)}")
        return "\n".join(lines)


def get_telegram_channel() -> TelegramChannel:
    """Factory: create TelegramChannel from environment variables."""
    return TelegramChannel(
        bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        chat_id=os.environ["TELEGRAM_CHAT_ID"],
    )
