"""Loop-owned lifecycle and bounded readiness for optional semantic search."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    # Imported for typing only; the runtime import stays inside the function
    # below to avoid a circular import with code_search.
    from .code_search import CodeSearchResponse

logger = logging.getLogger(__name__)

_USABLE_INDEX_COUNT_SQL = """
SELECT count(*)
FROM code_search_registry AS registry
JOIN code_search_indexes AS candidate
  ON candidate.index_id = registry.canonical_index_id
 AND candidate.repo_slug = registry.repo_slug
WHERE candidate.namespace_kind = 'main'
  AND candidate.namespace_key = 'main'
  AND candidate.status = 'ready'
  AND candidate.chunk_count > 0
  AND candidate.embedder_model = $1
  AND candidate.embedding_dim = $2
  AND candidate.embedder_fingerprint = $3
  AND candidate.embedder_fingerprint <> repeat('0', 64)
  AND candidate.policy_fingerprint <> repeat('0', 64)
  AND candidate.pipeline_fingerprint <> repeat('0', 64)
  AND EXISTS (
      SELECT 1
      FROM code_search_index_files AS manifest
      WHERE manifest.index_id = candidate.index_id
  )
  AND to_regclass(format('%I', 'code_chunks__' || candidate.storage_key)) IS NOT NULL
"""


def code_search_enabled(environment: Mapping[str, str] | None = None) -> bool:
    """Read the default-off gate without importing optional search packages."""

    env = os.environ if environment is None else environment
    return env.get("CODE_SEARCH_ENABLED", "").lower() in {"1", "true", "yes", "on"}


class CodeSearchOverloadedError(RuntimeError):
    """Bounded semantic capacity is exhausted."""

    status = 429
    type_uri = "urn:coordinator:code-search:overloaded"

    def __init__(self) -> None:
        super().__init__("Code search is busy; retry shortly.")


class CodeSearchStatus(BaseModel):
    """Closed body-aware status document shared by discovery clients."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    state: Literal["ready", "disabled", "uninitialized", "not_configured", "unavailable"]
    reason: str = Field(min_length=1, max_length=64)
    usable_index_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_truth_table(self) -> CodeSearchStatus:
        if self.available:
            if self.state != "ready" or self.reason != "ready" or self.usable_index_count < 1:
                raise ValueError("available status must prove ready usable indexes")
        elif self.usable_index_count != 0 or self.state == "ready":
            raise ValueError("unavailable status cannot advertise usable indexes")
        expected = {
            "disabled": {"disabled"},
            "uninitialized": {"uninitialized"},
            "not_configured": {"missing_configuration"},
            "unavailable": {
                "registry_unavailable",
                "provider_unavailable",
                "no_usable_index",
            },
            "ready": {"ready"},
        }
        if self.reason not in expected[self.state]:
            raise ValueError("status state and reason are inconsistent")
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


@dataclass(frozen=True, slots=True)
class CodeSearchRuntimeConfig:
    enabled: bool = False
    operation_timeout_seconds: float = 10.0
    shutdown_timeout_seconds: float = 5.0
    provider_ttl_seconds: float = 30.0
    index_ttl_seconds: float = 15.0
    failure_backoff_seconds: float = 2.0
    max_failure_backoff_seconds: float = 30.0
    max_concurrency: int = 4
    overload_timeout_seconds: float = 0.01

    def __post_init__(self) -> None:
        positive = (
            self.operation_timeout_seconds,
            self.shutdown_timeout_seconds,
            self.provider_ttl_seconds,
            self.index_ttl_seconds,
            self.failure_backoff_seconds,
            self.max_failure_backoff_seconds,
            self.overload_timeout_seconds,
        )
        if any(value <= 0 for value in positive) or self.max_concurrency < 1:
            raise ValueError("code-search runtime bounds must be positive")

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> CodeSearchRuntimeConfig:
        env = os.environ if environment is None else environment
        return cls(
            enabled=code_search_enabled(env),
            operation_timeout_seconds=_float_env(env, "CODE_SEARCH_TIMEOUT_SECONDS", 10.0),
            shutdown_timeout_seconds=_float_env(env, "CODE_SEARCH_SHUTDOWN_TIMEOUT_SECONDS", 5.0),
            provider_ttl_seconds=_float_env(env, "CODE_SEARCH_PROVIDER_TTL_SECONDS", 30.0),
            index_ttl_seconds=_float_env(env, "CODE_SEARCH_INDEX_TTL_SECONDS", 15.0),
            failure_backoff_seconds=_float_env(env, "CODE_SEARCH_FAILURE_BACKOFF_SECONDS", 2.0),
            max_failure_backoff_seconds=_float_env(
                env, "CODE_SEARCH_MAX_FAILURE_BACKOFF_SECONDS", 30.0
            ),
            max_concurrency=_int_env(env, "CODE_SEARCH_MAX_CONCURRENCY", 4),
            overload_timeout_seconds=_float_env(env, "CODE_SEARCH_OVERLOAD_TIMEOUT_SECONDS", 0.01),
        )


@dataclass(slots=True)
class _Cache:
    value: Any = None
    expires_at: float = 0.0
    failures: int = 0

    def clear(self) -> None:
        self.value = None
        self.expires_at = 0.0


class CodeSearchRuntime:
    """Own one pool/provider/service in the event loop that serves requests."""

    def __init__(self, config: CodeSearchRuntimeConfig) -> None:
        self.config = config
        self._pool: Any | None = None
        self._provider: Any | None = None
        self._service: Any | None = None
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._initial_status = _status("uninitialized", "uninitialized")
        self._provider_cache = _Cache()
        self._index_cache = _Cache()
        self._status_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._active: set[asyncio.Task[Any]] = set()
        self._state_counts: Counter[tuple[str, str, str, str, str, str]] = Counter()
        self._closed = False

    @classmethod
    async def create(
        cls,
        config: CodeSearchRuntimeConfig | None = None,
        *,
        environment: Mapping[str, str] | None = None,
        pool_factory: Callable[[], Awaitable[Any]] | None = None,
        provider_factory: Callable[[], Any] | None = None,
        service_factory: Callable[..., Any] | None = None,
        grant_resolver: Any | None = None,
        work_package_resolver: Any | None = None,
    ) -> CodeSearchRuntime:
        runtime = cls(config or CodeSearchRuntimeConfig.from_env(environment))
        started_at = monotonic()
        if not runtime.config.enabled:
            return runtime._finish_initialization(
                _status("disabled", "disabled"),
                started_at,
            )
        runtime._owner_loop = asyncio.get_running_loop()
        try:
            if provider_factory is None:

                def provider_factory() -> Any:
                    return _provider_from_env(environment)

            runtime._provider = provider_factory()
        except (KeyError, TypeError, ValueError):
            return runtime._finish_initialization(
                _status("not_configured", "missing_configuration"),
                started_at,
            )
        except Exception:
            return runtime._finish_initialization(
                _status("unavailable", "provider_unavailable"),
                started_at,
            )

        try:
            factory = pool_factory or (lambda: _pool_from_env(environment))
            runtime._pool = await asyncio.wait_for(
                factory(),
                timeout=runtime.config.operation_timeout_seconds,
            )
        except ValueError:
            return runtime._finish_initialization(
                _status("not_configured", "missing_configuration"),
                started_at,
            )
        except Exception:
            return runtime._finish_initialization(
                _status("unavailable", "registry_unavailable"),
                started_at,
            )

        try:
            if service_factory is None:
                from code_search_pkg.query_pg import QueryProviderContract

                from .code_search import CodeSearchService

                service_factory = CodeSearchService
                grant_resolver = grant_resolver or _grant_resolver_from_env(environment)
                provider = runtime._provider
                if provider is None:
                    raise RuntimeError("embedding provider is unavailable")

                async def embed_one(text: str) -> list[float]:
                    vectors = await provider.embed([text])
                    if len(vectors) != 1:
                        raise RuntimeError("embedding provider returned an invalid response")
                    return list(vectors[0])

                runtime._service = service_factory(
                    pool=runtime._pool,
                    embedder=embed_one,
                    provider_contract=QueryProviderContract(
                        model=runtime._provider.model_id,
                        dimension=runtime._provider.dimension,
                        embedder_fingerprint=runtime._provider.fingerprint,
                    ),
                    grant_resolver=grant_resolver,
                    work_package_resolver=work_package_resolver,
                )
            else:
                runtime._service = service_factory(
                    pool=runtime._pool,
                    provider=runtime._provider,
                )
        except Exception:
            await runtime._close_pool()
            await runtime._close_provider()
            return runtime._finish_initialization(
                _status("unavailable", "registry_unavailable"),
                started_at,
            )
        return runtime._finish_initialization(
            _status("unavailable", "no_usable_index"),
            started_at,
        )

    @property
    def state_counts(self) -> dict[tuple[str, str, str, str, str, str], int]:
        """Return privacy-safe completion counters for operational states."""

        return dict(self._state_counts)

    def status_snapshot(self) -> CodeSearchStatus:
        """Return the last bounded status without starting optional work."""

        if not self.config.enabled or self._service is None:
            return self._initial_status
        if isinstance(self._index_cache.value, CodeSearchStatus):
            return self._index_cache.value
        return self._initial_status

    async def status(self) -> CodeSearchStatus:
        self._assert_owner()
        started_at = monotonic()
        if not self.config.enabled or self._service is None:
            return self._record_status("readiness", self._initial_status, started_at)
        async with self._status_lock:
            return await self._status_after_lock(started_at)

    async def _status_after_lock(self, started_at: float) -> CodeSearchStatus:
        """Refresh provider/index readiness once for concurrent status callers."""

        provider_ready = await self._provider_ready()
        if not provider_ready:
            return self._record_status(
                "readiness",
                _status("unavailable", "provider_unavailable"),
                started_at,
            )
        provider, pool = self._provider, self._pool
        if provider is None or pool is None:
            return self._record_status(
                "readiness",
                _status("unavailable", "registry_unavailable"),
                started_at,
            )
        now = monotonic()
        cached_status = self._index_cache.value
        if isinstance(cached_status, CodeSearchStatus) and now < self._index_cache.expires_at:
            return self._record_status("readiness", cached_status, started_at)
        try:
            count = int(
                await asyncio.wait_for(
                    pool.fetchval(
                        _USABLE_INDEX_COUNT_SQL,
                        provider.model_id,
                        provider.dimension,
                        provider.fingerprint,
                    ),
                    timeout=self.config.operation_timeout_seconds,
                )
                or 0
            )
        except Exception:
            result = _status("unavailable", "registry_unavailable")
            self._cache_failure(self._index_cache, result)
            return self._record_status("readiness", result, started_at)
        result = (
            CodeSearchStatus(
                available=True,
                state="ready",
                reason="ready",
                usable_index_count=count,
            )
            if count > 0
            else _status("unavailable", "no_usable_index")
        )
        self._index_cache.value = result
        self._index_cache.failures = 0
        self._index_cache.expires_at = now + self.config.index_ttl_seconds
        return self._record_status("readiness", result, started_at)

    def _finish_initialization(
        self,
        status: CodeSearchStatus,
        started_at: float,
    ) -> CodeSearchRuntime:
        self._initial_status = status
        self._record_status("initialization", status, started_at)
        return self

    def _record_status(
        self,
        event: str,
        status: CodeSearchStatus,
        started_at: float,
    ) -> CodeSearchStatus:
        duration_bucket = _duration_bucket(monotonic() - started_at)
        repo_slug = "all"
        namespace_kind = "main" if event == "readiness" else "all"
        key = (
            event,
            status.state,
            status.reason,
            duration_bucket,
            repo_slug,
            namespace_kind,
        )
        self._state_counts[key] += 1
        logger.info(
            "code_search_runtime event=%s state=%s reason=%s "
            "repo_slug=%s namespace_kind=%s duration_bucket=%s",
            event,
            status.state,
            status.reason,
            repo_slug,
            namespace_kind,
            duration_bucket,
        )
        return status

    async def search(self, request: Any, *, principal_id: str) -> CodeSearchResponse:
        self._assert_owner()
        if self._closed or self._service is None:
            return _sanitized_unavailable(request)
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.config.overload_timeout_seconds,
            )
        except TimeoutError as error:
            raise CodeSearchOverloadedError() from error
        task = asyncio.current_task()
        if task is not None:
            self._active.add(task)
        try:
            # `_service` is an intentionally dynamic seam; state the contract it
            # is required to honour here rather than propagating Any upward.
            result: CodeSearchResponse = await asyncio.wait_for(
                self._service.search(request, principal_id=principal_id),
                timeout=self.config.operation_timeout_seconds,
            )
            state = getattr(result, "state", None)
            self.invalidate(
                provider=str(state) == "unavailable",
                indexes=True,
            )
            return result
        except asyncio.CancelledError:
            raise
        except Exception as error:
            from .code_search import CodeSearchError

            self.invalidate(provider=True, indexes=True)
            if isinstance(error, CodeSearchError):
                raise
            return _sanitized_unavailable(request)
        finally:
            if task is not None:
                self._active.discard(task)
            self._semaphore.release()

    def invalidate(self, *, provider: bool = True, indexes: bool = True) -> None:
        if provider:
            self._provider_cache.clear()
        if indexes:
            self._index_cache.clear()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        current = asyncio.current_task()
        active = [task for task in self._active if task is not current and not task.done()]
        for task in active:
            task.cancel()
        if active:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*active, return_exceptions=True),
                    timeout=self.config.shutdown_timeout_seconds,
                )
            except TimeoutError:
                logger.warning("code_search_shutdown_timeout")
        await self._close_pool()
        await self._close_provider()
        self.invalidate()
        self._service = None
        self._provider = None
        self._initial_status = _status("uninitialized", "uninitialized")

    async def _provider_ready(self) -> bool:
        provider = self._provider
        if provider is None:
            return False
        now = monotonic()
        if self._provider_cache.value is not None and now < self._provider_cache.expires_at:
            return bool(self._provider_cache.value)
        try:
            readiness = await asyncio.wait_for(
                provider.check_readiness(),
                timeout=self.config.operation_timeout_seconds,
            )
            ready = str(readiness.state) == "ready"
        except Exception:
            ready = False
        if ready:
            self._provider_cache.value = True
            self._provider_cache.failures = 0
            self._provider_cache.expires_at = now + self.config.provider_ttl_seconds
        else:
            self._cache_failure(self._provider_cache, False)
        return ready

    def _cache_failure(self, cache: _Cache, value: Any) -> None:
        cache.failures += 1
        delay = min(
            self.config.failure_backoff_seconds * (2 ** (cache.failures - 1)),
            self.config.max_failure_backoff_seconds,
        )
        cache.value = value
        cache.expires_at = monotonic() + delay

    async def _close_pool(self) -> None:
        pool, self._pool = self._pool, None
        if pool is None:
            return
        try:
            await asyncio.wait_for(
                pool.close(),
                timeout=self.config.shutdown_timeout_seconds,
            )
        except Exception:
            logger.warning("code_search_pool_close_failed", exc_info=False)

    async def _close_provider(self) -> None:
        provider, self._provider = self._provider, None
        if provider is None:
            return
        closer = getattr(provider, "aclose", None)
        if not callable(closer):
            closer = getattr(provider, "close", None)
        if not callable(closer):
            return
        try:
            result = closer()
            if hasattr(result, "__await__"):
                await asyncio.wait_for(
                    result,
                    timeout=self.config.shutdown_timeout_seconds,
                )
        except Exception:
            logger.warning("code_search_provider_close_failed", exc_info=False)

    def _assert_owner(self) -> None:
        if self._owner_loop is not None and asyncio.get_running_loop() is not self._owner_loop:
            raise RuntimeError("code-search runtime used outside its owning event loop")


_runtime: CodeSearchRuntime | Any | None = None


async def start_code_search_runtime() -> CodeSearchRuntime:
    """Create and publish the runtime in the current serving event loop."""

    global _runtime
    runtime = await CodeSearchRuntime.create()
    _runtime = runtime
    return runtime


async def stop_code_search_runtime() -> None:
    global _runtime
    runtime, _runtime = _runtime, None
    if runtime is not None:
        await runtime.close()


def get_code_search_runtime() -> CodeSearchRuntime:
    if _runtime is None:
        raise RuntimeError("code-search runtime is not initialized")
    return _runtime


def set_code_search_runtime(runtime: CodeSearchRuntime | Any | None) -> None:
    """Test seam for binding one process-local runtime."""

    global _runtime
    _runtime = runtime


def principal_id_for_api_key(principal: Mapping[str, Any]) -> str:
    """Bind search authority to identity without returning a credential value."""

    agent_id = principal.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        return agent_id
    api_key = principal.get("api_key")
    if not isinstance(api_key, str) or not api_key:
        raise ValueError("authenticated principal is missing")
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return f"coordinator-key-{digest}"


def _status(state: Any, reason: str) -> CodeSearchStatus:
    return CodeSearchStatus(
        available=False,
        state=state,
        reason=reason,
        usable_index_count=0,
    )


def _duration_bucket(elapsed_seconds: float) -> str:
    if elapsed_seconds < 0.01:
        return "lt_10ms"
    if elapsed_seconds < 0.1:
        return "lt_100ms"
    if elapsed_seconds < 1.0:
        return "lt_1s"
    return "gte_1s"


def _sanitized_unavailable(request: Any) -> CodeSearchResponse:
    from .code_search import (
        CodeSearchRequest,
        CodeSearchResponse,
        CodeSearchState,
        Fallback,
        RequestedIdentity,
        ScopeDisposition,
    )

    validated = (
        request
        if isinstance(request, CodeSearchRequest)
        else CodeSearchRequest.model_validate(request)
    )
    source: Literal["explicit", "work_package"] = (
        "explicit" if validated.scope.kind == "explicit" else "work_package"
    )
    authority: Literal["principal_grant", "work_package_registry"] = (
        "principal_grant" if source == "explicit" else "work_package_registry"
    )
    return CodeSearchResponse(
        state=CodeSearchState.UNAVAILABLE,
        current=False,
        request=RequestedIdentity(
            repo_slug=validated.repo_slug,
            source_revision=validated.source_revision,
            namespace=validated.namespace,
            index_id=validated.index_id,
        ),
        index=None,
        scope=ScopeDisposition(
            decision="allowed",
            source=source,
            authority=authority,
        ),
        results=[],
        fallback=Fallback(required=True, reason=CodeSearchState.UNAVAILABLE),
    )


async def _pool_from_env(environment: Mapping[str, str] | None) -> Any:
    env = os.environ if environment is None else environment
    dsn = env.get("POSTGRES_DSN", "").strip()
    if not dsn:
        raise ValueError("POSTGRES_DSN is required")
    import asyncpg

    return await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)


def _provider_from_env(environment: Mapping[str, str] | None) -> Any:
    env = os.environ if environment is None else environment
    from code_search_pkg.embedding_config import build_embedding_provider
    from code_search_pkg.embedding_protocol import (
        CredentialRef,
        EmbeddingContract,
        EmbeddingProviderKind,
    )

    kind = EmbeddingProviderKind(env["CODE_SEARCH_EMBEDDING_PROVIDER"])
    parameters = json.loads(env.get("CODE_SEARCH_INDEXING_PARAMS_JSON", "{}"))
    contract = EmbeddingContract(
        provider_kind=kind,
        model_id=env["CODE_SEARCH_EMBEDDING_MODEL"],
        dimension=int(env["CODE_SEARCH_EMBEDDING_DIMENSION"]),
        indexing_params=parameters,
        base_url=env.get("CODE_SEARCH_EMBEDDING_BASE_URL") or None,
        credential_ref=(
            CredentialRef.parse(env["CODE_SEARCH_EMBEDDING_CREDENTIAL_REF"])
            if env.get("CODE_SEARCH_EMBEDDING_CREDENTIAL_REF")
            else None
        ),
    )
    return build_embedding_provider(contract, environment=env)


def _grant_resolver_from_env(environment: Mapping[str, str] | None) -> Any:
    env = os.environ if environment is None else environment
    from .code_search_authorization import PrincipalCodeSearchGrant

    raw = json.loads(env.get("CODE_SEARCH_PRINCIPAL_GRANTS_JSON", "[]"))
    grants = [PrincipalCodeSearchGrant(**item) for item in raw]

    async def resolve(principal_id: str, repo_slug: str) -> Any:
        matches = [
            grant
            for grant in grants
            if grant.principal_id == principal_id and grant.repo_slug == repo_slug
        ]
        return matches[0] if len(matches) == 1 else None

    return resolve


def _float_env(environment: Mapping[str, str], name: str, default: float) -> float:
    return float(environment.get(name, str(default)))


def _int_env(environment: Mapping[str, str], name: str, default: int) -> int:
    return int(environment.get(name, str(default)))
