"""Standalone port allocator for parallel docker-compose stacks.

Assigns conflict-free port blocks to sessions without requiring any database
backend. Each block contains 4 ports at fixed offsets:
  +0 = db_port
  +1 = rest_port
  +2 = realtime_port
  +3 = api_port

Blocks are spaced by ``range_per_session`` (default 100).
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

from .config import PortAllocatorConfig


@dataclass(frozen=True)
class PortAllocation:
    """A port block allocation for a single session."""

    session_id: str
    db_port: int
    rest_port: int
    realtime_port: int
    api_port: int
    compose_project_name: str
    allocated_at: float
    expires_at: float

    @property
    def env_snippet(self) -> str:
        """Return an ``export VAR=value`` snippet ready for shell sourcing."""
        supabase_url = f"http://localhost:{self.rest_port}"
        return "\n".join(
            [
                f"export AGENT_COORDINATOR_DB_PORT={self.db_port}",
                f"export AGENT_COORDINATOR_REST_PORT={self.rest_port}",
                f"export AGENT_COORDINATOR_REALTIME_PORT={self.realtime_port}",
                f"export API_PORT={self.api_port}",
                f"export COMPOSE_PROJECT_NAME={self.compose_project_name}",
                f"export SUPABASE_URL={supabase_url}",
            ]
        )


class PortAllocatorService:
    """In-memory port range allocator with lease-based TTL tracking."""

    def __init__(self, config: PortAllocatorConfig | None = None) -> None:
        if config is None:
            config = PortAllocatorConfig()
        if config.base_port < 1024:
            raise ValueError(
                f"base_port must be >= 1024, got {config.base_port}"
            )
        if config.range_per_session < 4:
            raise ValueError(
                f"range_per_session must be >= 4, got {config.range_per_session}"
            )
        self._config = config
        self._allocations: dict[str, PortAllocation] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def allocate(self, session_id: str) -> PortAllocation | None:
        """Allocate a port block for *session_id*.

        Returns the allocation on success, or ``None`` when no port blocks
        are available.  Duplicate calls for the same *session_id* return
        the existing allocation with a refreshed TTL.
        """
        with self._lock:
            self._cleanup_expired()

            # Duplicate → return existing + refresh TTL
            if session_id in self._allocations:
                existing = self._allocations[session_id]
                now = time.time()
                refreshed = PortAllocation(
                    session_id=existing.session_id,
                    db_port=existing.db_port,
                    rest_port=existing.rest_port,
                    realtime_port=existing.realtime_port,
                    api_port=existing.api_port,
                    compose_project_name=existing.compose_project_name,
                    allocated_at=existing.allocated_at,
                    expires_at=now + self._config.ttl_minutes * 60,
                )
                self._allocations[session_id] = refreshed
                return refreshed

            # Find next free slot index
            used_indices: set[int] = set()
            for alloc in self._allocations.values():
                idx = (alloc.db_port - self._config.base_port) // self._config.range_per_session
                used_indices.add(idx)

            slot: int | None = None
            for candidate in range(self._config.max_sessions):
                if candidate not in used_indices:
                    slot = candidate
                    break

            if slot is None:
                return None  # range exhausted

            base = self._config.base_port + slot * self._config.range_per_session
            now = time.time()
            project_name = _compose_project_name(session_id)
            allocation = PortAllocation(
                session_id=session_id,
                db_port=base,
                rest_port=base + 1,
                realtime_port=base + 2,
                api_port=base + 3,
                compose_project_name=project_name,
                allocated_at=now,
                expires_at=now + self._config.ttl_minutes * 60,
            )
            self._allocations[session_id] = allocation
            return allocation

    def release(self, session_id: str) -> bool:
        """Release the allocation for *session_id*.

        Returns ``True`` unconditionally (idempotent).
        """
        with self._lock:
            self._allocations.pop(session_id, None)
            return True

    def status(self) -> list[PortAllocation]:
        """Return all active (non-expired) allocations."""
        with self._lock:
            self._cleanup_expired()
            return list(self._allocations.values())

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _cleanup_expired(self) -> None:
        """Remove allocations whose TTL has elapsed.  Caller holds lock."""
        now = time.time()
        expired = [
            sid for sid, alloc in self._allocations.items() if alloc.expires_at <= now
        ]
        for sid in expired:
            del self._allocations[sid]


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _compose_project_name(session_id: str) -> str:
    return f"ac-{hashlib.sha256(session_id.encode()).hexdigest()[:8]}"


# ------------------------------------------------------------------ #
# Singleton
# ------------------------------------------------------------------ #

_instance: PortAllocatorService | None = None
_instance_lock = threading.Lock()


def get_port_allocator(config: PortAllocatorConfig | None = None) -> PortAllocatorService:
    """Return the global ``PortAllocatorService`` singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            if config is None:
                config = PortAllocatorConfig.from_env()
            _instance = PortAllocatorService(config)
        return _instance


def reset_port_allocator() -> None:
    """Reset the singleton (for testing)."""
    global _instance
    with _instance_lock:
        _instance = None
