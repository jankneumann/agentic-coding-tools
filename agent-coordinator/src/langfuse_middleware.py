"""FastAPI middleware for Langfuse request tracing.

Traces every coordinator HTTP API request as a Langfuse trace with a span,
giving visibility into cloud agent interactions with the coordinator.
Each request creates a trace tagged with the agent identity (from API key)
and the operation being performed.

This is the primary mechanism for **cloud agent observability** -- since
cloud agents don't run Claude Code locally and can't use the Stop hook,
the coordinator traces their API calls server-side.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Paths to skip tracing (health checks, metrics, docs)
_SKIP_PATHS = frozenset({"/health", "/metrics", "/docs", "/openapi.json", "/redoc"})


class LangfuseTracingMiddleware(BaseHTTPMiddleware):
    """Middleware that creates a Langfuse trace for each API request.

    The trace captures:
    - Operation name derived from the URL path (e.g., "api:locks/acquire")
    - Agent identity from the X-API-Key header (resolved via config)
    - Request/response bodies for debugging
    - Timing information
    - HTTP status codes

    All traces are grouped by session_id (if provided in the request body)
    so that a cloud agent's coding session appears as a coherent timeline
    in Langfuse alongside any local agent traces from the Stop hook.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        from .langfuse_tracing import get_langfuse

        lf = get_langfuse()
        if lf is None:
            return await call_next(request)

        path = request.url.path
        if path in _SKIP_PATHS:
            return await call_next(request)

        start = time.time()
        agent_id = _resolve_agent_id(request)
        operation = f"api:{path.lstrip('/')}"
        session_id = request.headers.get("X-Session-Id")

        trace = None
        span = None
        try:
            trace = lf.trace(
                name=operation,
                session_id=session_id,
                user_id=agent_id,
                metadata={
                    "http_method": request.method,
                    "path": path,
                    "source": "coordinator-api",
                },
                tags=["coordinator", "api-request", request.method.lower()],
                input={"method": request.method, "path": path},
            )

            span = trace.span(
                name=f"{request.method} {path}",
                metadata={"agent_id": agent_id},
            )
        except Exception:
            logger.debug("Failed to create Langfuse trace for %s", path, exc_info=True)

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.time() - start) * 1000
            _finalize_trace(trace, span, 500, duration_ms, operation)
            raise

        duration_ms = (time.time() - start) * 1000
        _finalize_trace(trace, span, response.status_code, duration_ms, operation)

        return response


def _resolve_agent_id(request: Request) -> str:
    """Extract agent identity from the request API key."""
    api_key = request.headers.get("x-api-key")
    if not api_key:
        return "anonymous"

    try:
        from .config import get_config

        config = get_config()
        identity = config.api.api_key_identities.get(api_key, {})
        return identity.get("agent_id", "cloud-agent")
    except Exception:
        return "cloud-agent"


def _finalize_trace(
    trace: Any,
    span: Any,
    status_code: int,
    duration_ms: float,
    operation: str,
) -> None:
    """Update trace and span with response info."""
    level = "ERROR" if status_code >= 500 else "WARNING" if status_code >= 400 else "DEFAULT"

    if span is not None:
        try:
            span.end(
                output={"status_code": status_code, "duration_ms": round(duration_ms, 2)},
                level=level,
                status_message=f"HTTP {status_code}",
            )
        except Exception:
            pass

    if trace is not None:
        try:
            trace.update(
                output={"status_code": status_code, "duration_ms": round(duration_ms, 2)},
                level=level,
                status_message=f"{operation} -> {status_code}",
            )
        except Exception:
            pass

    # Note: No per-request flush here. The Langfuse SDK batches events
    # and flushes periodically. Per-request flushing adds unnecessary
    # latency. Events are flushed on shutdown via shutdown_langfuse().
