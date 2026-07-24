"""Lifecycle and readiness tests for the process-owned code-search runtime."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any

import pytest

from src.code_search import CodeSearchRequest
from src.code_search_runtime import (
    _USABLE_INDEX_COUNT_SQL,
    CodeSearchOverloadedError,
    CodeSearchRuntime,
    CodeSearchRuntimeConfig,
    CodeSearchStatus,
)


class _Pool:
    def __init__(self, usable_indexes: int = 1) -> None:
        self.usable_indexes = usable_indexes
        self.closed = False
        self.loops: list[asyncio.AbstractEventLoop] = []

    async def fetchval(self, _sql: str, *_args: Any) -> int:
        self.loops.append(asyncio.get_running_loop())
        return self.usable_indexes

    async def close(self) -> None:
        self.closed = True


class _Provider:
    model_id = "model"
    dimension = 3
    fingerprint = "a" * 64

    def __init__(self) -> None:
        self.ready = True
        self.probes = 0
        self.closed = False

    async def check_readiness(self) -> Any:
        from code_search_pkg.embedding_protocol import (
            EmbeddingErrorCode,
            EmbeddingReadiness,
        )

        self.probes += 1
        if self.ready:
            return EmbeddingReadiness.ready()
        return EmbeddingReadiness.failed(
            EmbeddingErrorCode.PROVIDER_FAILURE,
            "embedding provider request failed",
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0, 0.0] for _ in texts]

    async def aclose(self) -> None:
        self.closed = True


class _Service:
    def __init__(
        self,
        result: Any | None = None,
        operation: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        self.result = result
        self.operation = operation
        self.calls = 0

    async def search(self, _request: Any, *, principal_id: str) -> Any:
        assert principal_id and principal_id != "secret"
        self.calls += 1
        if self.operation is not None:
            return await self.operation()
        return self.result


def _config(**updates: Any) -> CodeSearchRuntimeConfig:
    values = {
        "enabled": True,
        "operation_timeout_seconds": 0.05,
        "shutdown_timeout_seconds": 0.05,
        "provider_ttl_seconds": 10.0,
        "index_ttl_seconds": 10.0,
        "failure_backoff_seconds": 0.01,
        "max_concurrency": 1,
        "overload_timeout_seconds": 0.001,
    }
    values.update(updates)
    return CodeSearchRuntimeConfig(**values)


@pytest.mark.asyncio
async def test_disabled_runtime_performs_zero_optional_work() -> None:
    calls: list[str] = []

    async def pool_factory() -> _Pool:
        calls.append("pool")
        return _Pool()

    def provider_factory() -> _Provider:
        calls.append("provider")
        return _Provider()

    runtime = await CodeSearchRuntime.create(
        CodeSearchRuntimeConfig(enabled=False),
        pool_factory=pool_factory,
        provider_factory=provider_factory,
    )

    assert calls == []
    assert runtime.status_snapshot() == CodeSearchStatus(
        available=False,
        state="disabled",
        reason="disabled",
        usable_index_count=0,
    )
    await runtime.close()
    assert calls == []


@pytest.mark.asyncio
async def test_runtime_resources_are_created_used_and_closed_in_owning_loop() -> None:
    pool = _Pool()
    provider = _Provider()
    owner = asyncio.get_running_loop()

    async def pool_factory() -> _Pool:
        assert asyncio.get_running_loop() is owner
        return pool

    runtime = await CodeSearchRuntime.create(
        _config(),
        pool_factory=pool_factory,
        provider_factory=lambda: provider,
        service_factory=lambda **_: _Service(),
    )
    status = await runtime.status()

    assert status.available is True
    assert status.usable_index_count == 1
    assert pool.loops == [owner]
    await runtime.close()
    assert pool.closed is True
    assert provider.closed is True


def test_status_truth_table_and_readiness_sql_match_frozen_contract() -> None:
    with pytest.raises(ValueError):
        CodeSearchStatus(
            available=False,
            state="unavailable",
            reason="initialization_failed",
            usable_index_count=0,
        )
    with pytest.raises(ValueError):
        CodeSearchStatus(
            available=True,
            state="ready",
            reason="ready",
            usable_index_count=0,
        )
    assert "FROM code_search_index_files AS manifest" in _USABLE_INDEX_COUNT_SQL
    assert "to_regclass" in _USABLE_INDEX_COUNT_SQL


@pytest.mark.asyncio
async def test_status_uses_ttl_then_recovers_after_failure_backoff() -> None:
    pool = _Pool()
    provider = _Provider()
    runtime = await CodeSearchRuntime.create(
        _config(provider_ttl_seconds=60, index_ttl_seconds=60),
        pool_factory=lambda: _async_value(pool),
        provider_factory=lambda: provider,
        service_factory=lambda **_: _Service(),
    )

    assert (await runtime.status()).available is True
    assert provider.probes == 1
    assert (await runtime.status()).available is True
    assert provider.probes == 1

    provider.ready = False
    runtime.invalidate(provider=True, indexes=False)
    assert (await runtime.status()).reason == "provider_unavailable"
    provider.ready = True
    assert (await runtime.status()).reason == "provider_unavailable"
    await asyncio.sleep(0.015)
    assert (await runtime.status()).available is True
    await runtime.close()


@pytest.mark.asyncio
async def test_unavailable_service_result_immediately_invalidates_readiness() -> None:
    provider = _Provider()
    service = _Service(result=SimpleNamespace(state="unavailable"))
    runtime = await CodeSearchRuntime.create(
        _config(),
        pool_factory=lambda: _async_value(_Pool()),
        provider_factory=lambda: provider,
        service_factory=lambda **_: service,
    )
    assert (await runtime.status()).available is True
    assert provider.probes == 1

    await runtime.search(_request(), principal_id="agent")
    assert (await runtime.status()).available is True
    assert provider.probes == 2
    await runtime.close()


@pytest.mark.asyncio
async def test_initialization_failure_degrades_without_failing_process() -> None:
    async def failing_pool() -> _Pool:
        raise RuntimeError("postgresql://secret@host/db")

    runtime = await CodeSearchRuntime.create(
        _config(),
        pool_factory=failing_pool,
        provider_factory=_Provider,
    )

    assert await runtime.status() == CodeSearchStatus(
        available=False,
        state="unavailable",
        reason="registry_unavailable",
        usable_index_count=0,
    )
    await runtime.close()


@pytest.mark.asyncio
async def test_initialization_and_readiness_emit_sanitized_state_evidence(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="src.code_search_runtime")
    runtime = await CodeSearchRuntime.create(
        _config(),
        pool_factory=lambda: _async_value(_Pool()),
        provider_factory=_Provider,
        service_factory=lambda **_: _Service(),
    )

    status = await runtime.status()

    assert status.available is True
    assert runtime.state_counts["initialization:unavailable:no_usable_index"] == 1
    assert runtime.state_counts["readiness:ready:ready"] == 1
    assert "event=initialization state=unavailable reason=no_usable_index" in caplog.text
    assert "event=readiness state=ready reason=ready" in caplog.text
    assert "duration_bucket=" in caplog.text
    assert "where is readiness checked" not in caplog.text
    await runtime.close()


@pytest.mark.asyncio
async def test_search_is_bounded_overload_is_retryable_and_shutdown_cancels() -> None:
    blocker = asyncio.Event()

    async def blocked() -> Any:
        await blocker.wait()

    service = _Service(operation=blocked)
    runtime = await CodeSearchRuntime.create(
        _config(operation_timeout_seconds=1),
        pool_factory=lambda: _async_value(_Pool()),
        provider_factory=_Provider,
        service_factory=lambda **_: service,
    )
    request = _request()
    first = asyncio.create_task(runtime.search(request, principal_id="agent"))
    await asyncio.sleep(0)
    with pytest.raises(CodeSearchOverloadedError):
        await runtime.search(request, principal_id="agent")

    await runtime.close()
    with pytest.raises(asyncio.CancelledError):
        await first


@pytest.mark.asyncio
async def test_query_timeout_returns_sanitized_unavailable_envelope() -> None:
    async def blocked() -> Any:
        await asyncio.Event().wait()

    runtime = await CodeSearchRuntime.create(
        _config(operation_timeout_seconds=0.005),
        pool_factory=lambda: _async_value(_Pool()),
        provider_factory=_Provider,
        service_factory=lambda **_: _Service(operation=blocked),
    )

    response = await runtime.search(_request(), principal_id="agent")
    assert response.state == "unavailable"
    assert response.results == []
    assert response.fallback.required is True
    await runtime.close()


async def _async_value(value: Any) -> Any:
    return value


def _request() -> CodeSearchRequest:
    return CodeSearchRequest.model_validate(
        {
            "query": "where is readiness checked",
            "repo_slug": "agentic_coding_tools",
            "source_revision": "a" * 40,
            "namespace": {"kind": "main", "key": "main"},
            "scope": {"kind": "explicit", "read_allow": ["agent-coordinator/**"]},
        }
    )
