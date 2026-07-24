"""Typed, fail-closed semantic code-search service."""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from time import monotonic
from typing import Annotated, Any, Literal
from uuid import UUID

from code_search_pkg.query_pg import (
    QueryableIndex,
    QueryProviderContract,
    query_codebase_pg,
    select_exact_index,
    select_main_index,
)
from code_search_pkg.registry_models import NamespaceKind
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .code_search_authorization import (
    ExplicitScopeRequest,
    PrincipalGrantResolver,
    ScopeForbiddenError,
    ScopeRejectedError,
    WorkPackageScopeRequest,
    WorkPackageScopeResolver,
    authorize_code_search_scope,
    validate_safe_glob,
)

logger = logging.getLogger(__name__)

FullRevision = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}([0-9a-f]{24})?$")]
RepoSlug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,50}$")]
SafeGlob = Annotated[str, StringConstraints(min_length=1, max_length=512)]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_REFERENCE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def code_search_enabled() -> bool:
    """Return whether semantic code search is explicitly enabled."""

    return os.environ.get("CODE_SEARCH_ENABLED", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class CodeSearchError(Exception):
    """Base transport-aware code-search error with a non-sensitive message."""

    status = 500
    type_uri = "urn:coordinator:code-search:error"


class CodeSearchForbiddenError(CodeSearchError):
    status = 403
    type_uri = "urn:coordinator:code-search:forbidden"


class CodeSearchState(StrEnum):
    READY = "ready"
    REVISION_MISMATCH = "revision_mismatch"
    NOT_INDEXED = "not_indexed"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"
    SCOPE_REJECTED = "scope_rejected"


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SearchNamespace(_ClosedModel):
    kind: NamespaceKind
    key: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_main_key(self) -> SearchNamespace:
        if self.kind is NamespaceKind.MAIN and self.key != "main":
            raise ValueError("main namespace must use key='main'")
        return self


class ExplicitScope(_ClosedModel):
    kind: Literal["explicit"] = "explicit"
    read_allow: list[SafeGlob] = Field(min_length=1, max_length=100)
    deny: list[SafeGlob] = Field(default_factory=list, max_length=100)

    @field_validator("read_allow", "deny")
    @classmethod
    def validate_patterns(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("scope patterns must be unique")
        return [validate_safe_glob(value) for value in values]


class WorkPackageScope(_ClosedModel):
    kind: Literal["work_package"] = "work_package"
    change_id: str = Field(min_length=1, max_length=200)
    package_id: str = Field(min_length=1, max_length=200)
    scope_revision: FullRevision

    @field_validator("change_id", "package_id")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        if not _REFERENCE_RE.fullmatch(value):
            raise ValueError("work-package identifier is invalid")
        return value


ScopeInput = Annotated[ExplicitScope | WorkPackageScope, Field(discriminator="kind")]


class CodeSearchRequest(_ClosedModel):
    query: str = Field(min_length=1, max_length=8192)
    repo_slug: RepoSlug
    source_revision: FullRevision
    namespace: SearchNamespace
    index_id: UUID | None = None
    scope: ScopeInput
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=1000)
    languages: list[str] | None = Field(default=None, max_length=30)
    paths: list[SafeGlob] | None = Field(default=None, max_length=100)

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        if len(set(values)) != len(values) or any(not value or len(value) > 64 for value in values):
            raise ValueError("languages are invalid")
        return values

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        if len(set(values)) != len(values):
            raise ValueError("paths must be unique")
        return [validate_safe_glob(value) for value in values]

    @model_validator(mode="after")
    def require_non_main_index(self) -> CodeSearchRequest:
        if self.namespace.kind is not NamespaceKind.MAIN and self.index_id is None:
            raise ValueError("non-main namespaces require an exact index_id")
        return self


class RequestedIdentity(_ClosedModel):
    repo_slug: RepoSlug
    source_revision: FullRevision
    namespace: SearchNamespace
    index_id: UUID | None


class IndexProvenance(_ClosedModel):
    index_id: UUID
    repo_slug: RepoSlug
    source_revision: FullRevision
    namespace: SearchNamespace
    embedder_model: str = Field(min_length=1, max_length=500)
    embedding_dim: int = Field(ge=1, le=65535)
    embedder_fingerprint: Fingerprint
    policy_fingerprint: Fingerprint
    pipeline_fingerprint: Fingerprint
    completed_at: datetime


class ScopeDisposition(_ClosedModel):
    decision: Literal["allowed", "rejected"]
    source: Literal["explicit", "work_package"]
    authority: Literal["principal_grant", "work_package_registry"]


class CodeSearchHit(_ClosedModel):
    file_path: str = Field(min_length=1, max_length=4096)
    language: str = Field(min_length=1, max_length=64)
    content: str = Field(max_length=200000)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    similarity: float = Field(ge=-1, le=1)
    repo_slug: RepoSlug
    source_revision: FullRevision
    index_id: UUID
    scope_decision: Literal["allowed"] = "allowed"


class Fallback(_ClosedModel):
    required: bool
    strategy: Literal["exact_search"] = "exact_search"
    reason: CodeSearchState | None


class CodeSearchResponse(_ClosedModel):
    state: CodeSearchState
    current: bool
    request: RequestedIdentity
    index: IndexProvenance | None
    scope: ScopeDisposition
    results: list[CodeSearchHit] = Field(max_length=50)
    fallback: Fallback

    @model_validator(mode="after")
    def validate_state_invariants(self) -> CodeSearchResponse:
        if self.state is CodeSearchState.READY:
            if (
                not self.current
                or self.index is None
                or self.scope.decision != "allowed"
                or self.fallback.required
                or self.fallback.reason is not None
            ):
                raise ValueError("ready response invariants are inconsistent")
        elif (
            self.current
            or self.results
            or not self.fallback.required
            or self.fallback.reason is not self.state
        ):
            raise ValueError("non-ready response invariants are inconsistent")
        if self.state is CodeSearchState.SCOPE_REJECTED:
            if self.scope.decision != "rejected" or self.index is not None:
                raise ValueError("scope_rejected requires rejected scope and no index")
        elif self.scope.decision != "allowed":
            raise ValueError("non-scope failures require an allowed scope")
        if self.state is CodeSearchState.NOT_INDEXED and self.index is not None:
            raise ValueError("not_indexed cannot identify a selected index")
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


Embedder = Callable[[str], Awaitable[Sequence[float]]]
Observer = Callable[[str, Mapping[str, str | int | float | None]], None]


class CodeSearchService:
    """Resolve authority and exact index identity before semantic work."""

    def __init__(
        self,
        *,
        pool: Any,
        embedder: Embedder | None,
        provider_contract: QueryProviderContract | None,
        grant_resolver: PrincipalGrantResolver,
        work_package_resolver: WorkPackageScopeResolver | None = None,
        observer: Observer | None = None,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._provider = provider_contract
        self._grant_resolver = grant_resolver
        self._work_package_resolver = work_package_resolver
        self._observer = observer
        self._state_counts: Counter[str] = Counter()

    async def search(
        self,
        request: CodeSearchRequest | Mapping[str, Any],
        *,
        principal_id: str,
    ) -> CodeSearchResponse:
        started_at = monotonic()
        validated = (
            request
            if isinstance(request, CodeSearchRequest)
            else CodeSearchRequest.model_validate(request)
        )
        identity = RequestedIdentity(
            repo_slug=validated.repo_slug,
            source_revision=validated.source_revision,
            namespace=validated.namespace,
            index_id=validated.index_id,
        )
        scope_source: Literal["explicit", "work_package"] = (
            "explicit" if isinstance(validated.scope, ExplicitScope) else "work_package"
        )
        default_authority: Literal["principal_grant", "work_package_registry"] = (
            "principal_grant" if scope_source == "explicit" else "work_package_registry"
        )
        try:
            grant = await self._grant_resolver(principal_id, validated.repo_slug)
            effective_scope = await authorize_code_search_scope(
                principal_id=principal_id,
                repo_slug=validated.repo_slug,
                namespace_kind=validated.namespace.kind.value,
                namespace_key=validated.namespace.key,
                source_revision=validated.source_revision,
                grant=grant,
                requested_scope=_authorization_scope(validated.scope),
                paths=validated.paths or (),
                work_package_resolver=self._work_package_resolver,
            )
        except ScopeForbiddenError as error:
            self._observe(validated, CodeSearchState.SCOPE_REJECTED, "forbidden", None, started_at)
            raise CodeSearchForbiddenError(
                "The principal has no code-search grant for this repository."
            ) from error
        except ScopeRejectedError:
            response = _non_ready_response(
                state=CodeSearchState.SCOPE_REJECTED,
                request=identity,
                index=None,
                scope=ScopeDisposition(
                    decision="rejected",
                    source=scope_source,
                    authority=default_authority,
                ),
            )
            self._observe_response(validated, response, started_at)
            return response
        except Exception:
            response = _non_ready_response(
                state=CodeSearchState.UNAVAILABLE,
                request=identity,
                index=None,
                scope=ScopeDisposition(
                    decision="allowed",
                    source=scope_source,
                    authority=default_authority,
                ),
            )
            self._observe_response(validated, response, started_at)
            return response

        disposition = ScopeDisposition(
            decision="allowed",
            source=effective_scope.source,
            authority=effective_scope.authority,
        )
        try:
            selected = await self._select_index(validated)
        except Exception:
            response = _non_ready_response(
                state=CodeSearchState.UNAVAILABLE,
                request=identity,
                index=None,
                scope=disposition,
            )
            self._observe_response(validated, response, started_at)
            return response
        if selected is None:
            response = _non_ready_response(
                state=CodeSearchState.NOT_INDEXED,
                request=identity,
                index=None,
                scope=disposition,
            )
            self._observe_response(validated, response, started_at)
            return response

        provenance = _index_provenance(selected)
        if selected.source_revision != validated.source_revision:
            response = _non_ready_response(
                state=CodeSearchState.REVISION_MISMATCH,
                request=identity,
                index=provenance,
                scope=disposition,
            )
            self._observe_response(validated, response, started_at)
            return response
        if (
            self._provider is None
            or self._embedder is None
            or not selected.matches_provider(self._provider)
        ):
            response = _non_ready_response(
                state=CodeSearchState.NOT_CONFIGURED,
                request=identity,
                index=provenance,
                scope=disposition,
            )
            self._observe_response(validated, response, started_at)
            return response

        try:
            embedding = await self._embedder(validated.query)
            if len(embedding) != selected.embedding_dim:
                raise ValueError("query embedding dimension is incompatible")
            rows = await query_codebase_pg(
                self._pool,
                selected.storage_key,
                embedding,
                limit=validated.limit,
                offset=validated.offset,
                languages=validated.languages,
                allow_path_regexes=effective_scope.allow_path_regexes,
                deny_path_regexes=effective_scope.deny_path_regexes,
                path_regexes=effective_scope.path_regexes,
            )
            hits = [_hit(row, selected) for row in rows if effective_scope.allows(row.file_path)][
                : validated.limit
            ]
        except Exception:
            response = _non_ready_response(
                state=CodeSearchState.UNAVAILABLE,
                request=identity,
                index=provenance,
                scope=disposition,
            )
            self._observe_response(validated, response, started_at)
            return response

        response = CodeSearchResponse(
            state=CodeSearchState.READY,
            current=True,
            request=identity,
            index=provenance,
            scope=disposition,
            results=hits,
            fallback=Fallback(required=False, reason=None),
        )
        self._observe_response(validated, response, started_at)
        return response

    async def _select_index(self, request: CodeSearchRequest) -> QueryableIndex | None:
        if request.namespace.kind is NamespaceKind.MAIN:
            return await select_main_index(self._pool, request.repo_slug)
        assert request.index_id is not None
        return await select_exact_index(
            self._pool,
            index_id=request.index_id,
            repo_slug=request.repo_slug,
            namespace_kind=request.namespace.kind,
            namespace_key=request.namespace.key,
        )

    def metrics_snapshot(self) -> dict[str, int]:
        """Return bounded per-state counters without request or source content."""

        return dict(self._state_counts)

    def _observe_response(
        self,
        request: CodeSearchRequest,
        response: CodeSearchResponse,
        started_at: float,
    ) -> None:
        self._observe(
            request,
            response.state,
            response.fallback.reason.value if response.fallback.reason else "ready",
            str(response.index.index_id) if response.index else None,
            started_at,
        )

    def _observe(
        self,
        request: CodeSearchRequest,
        state: CodeSearchState,
        reason: str,
        index_id: str | None,
        started_at: float,
    ) -> None:
        self._state_counts[state.value] += 1
        latency_ms = min((monotonic() - started_at) * 1000, 3_600_000)
        fields: dict[str, str | int | float | None] = {
            "repo_slug": request.repo_slug,
            "source_revision": request.source_revision,
            "index_id": index_id,
            "state": state.value,
            "reason": reason,
            "latency_ms": round(latency_ms, 3),
        }
        logger.info(
            "code_search_query_complete repo_slug=%s source_revision=%s "
            "index_id=%s state=%s reason=%s latency_ms=%.3f",
            fields["repo_slug"],
            fields["source_revision"],
            fields["index_id"],
            fields["state"],
            fields["reason"],
            fields["latency_ms"],
        )
        if self._observer is not None:
            try:
                self._observer("code_search_query_complete", fields)
            except Exception:
                logger.debug("code_search_observer_failed", exc_info=False)


def _authorization_scope(
    scope: ExplicitScope | WorkPackageScope,
) -> ExplicitScopeRequest | WorkPackageScopeRequest:
    if isinstance(scope, ExplicitScope):
        return ExplicitScopeRequest(
            read_allow=tuple(scope.read_allow),
            deny=tuple(scope.deny),
        )
    return WorkPackageScopeRequest(
        change_id=scope.change_id,
        package_id=scope.package_id,
        scope_revision=scope.scope_revision,
    )


def _index_provenance(index: QueryableIndex) -> IndexProvenance:
    return IndexProvenance(
        index_id=index.index_id,
        repo_slug=index.repo_slug,
        source_revision=index.source_revision,
        namespace=SearchNamespace(
            kind=index.namespace_kind,
            key=index.namespace_key,
        ),
        embedder_model=index.embedder_model,
        embedding_dim=index.embedding_dim,
        embedder_fingerprint=index.embedder_fingerprint,
        policy_fingerprint=index.policy_fingerprint,
        pipeline_fingerprint=index.pipeline_fingerprint,
        completed_at=index.completed_at,
    )


def _hit(row: Any, index: QueryableIndex) -> CodeSearchHit:
    return CodeSearchHit(
        file_path=row.file_path,
        language=row.language,
        content=row.content,
        start_line=row.start_line,
        end_line=row.end_line,
        similarity=float(row.score),
        repo_slug=index.repo_slug,
        source_revision=index.source_revision,
        index_id=index.index_id,
    )


def _non_ready_response(
    *,
    state: CodeSearchState,
    request: RequestedIdentity,
    index: IndexProvenance | None,
    scope: ScopeDisposition,
) -> CodeSearchResponse:
    return CodeSearchResponse(
        state=state,
        current=False,
        request=request,
        index=index,
        scope=scope,
        results=[],
        fallback=Fallback(required=True, reason=state),
    )


_service: CodeSearchService | None = None


def get_code_search_service() -> CodeSearchService:
    if _service is None:
        raise RuntimeError("code-search service is not initialized")
    return _service


def init_code_search_service(service: CodeSearchService | None) -> None:
    global _service
    _service = service
