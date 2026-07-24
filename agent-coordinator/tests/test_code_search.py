from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import pytest
from code_search_pkg.query_pg import QueryableIndex, QueryProviderContract
from code_search_pkg.registry_models import NamespaceKind
from code_search_pkg.schema import QueryResult
from pydantic import ValidationError

from src.code_search import (
    CodeSearchForbiddenError,
    CodeSearchRequest,
    CodeSearchResponse,
    CodeSearchService,
    CodeSearchState,
    ExplicitScope,
    Fallback,
    RequestedIdentity,
    ScopeDisposition,
    SearchNamespace,
    code_search_enabled,
)
from src.code_search_authorization import PrincipalCodeSearchGrant

REVISION = "a" * 40
OTHER_REVISION = "b" * 40
FINGERPRINT = "c" * 64
INDEX_ID = UUID("11111111-1111-4111-8111-111111111111")
PROVIDER = QueryProviderContract(
    model="text-embedding-model",
    dimension=3,
    embedder_fingerprint=FINGERPRINT,
)


def _index(*, revision: str = REVISION) -> QueryableIndex:
    return QueryableIndex(
        index_id=INDEX_ID,
        storage_key="i_11111111111111111111111111111111",
        repo_slug="agentic_coding_tools",
        namespace_kind=NamespaceKind.MAIN,
        namespace_key="main",
        source_revision=revision,
        embedder_model=PROVIDER.model,
        embedding_dim=PROVIDER.dimension,
        policy_fingerprint="d" * 64,
        pipeline_fingerprint="e" * 64,
        embedder_fingerprint=PROVIDER.embedder_fingerprint,
        chunk_count=2,
        completed_at=datetime(2026, 7, 23, 12, tzinfo=UTC),
    )


def _request(**updates: object) -> CodeSearchRequest:
    values: dict[str, object] = {
        "query": "where is authorization enforced?",
        "repo_slug": "agentic_coding_tools",
        "source_revision": REVISION,
        "namespace": {"kind": "main", "key": "main"},
        "scope": {
            "kind": "explicit",
            "read_allow": ["agent-coordinator/**"],
            "deny": ["agent-coordinator/secrets/**"],
        },
        "limit": 10,
        "offset": 0,
    }
    values.update(updates)
    return CodeSearchRequest.model_validate(values)


class FakePool:
    pass


def _service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    index: QueryableIndex | None = None,
    provider: QueryProviderContract | None = PROVIDER,
    rows: list[QueryResult] | None = None,
    embed_error: Exception | None = None,
    query_error: Exception | None = None,
) -> tuple[CodeSearchService, dict[str, object]]:
    calls: dict[str, object] = {"select": 0, "embed": 0, "query": 0}

    async def select_main(_pool: object, repo_slug: str) -> QueryableIndex | None:
        calls["select"] = int(calls["select"]) + 1
        assert repo_slug == "agentic_coding_tools"
        return index

    async def select_exact(*args: object, **kwargs: object) -> QueryableIndex | None:
        raise AssertionError("main requests must not use exact non-main selection")

    async def embed(text: str) -> list[float]:
        calls["embed"] = int(calls["embed"]) + 1
        calls["embedded_text"] = text
        if embed_error:
            raise embed_error
        return [0.1, 0.2, 0.3]

    async def query(*args: object, **kwargs: object) -> list[QueryResult]:
        calls["query"] = int(calls["query"]) + 1
        calls["query_kwargs"] = kwargs
        if query_error:
            raise query_error
        return list(rows or [])

    async def grant_resolver(principal_id: str, repo_slug: str) -> PrincipalCodeSearchGrant | None:
        return PrincipalCodeSearchGrant(
            principal_id=principal_id,
            repo_slug=repo_slug,
            namespace_kind="main",
            namespace_key="main",
            read_allow=("agent-coordinator/**",),
            deny=("agent-coordinator/private/**",),
        )

    monkeypatch.setattr("src.code_search.select_main_index", select_main)
    monkeypatch.setattr("src.code_search.select_exact_index", select_exact)
    monkeypatch.setattr("src.code_search.query_codebase_pg", query)
    service = CodeSearchService(
        pool=FakePool(),
        embedder=embed,
        provider_contract=provider,
        grant_resolver=grant_resolver,
    )
    return service, calls


def test_flag_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODE_SEARCH_ENABLED", raising=False)
    assert code_search_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_flag_truthy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CODE_SEARCH_ENABLED", value)
    assert code_search_enabled() is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("query", ""),
        ("query", "q" * 8193),
        ("repo_slug", "Bad-Slug"),
        ("source_revision", "abc123"),
        ("limit", 51),
        ("offset", 1001),
        ("paths", ["./agent-coordinator/**"]),
    ],
)
def test_request_rejects_unbounded_or_noncanonical_input(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _request(**{field: value})


def test_non_main_request_requires_exact_index_id() -> None:
    with pytest.raises(ValidationError):
        _request(namespace={"kind": "feature", "key": "openspec/example"})


def test_request_models_forbid_unknown_fields_and_mixed_scope() -> None:
    values = _request().model_dump(mode="json")
    values["unexpected"] = True
    with pytest.raises(ValidationError):
        CodeSearchRequest.model_validate(values)
    with pytest.raises(ValidationError):
        _request(
            scope={
                "kind": "explicit",
                "read_allow": ["agent-coordinator/**"],
                "change_id": "change",
            }
        )


@pytest.mark.asyncio
async def test_revision_mismatch_stops_before_embedding_and_knn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, calls = _service(monkeypatch, index=_index(revision=OTHER_REVISION))

    response = await service.search(_request(), principal_id="codex")

    assert response.state is CodeSearchState.REVISION_MISMATCH
    assert response.current is False
    assert response.results == []
    assert response.fallback.required is True
    assert response.fallback.reason is CodeSearchState.REVISION_MISMATCH
    assert response.index is not None
    assert response.index.completed_at == datetime(2026, 7, 23, 12, tzinfo=UTC)
    assert calls["embed"] == 0
    assert calls["query"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["model", "dimension", "fingerprint"])
async def test_provider_mismatch_stops_before_embedding_and_knn(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    mismatched = QueryProviderContract(
        model="different-model" if field == "model" else PROVIDER.model,
        dimension=4 if field == "dimension" else PROVIDER.dimension,
        embedder_fingerprint="f" * 64 if field == "fingerprint" else PROVIDER.embedder_fingerprint,
    )
    service, calls = _service(
        monkeypatch,
        index=_index(),
        provider=mismatched,
    )

    response = await service.search(_request(), principal_id="codex")

    assert response.state is CodeSearchState.NOT_CONFIGURED
    assert response.results == []
    assert calls["embed"] == 0
    assert calls["query"] == 0


@pytest.mark.asyncio
async def test_non_main_selection_requires_and_uses_exact_index_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = _index()
    selected = QueryableIndex(
        index_id=selected.index_id,
        storage_key=selected.storage_key,
        repo_slug=selected.repo_slug,
        namespace_kind=NamespaceKind.FEATURE,
        namespace_key="openspec/change",
        source_revision=selected.source_revision,
        embedder_model=selected.embedder_model,
        embedding_dim=selected.embedding_dim,
        policy_fingerprint=selected.policy_fingerprint,
        pipeline_fingerprint=selected.pipeline_fingerprint,
        embedder_fingerprint=selected.embedder_fingerprint,
        chunk_count=selected.chunk_count,
        completed_at=selected.completed_at,
    )
    calls: dict[str, object] = {"main": 0, "exact": 0, "embed": 0, "query": 0}

    async def select_main(*args: object, **kwargs: object) -> QueryableIndex | None:
        calls["main"] = int(calls["main"]) + 1
        return None

    async def select_exact(
        pool: object,
        *,
        index_id: UUID,
        repo_slug: str,
        namespace_kind: NamespaceKind,
        namespace_key: str,
    ) -> QueryableIndex | None:
        calls["exact"] = int(calls["exact"]) + 1
        calls["selector"] = (index_id, repo_slug, namespace_kind, namespace_key)
        return selected

    async def embed(query: str) -> list[float]:
        calls["embed"] = int(calls["embed"]) + 1
        return [0.1, 0.2, 0.3]

    async def query(*args: object, **kwargs: object) -> list[QueryResult]:
        calls["query"] = int(calls["query"]) + 1
        return []

    async def grant_resolver(principal_id: str, repo_slug: str) -> PrincipalCodeSearchGrant | None:
        return PrincipalCodeSearchGrant(
            principal_id=principal_id,
            repo_slug=repo_slug,
            namespace_kind="feature",
            namespace_key="openspec/change",
            read_allow=("agent-coordinator/**",),
        )

    monkeypatch.setattr("src.code_search.select_main_index", select_main)
    monkeypatch.setattr("src.code_search.select_exact_index", select_exact)
    monkeypatch.setattr("src.code_search.query_codebase_pg", query)
    service = CodeSearchService(
        pool=FakePool(),
        embedder=embed,
        provider_contract=PROVIDER,
        grant_resolver=grant_resolver,
    )
    request = _request(
        namespace={"kind": "feature", "key": "openspec/change"},
        index_id=str(INDEX_ID),
    )

    response = await service.search(request, principal_id="codex")

    assert response.state is CodeSearchState.READY
    assert calls["main"] == 0
    assert calls["exact"] == 1
    assert calls["selector"] == (
        INDEX_ID,
        "agentic_coding_tools",
        NamespaceKind.FEATURE,
        "openspec/change",
    )


@pytest.mark.asyncio
async def test_missing_index_is_structured_not_indexed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, calls = _service(monkeypatch, index=None)
    response = await service.search(_request(), principal_id="codex")
    assert response.state is CodeSearchState.NOT_INDEXED
    assert response.index is None
    assert response.results == []
    assert calls["embed"] == 0


@pytest.mark.asyncio
async def test_missing_principal_grant_is_sanitized_403_before_semantic_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, calls = _service(monkeypatch, index=_index())

    async def missing_grant(principal_id: str, repo_slug: str) -> PrincipalCodeSearchGrant | None:
        return None

    service._grant_resolver = missing_grant  # type: ignore[attr-defined]

    with pytest.raises(CodeSearchForbiddenError) as error:
        await service.search(_request(), principal_id="codex")

    assert error.value.status == 403
    assert "agent-coordinator/**" not in str(error.value)
    assert calls["select"] == 0
    assert calls["embed"] == 0
    assert calls["query"] == 0


@pytest.mark.asyncio
async def test_ready_response_has_exact_provenance_and_defensive_filtering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        QueryResult(
            file_path="agent-coordinator/src/code_search.py",
            language="python",
            content="class CodeSearchService:",
            start_line=10,
            end_line=20,
            score=0.82,
        ),
        QueryResult(
            file_path="agent-coordinator/private/key.py",
            language="python",
            content="do not return",
            start_line=1,
            end_line=2,
            score=0.99,
        ),
        QueryResult(
            file_path="skills/worktree/scripts/worktree.py",
            language="python",
            content="outside grant",
            start_line=1,
            end_line=2,
            score=0.95,
        ),
    ]
    service, calls = _service(monkeypatch, index=_index(), rows=rows)

    response = await service.search(
        _request(paths=["agent-coordinator/**"]),
        principal_id="codex",
    )

    assert response.state is CodeSearchState.READY
    assert response.current is True
    assert response.fallback.required is False
    assert response.index is not None
    assert str(response.index.index_id) == str(INDEX_ID)
    assert [hit.file_path for hit in response.results] == ["agent-coordinator/src/code_search.py"]
    hit = response.results[0]
    assert hit.repo_slug == "agentic_coding_tools"
    assert hit.source_revision == REVISION
    assert hit.index_id == INDEX_ID
    assert hit.similarity == pytest.approx(0.82)
    query_kwargs = calls["query_kwargs"]
    assert isinstance(query_kwargs, dict)
    assert query_kwargs["limit"] == 10
    assert query_kwargs["offset"] == 0
    assert query_kwargs["allow_path_regexes"]
    assert query_kwargs["deny_path_regexes"]
    assert query_kwargs["path_regexes"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", ["embed", "query"])
async def test_optional_runtime_failures_are_sanitized_without_partial_hits(
    monkeypatch: pytest.MonkeyPatch,
    failure_at: str,
) -> None:
    kwargs = {
        "embed_error": RuntimeError("postgres://secret@db/internal query=private source body")
        if failure_at == "embed"
        else None,
        "query_error": RuntimeError("postgres://secret@db/internal query=private source body")
        if failure_at == "query"
        else None,
    }
    service, _ = _service(monkeypatch, index=_index(), **kwargs)

    response = await service.search(_request(), principal_id="codex")

    assert response.state is CodeSearchState.UNAVAILABLE
    assert response.results == []
    assert response.fallback.reason is CodeSearchState.UNAVAILABLE
    rendered = str(response.to_dict())
    assert "secret" not in rendered
    assert "private source body" not in rendered


@pytest.mark.asyncio
async def test_privacy_safe_observability_excludes_query_content_and_scope(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, _ = _service(
        monkeypatch,
        index=_index(),
        rows=[
            QueryResult(
                file_path="agent-coordinator/src/code_search.py",
                language="python",
                content="SENSITIVE SOURCE CONTENT",
                start_line=1,
                end_line=2,
                score=0.8,
            )
        ],
    )
    caplog.set_level(logging.INFO, logger="src.code_search")

    response = await service.search(
        _request(query="SENSITIVE QUERY TEXT"),
        principal_id="codex",
    )

    assert response.state is CodeSearchState.READY
    log_text = caplog.text
    assert "SENSITIVE QUERY TEXT" not in log_text
    assert "SENSITIVE SOURCE CONTENT" not in log_text
    assert "agent-coordinator/**" not in log_text
    assert "state=ready" in log_text


def test_response_contract_serialization_uses_similarity_and_closed_envelope() -> None:
    scope = ExplicitScope(
        kind="explicit",
        read_allow=["agent-coordinator/**"],
        deny=[],
    )
    request = CodeSearchRequest(
        query="q",
        repo_slug="agentic_coding_tools",
        source_revision=REVISION,
        namespace=SearchNamespace(kind="main", key="main"),
        scope=scope,
    )
    assert set(request.model_dump()) == {
        "query",
        "repo_slug",
        "source_revision",
        "namespace",
        "index_id",
        "scope",
        "limit",
        "offset",
        "languages",
        "paths",
    }


@pytest.mark.parametrize(
    ("state", "index", "decision"),
    [
        (CodeSearchState.SCOPE_REJECTED, _index(), "rejected"),
        (CodeSearchState.SCOPE_REJECTED, None, "allowed"),
        (CodeSearchState.NOT_INDEXED, _index(), "allowed"),
        (CodeSearchState.UNAVAILABLE, None, "rejected"),
    ],
)
def test_response_rejects_contradictory_scope_and_index_states(
    state: CodeSearchState,
    index: QueryableIndex | None,
    decision: str,
) -> None:
    request = _request()
    index_payload = None
    if index is not None:
        index_payload = {
            "index_id": index.index_id,
            "repo_slug": index.repo_slug,
            "source_revision": index.source_revision,
            "namespace": {
                "kind": index.namespace_kind,
                "key": index.namespace_key,
            },
            "embedder_model": index.embedder_model,
            "embedding_dim": index.embedding_dim,
            "embedder_fingerprint": index.embedder_fingerprint,
            "policy_fingerprint": index.policy_fingerprint,
            "pipeline_fingerprint": index.pipeline_fingerprint,
            "completed_at": index.completed_at,
        }
    with pytest.raises(ValidationError):
        CodeSearchResponse(
            state=state,
            current=False,
            request=RequestedIdentity(
                repo_slug=request.repo_slug,
                source_revision=request.source_revision,
                namespace=request.namespace,
                index_id=request.index_id,
            ),
            index=index_payload,
            scope=ScopeDisposition(
                decision=decision,
                source="explicit",
                authority="principal_grant",
            ),
            results=[],
            fallback=Fallback(required=True, reason=state),
        )


@pytest.mark.asyncio
async def test_grant_resolver_failure_is_sanitized_before_semantic_work(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, calls = _service(monkeypatch, index=_index())

    async def failing_resolver(
        principal_id: str, repo_slug: str
    ) -> PrincipalCodeSearchGrant | None:
        raise RuntimeError("postgres://credential query text agent-coordinator/**")

    service._grant_resolver = failing_resolver  # type: ignore[attr-defined]
    caplog.set_level(logging.INFO, logger="src.code_search")

    response = await service.search(_request(), principal_id="codex")

    assert response.state is CodeSearchState.UNAVAILABLE
    assert calls["select"] == 0
    assert calls["embed"] == 0
    assert calls["query"] == 0
    rendered = str(response.to_dict()) + caplog.text
    assert "credential" not in rendered
    assert "query text" not in rendered
    assert "agent-coordinator/**" not in rendered
