"""Database client abstraction for Agent Coordinator.

Provides a DatabaseClient protocol with two implementations:
- SupabaseClient: PostgREST HTTP via httpx (default, zero-config with Supabase)
- DirectPostgresClient: asyncpg for direct PostgreSQL connections (self-hosted)

Usage:
    from src.db import get_db, DatabaseClient

    # Production: uses factory based on DB_BACKEND env var
    db = get_db()

    # Testing: inject a mock
    service = LockService(db=mock_client)
"""

from typing import Any, Protocol, runtime_checkable

import httpx

from .config import SupabaseConfig, get_config


@runtime_checkable
class DatabaseClient(Protocol):
    """Protocol for database backends.

    All implementations must support PostgreSQL-compatible operations.
    Services depend on this protocol, not on a specific implementation.
    """

    async def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
        """Call a stored PostgreSQL function."""
        ...

    async def query(
        self,
        table: str,
        query_params: str | None = None,
        select: str = "*",
    ) -> list[dict[str, Any]]:
        """Query a table with optional filters."""
        ...

    async def insert(
        self,
        table: str,
        data: dict[str, Any],
        return_data: bool = True,
    ) -> dict[str, Any]:
        """Insert a row."""
        ...

    async def update(
        self,
        table: str,
        match: dict[str, Any],
        data: dict[str, Any],
        return_data: bool = True,
    ) -> list[dict[str, Any]]:
        """Update matching rows."""
        ...

    async def delete(self, table: str, match: dict[str, Any]) -> None:
        """Delete matching rows."""
        ...

    async def close(self) -> None:
        """Close the connection."""
        ...


class SupabaseClient:
    """Async Supabase client for coordination operations.

    Uses httpx to communicate with Supabase's PostgREST API.
    This is the default backend (DB_BACKEND=supabase).
    """

    def __init__(self, config: SupabaseConfig | None = None):
        self._config = config
        self._client: httpx.AsyncClient | None = None

    @property
    def config(self) -> SupabaseConfig:
        if self._config is None:
            self._config = get_config().supabase
        return self._config

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        """Get auth headers for Supabase requests."""
        return {
            "apikey": self.config.service_key,
            "Authorization": f"Bearer {self.config.service_key}",
            "Content-Type": "application/json",
        }

    async def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
        """Call a Supabase RPC function.

        Args:
            function_name: Name of the PostgreSQL function
            params: Parameters to pass to the function

        Returns:
            The function result (usually JSONB -> dict)

        Raises:
            httpx.HTTPStatusError: On API errors
        """
        response = await self.client.post(
            f"{self.config.url}{self.config.rest_prefix}/rpc/{function_name}",
            headers=self._headers(),
            json=params,
        )
        response.raise_for_status()
        return response.json()

    async def query(
        self,
        table: str,
        query_params: str | None = None,
        select: str = "*",
    ) -> list[dict[str, Any]]:
        """Query a table with optional filters.

        Args:
            table: Table name
            query_params: PostgREST query string (e.g., "status=eq.pending&order=created_at.desc")
            select: Columns to select (default: "*")

        Returns:
            List of matching rows
        """
        url = f"{self.config.url}{self.config.rest_prefix}/{table}?select={select}"
        if query_params:
            url += f"&{query_params}"

        response = await self.client.get(url, headers=self._headers())
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def insert(
        self,
        table: str,
        data: dict[str, Any],
        return_data: bool = True,
    ) -> dict[str, Any]:
        """Insert a row into a table.

        Args:
            table: Table name
            data: Row data
            return_data: Whether to return the inserted row

        Returns:
            The inserted row (if return_data=True) or empty dict
        """
        headers = self._headers()
        if return_data:
            headers["Prefer"] = "return=representation"

        response = await self.client.post(
            f"{self.config.url}{self.config.rest_prefix}/{table}",
            headers=headers,
            json=data,
        )
        response.raise_for_status()

        result = response.json()
        return result[0] if result else {}

    async def update(
        self,
        table: str,
        match: dict[str, Any],
        data: dict[str, Any],
        return_data: bool = True,
    ) -> list[dict[str, Any]]:
        """Update matching rows in a table.

        Args:
            table: Table name
            match: Conditions for matching rows (column=value)
            data: New values for matched rows
            return_data: Whether to return updated rows

        Returns:
            List of updated rows (if return_data=True)
        """
        query_parts = [f"{k}=eq.{v}" for k, v in match.items()]
        query_string = "&".join(query_parts)

        headers = self._headers()
        if return_data:
            headers["Prefer"] = "return=representation"

        response = await self.client.patch(
            f"{self.config.url}{self.config.rest_prefix}/{table}?{query_string}",
            headers=headers,
            json=data,
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def delete(
        self,
        table: str,
        match: dict[str, Any],
    ) -> None:
        """Delete matching rows from a table.

        Args:
            table: Table name
            match: Conditions for matching rows (column=value)
        """
        query_parts = [f"{k}=eq.{v}" for k, v in match.items()]
        query_string = "&".join(query_parts)

        response = await self.client.delete(
            f"{self.config.url}{self.config.rest_prefix}/{table}?{query_string}",
            headers=self._headers(),
        )
        response.raise_for_status()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def create_db_client() -> DatabaseClient:
    """Factory: returns the appropriate DatabaseClient based on config.

    Uses DB_BACKEND env var (default: "supabase").
    """
    config = get_config()
    backend = config.database.backend

    if backend == "supabase":
        return SupabaseClient(config.supabase)
    elif backend == "postgres":
        try:
            from .db_postgres import DirectPostgresClient
        except ImportError as e:
            raise ImportError(
                "asyncpg is required for DB_BACKEND=postgres. "
                "Install with: pip install agent-coordinator[postgres]"
            ) from e
        return DirectPostgresClient(config.database.postgres)
    else:
        raise ValueError(f"Unknown database backend: {backend}")


# Global client instance (lazy-loaded)
_db: DatabaseClient | None = None


def get_db() -> DatabaseClient:
    """Get the global database client instance."""
    global _db
    if _db is None:
        _db = create_db_client()
    return _db


async def close_db() -> None:
    """Close the global database client."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


def reset_db() -> None:
    """Reset the global database client (for testing)."""
    global _db
    _db = None
