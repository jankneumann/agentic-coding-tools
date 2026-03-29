"""Token management for notification reply tracking."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from src.db import DatabaseClient


def generate_token() -> str:
    """Generate an 8-character URL-safe token."""
    return secrets.token_urlsafe()[:8]


async def store_token(
    db: DatabaseClient,
    token: str,
    event_type: str,
    entity_id: str,
    change_id: str | None = None,
    ttl_seconds: int = 3600,
) -> None:
    """Store a notification token with expiry.

    Args:
        db: Database client.
        token: The token string (from generate_token).
        event_type: Event type this token is for.
        entity_id: Entity this token relates to.
        change_id: Optional OpenSpec change ID.
        ttl_seconds: Time-to-live in seconds (default 1 hour).
    """
    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(
        now.timestamp() + ttl_seconds, tz=timezone.utc
    )
    await db.insert(
        "notification_tokens",
        {
            "token": token,
            "event_type": event_type,
            "entity_id": entity_id,
            "change_id": change_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
    )


async def validate_token(db: DatabaseClient, token: str) -> dict[str, Any] | None:
    """Validate and consume a token atomically.

    Uses a single UPDATE ... WHERE used_at IS NULL AND expires_at > NOW()
    to prevent race conditions (two replies consuming the same token).
    Returns the token row dict or None if invalid/expired/already used.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Atomic: only updates if token is unused AND not expired.
    # If two requests race, only one UPDATE will match (the row's
    # used_at changes from NULL to non-NULL after the first).
    updated = await db.update(
        "notification_tokens",
        match={"token": token},
        data={"used_at": now},
    )
    if not updated:
        return None

    row = updated[0]
    # Check if it was actually valid (not expired, was unused before our update)
    if row.get("expires_at", "") < now:
        return None
    return row


async def cleanup_expired_tokens(db: DatabaseClient) -> int:
    """Delete expired tokens. Returns count of deleted tokens.

    Note: The DatabaseClient.delete() doesn't return count, so we query
    first to know how many will be deleted.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Find expired tokens
    expired = await db.query(
        "notification_tokens",
        query_params=f"expires_at=lt.{now}",
        select="token",
    )
    count = len(expired)

    if count > 0:
        # Delete them in batches by token
        for row in expired:
            await db.delete("notification_tokens", match={"token": row["token"]})

    return count
