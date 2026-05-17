"""SSE (Server-Sent Events) stream handler for the Kanban visualization.

Implements:
  POST /events/auth  — mint a short-lived JWT bound to change_ids
  GET  /events/work  — SSE stream; validates JWT, registers callbacks on the
                       existing EventBusService, filters by subscribed change_ids

Design decisions:
  D2  — SSE chosen over WebSocket; JWT token-in-URL for auth (browser
        EventSource cannot attach custom headers).
  D11 — Fail-closed: if COORDINATOR_SSE_SIGNING_KEY is unset, both endpoints
        return 503.

JWT library: PyJWT (``pip install PyJWT``).  Already in the coordinator deps.
SSE library: sse-starlette (``pip install sse-starlette``).

Backpressure: server caps at 100 events/sec/connection; excess coalesced into
a single ``snapshot`` event.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────────────────

_SSE_SIGNING_KEY_ENV = "COORDINATOR_SSE_SIGNING_KEY"
_TOKEN_TTL_SECONDS = 300
_TOKEN_MAX_TTL = 600
_BACKPRESSURE_LIMIT = 100  # events/sec/connection before coalescing to snapshot

# Single-use nonce store: {nonce -> expiry datetime}
# In-process dict is sufficient for single-worker deployments. For multi-worker,
# replace with a Redis/DB-backed store (follow-up: add-coordinator-consent-tokens).
_nonce_store: dict[str, datetime] = {}


def _get_signing_key() -> str | None:
    """Return COORDINATOR_SSE_SIGNING_KEY, or None if unset."""
    return os.environ.get(_SSE_SIGNING_KEY_ENV, "").strip() or None


def _signing_key_or_503() -> str:
    """Return signing key or raise a 503-suitable error."""
    key = _get_signing_key()
    if not key:
        raise RuntimeError(
            "COORDINATOR_SSE_SIGNING_KEY is not set — SSE endpoints are fail-closed. "
            "Set the env var to a 32-byte secret to enable the SSE stream."
        )
    return key


# ─── JWT helpers ─────────────────────────────────────────────────────────────

def mint_events_token(
    change_ids: list[str],
    key_id: str | None = None,
    ttl: int = _TOKEN_TTL_SECONDS,
) -> dict[str, Any]:
    """Mint a short-lived JWT for the SSE auth handshake.

    Returns:
        {token: str, expires_at: str, aud: str, change_ids: list[str]}
    Raises:
        RuntimeError if COORDINATOR_SSE_SIGNING_KEY is unset (fail-closed).
        ValueError if change_ids is empty.
    """
    import jwt  # PyJWT

    signing_key = _signing_key_or_503()
    if not change_ids:
        raise ValueError("change_ids must be non-empty")

    ttl_clamped = max(1, min(ttl, _TOKEN_MAX_TTL))
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=ttl_clamped)
    nonce = str(uuid.uuid4())

    # Persist nonce until expiry (single-use store)
    _nonce_store[nonce] = exp
    _prune_nonces()

    payload: dict[str, Any] = {
        "aud": "events",
        "exp": exp,
        "iat": now,
        "nonce": nonce,
        "change_ids": sorted(change_ids),
    }
    if key_id:
        payload["key_id"] = key_id

    token = jwt.encode(payload, signing_key, algorithm="HS256")
    return {
        "token": token,
        "expires_at": exp.isoformat(),
        "aud": "events",
        "change_ids": sorted(change_ids),
    }


def validate_events_token(
    token: str,
    required_change_ids: list[str],
) -> dict[str, Any]:
    """Validate an events JWT.

    Returns the decoded payload on success.
    Raises:
        jwt.InvalidTokenError subclass on any failure (expired, bad sig, etc.)
        ValueError on aud/nonce/change_ids mismatch.
    Raises RuntimeError if COORDINATOR_SSE_SIGNING_KEY is unset.
    """
    import jwt  # PyJWT

    signing_key = _signing_key_or_503()

    payload = jwt.decode(
        token,
        signing_key,
        algorithms=["HS256"],
        audience="events",
    )

    # Nonce replay check
    nonce = payload.get("nonce")
    if not nonce or nonce not in _nonce_store:
        raise ValueError("Token nonce is invalid or has already been used")

    # Consume the nonce (single-use)
    del _nonce_store[nonce]

    # change_ids must match exactly
    token_ids = sorted(payload.get("change_ids", []))
    req_ids = sorted(required_change_ids)
    if token_ids != req_ids:
        raise ValueError(
            f"Token change_ids {token_ids} do not match requested {req_ids}"
        )

    return payload


def _prune_nonces() -> None:
    """Remove expired nonces from the in-process store."""
    now = datetime.now(UTC)
    expired = [n for n, exp in _nonce_store.items() if exp <= now]
    for n in expired:
        _nonce_store.pop(n, None)


# ─── SSE event generator ─────────────────────────────────────────────────────

async def _build_snapshot(change_ids: list[str]) -> str:
    """Build a snapshot payload for the given change_ids."""
    try:
        from .issue_service import IssueService
        from .worktrees_view import get_active_worktrees

        service = IssueService()
        issues = await service.list_issues(labels=[f"change:{cid}" for cid in change_ids])
        work_queue = [i.to_dict() for i in issues]
    except Exception as exc:
        logger.warning("snapshot: issue query failed: %s", exc)
        work_queue = []

    try:
        worktrees = get_active_worktrees()
    except Exception as exc:
        logger.warning("snapshot: worktrees query failed: %s", exc)
        worktrees = []

    payload = {
        "work_queue": work_queue,
        "active_agents": worktrees,
        "subscribed_change_ids": sorted(change_ids),
    }
    return json.dumps(payload)


async def sse_event_generator(
    change_ids: list[str],
    event_bus: Any,  # EventBusService
) -> AsyncIterator[dict[str, Any]]:
    """Async generator yielding SSE events for ``GET /events/work``.

    Yields dicts with ``event`` and ``data`` keys (sse-starlette format).
    Emits an initial ``snapshot`` then routes ``coordinator_task`` payloads as
    ``transition`` events and ``coordinator_audit`` payloads as ``audit`` events.

    Backpressure: if more than ``_BACKPRESSURE_LIMIT`` events arrive within a
    1-second window, they are coalesced into a single ``snapshot``.
    """
    from .event_bus import CoordinatorEvent

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)

    def _make_transition(evt: CoordinatorEvent) -> dict[str, Any]:
        ctx = evt.context or {}
        return {
            "event": "transition",
            "data": json.dumps({
                "work_queue_id": evt.entity_id,
                "from": ctx.get("from_status") or ctx.get("from", ""),
                "to": ctx.get("to_status") or ctx.get("to", evt.event_type.split(".")[-1]),
                "agent_id": evt.agent_id,
                "ts": evt.timestamp,
            }),
        }

    def _make_audit(evt: CoordinatorEvent) -> dict[str, Any]:
        ctx = evt.context or {}
        return {
            "event": "audit",
            "data": json.dumps({
                "audit_id": evt.entity_id,
                "agent_id": evt.agent_id,
                "operation": ctx.get("operation", evt.event_type),
                "args_summary": ctx.get("args_summary", evt.summary),
                "ts": evt.timestamp,
            }),
        }

    async def _on_task_event(evt: CoordinatorEvent) -> None:
        if not evt.change_id or evt.change_id not in change_ids:
            return
        await queue.put(_make_transition(evt))

    async def _on_audit_event(evt: CoordinatorEvent) -> None:
        if not evt.change_id or evt.change_id not in change_ids:
            return
        await queue.put(_make_audit(evt))

    event_bus.on_event("coordinator_task", _on_task_event)
    event_bus.on_event("coordinator_audit", _on_audit_event)

    # Initial snapshot
    snapshot_data = await _build_snapshot(change_ids)
    yield {"event": "snapshot", "data": snapshot_data}

    # Emit events; track backpressure
    window_start = asyncio.get_event_loop().time()
    window_count = 0

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=30.0)
            except TimeoutError:
                # Heartbeat keep-alive
                yield {"event": "ping", "data": "{}"}
                continue

            now = asyncio.get_event_loop().time()
            if now - window_start > 1.0:
                window_start = now
                window_count = 0

            window_count += 1
            if window_count > _BACKPRESSURE_LIMIT:
                # Coalesce: drain queue and emit a single snapshot
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                snapshot_data = await _build_snapshot(change_ids)
                yield {"event": "snapshot", "data": snapshot_data}
                window_count = 0
                continue

            yield item
    except asyncio.CancelledError:
        pass
