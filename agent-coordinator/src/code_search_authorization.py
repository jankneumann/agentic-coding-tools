"""Principal-bound, fail-closed authorization for semantic code search."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

_REVISION_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_MAX_GLOB_LENGTH = 512
_MAX_GLOBS = 100


class ScopeAuthorizationError(RuntimeError):
    """Base class for sanitized authorization failures."""


class ScopeForbiddenError(ScopeAuthorizationError):
    """The process principal has no matching server-owned repository grant."""


class ScopeRejectedError(ScopeAuthorizationError):
    """The caller's requested scope is malformed, stale, or unresolvable."""


@dataclass(frozen=True, slots=True)
class ExplicitScopeRequest:
    read_allow: tuple[str, ...]
    deny: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_patterns(self.read_allow, require_allow=True)
        _validate_patterns(self.deny)


@dataclass(frozen=True, slots=True)
class WorkPackageScopeRequest:
    change_id: str
    package_id: str
    scope_revision: str

    def __post_init__(self) -> None:
        if not _valid_reference(self.change_id) or not _valid_reference(self.package_id):
            raise ValueError("work-package identifiers are invalid")
        if not _REVISION_RE.fullmatch(self.scope_revision):
            raise ValueError("scope_revision must be a full lowercase Git object ID")


RequestedScope = ExplicitScopeRequest | WorkPackageScopeRequest


@dataclass(frozen=True, slots=True)
class PrincipalCodeSearchGrant:
    """Server-owned code visibility ceiling for one authenticated principal."""

    principal_id: str
    repo_slug: str
    namespace_kind: str
    namespace_key: str
    read_allow: tuple[str, ...]
    deny: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.principal_id:
            raise ValueError("principal_id must not be empty")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,50}", self.repo_slug):
            raise ValueError("repo_slug is invalid")
        if self.namespace_kind not in {"main", "feature", "work_package"}:
            raise ValueError("namespace_kind is invalid")
        if not 1 <= len(self.namespace_key) <= 255:
            raise ValueError("namespace_key is invalid")
        if self.namespace_kind == "main" and self.namespace_key != "main":
            raise ValueError("main grants must use namespace_key='main'")
        _validate_patterns(self.read_allow, require_allow=True)
        _validate_patterns(self.deny)


@dataclass(frozen=True, slots=True)
class WorkPackageScopeRecord:
    """Immutable declaration returned by the trusted work-package resolver."""

    repo_slug: str
    change_id: str
    package_id: str
    source_revision: str
    read_allow: tuple[str, ...]
    deny: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,50}", self.repo_slug):
            raise ValueError("repo_slug is invalid")
        if not _valid_reference(self.change_id) or not _valid_reference(self.package_id):
            raise ValueError("work-package identifiers are invalid")
        if not _REVISION_RE.fullmatch(self.source_revision):
            raise ValueError("source_revision must be a full lowercase Git object ID")
        _validate_patterns(self.read_allow, require_allow=True)
        _validate_patterns(self.deny)


class WorkPackageScopeResolver(Protocol):
    async def __call__(
        self,
        repo_slug: str,
        change_id: str,
        package_id: str,
        source_revision: str,
    ) -> WorkPackageScopeRecord | None: ...


PrincipalGrantResolver = Callable[[str, str], Awaitable[PrincipalCodeSearchGrant | None]]


@dataclass(frozen=True, slots=True)
class EffectiveCodeSearchScope:
    """Normalized authorization result used by SQL and defensive hit filtering."""

    allow_layers: tuple[tuple[str, ...], ...]
    deny: tuple[str, ...]
    path_filters: tuple[str, ...]
    source: Literal["explicit", "work_package"]
    authority: Literal["principal_grant", "work_package_registry"]

    @property
    def allow_path_regexes(self) -> list[str]:
        # The adapter applies ANY within one list. A single positive-lookahead
        # expression preserves AND across authority/narrowing layers while each
        # layer remains an OR. PostgreSQL ARE supports look-ahead constraints.
        lookaheads = "".join(f"(?={_regex_union(layer)})" for layer in self.allow_layers)
        return [f"^{lookaheads}.*$"]

    @property
    def deny_path_regexes(self) -> list[str] | None:
        return [glob_to_postgres_regex(pattern) for pattern in self.deny] or None

    @property
    def path_regexes(self) -> list[str] | None:
        return [glob_to_postgres_regex(pattern) for pattern in self.path_filters] or None

    def allows(self, file_path: str) -> bool:
        if not _is_normalized_relative(file_path, max_length=4096):
            return False
        if any(not _matches_any(file_path, layer) for layer in self.allow_layers):
            return False
        if self.path_filters and not _matches_any(file_path, self.path_filters):
            return False
        return not _matches_any(file_path, self.deny)


async def authorize_code_search_scope(
    *,
    principal_id: str,
    repo_slug: str,
    namespace_kind: str,
    namespace_key: str,
    source_revision: str,
    grant: PrincipalCodeSearchGrant | None,
    requested_scope: RequestedScope,
    paths: Sequence[str] = (),
    work_package_resolver: WorkPackageScopeResolver | None = None,
) -> EffectiveCodeSearchScope:
    """Intersect caller narrowing with a server-owned grant or reject safely."""

    if (
        grant is None
        or grant.principal_id != principal_id
        or grant.repo_slug != repo_slug
        or grant.namespace_kind != namespace_kind
        or grant.namespace_key != namespace_key
    ):
        raise ScopeForbiddenError("code-search grant is not authorized")
    try:
        normalized_paths = _canonical_patterns(paths)
    except ValueError as error:
        raise ScopeRejectedError("caller paths are invalid") from error

    if isinstance(requested_scope, ExplicitScopeRequest):
        effective = EffectiveCodeSearchScope(
            allow_layers=(grant.read_allow, requested_scope.read_allow),
            deny=_deduplicated((*grant.deny, *requested_scope.deny)),
            path_filters=normalized_paths,
            source="explicit",
            authority="principal_grant",
        )
        _require_nonempty_effective_scope(effective)
        return effective

    if requested_scope.scope_revision != source_revision:
        raise ScopeRejectedError("work-package scope revision is stale")
    if work_package_resolver is None:
        raise ScopeRejectedError("work-package scope cannot be resolved")
    try:
        record = await work_package_resolver(
            repo_slug,
            requested_scope.change_id,
            requested_scope.package_id,
            source_revision,
        )
    except Exception as error:
        raise ScopeRejectedError("work-package scope cannot be resolved") from error
    if (
        record is None
        or record.repo_slug != repo_slug
        or record.change_id != requested_scope.change_id
        or record.package_id != requested_scope.package_id
        or record.source_revision != source_revision
    ):
        raise ScopeRejectedError("work-package scope provenance does not match")
    effective = EffectiveCodeSearchScope(
        allow_layers=(grant.read_allow, record.read_allow),
        deny=_deduplicated((*grant.deny, *record.deny)),
        path_filters=normalized_paths,
        source="work_package",
        authority="work_package_registry",
    )
    _require_nonempty_effective_scope(effective)
    return effective


def validate_safe_glob(pattern: str) -> str:
    """Validate one canonical normalized repository-relative glob."""

    if not _is_normalized_relative(pattern, max_length=_MAX_GLOB_LENGTH):
        raise ValueError("scope glob must be normalized and repository-relative")
    return pattern


def glob_to_postgres_regex(pattern: str) -> str:
    """Translate canonical ``fnmatch``-style syntax to a PostgreSQL-safe regex."""

    validate_safe_glob(pattern)
    expression: list[str] = ["^"]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            while index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 1
            expression.append(".*")
        elif char == "?":
            expression.append(".")
        elif char == "[":
            end = pattern.find("]", index + 1)
            if end < 0:
                expression.append(r"\[")
            else:
                content = pattern[index + 1 : end]
                if not content:
                    expression.append(r"\[\]")
                else:
                    if content[0] in {"!", "^"}:
                        content = "^" + content[1:]
                    content = content.replace("\\", r"\\")
                    expression.append(f"[{content}]")
                index = end
        else:
            expression.append(re.escape(char))
        index += 1
    expression.append("$")
    return "".join(expression)


def _matches_any(path: str, patterns: Sequence[str]) -> bool:
    return any(re.fullmatch(glob_to_postgres_regex(pattern), path) for pattern in patterns)


def _regex_union(patterns: Sequence[str]) -> str:
    bodies = [
        glob_to_postgres_regex(pattern).removeprefix("^").removesuffix("$") for pattern in patterns
    ]
    return f"^(?:{'|'.join(bodies)})$"


def _validate_patterns(patterns: Sequence[str], *, require_allow: bool = False) -> None:
    if require_allow and not patterns:
        raise ValueError("read_allow must not be empty")
    _canonical_patterns(patterns)


def _canonical_patterns(patterns: Sequence[str]) -> tuple[str, ...]:
    if isinstance(patterns, (str, bytes)) or len(patterns) > _MAX_GLOBS:
        raise ValueError("scope pattern list is invalid")
    normalized = tuple(validate_safe_glob(pattern) for pattern in patterns)
    if len(set(normalized)) != len(normalized):
        raise ValueError("scope patterns must be unique")
    return normalized


def _deduplicated(patterns: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(patterns))


def _require_nonempty_effective_scope(scope: EffectiveCodeSearchScope) -> None:
    """Require one bounded concrete path witness across every scope layer.

    Glob intersection and subtraction are regular-language operations, but a
    complete automaton product would let caller-controlled pattern counts cause
    exponential work. Instead, derive a bounded set of concrete witnesses from
    each pattern's literal prefix/suffix and fail closed when none proves the
    scope usable. This can conservatively reject an unusually complex but
    theoretically non-empty scope; it can never authorize a path that the
    effective scope itself rejects.
    """

    positive_patterns = [
        pattern
        for layer in (
            *scope.allow_layers,
            *((scope.path_filters,) if scope.path_filters else ()),
        )
        for pattern in layer
    ]
    prefixes = list(dict.fromkeys(_literal_prefix(pattern) for pattern in positive_patterns))
    suffixes = list(dict.fromkeys(_literal_suffix(pattern) for pattern in positive_patterns))
    candidates = list(dict.fromkeys(_glob_witness(pattern) for pattern in positive_patterns))
    for prefix in prefixes:
        for suffix in suffixes:
            candidates.append(f"{prefix}scope{suffix}")
            if len(candidates) >= 4096:
                break
        if len(candidates) >= 4096:
            break
    if not any(scope.allows(candidate) for candidate in candidates):
        raise ScopeRejectedError("effective scope is empty")


def _literal_prefix(pattern: str) -> str:
    wildcard_indexes = (
        pattern.find("*"),
        pattern.find("?"),
        pattern.find("["),
    )
    wildcard = min(
        (index for index in wildcard_indexes if index >= 0),
        default=len(pattern),
    )
    return pattern[:wildcard]


def _literal_suffix(pattern: str) -> str:
    wildcard = max(pattern.rfind("*"), pattern.rfind("?"), pattern.rfind("]"))
    return pattern[wildcard + 1 :] if wildcard >= 0 else ""


def _glob_witness(pattern: str) -> str:
    witness: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            while index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 1
            witness.append("scope")
        elif char == "?":
            witness.append("x")
        elif char == "[":
            end = pattern.find("]", index + 1)
            if end < 0:
                witness.append("[")
            else:
                content = pattern[index + 1 : end].lstrip("!^")
                witness.append(content[0] if content else "x")
                index = end
        else:
            witness.append(char)
        index += 1
    return "".join(witness)


def _valid_reference(value: str) -> bool:
    return bool(
        isinstance(value, str) and len(value) <= 200 and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value)
    )


def _is_normalized_relative(value: str, *, max_length: int) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_length
        or value.startswith(("/", "./"))
        or value.endswith("/")
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        return False
    segments = value.split("/")
    return all(segment not in {"", ".", ".."} for segment in segments)
