"""Token management for notification reply tracking."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
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
    now = datetime.now(UTC)
    expires_at = datetime.fromtimestamp(
        now.timestamp() + ttl_seconds, tz=UTC
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
    """Validate and consume a token.

    Checks that the token exists, is unused (used_at IS NULL), and has not
    expired before marking it as used. Returns the token row or None.
    """
    now = datetime.now(UTC).isoformat()

    # Query with full conditions: unused AND not expired
    rows = await db.query(
        "notification_tokens",
        query_params=f"token=eq.{token}&used_at=is.null&expires_at=gt.{now}",
    )
    if not rows:
        return None

    # Mark as used
    updated = await db.update(
        "notification_tokens",
        match={"token": token},
        data={"used_at": now},
    )
    if not updated:
        return None

    return updated[0]


async def cleanup_expired_tokens(db: DatabaseClient) -> int:
    """Delete expired tokens. Returns count of deleted tokens.

    Note: The DatabaseClient.delete() doesn't return count, so we query
    first to know how many will be deleted.
    """
    now = datetime.now(UTC).isoformat()

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
