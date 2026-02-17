"""Direct PostgreSQL client using asyncpg.

Alternative database backend for self-hosted PostgreSQL, Amazon RDS, Neon, etc.
Requires: pip install agent-coordinator[postgres]

This client translates the DatabaseClient protocol methods into standard SQL
executed via asyncpg's connection pool.
"""

import re
from typing import Any
from uuid import UUID

import asyncpg  # noqa: I001

from .config import PostgresConfig

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _coerce_filter_value(val: str) -> Any:
    """Coerce a PostgREST filter string value to the appropriate Python type.

    asyncpg requires typed parameters — passing a string for a UUID or int
    column causes a type mismatch error.
    """
    if val.lower() in ("true", "false"):
        return val.lower() == "true"
    if _UUID_RE.match(val):
        return UUID(val)
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def _validate_identifier(identifier: str, *, allow_qualified: bool = False) -> str:
    """Validate SQL identifiers used for dynamic SQL construction."""
    parts = identifier.split(".") if allow_qualified else [identifier]
    if not parts or any(not _IDENT_RE.match(part) for part in parts):
        raise ValueError(f"Unsafe identifier: {identifier}")
    return identifier


def _validate_select_clause(select: str) -> str:
    """Validate a restricted SELECT projection string."""
    if select.strip() == "*":
        return select
    columns = [col.strip() for col in select.split(",")]
    if not columns:
        raise ValueError("Empty select clause")
    for col in columns:
        _validate_identifier(col, allow_qualified=True)
    return ", ".join(columns)


class DirectPostgresClient:
    """Direct PostgreSQL client using asyncpg connection pool.

    Translates the DatabaseClient interface to standard SQL.
    Use when connecting directly to PostgreSQL without PostgREST.
    """

    def __init__(self, config: PostgresConfig | None = None):
        self._config = config or PostgresConfig()
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                dsn=self._config.dsn,
                min_size=self._config.pool_min,
                max_size=self._config.pool_max,
            )
        return self._pool

    async def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
        """Call a PostgreSQL function.

        Translates to: SELECT function_name(p1 := $1, p2 := $2, ...)
        """
        _validate_identifier(function_name, allow_qualified=True)
        pool = await self._get_pool()

        # Build named parameter call
        param_names = list(params.keys())
        param_values = list(params.values())
        param_clause = ", ".join(
            f"{name} := ${i + 1}" for i, name in enumerate(param_names)
        )

        query = f"SELECT {function_name}({param_clause})"
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, *param_values)
            if row is None:
                return None
            result = row[0]
            # PostgreSQL JSONB returns dict directly via asyncpg
            return result

    async def query(
        self,
        table: str,
        query_params: str | None = None,
        select: str = "*",
    ) -> list[dict[str, Any]]:
        """Query a table with optional PostgREST-style filters.

        Translates PostgREST filter syntax to SQL WHERE clauses.
        """
        pool = await self._get_pool()

        where_clauses: list[str] = []
        order_clause = ""
        limit_clause = ""
        values: list[Any] = []
        param_idx = 1

        if query_params:
            for part in query_params.split("&"):
                if part.startswith("order="):
                    order_parts = part[6:].split(".")
                    col = _validate_identifier(order_parts[0], allow_qualified=True)
                    is_desc = len(order_parts) > 1 and order_parts[1] == "desc"
                    direction = "DESC" if is_desc else "ASC"
                    order_clause = f" ORDER BY {col} {direction}"
                elif part.startswith("limit="):
                    limit_clause = f" LIMIT {int(part[6:])}"
                elif "=eq." in part:
                    col, val = part.split("=eq.", 1)
                    _validate_identifier(col, allow_qualified=True)
                    where_clauses.append(f"{col} = ${param_idx}")
                    values.append(_coerce_filter_value(val))
                    param_idx += 1
                elif "=gt." in part:
                    col, val = part.split("=gt.", 1)
                    _validate_identifier(col, allow_qualified=True)
                    if val == "now()":
                        where_clauses.append(f"{col} > NOW()")
                    else:
                        where_clauses.append(f"{col} > ${param_idx}")
                        values.append(_coerce_filter_value(val))
                        param_idx += 1
                elif "=gte." in part:
                    col, val = part.split("=gte.", 1)
                    _validate_identifier(col, allow_qualified=True)
                    where_clauses.append(f"{col} >= ${param_idx}")
                    values.append(_coerce_filter_value(val))
                    param_idx += 1
                elif "=lte." in part:
                    col, val = part.split("=lte.", 1)
                    _validate_identifier(col, allow_qualified=True)
                    where_clauses.append(f"{col} <= ${param_idx}")
                    values.append(_coerce_filter_value(val))
                    param_idx += 1
                elif "=in." in part:
                    col, val = part.split("=in.", 1)
                    _validate_identifier(col, allow_qualified=True)
                    # Parse PostgREST IN syntax: (val1,val2,val3)
                    in_values = val.strip("()").replace('"', "").split(",")
                    placeholders = ", ".join(
                        f"${param_idx + i}" for i in range(len(in_values))
                    )
                    where_clauses.append(f"{col} IN ({placeholders})")
                    values.extend(_coerce_filter_value(v) for v in in_values)
                    param_idx += len(in_values)

        where = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        safe_select = _validate_select_clause(select)
        safe_table = _validate_identifier(table, allow_qualified=True)
        query_sql = (
            f"SELECT {safe_select} FROM {safe_table}{where}{order_clause}{limit_clause}"
        )

        async with pool.acquire() as conn:
            rows = await conn.fetch(query_sql, *values)
            return [dict(row) for row in rows]

    async def insert(
        self,
        table: str,
        data: dict[str, Any],
        return_data: bool = True,
    ) -> dict[str, Any]:
        """Insert a row into a table."""
        pool = await self._get_pool()

        columns = list(data.keys())
        _validate_identifier(table, allow_qualified=True)
        for col in columns:
            _validate_identifier(col, allow_qualified=False)
        values = list(data.values())
        placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
        col_list = ", ".join(columns)

        returning = " RETURNING *" if return_data else ""
        query = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}){returning}"

        async with pool.acquire() as conn:
            if return_data:
                row = await conn.fetchrow(query, *values)
                return dict(row) if row else {}
            else:
                await conn.execute(query, *values)
                return {}

    async def update(
        self,
        table: str,
        match: dict[str, Any],
        data: dict[str, Any],
        return_data: bool = True,
    ) -> list[dict[str, Any]]:
        """Update matching rows in a table."""
        pool = await self._get_pool()

        set_parts = []
        _validate_identifier(table, allow_qualified=True)
        values: list[Any] = []
        idx = 1

        for col, val in data.items():
            _validate_identifier(col, allow_qualified=False)
            set_parts.append(f"{col} = ${idx}")
            values.append(val)
            idx += 1

        where_parts = []
        for col, val in match.items():
            _validate_identifier(col, allow_qualified=False)
            where_parts.append(f"{col} = ${idx}")
            values.append(val)
            idx += 1

        set_clause = ", ".join(set_parts)
        where_clause = " AND ".join(where_parts)
        returning = " RETURNING *" if return_data else ""

        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}{returning}"

        async with pool.acquire() as conn:
            if return_data:
                rows = await conn.fetch(query, *values)
                return [dict(row) for row in rows]
            else:
                await conn.execute(query, *values)
                return []

    async def delete(
        self,
        table: str,
        match: dict[str, Any],
    ) -> None:
        """Delete matching rows from a table."""
        pool = await self._get_pool()
        _validate_identifier(table, allow_qualified=True)

        where_parts = []
        values: list[Any] = []
        for idx, (col, val) in enumerate(match.items(), 1):
            _validate_identifier(col, allow_qualified=False)
            where_parts.append(f"{col} = ${idx}")
            values.append(val)

        where_clause = " AND ".join(where_parts)
        query = f"DELETE FROM {table} WHERE {where_clause}"

        async with pool.acquire() as conn:
            await conn.execute(query, *values)

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
