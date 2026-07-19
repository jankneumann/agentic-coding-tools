"""Semantic code-search service for the coordinator (change: add-semantic-code-search).

Sibling of ``memory.py``: a service class over injected backends, plus module-level accessors.
Consumed by BOTH surfaces (design D5 — exposed as a tool/endpoint, never an MCP resource, so it
survives http_proxy mode):

  - ``search_code`` MCP tool in ``coordination_mcp.py``  (local agents)
  - ``POST /search/code`` in ``coordination_api.py``     (cloud agents)

Both delegate to ``CodeSearchService.search`` so their payloads are identical by construction.
Search is a READ (design D5): it never locks, enqueues, or triggers indexing. Registration on
both surfaces is gated by ``CODE_SEARCH_ENABLED`` (design D10, default off), so nothing depends on
unproven retrieval quality until the spike gate (D9) is closed.

The pgvector KNN and registry lookup are injected as backends. In production they wrap the
coordinator's asyncpg pool (``make_pg_backends``); in tests they are mocked, so all of the
service logic — server-side embedding (D4), embedder-consistency check (D4), scope filtering
(D7), and the error taxonomy — is unit-testable without a live database or embedder.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any

logger = logging.getLogger(__name__)


# --- feature flag (design D10) ---------------------------------------------------------------

def code_search_enabled() -> bool:
    """True iff CODE_SEARCH_ENABLED is truthy. Default off — no surface registration otherwise."""
    return os.environ.get("CODE_SEARCH_ENABLED", "").lower() in ("1", "true", "yes", "on")


# --- error taxonomy (maps to the OpenAPI Problem responses) ----------------------------------

class CodeSearchError(Exception):
    """Base for code-search errors. `status` is the HTTP code the API layer emits."""

    status = 500
    type_uri = "urn:coordinator:code-search:error"


class RepoNotIndexedError(CodeSearchError):
    """Repo has no registry row — distinct from 'indexed but no similar chunks' (409)."""

    status = 409
    type_uri = "urn:coordinator:code-search:repo-not-indexed"


class EmbedderMismatchError(CodeSearchError):
    """Query-time embedder != the model the repo was indexed with (design D4) (422)."""

    status = 422
    type_uri = "urn:coordinator:code-search:embedder-mismatch"


# --- result shapes -----------------------------------------------------------------------------

@dataclass
class CodeSearchHit:
    file_path: str
    language: str
    content: str
    start_line: int
    end_line: int
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "content": self.content,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "score": self.score,
        }


@dataclass
class CodeSearchResponse:
    repo: str
    results: list[CodeSearchHit] = field(default_factory=list)
    scope_filtered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "results": [h.to_dict() for h in self.results],
            "scope_filtered": self.scope_filtered,
        }


# --- scope filtering (design D7) ---------------------------------------------------------------

def filter_by_scope(
    hits: Sequence[CodeSearchHit],
    read_allow: Sequence[str] | None,
    deny: Sequence[str] | None,
) -> list[CodeSearchHit]:
    """Drop hits outside read_allow globs or inside deny globs.

    Uses the same ``fnmatch`` semantics as
    ``skills/parallel-infrastructure/scripts/scope_checker.py`` so an agent can never retrieve
    code its work package is not allowed to read. Empty/None read_allow means "no allow
    restriction" (parity with ripgrep today); deny always subtracts.
    """
    allow = list(read_allow or [])
    block = list(deny or [])
    out: list[CodeSearchHit] = []
    for h in hits:
        if allow and not any(fnmatch(h.file_path, g) for g in allow):
            continue
        if block and any(fnmatch(h.file_path, g) for g in block):
            continue
        out.append(h)
    return out


# Injected backend signatures (async):
RegistryLookup = Callable[[str], Awaitable[dict[str, Any] | None]]
Embedder = Callable[[str], Awaitable[Sequence[float]]]
# (repo, embedding, limit, offset, languages, paths) -> ranked row dicts
SearchBackend = Callable[..., Awaitable[list[dict[str, Any]]]]


class CodeSearchService:
    """Embed the query server-side, run the pgvector KNN, scope-filter, return hits."""

    def __init__(
        self,
        registry_lookup: RegistryLookup,
        embedder: Embedder,
        search_backend: SearchBackend,
        embedder_model: str | None = None,
    ):
        self._registry = registry_lookup
        self._embedder = embedder
        self._search = search_backend
        self._model = embedder_model or os.environ.get(
            "CODE_SEARCH_EMBEDDER", "sentence-transformers/all-MiniLM-L6-v2"
        )

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
        # 1. Registry: repo must be indexed, and the registered embedder must match ours (D4).
        row = await self._registry(repo)
        if row is None:
            raise RepoNotIndexedError(
                f"Repo {repo!r} has no code_search_registry entry. Run index_repo first."
            )
        if row.get("embedder_model") != self._model:
            raise EmbedderMismatchError(
                f"Repo {repo!r} indexed with {row.get('embedder_model')!r}, "
                f"service configured with {self._model!r}"
            )

        # 2. Server-side query embedding (callers send text only — cloud agents lack a model) (D4).
        embedding = await self._embedder(query)

        # 3. One-statement KNN. Over-fetch when a scope will post-filter, to still fill `limit`.
        fetch = limit * 4 if scope else limit
        rows = await self._search(repo, embedding, fetch, offset, languages, paths)
        hits = [
            CodeSearchHit(
                file_path=r["file_path"],
                language=r["language"],
                content=r["content"],
                start_line=r["start_line"],
                end_line=r["end_line"],
                score=float(r["score"]),
            )
            for r in rows
        ]

        # 4. Scope filtering (D7).
        scoped = scope is not None
        if scoped:
            read_allow, deny = await self._resolve_scope(scope)
            hits = filter_by_scope(hits, read_allow, deny)[:limit]
        else:
            hits = hits[:limit]

        return CodeSearchResponse(repo=repo, results=hits, scope_filtered=scoped)

    async def _resolve_scope(self, scope: dict[str, Any]) -> tuple[list[str], list[str]]:
        """Resolve a scope to (read_allow, deny) globs.

        Explicit ``{read_allow, deny}`` is used as-is. A ``{work_package: id}`` reference is
        resolved from work-packages.yaml when a resolver is configured; absent one, it degrades to
        no restriction (the reference is advisory, not a hard dependency of the read path).
        """
        if "read_allow" in scope or "deny" in scope:
            return list(scope.get("read_allow", [])), list(scope.get("deny", []))
        # work_package resolution is environment-specific; default to unrestricted if unavailable.
        return [], []


# --- production backend wiring (thin; exercised where asyncpg + ParadeDB exist) ---------------

def make_pg_backends(pool: Any) -> tuple[RegistryLookup, SearchBackend]:
    """Build (registry_lookup, search_backend) over a live asyncpg pool.

    Thin translation to raw SQL — the pgvector KNN cannot go through the PostgREST-style
    DatabaseClient. Not unit-tested here (needs a DB); the SQL matches contracts/db/schema.sql
    and packages/code-search query_pg.
    """
    from code_search_pkg.query_pg import build_search_sql, to_pgvector_literal

    async def registry_lookup(repo: str) -> dict[str, Any] | None:
        row = await pool.fetchrow(
            "SELECT repo_slug, embedder_model, embedding_dim FROM code_search_registry "
            "WHERE repo_slug = $1",
            repo,
        )
        return dict(row) if row else None

    async def search_backend(repo, embedding, limit, offset, languages, paths):
        rows = await pool.fetch(
            build_search_sql(repo),
            to_pgvector_literal(embedding),
            languages,
            paths,
            limit,
            offset,
        )
        return [dict(r) for r in rows]

    return registry_lookup, search_backend


_service: CodeSearchService | None = None


def get_code_search_service() -> CodeSearchService:
    """Module-level accessor (mirrors get_memory_service). Wired lazily from the app lifespan."""
    if _service is None:
        raise RuntimeError(
            "code-search service not initialized — call init_code_search_service() at startup"
        )
    return _service


def init_code_search_service(service: CodeSearchService) -> None:
    global _service
    _service = service
