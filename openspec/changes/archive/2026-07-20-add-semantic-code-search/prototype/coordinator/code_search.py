"""PROTOTYPE — Coordinator code-search service (change: add-semantic-code-search).

Sibling of ``agent-coordinator/src/memory.py`` in shape: a dataclass result model, a service
class over the database client, and a module-level accessor. Consumed by BOTH surfaces
(design D5 — tool/endpoint only, never an MCP resource, so it survives http_proxy mode):

    # coordination_mcp.py                       # coordination_api.py
    @mcp.tool                                   @router.post("/search/code")
    async def search_code(                      async def search_code_endpoint(
        query: str, repo: str,                      req: CodeSearchRequest,  # contracts/generated
        limit: int = 10, offset: int = 0,       ) -> CodeSearchResponse:
        languages: list[str] | None = None,         svc = get_code_search_service()
        paths: list[str] | None = None,             return await svc.search(**req.model_dump())
        scope: dict | None = None,
    ) -> dict: ...  # same service call

Both registrations are gated by CODE_SEARCH_ENABLED (design D10). Search is classified `read`:
no locks, no queueing, no indexing side effects (design D5).
NOT wired into any build — illustrative prototype.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class RepoNotIndexedError(Exception):
    """Distinguishable from empty results (spec: unindexed repo). Maps to HTTP 409."""


class EmbedderMismatchError(Exception):
    """Query embedder != registry embedder — hard error, never silent degradation (D4). 422."""


@dataclass
class CodeSearchResult:
    file_path: str
    language: str
    content: str
    start_line: int
    end_line: int
    score: float


@dataclass
class CodeSearchResponse:
    repo: str
    results: list[CodeSearchResult] = field(default_factory=list)
    scope_filtered: bool = False


class CodeSearchService:
    """Semantic retrieval: embed server-side, KNN in Postgres, scope-filter, return slices."""

    def __init__(self, db: Any | None = None, embedder: Any | None = None):
        self._db = db
        self._embedder = embedder  # lazy warm SentenceTransformers default; LiteLLM via env (D4)

    async def search(
        self,
        query: str,
        repo: str,
        limit: int = 10,
        offset: int = 0,
        languages: list[str] | None = None,
        paths: list[str] | None = None,
        scope: dict[str, Any] | None = None,
    ) -> CodeSearchResponse:
        # 1. Registry lookup — repo must be indexed, and the registered embedder must match
        #    the service's configured model (D4). Missing row → RepoNotIndexedError (409).
        registry = await self._get_registry_row(repo)
        if registry is None:
            raise RepoNotIndexedError(
                f"Repo '{repo}' has no code_search_registry entry. Run index_repo first."
            )
        if registry["embedder_model"] != self._embedder_model_name():
            raise EmbedderMismatchError(
                f"Registry has {registry['embedder_model']!r}, "
                f"service configured with {self._embedder_model_name()!r}"
            )

        # 2. Server-side query embedding (callers send text only — cloud agents have no model).
        query_embedding = await self._embed(query)

        # 3. One-statement ranking + filtering (packages/code-search query_pg.query_codebase_pg).
        #    Over-fetch when a scope is present so post-filtering can still fill `limit`.
        fetch_limit = limit * 3 if scope else limit
        raw = await self._knn(repo, query_embedding, fetch_limit, offset, languages, paths)

        # 4. Optional scope filtering (D7): same glob semantics as
        #    skills/parallel-infrastructure/scripts/scope_checker.py via a shared helper.
        if scope is not None:
            read_allow, deny = await self._resolve_scope_globs(scope)
            raw = [
                r for r in raw
                if any(fnmatch.fnmatch(r.file_path, g) for g in read_allow)
                and not any(fnmatch.fnmatch(r.file_path, g) for g in deny)
            ][:limit]

        return CodeSearchResponse(repo=repo, results=raw, scope_filtered=scope is not None)

    # -- helpers (implemented against DatabaseClient / asyncpg in the real module) -----------

    async def _get_registry_row(self, repo: str) -> dict[str, Any] | None:
        raise NotImplementedError("prototype")

    def _embedder_model_name(self) -> str:
        raise NotImplementedError("prototype")

    async def _embed(self, text: str) -> Any:
        raise NotImplementedError("prototype")

    async def _knn(
        self,
        repo: str,
        embedding: Any,
        limit: int,
        offset: int,
        languages: list[str] | None,
        paths: list[str] | None,
    ) -> list[CodeSearchResult]:
        raise NotImplementedError("prototype")

    async def _resolve_scope_globs(
        self, scope: dict[str, Any]
    ) -> tuple[list[str], list[str]]:
        """scope = {'work_package': 'wp-x'} → that package's (read_allow, deny) globs,
        or explicit {'read_allow': [...], 'deny': [...]} passed through."""
        raise NotImplementedError("prototype")


_service: CodeSearchService | None = None


def get_code_search_service() -> CodeSearchService:
    global _service
    if _service is None:
        _service = CodeSearchService()
    return _service
