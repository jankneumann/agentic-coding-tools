"""Gmail notification channel using SMTP via aiosmtplib."""

from __future__ import annotations

import hashlib
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from src.event_bus import CoordinatorEvent
from src.status import generate_token

from .templates import (
    render_approval_email,
    render_escalation_email,
    render_stale_agent_email,
    render_status_email,
)

logger = logging.getLogger(__name__)


class GmailChannel:
    """Outbound Gmail notification channel via SMTP.

    Implements the NotificationChannel protocol. IMAP relay is handled
    separately by wp-gmail-relay.
    """

    channel_id: str = "gmail"

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        sender_email: str,
        recipient_email: str,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.sender_email = sender_email
        self.recipient_email = recipient_email

    async def send(self, event: CoordinatorEvent) -> bool:
        """Send an HTML email notification for the event."""
        token = generate_token()
        subject, html_body = self._render(event, token)

        msg = MIMEMultipart("alternative")
        msg["From"] = self.sender_email
        msg["To"] = self.recipient_email
        msg["Subject"] = subject

        # Custom headers for machine parsing
        msg["X-Coordinator-Token"] = token
        msg["X-Coordinator-Event"] = event.event_type
        if event.change_id:
            msg["X-Coordinator-Change-Id"] = event.change_id

        # Thread emails by change_id
        if event.change_id:
            thread_id = _thread_message_id(event.change_id, self.sender_email)
            msg["In-Reply-To"] = thread_id
            msg["References"] = thread_id

        msg.attach(MIMEText(html_body, "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=True,
            )
            logger.info(
                "Gmail: sent %s notification for %s (token=%s)",
                event.event_type,
                event.change_id or event.entity_id,
                token,
            )
            return True
        except Exception as exc:
            logger.error("Gmail: failed to send email: %s", exc)
            raise

    async def test(self) -> bool:
        """Test SMTP connectivity."""
        try:
            smtp = aiosmtplib.SMTP(
                hostname=self.smtp_host,
                port=self.smtp_port,
                start_tls=True,
            )
            await smtp.connect()
            await smtp.quit()
            return True
        except Exception as exc:
            logger.warning("Gmail: connection test failed: %s", exc)
            return False

    def supports_reply(self) -> bool:
        return True

    @staticmethod
    def _render(event: CoordinatorEvent, token: str) -> tuple[str, str]:
        """Select the appropriate template based on event type."""
        if event.event_type.startswith("approval."):
            return render_approval_email(event, token)
        elif event.event_type.startswith("status.escalated") or event.event_type == "status.escalated":
            return render_escalation_email(event, token)
        elif event.event_type == "agent.stale":
            return render_stale_agent_email(event)
        else:
            return render_status_email(event)


def _thread_message_id(change_id: str, sender: str) -> str:
    """Generate a deterministic Message-ID for threading by change_id."""
    domain = sender.split("@")[-1] if "@" in sender else "coordinator.local"
    hash_val = hashlib.sha256(change_id.encode()).hexdigest()[:16]
    return f"<coordinator-{hash_val}@{domain}>"


def get_gmail_channel() -> GmailChannel:
    """Factory: create GmailChannel from environment variables."""
    return GmailChannel(
        smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_user=os.environ["SMTP_USER"],
        smtp_password=os.environ["SMTP_PASSWORD"],
        sender_email=os.environ["NOTIFICATION_SENDER_EMAIL"],
        recipient_email=os.environ["NOTIFICATION_RECIPIENT_EMAIL"],
    )
