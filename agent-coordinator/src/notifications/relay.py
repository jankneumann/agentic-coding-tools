"""Reply parser and routing engine for inbound email replies.

Extracts tokens from subject lines, parses reply commands, validates
senders, and routes actions to the appropriate coordinator services.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Token pattern: [#XXXXXXXX] where X is 8-12 alphanumeric chars
_TOKEN_RE = re.compile(r"\[#([A-Za-z0-9]{8,12})\]")

# Quoted-text markers for stripping
_QUOTED_LINE_RE = re.compile(r"^>.*$", re.MULTILINE)
_ON_DATE_WROTE_RE = re.compile(r"^On .+ wrote:$", re.MULTILINE)
_SIGNATURE_RE = re.compile(r"^-- ?$", re.MULTILINE)

# Command mappings (lowercase -> (command_type, command_value))
_APPROVAL_YES = {"approved", "approve", "yes"}
_APPROVAL_NO = {"denied", "deny", "no"}


def extract_token(subject: str) -> str | None:
    """Extract a notification token from an email subject line.

    Looks for patterns like [#AbCdEfGh] in the subject.
    Returns the token string (without brackets/hash) or None.
    """
    match = _TOKEN_RE.search(subject)
    return match.group(1) if match else None


def parse_reply(body: str) -> tuple[str, str | None]:
    """Parse an email reply body into a command.

    Returns:
        (command_type, command_value) tuple where command_type is one of:
        'approval', 'gate_check', 'phase_skip', 'guidance'
    """
    cleaned = clean_reply_body(body)
    if not cleaned.strip():
        return ("guidance", None)  # Empty body — no actionable content

    lines = cleaned.strip().splitlines()
    first_line = lines[0].strip()

    # Extract first word and strip punctuation
    words = first_line.split()
    if not words:
        return ("guidance", cleaned)

    keyword = re.sub(r"[^\w]", "", words[0]).lower()

    if keyword in _APPROVAL_YES:
        return ("approval", "approved")
    elif keyword in _APPROVAL_NO:
        return ("approval", "denied")
    elif keyword == "resolved":
        return ("gate_check", None)
    elif keyword == "skip":
        return ("phase_skip", None)
    else:
        return ("guidance", cleaned.strip())


def validate_sender(sender: str, allowed_senders: str) -> bool:
    """Validate sender email against a comma-separated allowlist.

    Case-insensitive exact match. No domain wildcards.
    """
    sender_lower = sender.strip().lower()
    allowed = [s.strip().lower() for s in allowed_senders.split(",") if s.strip()]
    return sender_lower in allowed


def clean_reply_body(raw_body: str) -> str:
    """Strip quoted text, signatures, and other noise from a reply body.

    Removes:
    - Lines starting with '>' (quoted text)
    - 'On <date> <person> wrote:' lines
    - Signature blocks (starting with '-- ')
    """
    # Truncate at signature
    sig_match = _SIGNATURE_RE.search(raw_body)
    if sig_match:
        raw_body = raw_body[: sig_match.start()]

    # Truncate at "On ... wrote:" lines
    on_match = _ON_DATE_WROTE_RE.search(raw_body)
    if on_match:
        raw_body = raw_body[: on_match.start()]

    # Remove quoted lines
    cleaned = _QUOTED_LINE_RE.sub("", raw_body)

    # Collapse multiple blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()


async def route_reply(
    command_type: str,
    command_value: str | None,
    token_data: dict[str, Any],
    db: Any,
) -> dict[str, Any]:
    """Route a parsed reply command to the appropriate coordinator service.

    Args:
        command_type: One of 'approval', 'gate_check', 'phase_skip', 'guidance'
        command_value: Value for the command (e.g., 'approved', 'denied', or guidance text)
        token_data: Token row from the database (contains entity_id, change_id, etc.)
        db: Database client instance

    Returns:
        Dict with 'status' and any relevant result data.
    """
    entity_id = token_data.get("entity_id", "")
    change_id = token_data.get("change_id")

    if command_type == "approval":
        from src.approval import ApprovalService

        approval_svc = ApprovalService(db=db)
        result = await approval_svc.decide_request(
            request_id=entity_id,
            decision=command_value or "approved",
            decided_by="email-relay",
            reason="Replied via email",
        )
        if result is None:
            return {"status": "not_found", "entity_id": entity_id}
        return {
            "status": "routed",
            "command_type": "approval",
            "decision": command_value,
            "entity_id": entity_id,
        }

    elif command_type in ("gate_check", "phase_skip"):
        # Emit a pg_notify on coordinator_status channel
        payload = json.dumps(
            {
                "event_type": command_type,
                "entity_id": entity_id,
                "change_id": change_id,
                "source": "email-relay",
            }
        )
        try:
            await db.rpc(
                "pg_notify_bridge",
                {"p_channel": "coordinator_status", "p_payload": payload},
            )
        except Exception:
            logger.warning(
                "pg_notify failed for %s on entity %s",
                command_type,
                entity_id,
                exc_info=True,
            )
            return {
                "status": "failed",
                "command_type": command_type,
                "entity_id": entity_id,
                "reason": "pg_notify_failed",
            }
        return {
            "status": "routed",
            "command_type": command_type,
            "entity_id": entity_id,
        }

    elif command_type == "guidance":
        if not command_value or not command_value.strip():
            return {"status": "skipped", "reason": "empty_guidance"}

        from src.memory import MemoryService

        memory_svc = MemoryService(db=db)
        mem_result = await memory_svc.remember(
            event_type="discovery",
            summary=f"Human feedback via email for {change_id or entity_id}",
            details={"guidance": command_value, "entity_id": entity_id},
            tags=["human-feedback", change_id] if change_id else ["human-feedback"],
            agent_id="email-relay",
        )
        return {
            "status": "routed",
            "command_type": "guidance",
            "memory_result": {
                "success": mem_result.success,
                "memory_id": mem_result.memory_id,
            },
        }

    else:
        logger.warning("Unknown command type: %s", command_type)
        return {"status": "unknown_command", "command_type": command_type}
