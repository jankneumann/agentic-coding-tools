"""Database transport client using asyncpg (SELECT only)."""

from __future__ import annotations

import os
import time
from typing import Any

from evaluation.gen_eval.models import ActionStep

from .base import StepContext, StepResult


class DbClient:
    """Execute SELECT queries via asyncpg. Mutations are rejected."""

    def __init__(
        self,
        dsn_env: str = "DATABASE_URL",
        default_timeout: float = 30.0,
    ) -> None:
        self._dsn_env = dsn_env
        self._default_timeout = default_timeout
        self._pool: Any | None = None

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            import asyncpg

            dsn = os.environ.get(self._dsn_env)
            if not dsn:
                raise RuntimeError(f"Environment variable {self._dsn_env} is not set")
            self._pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=3)
        return self._pool

    @staticmethod
    def _is_select(sql: str) -> bool:
        """Return True only if the SQL is a SELECT statement."""
        stripped = sql.strip().upper()
        # Allow WITH ... SELECT (CTEs)
        if stripped.startswith("WITH"):
            # Check that the non-CTE part is a SELECT
            # Simple heuristic: must not contain INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE
            forbidden = {
                "INSERT",
                "UPDATE",
                "DELETE",
                "DROP",
                "ALTER",
                "CREATE",
                "TRUNCATE",
            }
            tokens = stripped.split()
            return not bool(forbidden & set(tokens))
        return stripped.startswith("SELECT")

    # ------------------------------------------------------------------
    # TransportClient protocol
    # ------------------------------------------------------------------

    async def execute(self, step: ActionStep, context: StepContext) -> StepResult:
        """Execute a SELECT query from *step.sql*."""
        start = time.perf_counter()
        try:
            sql = step.sql
            if not sql:
                elapsed = (time.perf_counter() - start) * 1000
                return StepResult(error="No SQL provided in step", duration_ms=elapsed)

            if not self._is_select(sql):
                elapsed = (time.perf_counter() - start) * 1000
                return StepResult(
                    error="Only SELECT queries are allowed (no mutations)",
                    duration_ms=elapsed,
                )

            # Variable interpolation
            for var_key, var_val in context.variables.items():
                sql = sql.replace(f"${{{var_key}}}", str(var_val))

            pool = await self._ensure_pool()
            timeout = step.timeout_seconds or context.timeout_seconds

            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, timeout=timeout)

            result_rows: list[dict[str, Any]] = [dict(r) for r in rows]
            body: dict[str, Any] = {"rows": result_rows, "count": len(result_rows)}

            elapsed = (time.perf_counter() - start) * 1000
            return StepResult(body=body, duration_ms=elapsed)
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return StepResult(error=str(exc), duration_ms=elapsed)

    async def health_check(self) -> bool:
        """Test database connectivity with SELECT 1."""
        try:
            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def cleanup(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
