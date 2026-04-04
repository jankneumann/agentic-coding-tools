"""Langfuse observability for the Agent Coordinator.

Provides cross-agent session tracing: coordinator operations appear as spans
within Langfuse traces, giving visibility into both coding agent sessions
(via the Claude Code Stop hook) and coordinator-side API processing
(via FastAPI middleware).

Disabled by default -- enable via LANGFUSE_ENABLED=true.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy Langfuse client -- only initialized when enabled
# ---------------------------------------------------------------------------

_langfuse: Any = None
_initialized = False


def _is_enabled() -> bool:
    return os.environ.get("LANGFUSE_ENABLED", "false").lower() == "true"


def init_langfuse() -> None:
    """Initialize the Langfuse client from configuration.

    Safe to call multiple times -- subsequent calls are no-ops.
    """
    global _langfuse, _initialized

    if _initialized:
        return
    _initialized = True

    if not _is_enabled():
        logger.debug("Langfuse disabled (LANGFUSE_ENABLED=false)")
        return

    try:
        from langfuse import Langfuse

        from .config import get_config

        config = get_config()
        lf_config = config.langfuse

        _langfuse = Langfuse(
            public_key=lf_config.public_key,
            secret_key=lf_config.secret_key,
            host=lf_config.host,
            debug=lf_config.debug,
            release=os.environ.get("COORDINATOR_VERSION", "dev"),
        )

        logger.info(
            "Langfuse initialized (host=%s, project_key=%s...)",
            lf_config.host,
            lf_config.public_key[:12] if lf_config.public_key else "(empty)",
        )
    except ImportError:
        logger.warning(
            "langfuse package not installed -- install with: "
            "uv sync --extra observability"
        )
    except Exception:
        logger.warning("Failed to initialize Langfuse -- falling back to no-op", exc_info=True)


def get_langfuse() -> Any | None:
    """Return the Langfuse client, or None if disabled."""
    return _langfuse


def shutdown_langfuse() -> None:
    """Flush pending events and shut down the Langfuse client."""
    global _langfuse, _initialized
    if _langfuse is not None:
        try:
            _langfuse.flush()
            _langfuse.shutdown()
        except Exception:
            logger.debug("Langfuse shutdown error", exc_info=True)
    _langfuse = None
    _initialized = False


# ---------------------------------------------------------------------------
# Trace / span helpers for coordinator operations
# ---------------------------------------------------------------------------


def create_trace(
    *,
    name: str,
    session_id: str | None = None,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    input: Any = None,
) -> Any | None:
    """Create a Langfuse trace. Returns the trace object or None if disabled."""
    lf = get_langfuse()
    if lf is None:
        return None

    try:
        return lf.trace(
            name=name,
            session_id=session_id,
            user_id=user_id,
            metadata=metadata or {},
            tags=tags or [],
            input=input,
        )
    except Exception:
        logger.debug("Failed to create Langfuse trace", exc_info=True)
        return None


def create_span(
    trace: Any,
    *,
    name: str,
    input: Any = None,
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """Create a span on an existing trace. Returns the span or None."""
    if trace is None:
        return None

    try:
        return trace.span(
            name=name,
            input=input,
            metadata=metadata or {},
            start_time=time.time(),
        )
    except Exception:
        logger.debug("Failed to create Langfuse span", exc_info=True)
        return None


def end_span(
    span: Any,
    *,
    output: Any = None,
    status_message: str | None = None,
    level: str = "DEFAULT",
) -> None:
    """End a Langfuse span with output and status."""
    if span is None:
        return

    try:
        span.end(
            output=output,
            status_message=status_message,
            level=level,
        )
    except Exception:
        logger.debug("Failed to end Langfuse span", exc_info=True)


@contextmanager
def trace_operation(
    *,
    name: str,
    session_id: str | None = None,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    input: Any = None,
) -> Generator[Any, None, None]:
    """Context manager that creates a trace, yields it, and updates on exit.

    Usage::

        with trace_operation(name="acquire_lock", user_id=agent_id) as trace:
            # ... do work ...
            if trace:
                trace.update(output={"status": "acquired"})
    """
    trace = create_trace(
        name=name,
        session_id=session_id,
        user_id=user_id,
        metadata=metadata,
        tags=tags,
        input=input,
    )
    try:
        yield trace
    except Exception as exc:
        if trace is not None:
            try:
                trace.update(
                    output={"error": str(exc)},
                    level="ERROR",
                    status_message=str(exc),
                )
            except Exception:
                pass
        raise
    finally:
        # Ensure events are flushed promptly
        lf = get_langfuse()
        if lf is not None:
            try:
                lf.flush()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Reset for testing
# ---------------------------------------------------------------------------


def reset_langfuse() -> None:
    """Reset all Langfuse state. For testing only."""
    global _langfuse, _initialized
    _langfuse = None
    _initialized = False
