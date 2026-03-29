"""Gmail notification channel using SMTP via aiosmtplib."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from src.event_bus import CoordinatorEvent
from src.status import generate_token, validate_token

from .relay import clean_reply_body, extract_token, parse_reply, route_reply, validate_sender
from .templates import (
    render_approval_email,
    render_escalation_email,
    render_stale_agent_email,
    render_status_email,
)

logger = logging.getLogger(__name__)

try:
    import aioimaplib

    _HAS_AIOIMAPLIB = True
except ImportError:
    aioimaplib = None  # type: ignore[assignment]
    _HAS_AIOIMAPLIB = False


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

    # --- IMAP IDLE listener for inbound replies ---

    async def start_imap_listener(self) -> None:
        """Start the IMAP IDLE listener for processing email replies.

        Connects to the IMAP server, enters IDLE mode, and processes
        new messages as they arrive. Requires aioimaplib to be installed.

        Environment variables:
            IMAP_HOST: IMAP server hostname (default: imap.gmail.com)
            IMAP_PORT: IMAP server port (default: 993)
            IMAP_USER: IMAP username
            IMAP_PASSWORD: IMAP password
            NOTIFICATION_ALLOWED_SENDERS: Comma-separated sender allowlist
        """
        if not _HAS_AIOIMAPLIB:
            logger.warning(
                "IMAP listener not available: aioimaplib is not installed. "
                "Install with: uv add aioimaplib"
            )
            return

        self._imap_stop_event = asyncio.Event()

        imap_host = os.environ.get("IMAP_HOST", "imap.gmail.com")
        imap_port = int(os.environ.get("IMAP_PORT", "993"))
        imap_user = os.environ.get("IMAP_USER", "")
        imap_password = os.environ.get("IMAP_PASSWORD", "")
        allowed_senders = os.environ.get("NOTIFICATION_ALLOWED_SENDERS", "")

        if not imap_user or not imap_password:
            logger.error("IMAP_USER and IMAP_PASSWORD must be set for IMAP listener")
            return

        logger.info("Starting IMAP IDLE listener on %s:%d", imap_host, imap_port)

        try:
            imap_client = aioimaplib.IMAP4_SSL(host=imap_host, port=imap_port)
            await imap_client.wait_hello_from_server()
            await imap_client.login(imap_user, imap_password)
            await imap_client.select("INBOX")

            while not self._imap_stop_event.is_set():
                # Search for unseen messages
                _, data = await imap_client.search("UNSEEN")
                if data and data[0]:
                    msg_ids = data[0].split()
                    for msg_id in msg_ids:
                        await self._process_imap_message(
                            imap_client, msg_id, allowed_senders
                        )

                # Enter IDLE mode, wait for new mail or stop signal
                idle_task = await imap_client.idle_start(timeout=300)
                # Wait for either idle response or stop event
                done, _ = await asyncio.wait(
                    {idle_task, asyncio.create_task(self._imap_stop_event.wait())},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                imap_client.idle_done()

                if self._imap_stop_event.is_set():
                    break

            await imap_client.logout()
        except Exception:
            logger.error("IMAP listener error", exc_info=True)

    async def stop_imap_listener(self) -> None:
        """Stop the IMAP IDLE listener."""
        if hasattr(self, "_imap_stop_event"):
            self._imap_stop_event.set()
            logger.info("IMAP listener stop requested")
        else:
            logger.debug("IMAP listener was not running")

    async def _process_imap_message(
        self,
        imap_client: object,
        msg_id: bytes,
        allowed_senders: str,
    ) -> None:
        """Process a single IMAP message: parse, validate, route."""
        import email

        from src.db import get_db

        try:
            _, msg_data = await imap_client.fetch(msg_id, "(RFC822)")  # type: ignore[union-attr]
            if not msg_data or not msg_data[1]:
                return

            raw_email = msg_data[1]
            msg = email.message_from_bytes(
                raw_email if isinstance(raw_email, bytes) else raw_email.encode()
            )

            sender = msg.get("From", "")
            subject = msg.get("Subject", "")

            # Extract sender email from "Name <email>" format
            if "<" in sender and ">" in sender:
                sender = sender.split("<")[1].split(">")[0]

            # Validate sender
            if allowed_senders and not validate_sender(sender, allowed_senders):
                logger.info("Rejected reply from unlisted sender: %s", sender)
                return

            # Extract token from subject
            token = extract_token(subject)
            if not token:
                logger.debug("No token found in subject: %s", subject)
                return

            # Validate token
            db = get_db()
            token_data = await validate_token(db, token)
            if not token_data:
                logger.info("Invalid or expired token: %s", token)
                return

            # Get body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode("utf-8", errors="replace")
                        break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")

            # Parse and route
            command_type, command_value = parse_reply(body)
            result = await route_reply(command_type, command_value, token_data, db)
            logger.info(
                "Routed email reply: token=%s command=%s result=%s",
                token,
                command_type,
                result.get("status"),
            )

        except Exception:
            logger.error("Failed to process IMAP message %s", msg_id, exc_info=True)

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
