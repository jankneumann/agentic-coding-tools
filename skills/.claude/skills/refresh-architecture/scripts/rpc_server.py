#!/usr/bin/env python3
"""refresh-architecture RPC server (wp-build-graph task 3.8).

Implements the contract in ``contracts/internal/refresh-architecture-rpc.yaml``:

    is_graph_stale   — non-blocking freshness probe from file mtime
    trigger_refresh  — idempotently spawn a refresh subprocess
    get_refresh_status — poll an in-flight or completed refresh by id

Transport is subprocess-style. The coordinator invokes this module with

    python -m rpc_server <method> '<json-args>'

and parses the JSON result printed to stdout. This avoids a long-running
service while still providing a callable surface across process boundaries.

## Concurrency model

- At most ONE refresh in flight per ``RefreshServer`` instance.
- ``trigger_refresh`` is idempotent: if a refresh is already running, it
  returns the existing refresh_id and ``is_new=false``.
- Subprocess state is held in-memory (no persistence). A process restart
  "forgets" in-flight refreshes — callers MUST treat ``UNKNOWN`` as a cue
  to trigger a fresh run.

## Failure semantics

Per the contract "Failure modes" section, callers of ``is_graph_stale`` /
``trigger_refresh`` / ``get_refresh_status`` MUST tolerate errors from this
module by proceeding with a "full test suite" fallback — the coordinator
must NEVER block merge train progress on refresh-architecture availability.
"""

from __future__ import annotations

import argparse
import enum
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_GRAPH_PATH = Path("docs/architecture-analysis/architecture.graph.json")
DEFAULT_MAX_AGE_HOURS = 6
#: Estimated duration of a full refresh when we have no historical data.
DEFAULT_ESTIMATED_DURATION_S = 60


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------


class RefreshStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


# ---------------------------------------------------------------------------
# Subprocess abstraction
# ---------------------------------------------------------------------------


class _ProcessLike(Protocol):
    """Minimal subprocess.Popen surface used by the server."""

    pid: int

    def poll(self) -> int | None: ...


Spawner = Callable[[list[str]], _ProcessLike]
"""Factory for launching a refresh subprocess. Tests inject a fake."""


def _default_spawner(cmd: list[str]) -> _ProcessLike:
    """Default spawner: detached subprocess.Popen."""
    return subprocess.Popen(  # noqa: S603 — trusted command
        cmd,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# Refresh handle
# ---------------------------------------------------------------------------


@dataclass
class _RefreshHandle:
    """In-memory record of a spawned refresh run."""

    refresh_id: str
    started_at: datetime
    process: _ProcessLike
    reason: str
    caller: str
    completed_at: datetime | None = None
    error_message: str | None = None
    _cached_status: RefreshStatus | None = None

    def poll_status(self) -> RefreshStatus:
        """Poll the subprocess and memoize the terminal result."""
        if self._cached_status in {
            RefreshStatus.COMPLETED,
            RefreshStatus.FAILED,
        }:
            return self._cached_status

        rc = self.process.poll()
        if rc is None:
            self._cached_status = RefreshStatus.RUNNING
            return RefreshStatus.RUNNING

        self.completed_at = datetime.now(UTC)
        if rc == 0:
            self._cached_status = RefreshStatus.COMPLETED
        else:
            self._cached_status = RefreshStatus.FAILED
            self.error_message = f"refresh subprocess exited with code {rc}"
        return self._cached_status


# ---------------------------------------------------------------------------
# RefreshServer
# ---------------------------------------------------------------------------


class RefreshServer:
    """In-memory coordinator for refresh-architecture runs.

    Thread-safe for all RPC methods. Subprocess state is held in the
    ``_handles`` dict keyed by refresh_id; the currently-active refresh (at
    most one) is tracked in ``_active_id``.
    """

    def __init__(
        self,
        graph_path: Path | str = DEFAULT_GRAPH_PATH,
        max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
        spawner: Spawner | None = None,
        refresh_cmd: list[str] | None = None,
    ) -> None:
        self.graph_path = Path(graph_path)
        self.max_age_hours = max_age_hours
        self._spawner: Spawner = spawner or _default_spawner
        self._refresh_cmd: list[str] = refresh_cmd or [
            "bash",
            str(
                Path(__file__).resolve().parent.parent / "refresh_architecture.sh"
            ),
        ]
        self._handles: dict[str, _RefreshHandle] = {}
        self._active_id: str | None = None
        self._lock = threading.Lock()

    # ---- freshness probe ----

    def is_graph_stale(self, max_age_hours: int | None = None) -> dict[str, Any]:
        """Return staleness metadata for the architecture graph."""
        threshold = max_age_hours if max_age_hours is not None else self.max_age_hours
        stale: bool
        mtime_iso: str | None
        node_count: int | None

        if not self.graph_path.exists():
            stale = True
            mtime_iso = None
            node_count = None
        else:
            mtime = self.graph_path.stat().st_mtime
            age_s = time.time() - mtime
            stale = age_s > threshold * 3600
            mtime_iso = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
            try:
                with open(self.graph_path) as f:
                    data = json.load(f)
                node_count = len(data.get("nodes", []))
            except (OSError, json.JSONDecodeError):
                node_count = None

        with self._lock:
            in_flight, current_id = self._current_in_flight_locked()

        return {
            "stale": stale,
            "graph_mtime": mtime_iso,
            "node_count": node_count,
            "refresh_in_flight": in_flight,
            "current_refresh_id": current_id,
        }

    # ---- trigger ----

    def trigger_refresh(self, reason: str, caller: str) -> dict[str, Any]:
        """Spawn a refresh (idempotent while one is already running)."""
        if not reason:
            raise ValueError("reason is required")
        if not caller:
            raise ValueError("caller is required")

        with self._lock:
            in_flight, current_id = self._current_in_flight_locked()
            if in_flight and current_id is not None:
                logger.info(
                    "trigger_refresh: reusing in-flight id=%s (caller=%s, reason=%s)",
                    current_id,
                    caller,
                    reason,
                )
                return {
                    "refresh_id": current_id,
                    "is_new": False,
                    "estimated_duration_s": DEFAULT_ESTIMATED_DURATION_S,
                }

            refresh_id = uuid.uuid4().hex[:16]
            try:
                proc = self._spawner(list(self._refresh_cmd))
            except OSError as exc:
                raise RuntimeError(
                    f"failed to spawn refresh subprocess: {exc}"
                ) from exc
            handle = _RefreshHandle(
                refresh_id=refresh_id,
                started_at=datetime.now(UTC),
                process=proc,
                reason=reason,
                caller=caller,
            )
            self._handles[refresh_id] = handle
            self._active_id = refresh_id
            logger.info(
                "trigger_refresh: spawned id=%s pid=%s (caller=%s, reason=%s)",
                refresh_id,
                proc.pid,
                caller,
                reason,
            )
            return {
                "refresh_id": refresh_id,
                "is_new": True,
                "estimated_duration_s": DEFAULT_ESTIMATED_DURATION_S,
            }

    # ---- poll status ----

    def get_refresh_status(self, refresh_id: str) -> dict[str, Any]:
        """Return status dict for a given refresh id."""
        with self._lock:
            handle = self._handles.get(refresh_id)
            if handle is None:
                return {
                    "status": RefreshStatus.UNKNOWN.value,
                    "started_at": None,
                    "completed_at": None,
                    "error_message": None,
                }
            status = handle.poll_status()
            # If this was the active refresh and it finished, clear active slot.
            if status in {RefreshStatus.COMPLETED, RefreshStatus.FAILED}:
                if self._active_id == refresh_id:
                    self._active_id = None
            return {
                "status": status.value,
                "started_at": handle.started_at.isoformat(),
                "completed_at": (
                    handle.completed_at.isoformat() if handle.completed_at else None
                ),
                "error_message": handle.error_message,
            }

    # ---- internal helpers ----

    def _current_in_flight_locked(self) -> tuple[bool, str | None]:
        """Return (in_flight, active_id) under the server lock."""
        if self._active_id is None:
            return False, None
        handle = self._handles.get(self._active_id)
        if handle is None:
            self._active_id = None
            return False, None
        status = handle.poll_status()
        if status == RefreshStatus.RUNNING:
            return True, self._active_id
        # Terminal — clear the active slot
        self._active_id = None
        return False, None


# ---------------------------------------------------------------------------
# Module-level singleton (for CLI)
# ---------------------------------------------------------------------------


_SERVER: RefreshServer | None = None
_SERVER_LOCK = threading.Lock()


def get_server() -> RefreshServer:
    global _SERVER
    with _SERVER_LOCK:
        if _SERVER is None:
            graph_path = Path(
                os.environ.get("REFRESH_RPC_GRAPH_PATH", str(DEFAULT_GRAPH_PATH))
            )
            _SERVER = RefreshServer(graph_path=graph_path)
        return _SERVER


# ---------------------------------------------------------------------------
# CLI entry point: subprocess-style invocation
# ---------------------------------------------------------------------------


_METHODS: set[str] = {"is_graph_stale", "trigger_refresh", "get_refresh_status"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "refresh-architecture RPC server. Invoke as "
            "`python -m rpc_server <method> <json-args>` — prints a JSON "
            "result to stdout and exits 0 on success."
        ),
    )
    parser.add_argument("method", help=f"One of: {sorted(_METHODS)}")
    parser.add_argument(
        "json_args",
        nargs="?",
        default="{}",
        help="JSON-encoded argument dict (default: {})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    args = parse_args(argv)
    if args.method not in _METHODS:
        print(
            json.dumps(
                {"error": f"unknown method: {args.method}", "valid": sorted(_METHODS)}
            ),
            file=sys.stderr,
        )
        return 2
    try:
        kwargs = json.loads(args.json_args)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON args: {exc}"}), file=sys.stderr)
        return 2
    if not isinstance(kwargs, dict):
        print(json.dumps({"error": "args must be a JSON object"}), file=sys.stderr)
        return 2

    server = get_server()
    try:
        if args.method == "is_graph_stale":
            result = server.is_graph_stale(**kwargs)
        elif args.method == "trigger_refresh":
            result = server.trigger_refresh(**kwargs)
        else:  # get_refresh_status
            result = server.get_refresh_status(**kwargs)
    except (ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
