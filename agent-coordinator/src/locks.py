"""File locking service for Agent Coordinator.

Provides distributed file locking to prevent concurrent edits by multiple agents.
Locks are stored in Supabase with automatic TTL expiration.
"""

from dataclasses import dataclass
from datetime import datetime

from .config import get_config
from .db import SupabaseClient, get_db


@dataclass
class Lock:
    """Represents an active file lock."""

    file_path: str
    locked_by: str
    agent_type: str
    locked_at: datetime
    expires_at: datetime
    reason: str | None = None
    session_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Lock":
        return cls(
            file_path=data["file_path"],
            locked_by=data["locked_by"],
            agent_type=data["agent_type"],
            locked_at=datetime.fromisoformat(data["locked_at"].replace("Z", "+00:00")),
            expires_at=datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")),
            reason=data.get("reason"),
            session_id=data.get("session_id"),
        )


@dataclass
class LockResult:
    """Result of a lock acquisition attempt."""

    success: bool
    action: str | None = None  # 'acquired', 'refreshed', or None
    file_path: str | None = None
    expires_at: datetime | None = None
    reason: str | None = None  # Error reason if failed
    locked_by: str | None = None  # Who holds the lock if failed
    lock_reason: str | None = None  # Why they have the lock

    @classmethod
    def from_dict(cls, data: dict) -> "LockResult":
        expires_at = None
        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(
                str(data["expires_at"]).replace("Z", "+00:00")
            )

        return cls(
            success=data["success"],
            action=data.get("action"),
            file_path=data.get("file_path"),
            expires_at=expires_at,
            reason=data.get("reason"),
            locked_by=data.get("locked_by"),
            lock_reason=data.get("lock_reason"),
        )


class LockService:
    """Service for managing file locks."""

    def __init__(self, db: SupabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> SupabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def acquire(
        self,
        file_path: str,
        agent_id: str | None = None,
        agent_type: str | None = None,
        session_id: str | None = None,
        reason: str | None = None,
        ttl_minutes: int | None = None,
    ) -> LockResult:
        """Acquire a lock on a file.

        Args:
            file_path: Path to the file to lock (relative to repo root)
            agent_id: Agent requesting the lock (default: from config)
            agent_type: Type of agent (default: from config)
            session_id: Optional session identifier
            reason: Why the lock is needed (for debugging)
            ttl_minutes: Lock TTL in minutes (default: from config)

        Returns:
            LockResult indicating success/failure and lock details
        """
        config = get_config()

        result = await self.db.rpc(
            "acquire_lock",
            {
                "p_file_path": file_path,
                "p_agent_id": agent_id or config.agent.agent_id,
                "p_agent_type": agent_type or config.agent.agent_type,
                "p_session_id": session_id or config.agent.session_id,
                "p_reason": reason,
                "p_ttl_minutes": ttl_minutes or config.lock.default_ttl_minutes,
            },
        )

        return LockResult.from_dict(result)

    async def release(
        self,
        file_path: str,
        agent_id: str | None = None,
    ) -> LockResult:
        """Release a lock on a file.

        Args:
            file_path: Path to the file to unlock
            agent_id: Agent releasing the lock (default: from config)

        Returns:
            LockResult indicating success/failure
        """
        config = get_config()

        result = await self.db.rpc(
            "release_lock",
            {
                "p_file_path": file_path,
                "p_agent_id": agent_id or config.agent.agent_id,
            },
        )

        return LockResult.from_dict(result)

    async def check(
        self,
        file_paths: list[str] | None = None,
        locked_by: str | None = None,
    ) -> list[Lock]:
        """Check which files are currently locked.

        Args:
            file_paths: Specific files to check (None for all active locks)
            locked_by: Filter by agent ID (None for all agents)

        Returns:
            List of active locks
        """
        query = "expires_at=gt.now()&order=locked_at.desc"

        if file_paths:
            # URL-encode the file paths for the IN query
            paths_str = ",".join(f'"{p}"' for p in file_paths)
            query += f"&file_path=in.({paths_str})"

        if locked_by:
            query += f"&locked_by=eq.{locked_by}"

        locks = await self.db.query("file_locks", query)
        return [Lock.from_dict(lock) for lock in locks]

    async def extend(
        self,
        file_path: str,
        agent_id: str | None = None,
        ttl_minutes: int | None = None,
    ) -> LockResult:
        """Extend an existing lock's TTL.

        This is equivalent to re-acquiring a lock you already hold.

        Args:
            file_path: Path to the file
            agent_id: Agent extending the lock (default: from config)
            ttl_minutes: New TTL in minutes from now

        Returns:
            LockResult indicating success/failure
        """
        return await self.acquire(
            file_path=file_path,
            agent_id=agent_id,
            ttl_minutes=ttl_minutes,
        )

    async def is_locked(self, file_path: str) -> Lock | None:
        """Check if a specific file is locked.

        Args:
            file_path: Path to check

        Returns:
            Lock object if locked, None if not
        """
        locks = await self.check([file_path])
        return locks[0] if locks else None


# Global service instance
_lock_service: LockService | None = None


def get_lock_service() -> LockService:
    """Get the global lock service instance."""
    global _lock_service
    if _lock_service is None:
        _lock_service = LockService()
    return _lock_service
