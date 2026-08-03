"""Scoped, deterministic semantic-context retrieval for coding jobs (ri-12).

This module turns one coordinator code-search response into the machine-readable
form of a ``Semantic code context`` section: a bounded, deduplicated, in-scope
list of hits with provenance, or an explicit fallback saying why nothing was
injected. It owns request construction, revision and namespace resolution, scope
derivation, the local deny re-check, deduplication, budgeting, and fallback
classification. It does not speak HTTP (``coordination-bridge`` does) and does
not render markdown (``render_semantic_context`` does).

Three properties are load-bearing and are what the tests in
``skills/tests/context-engineering/`` exist to hold:

**Determinism.** Ranking uses the five-tuple of design decision D5 and nothing
else — no clock, no RNG, no ``set``/``dict`` iteration over unordered input, no
object identity. The key is total within one response, so ``sorted()``'s
stability is never relied upon and the output cannot depend on the order the
service happened to return results in.

**Fail-closed.** Every path that cannot produce trustworthy context produces an
explicit :class:`ContextFallback`, never a silently empty success.
:func:`collect_semantic_context` never raises: raising would make an optional
context input able to block a coding job, which design decision D8 forbids.

**Scope safety.** The scope sent to the service is the *explicit* scope derived
from ri-08's ``index_scopes()`` (D2), and every returned hit is re-checked
against it locally. Widening a package's declared read scope is the exact
failure this change exists to prevent.

Opt-in: ``SEMANTIC_CONTEXT_INJECTION`` gates everything and defaults **off**
(D9). With it off the helper short-circuits before touching git, the bridge, or
the network, so behaviour is byte-identical to a tree without this module.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Version of ``semantic-context-section.schema.json`` this module emits.
SCHEMA_VERSION = 1

#: Number of decimal places the similarity score is collapsed to before ranking.
#: Float noise below this threshold is not a meaningful relevance difference, and
#: letting it decide order would hide the structural tie-breakers that make the
#: rank key reproducible.
SCORE_PRECISION = 6

#: ``FullRevision`` from ``agent-coordinator/src/code_search.py`` -- SHA-1 today,
#: SHA-256 tolerated, nothing else.
FULL_REVISION_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")

#: The ``index_id`` shape both published schemas pin with a ``pattern``, because
#: ``format: uuid`` is an annotation a validator ignores by default.
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

#: Repository-relative, no ``..`` segment, no NUL. Identical to the ``file_path``
#: pattern in both published schemas; a rendered section invites a worker to open
#: these paths, so one that escapes the repository must be unrepresentable.
SAFE_RELATIVE_PATH_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[^\x00]+$")

#: The closed omission vocabulary of ``semantic-context-section.schema.json``:
#: two dedup reasons (D5), four budget reasons (D6), one scope reason (D2).
OMISSION_REASONS: tuple[str, ...] = (
    "duplicate_exact",
    "duplicate_contained",
    "hit_count_cap",
    "file_count_cap",
    "hit_line_cap",
    "total_line_cap",
    "scope_filtered",
)


def _require(condition: bool, message: str) -> None:
    """Raise ``ValueError`` when a value-type invariant is violated.

    Value types validate in ``__post_init__`` rather than trusting their callers:
    the response they are built from crosses a network boundary, and every field
    here is either a scope claim or a provenance claim.
    """
    if not condition:
        raise ValueError(message)


def _is_int(value: object) -> bool:
    """True for a real integer. ``bool`` is excluded: ``True`` is not line 1."""
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_line_span(start_line: object, end_line: object) -> None:
    """Enforce the one invariant JSON Schema cannot express.

    ``end_line >= start_line`` compares two sibling properties, which JSON Schema
    has no vocabulary for. The contracts README records it as a producer
    obligation and hands it here, so it is enforced by the constructor: an
    inverted range cannot exist long enough to be rendered.
    """
    _require(_is_int(start_line), "start_line must be an integer")
    _require(_is_int(end_line), "end_line must be an integer")
    start = int(start_line)  # type: ignore[call-overload]
    end = int(end_line)  # type: ignore[call-overload]
    _require(start >= 1, "start_line must be 1-based")
    _require(end >= 1, "end_line must be 1-based")
    _require(end >= start, "end_line must not be less than start_line")


def _validate_file_path(file_path: object) -> None:
    _require(isinstance(file_path, str), "file_path must be a string")
    path = str(file_path)
    _require(1 <= len(path) <= 4096, "file_path must be 1-4096 characters")
    _require(
        SAFE_RELATIVE_PATH_RE.match(path) is not None,
        "file_path must be repository-relative with no '..' segment",
    )


@dataclass(frozen=True, slots=True)
class InjectedHit:
    """One retrieved excerpt, in the section's vocabulary rather than ri-03's.

    ``score`` carries the coordinator's ``similarity`` and ``indexed_commit``
    carries its ``source_revision``; the mapping is fixed by the contracts
    README so the two vocabularies cannot drift apart silently.

    ``scope_decision`` is always ``allowed``. A hit that fails the local deny
    re-check is omitted with reason ``scope_filtered``, never rendered with a
    downgraded decision -- a section that shows a denied file has already leaked
    it.
    """

    file_path: str
    start_line: int
    end_line: int
    score: float
    indexed_commit: str
    index_id: str
    language: str
    content: str
    scope_decision: str = "allowed"

    def __post_init__(self) -> None:
        _validate_file_path(self.file_path)
        _validate_line_span(self.start_line, self.end_line)
        _require(
            isinstance(self.score, (int, float)) and not isinstance(self.score, bool),
            "score must be a number",
        )
        _require(-1 <= float(self.score) <= 1, "score must be within [-1, 1]")
        _require(
            isinstance(self.indexed_commit, str)
            and FULL_REVISION_RE.match(self.indexed_commit) is not None,
            "indexed_commit must be a full git revision",
        )
        _require(
            isinstance(self.index_id, str) and UUID_RE.match(self.index_id) is not None,
            "index_id must be a UUID",
        )
        _require(
            isinstance(self.language, str) and 1 <= len(self.language) <= 64,
            "language must be 1-64 characters",
        )
        _require(isinstance(self.content, str), "content must be a string")
        _require(self.scope_decision == "allowed", "scope_decision must be 'allowed'")

    @property
    def line_count(self) -> int:
        """Lines this hit spends from the budget; never zero or negative."""
        return self.end_line - self.start_line + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "score": self.score,
            "indexed_commit": self.indexed_commit,
            "index_id": self.index_id,
            "scope_decision": self.scope_decision,
            "language": self.language,
            "content": self.content,
        }


@dataclass(frozen=True, slots=True)
class Omission:
    """A hit the service returned that the section did not render, and why.

    Omissions carry the same path and line-span guarantees as rendered hits: an
    omission names a file too, and an audit of what was dropped is only useful
    if the record of it is as trustworthy as the record of what was kept.
    """

    file_path: str
    start_line: int
    end_line: int
    reason: str

    def __post_init__(self) -> None:
        _validate_file_path(self.file_path)
        _validate_line_span(self.start_line, self.end_line)
        _require(
            self.reason in OMISSION_REASONS,
            f"reason must be one of {OMISSION_REASONS!r}, got {self.reason!r}",
        )

    @classmethod
    def of(cls, hit: InjectedHit, reason: str) -> Omission:
        """The omission record for ``hit``, so call sites cannot mismatch fields."""
        return cls(
            file_path=hit.file_path,
            start_line=hit.start_line,
            end_line=hit.end_line,
            reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "reason": self.reason,
        }


def rank_key(hit: InjectedHit) -> tuple[float, str, int, int, str]:
    """The deterministic five-tuple of design decision D5.

    Higher similarity first (hence the negation), then UTF-8 byte order of the
    path, then the line span, then the index identity. The last four components
    are unique within one response, so the key is total: no two hits can compare
    equal, and the sort therefore never falls through to input order.

    The rounding is deliberate. Two hits whose scores differ in the twelfth
    decimal place are equally relevant, and letting that difference decide their
    order would mean the section's contents depend on floating-point noise from
    the embedding pipeline.
    """
    return (
        -round(float(hit.score), SCORE_PRECISION),
        hit.file_path,
        hit.start_line,
        hit.end_line,
        str(hit.index_id),
    )


def rank_hits(hits: Iterable[InjectedHit]) -> tuple[InjectedHit, ...]:
    """Hits in deterministic rank order."""
    return tuple(sorted(hits, key=rank_key))


def deduplicate(
    ranked: Sequence[InjectedHit],
) -> tuple[tuple[InjectedHit, ...], tuple[Omission, ...]]:
    """Drop repeats and fully-contained spans in one forward pass over rank order.

    Two reasons, and they are not interchangeable. ``duplicate_exact`` is the
    same ``(file_path, start_line, end_line)`` already kept -- typically the same
    chunk served by two indexes, where the survivor is the lower ``index_id``
    because that is the rank tie-breaker. ``duplicate_contained`` is a span that
    lies entirely inside one already kept, which carries no line the reader is
    not already getting.

    Partial overlap is **kept**: two chunks sharing three lines still carry
    distinct code, and dropping either loses content the caller asked for.

    Because the pass runs in rank order the survivor of any collision is always
    the higher-ranked hit, and kept spans are held per file in a list appended in
    that order and scanned linearly -- no set membership over floats, no sort by
    a mutable key.
    """
    kept: list[InjectedHit] = []
    omissions: list[Omission] = []
    spans_by_file: dict[str, list[tuple[int, int]]] = {}

    for hit in ranked:
        spans = spans_by_file.setdefault(hit.file_path, [])
        span = (hit.start_line, hit.end_line)
        if span in spans:
            omissions.append(Omission.of(hit, "duplicate_exact"))
            continue
        if any(start <= hit.start_line and hit.end_line <= end for start, end in spans):
            omissions.append(Omission.of(hit, "duplicate_contained"))
            continue
        spans.append(span)
        kept.append(hit)

    return tuple(kept), tuple(omissions)


# ---------------------------------------------------------------------------
# Budget (D6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """The four bounds a rendered section must respect.

    Lines and hit counts rather than tokens: tokenization is vendor-specific, so
    a token budget would let two vendors build two different sections from one
    response and would make the determinism tests unwritable.
    """

    max_hits: int = 8
    max_files: int = 5
    max_total_lines: int = 240
    max_hit_lines: int = 40

    def __post_init__(self) -> None:
        for name in ("max_hits", "max_files", "max_total_lines", "max_hit_lines"):
            value = getattr(self, name)
            _require(_is_int(value) and value >= 1, f"{name} must be a positive integer")

    @property
    def query_limit(self) -> int:
        """How many hits to ask the service for.

        Three times the render budget so dedup and budgeting have material to
        work with, capped at ri-03's own server-side maximum of 50 so the request
        can never be rejected for asking too much.
        """
        return min(self.max_hits * QUERY_LIMIT_MULTIPLIER, MAX_QUERY_LIMIT)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ContextBudget:
        """Resolve the bounds from the environment, one override per bound.

        An unusable value degrades to that bound's default rather than raising or
        disabling the bound. ``collect_semantic_context`` never raises, and a
        typo in an override must not be able to widen a budget.
        """
        source = os.environ if env is None else env
        resolved: dict[str, int] = {}
        for name, variable in BUDGET_ENV_VARS.items():
            raw = source.get(variable)
            if raw is None:
                continue
            try:
                value = int(str(raw).strip())
            except ValueError:
                continue
            if value >= 1:
                resolved[name] = value
        return cls(**resolved)

    def to_dict(self) -> dict[str, int]:
        return {
            "max_hits": self.max_hits,
            "max_files": self.max_files,
            "max_total_lines": self.max_total_lines,
            "max_hit_lines": self.max_hit_lines,
        }


#: The bounds' environment overrides, one per bound (D6).
BUDGET_ENV_VARS: dict[str, str] = {
    "max_hits": "SEMANTIC_CONTEXT_MAX_HITS",
    "max_files": "SEMANTIC_CONTEXT_MAX_FILES",
    "max_total_lines": "SEMANTIC_CONTEXT_MAX_TOTAL_LINES",
    "max_hit_lines": "SEMANTIC_CONTEXT_MAX_HIT_LINES",
}

#: How many hits to request per rendered hit, and ri-03's own ceiling.
QUERY_LIMIT_MULTIPLIER = 3
MAX_QUERY_LIMIT = 50

#: The fixed precedence of D6. A hit failing several bounds at once is recorded
#: against the first of these that fails, so the reason is a function of the
#: inputs and not of the order the implementation happens to test them in.
BUDGET_REASON_ORDER: tuple[str, ...] = (
    "hit_count_cap",
    "file_count_cap",
    "hit_line_cap",
    "total_line_cap",
)

DEFAULT_BUDGET = ContextBudget()


def apply_budget(
    hits: Sequence[InjectedHit], budget: ContextBudget
) -> tuple[tuple[InjectedHit, ...], tuple[Omission, ...]]:
    """First-fit over the ranked, deduplicated hits. No early break.

    A hit is admitted iff **all** four bounds hold. Otherwise it is omitted with
    the first failing reason in :data:`BUDGET_REASON_ORDER` and **the scan
    continues**, so a later small hit can still be admitted after a large one was
    skipped.

    Breaking out of the loop on the first failure would be cheaper and wrong: the
    section's contents would then depend on where the first oversized hit landed
    in the ranking, reintroducing exactly the arrival-order dependence the rank
    key was built to remove.
    """
    kept: list[InjectedHit] = []
    omissions: list[Omission] = []
    files: dict[str, None] = {}
    used_lines = 0

    for hit in hits:
        lines = hit.line_count
        if len(kept) >= budget.max_hits:
            reason = "hit_count_cap"
        elif hit.file_path not in files and len(files) >= budget.max_files:
            reason = "file_count_cap"
        elif lines > budget.max_hit_lines:
            reason = "hit_line_cap"
        elif used_lines + lines > budget.max_total_lines:
            reason = "total_line_cap"
        else:
            kept.append(hit)
            files[hit.file_path] = None
            used_lines += lines
            continue
        omissions.append(Omission.of(hit, reason))

    return tuple(kept), tuple(omissions)


def filter_scope(
    hits: Sequence[InjectedHit], scopes: Any
) -> tuple[tuple[InjectedHit, ...], tuple[Omission, ...]]:
    """Re-apply the package's read scope to what the service returned (D2).

    Defense in depth, and deliberately redundant: a same-revision index cannot
    return a path its own scope excluded. But ri-12 sends the scope from the
    *client* side, so this local re-check is what makes the skill's boundary
    claim self-verifying rather than a claim about someone else's code.

    ``scopes`` is anything exposing ``allows(path) -> bool`` -- ri-08's
    ``IndexScopes`` in production, a stub in tests.
    """
    kept: list[InjectedHit] = []
    omissions: list[Omission] = []
    for hit in hits:
        if scopes is not None and not scopes.allows(hit.file_path):
            omissions.append(Omission.of(hit, "scope_filtered"))
            continue
        kept.append(hit)
    return tuple(kept), tuple(omissions)


def select_hits(
    hits: Iterable[InjectedHit], budget: ContextBudget, scopes: Any
) -> tuple[tuple[InjectedHit, ...], tuple[Omission, ...]]:
    """Rank, re-scope, deduplicate, then budget -- in that order.

    Scope filtering runs before deduplication so a hit that is not allowed to be
    read cannot occupy a slot, suppress an in-scope duplicate, or spend part of
    the line budget. Omissions come out grouped by stage and in rank order
    within each stage, which is a deterministic function of the response.
    """
    ranked = rank_hits(hits)
    in_scope, scope_omissions = filter_scope(ranked, scopes)
    deduped, dedup_omissions = deduplicate(in_scope)
    kept, budget_omissions = apply_budget(deduped, budget)
    return kept, scope_omissions + dedup_omissions + budget_omissions


# ---------------------------------------------------------------------------
# Fallback vocabulary (D8)
# ---------------------------------------------------------------------------

#: The five triggers. Each is a different remedy, which is why `stale` and
#: `mismatched` are not collapsed: `stale` means *this agent* must commit or
#: re-index, `mismatched` means the *index* is behind.
#:
#: Four describe a failure. `no_context` (D14) is the only one that describes a
#: *healthy, current* index: the query succeeded and the section still has
#: nothing to show. It exists because the alternative was filing a working
#: service under `unavailable`, which sends a reader looking for an outage that
#: never happened.
FALLBACK_TRIGGERS: tuple[str, ...] = (
    "stale",
    "unavailable",
    "mismatched",
    "out_of_scope",
    "no_context",
)

#: Every reason in ``semantic-context-section.schema.json``. Distinct per cause,
#: so a test can assert exactly why the fallback happened rather than only that
#: one did.
FALLBACK_REASONS: tuple[str, ...] = (
    "working_tree_dirty",
    "revision_not_indexed",
    "injection_disabled",
    "capability_absent",
    "transport_unsupported",
    "revision_unresolvable",
    "bridge_failed",
    "service_unavailable",
    "service_overloaded",
    "unknown_state",
    "index_revision_differs",
    "scope_rejected",
    "no_declared_scope",
    "scope_self_cancelling",
    "all_hits_scope_filtered",
    # D14's two relevance reasons. They are different facts about the world:
    # only `all_hits_omitted` could have been changed by a larger budget.
    "index_returned_no_hits",
    "all_hits_omitted",
)

#: D14's trigger for a ready index that yielded nothing renderable, paired with
#: the reason for each of the two ways that happens.
NO_CONTEXT_EMPTY_INDEX: tuple[str, str] = ("no_context", "index_returned_no_hits")
NO_CONTEXT_ALL_OMITTED: tuple[str, str] = ("no_context", "all_hits_omitted")

#: ri-03's ``CodeSearchState``. Anything outside this set is a coordinator this
#: client does not understand.
SERVICE_STATES: tuple[str, ...] = (
    "ready",
    "revision_mismatch",
    "not_indexed",
    "not_configured",
    "unavailable",
    "scope_rejected",
)

#: Total mapping from a *non-ready* service state onto a trigger and reason.
STATE_FALLBACKS: dict[str, tuple[str, str]] = {
    "not_indexed": ("stale", "revision_not_indexed"),
    "revision_mismatch": ("mismatched", "index_revision_differs"),
    "scope_rejected": ("out_of_scope", "scope_rejected"),
    "not_configured": ("unavailable", "service_unavailable"),
    "unavailable": ("unavailable", "service_unavailable"),
}

#: What an unrecognized state maps to. A future coordinator adding a seventh
#: state must degrade to exact search, never to an injection this client cannot
#: reason about.
UNKNOWN_STATE_FALLBACK: tuple[str, str] = ("unavailable", "unknown_state")

#: Git's null object id, used as ``requested_revision`` when no revision was
#: resolved. The section schema requires the field on fallbacks too, and a
#: placeholder that is recognizably "no commit" is more honest than either
#: omitting a required field or inventing a plausible-looking hash.
UNRESOLVED_REVISION = "0" * 40

#: The flag that gates everything, and the values that count as on -- matching
#: ri-03's ``code_search_enabled()`` so the two switches read the same way.
INJECTION_FLAG = "SEMANTIC_CONTEXT_INJECTION"
TRUTHY_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})

#: Default repository slug, matching ri-03's ``RepoSlug`` shape.
DEFAULT_REPO_SLUG = "agentic_coding_tools"

#: How long a git probe may take before it counts as unresolvable. A context
#: helper must not be able to hang a coding job.
GIT_TIMEOUT_SECONDS = 15

_CONSUMER_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def fallback_for_state(state: str) -> tuple[str, str]:
    """The trigger and reason for any service state string, known or not.

    Total by construction: an unrecognized state is not an error to be handled
    somewhere else, it is ``unavailable`` / ``unknown_state`` here.
    """
    if state in STATE_FALLBACKS:
        return STATE_FALLBACKS[state]
    return UNKNOWN_STATE_FALLBACK


def injection_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Whether ``SEMANTIC_CONTEXT_INJECTION`` is explicitly on. Default off (D9)."""
    source = os.environ if env is None else env
    return str(source.get(INJECTION_FLAG, "")).strip().lower() in TRUTHY_VALUES


# ---------------------------------------------------------------------------
# Result value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SectionProvenance:
    """Which index answered, and under what authority."""

    repo_slug: str
    namespace_kind: str
    namespace_key: str
    index_id: str
    scope_authority: str
    read_allow_count: int
    deny_count: int
    embedder_model: str | None = None
    embedding_dim: int | None = None
    scope_decision: str = "allowed"

    def __post_init__(self) -> None:
        _require(
            self.namespace_kind in ("main", "feature", "work_package"),
            "namespace_kind must be main, feature, or work_package",
        )
        _require(
            isinstance(self.namespace_key, str) and 1 <= len(self.namespace_key) <= 255,
            "namespace_key must be 1-255 characters",
        )
        _require(
            isinstance(self.index_id, str) and UUID_RE.match(self.index_id) is not None,
            "index_id must be a UUID",
        )
        _require(
            self.scope_authority in ("principal_grant", "work_package_registry"),
            "scope_authority must mirror ri-03's ScopeDisposition.authority",
        )
        _require(
            _is_int(self.read_allow_count) and self.read_allow_count >= 1,
            "read_allow_count must be at least 1",
        )
        _require(
            _is_int(self.deny_count) and self.deny_count >= 0,
            "deny_count must not be negative",
        )
        _require(self.scope_decision == "allowed", "scope_decision must be 'allowed'")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "repo_slug": self.repo_slug,
            "namespace_kind": self.namespace_kind,
            "namespace_key": self.namespace_key,
            "index_id": self.index_id,
            "scope_decision": self.scope_decision,
            "scope_authority": self.scope_authority,
            "read_allow_count": self.read_allow_count,
            "deny_count": self.deny_count,
        }
        if self.embedder_model is not None:
            payload["embedder_model"] = self.embedder_model
        if self.embedding_dim is not None:
            payload["embedding_dim"] = self.embedding_dim
        return payload


@dataclass(frozen=True, slots=True)
class ContextFallback:
    """Why nothing was injected and what the worker should do instead."""

    trigger: str
    reason: str
    strategy: str = "exact_search"
    service_state: str | None = None

    def __post_init__(self) -> None:
        _require(self.trigger in FALLBACK_TRIGGERS, f"unknown trigger {self.trigger!r}")
        _require(self.reason in FALLBACK_REASONS, f"unknown reason {self.reason!r}")
        _require(self.strategy == "exact_search", "exact search is the only fallback")
        _require(
            self.service_state is None or self.service_state in SERVICE_STATES,
            "service_state must be a CodeSearchState, or absent when no query ran",
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trigger": self.trigger,
            "reason": self.reason,
            "strategy": self.strategy,
        }
        if self.service_state is not None:
            payload["service_state"] = self.service_state
        return payload


@dataclass(frozen=True, slots=True)
class SemanticContextResult:
    """One ``Semantic code context`` section, injected or fallen back.

    The two states are enforced here as well as in the schema: an injected
    result with a fallback attached, or a fallback carrying hits, cannot be
    constructed. A rendered section has no honest way to display either.
    """

    status: str
    consumer: str
    requested_revision: str
    hits: tuple[InjectedHit, ...] = ()
    omissions: tuple[Omission, ...] = ()
    provenance: SectionProvenance | None = None
    fallback: ContextFallback | None = None

    def __post_init__(self) -> None:
        _require(self.status in ("injected", "fallback"), "status must be injected or fallback")
        _require(
            _CONSUMER_RE.match(self.consumer) is not None,
            "consumer must be a lowercase identifier",
        )
        _require(
            FULL_REVISION_RE.match(self.requested_revision) is not None,
            "requested_revision must be a full git revision",
        )
        if self.status == "injected":
            _require(bool(self.hits), "an injected section must carry at least one hit")
            _require(self.provenance is not None, "an injected section must carry provenance")
            _require(self.fallback is None, "an injected section cannot carry a fallback")
        else:
            _require(not self.hits, "a fallback section must carry no hits")
            _require(self.fallback is not None, "a fallback section must say why")
            _require(self.provenance is None, "a fallback section has no index provenance")

    @property
    def injected(self) -> bool:
        return self.status == "injected"

    def to_dict(self) -> dict[str, Any]:
        """The section schema's shape.

        ``provenance`` and ``fallback`` are *omitted* rather than set to null:
        the schema's ``oneOf`` forbids the key outright on the opposite branch,
        and a present-but-null key would fail both branches.
        """
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "consumer": self.consumer,
            "requested_revision": self.requested_revision,
            "hits": [hit.to_dict() for hit in self.hits],
            "omissions": [omission.to_dict() for omission in self.omissions],
        }
        if self.provenance is not None:
            payload["provenance"] = self.provenance.to_dict()
        if self.fallback is not None:
            payload["fallback"] = self.fallback.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class SemanticContextRequest:
    """What a coding job asks for.

    ``change_id`` and ``package_id`` are optional because ``quick-task`` and
    ad-hoc debugging have neither. Their absence is not a licence to widen: with
    no declared scope the helper returns ``out_of_scope`` /
    ``no_declared_scope`` rather than inventing a repository-root scope.
    """

    repository: Path
    query: str
    consumer: str
    change_id: str | None = None
    package_id: str | None = None
    budget: ContextBudget | None = None
    repo_slug: str = DEFAULT_REPO_SLUG

    def __post_init__(self) -> None:
        _require(
            isinstance(self.query, str) and 1 <= len(self.query) <= 8192,
            "query must be 1-8192 characters",
        )
        _require(
            _CONSUMER_RE.match(str(self.consumer)) is not None,
            "consumer must be a lowercase identifier, e.g. 'implement-feature'",
        )

    @property
    def has_package_context(self) -> bool:
        return bool(self.change_id and self.package_id)

    def resolved_budget(self, env: Mapping[str, str] | None = None) -> ContextBudget:
        """The caller's explicit budget, or the environment-resolved default."""
        if self.budget is not None:
            return self.budget
        return ContextBudget.from_env(env)


# ---------------------------------------------------------------------------
# Injectable seams
# ---------------------------------------------------------------------------

#: ``(request_body) -> bridge envelope``. The only path to the network, and the
#: seam ri-12's tests replace. Kept as a plain callable taking the already-built
#: ``CodeSearchRequest`` body so this module never imports the transport at
#: module scope: `coordination-bridge` is a sibling skill, and a hard import
#: would make this module unloadable wherever that skill is not installed.
CodeSearchClient = Any

#: ``() -> capability flags``, normally ``detect_coordination()``.
CoordinationDetector = Any

#: ``(repository, argv) -> stdout or None``. ``None`` means the command failed.
GitRunner = Any


def _default_search_client(body: Mapping[str, Any]) -> dict[str, Any]:
    """POST the request through ``coordination_bridge.try_code_search``.

    Imported lazily and defensively. The helper is owned by another work
    package; until it exists, or wherever the bridge is not installed, this
    degrades to a ``bridge_failed`` fallback instead of an ImportError that
    would take down the coding job this context was only an optional input to.
    """
    try:
        bridge = _import_bridge()
        helper = getattr(bridge, "try_code_search", None)
        if helper is None:
            return {"status": "failed", "reason": "bridge_helper_missing"}
        try:
            # The bridge's uniform style is keyword arguments mirroring the
            # payload; a single-argument helper is accepted as the alternative
            # rather than assumed away, because the helper is another package's
            # to define and a wrong guess here must degrade, not raise.
            return dict(helper(**dict(body)))
        except TypeError:
            return dict(helper(dict(body)))
    except Exception:  # pragma: no cover - transport guard
        return {"status": "failed", "reason": "bridge_call_failed"}


def _default_detect() -> dict[str, Any]:
    """Capability flags from the bridge; an empty mapping when it cannot answer.

    An empty mapping reads as ``CAN_CODE_SEARCH`` false, which is the
    fail-closed answer: no evidence of a usable index means no injection.
    """
    try:
        return dict(_import_bridge().detect_coordination())
    except Exception:  # pragma: no cover - detection guard
        return {}


def _import_bridge() -> Any:
    """Import the sibling ``coordination_bridge`` module by flat name."""
    bridge_dir = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts"
    if str(bridge_dir) not in sys.path:
        sys.path.insert(0, str(bridge_dir))
    import coordination_bridge

    return coordination_bridge


def _run_git(repository: Path, args: Sequence[str]) -> str | None:
    """Run one read-only git command; ``None`` when it could not answer."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _default_load_package(
    repository: Path, change_id: str, package_id: str
) -> Mapping[str, Any] | None:
    """One package out of the change's ``work-packages.yaml``, or ``None``."""
    try:
        import yaml
    except ImportError:  # pragma: no cover - environment guard
        return None
    path = Path(repository) / "openspec" / "changes" / change_id / "work-packages.yaml"
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(document, Mapping):
        return None
    for package in document.get("packages") or ():
        if isinstance(package, Mapping) and package.get("package_id") == package_id:
            return package
    return None


def _default_load_checkpoint(
    repository: Path, change_id: str, package_id: str
) -> Mapping[str, Any] | None:
    """The ri-09 checkpoint report for this package, or ``None`` when absent."""
    path = (
        Path(repository)
        / "openspec"
        / "changes"
        / change_id
        / "context-checkpoints"
        / f"{package_id}.json"
    )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, Mapping) else None


def _default_index_scopes(package: Mapping[str, Any]) -> Any:
    """ri-08's resolved read scope for ``package``, or ``None`` if unavailable.

    Imported lazily: ``context_impact`` calls ``sys.exit`` when pyyaml is
    missing, and a context helper must never be able to terminate its caller.
    ``None`` degrades to ``no_declared_scope``, which is fail-closed.
    """
    scopes_dir = Path(__file__).resolve().parents[2] / "validate-packages" / "scripts"
    if str(scopes_dir) not in sys.path:
        sys.path.insert(0, str(scopes_dir))
    try:
        from context_impact import index_scopes
    except (ImportError, SystemExit):  # pragma: no cover - environment guard
        return None
    return index_scopes(package)


def _normalize_read_scope(scopes: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Normalize through ri-09's ``ReadScope``; raise on a self-cancelling scope.

    ``ReadScope`` resolves deny precedence on the value and refuses a scope whose
    deny list cancels every glob it allows, because an empty ``read_allow``
    means "no restriction" downstream -- silently emptying one would widen the
    scope instead of narrowing it. Reusing it keeps that rule defined once.
    """
    adapter_dir = Path(__file__).resolve().parents[2] / "project-context-refresh" / "scripts"
    if str(adapter_dir) not in sys.path:
        sys.path.insert(0, str(adapter_dir))
    try:
        from semantic_adapter import ReadScope
    except (ImportError, SystemExit):  # pragma: no cover - environment guard
        return (
            tuple(getattr(scopes, "read_allow", ()) or ()),
            tuple(getattr(scopes, "deny", ()) or ()),
        )
    normalized = ReadScope.from_index_scopes(scopes)
    return tuple(normalized.read_allow), tuple(normalized.deny)


def _work_package_namespace(change_id: str, package_id: str) -> tuple[str, str]:
    """ri-09's branch-local namespace, so the naming rule has one definition."""
    adapter_dir = Path(__file__).resolve().parents[2] / "project-context-refresh" / "scripts"
    if str(adapter_dir) not in sys.path:
        sys.path.insert(0, str(adapter_dir))
    try:
        from semantic_adapter import IndexNamespace
    except (ImportError, SystemExit):  # pragma: no cover - environment guard
        return ("work_package", f"{change_id}--{package_id}")
    namespace = IndexNamespace.for_work_package(change_id, package_id)
    return (namespace.kind, namespace.key)


@dataclass(frozen=True, slots=True)
class SemanticContextRuntime:
    """The injectable environment ``collect_semantic_context`` runs against.

    Every boundary this helper crosses -- the network, git, the filesystem, the
    process environment -- is a field here, so a test can drive the whole
    decision tree without a coordinator, a repository, or a checkpoint on disk.
    """

    search: CodeSearchClient = _default_search_client
    detect: CoordinationDetector = _default_detect
    git: GitRunner = _run_git
    load_package: Any = _default_load_package
    load_checkpoint: Any = _default_load_checkpoint
    index_scopes: Any = _default_index_scopes
    env: Mapping[str, str] | None = None

    @property
    def environ(self) -> Mapping[str, str]:
        return os.environ if self.env is None else self.env


DEFAULT_RUNTIME = SemanticContextRuntime()


class _FallbackSignal(Exception):
    """Internal control flow: a step decided the section cannot be injected.

    Raised only inside this module and always caught by
    :func:`collect_semantic_context`, which converts it into a
    :class:`SemanticContextResult`. It never escapes.
    """

    def __init__(self, trigger: str, reason: str, service_state: str | None = None) -> None:
        super().__init__(f"{trigger}/{reason}")
        self.trigger = trigger
        self.reason = reason
        self.service_state = service_state


def _fallback_result(
    request: SemanticContextRequest,
    revision: str,
    trigger: str,
    reason: str,
    service_state: str | None = None,
) -> SemanticContextResult:
    return SemanticContextResult(
        status="fallback",
        consumer=request.consumer,
        requested_revision=revision,
        fallback=ContextFallback(trigger=trigger, reason=reason, service_state=service_state),
    )


def resolve_revision(repository: Path, runtime: SemanticContextRuntime) -> tuple[Path, str]:
    """The worktree root and the revision the agent is actually editing (D3).

    ``HEAD`` in *this* worktree, not the merge base against main: the merge base
    is by construction not the tree the agent is reading, so hits from it would
    carry a truthful revision that is nonetheless the wrong code.

    A dirty working tree is :class:`stale` and short-circuits before any query.
    The coordinator would answer truthfully for ``HEAD`` and the agent would
    silently receive pre-edit content for files it just changed; a cheap
    ``status --porcelain`` converts that subtle wrongness into an explicit,
    testable state. The check is not narrowed to the package's ``write_allow``:
    the index embeds the whole read scope, so an edit anywhere in it can
    invalidate a retrieved hit.
    """
    toplevel = runtime.git(repository, ("rev-parse", "--show-toplevel"))
    if not toplevel or not toplevel.strip():
        raise _FallbackSignal("unavailable", "revision_unresolvable")
    root = Path(toplevel.strip())

    head = runtime.git(root, ("rev-parse", "HEAD"))
    if head is None:
        raise _FallbackSignal("unavailable", "revision_unresolvable")
    revision = head.strip()
    if FULL_REVISION_RE.match(revision) is None:
        raise _FallbackSignal("unavailable", "revision_unresolvable")

    porcelain = runtime.git(root, ("status", "--porcelain"))
    if porcelain is None:
        raise _FallbackSignal("unavailable", "revision_unresolvable")
    if porcelain.strip():
        raise _FallbackSignal("stale", "working_tree_dirty")

    return root, revision


def resolve_scope(
    request: SemanticContextRequest, root: Path, runtime: SemanticContextRuntime
) -> tuple[Any, tuple[str, ...], tuple[str, ...]]:
    """The package's declared read scope, as an explicit scope payload (D2).

    Explicit, never ``kind="work_package"``: ``start_code_search_runtime()``
    builds the coordinator runtime with no ``work_package_resolver``, so a
    work-package scope is rejected on every single call. Sending one would make
    every job a fallback.

    With no change or package there is no declared scope, and the helper does not
    invent one. Widening to the repository root is exactly the failure this
    change exists to prevent.
    """
    if not request.has_package_context:
        raise _FallbackSignal("out_of_scope", "no_declared_scope")

    package = runtime.load_package(root, request.change_id, request.package_id)
    if not package:
        raise _FallbackSignal("out_of_scope", "no_declared_scope")

    scopes = runtime.index_scopes(package)
    if scopes is None:
        raise _FallbackSignal("out_of_scope", "no_declared_scope")

    try:
        read_allow, deny = _normalize_read_scope(scopes)
    except ValueError as error:
        raise _FallbackSignal("out_of_scope", "scope_self_cancelling") from error
    if not read_allow:
        raise _FallbackSignal("out_of_scope", "no_declared_scope")
    return scopes, read_allow, deny


def resolve_namespace(
    request: SemanticContextRequest,
    root: Path,
    revision: str,
    runtime: SemanticContextRuntime,
) -> tuple[str, str, str | None]:
    """Which index partition to query, and its exact id when required (D4).

    Two steps, no probing. The ri-09 checkpoint report is a deterministic,
    inspectable input: when it records a *succeeded* index at exactly this
    revision, its registry record id is the only place client-side that holds
    the ``index_id`` a non-main namespace requires. Anything else -- no report,
    a failed one, one pinned to another revision, an id that is not a UUID --
    falls back to the canonical ``main``/``main`` pointer and lets the
    coordinator decide, which yields ``revision_mismatch`` if main is behind.

    Trying the work-package namespace and retrying canonical on failure would
    cost two queries and make "which index answered" depend on transient service
    state. Branch on the record, do not probe.
    """
    if not request.has_package_context:
        return ("main", "main", None)

    report = runtime.load_checkpoint(root, request.change_id, request.package_id)
    if not isinstance(report, Mapping):
        return ("main", "main", None)
    index = report.get("semantic_index")
    if not isinstance(index, Mapping):
        return ("main", "main", None)
    if index.get("status") != "succeeded" or index.get("indexed_revision") != revision:
        return ("main", "main", None)
    record_id = index.get("registry_record_id")
    if not isinstance(record_id, str) or UUID_RE.match(record_id) is None:
        return ("main", "main", None)

    kind, key = _work_package_namespace(str(request.change_id), str(request.package_id))
    if len(key) > 255:
        return ("main", "main", None)
    return (kind, key, record_id)


def build_request_body(
    request: SemanticContextRequest,
    revision: str,
    namespace: tuple[str, str, str | None],
    read_allow: Sequence[str],
    deny: Sequence[str],
    budget: ContextBudget,
) -> dict[str, Any]:
    """The ri-03 ``CodeSearchRequest`` body, built from resolved inputs only."""
    kind, key, index_id = namespace
    return {
        "query": request.query,
        "repo_slug": request.repo_slug,
        "source_revision": revision,
        "namespace": {"kind": kind, "key": key},
        "index_id": index_id,
        "scope": {
            "kind": "explicit",
            "read_allow": list(read_allow),
            "deny": list(deny),
        },
        "limit": budget.query_limit,
        "offset": 0,
    }


def _envelope_failure_reason(envelope: Mapping[str, Any]) -> str:
    """Why a non-``ok`` bridge envelope means no context.

    Overload and outage are named separately from a generic bridge failure
    because they say something different to whoever reads the fallback: retry
    later versus this deployment has no index.
    """
    status_code = envelope.get("status_code")
    if status_code == 429:
        return "service_overloaded"
    if _is_int(status_code) and int(status_code) >= 500:
        return "service_unavailable"
    if envelope.get("reason") in ("capability_absent", "capability_unavailable"):
        return "capability_absent"
    return "bridge_failed"


def _hit_from_response(payload: Mapping[str, Any]) -> InjectedHit:
    """One ``CodeSearchHit`` in the section's vocabulary (contracts README)."""
    return InjectedHit(
        file_path=payload.get("file_path"),  # type: ignore[arg-type]
        start_line=payload.get("start_line"),  # type: ignore[arg-type]
        end_line=payload.get("end_line"),  # type: ignore[arg-type]
        score=payload.get("similarity"),  # type: ignore[arg-type]
        indexed_commit=payload.get("source_revision"),  # type: ignore[arg-type]
        index_id=str(payload.get("index_id")),
        language=payload.get("language"),  # type: ignore[arg-type]
        content=payload.get("content"),  # type: ignore[arg-type]
    )


def _parse_hits(response: Mapping[str, Any], revision: str) -> tuple[InjectedHit, ...]:
    """Every returned result, or a ``bridge_failed`` signal if any is malformed.

    A response this client cannot represent faithfully is not partially usable.
    Dropping the bad entries and rendering the rest would mean the section's
    contents depend on a defect in the producer, and the omission vocabulary has
    no honest reason code for "we could not read this one".
    """
    results = response.get("results")
    if results is None:
        results = ()
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise _FallbackSignal("unavailable", "bridge_failed", "ready")
    hits: list[InjectedHit] = []
    for payload in results:
        if not isinstance(payload, Mapping):
            raise _FallbackSignal("unavailable", "bridge_failed", "ready")
        try:
            hits.append(_hit_from_response(payload))
        except (ValueError, TypeError) as error:
            raise _FallbackSignal("unavailable", "bridge_failed", "ready") from error
    for hit in hits:
        if hit.indexed_commit != revision:
            # `state=ready` promised the index matches; it does not.
            raise _FallbackSignal("mismatched", "index_revision_differs", "ready")
    return tuple(hits)


def _build_provenance(
    request: SemanticContextRequest,
    response: Mapping[str, Any],
    namespace: tuple[str, str, str | None],
    read_allow: Sequence[str],
    deny: Sequence[str],
) -> SectionProvenance:
    index = response.get("index")
    if not isinstance(index, Mapping):
        raise _FallbackSignal("unavailable", "bridge_failed", "ready")
    scope = response.get("scope")
    authority = "principal_grant"
    if isinstance(scope, Mapping) and scope.get("authority") in (
        "principal_grant",
        "work_package_registry",
    ):
        authority = str(scope["authority"])
    kind, key, _ = namespace
    try:
        return SectionProvenance(
            repo_slug=str(index.get("repo_slug") or request.repo_slug),
            namespace_kind=kind,
            namespace_key=key,
            index_id=str(index.get("index_id")),
            scope_authority=authority,
            read_allow_count=len(read_allow),
            deny_count=len(deny),
            embedder_model=index.get("embedder_model"),
            embedding_dim=index.get("embedding_dim"),
        )
    except (ValueError, TypeError) as error:
        raise _FallbackSignal("unavailable", "bridge_failed", "ready") from error


def collect_semantic_context(
    request: SemanticContextRequest,
    runtime: SemanticContextRuntime | None = None,
) -> SemanticContextResult:
    """Retrieve scoped semantic context for one coding job. Never raises.

    Local preconditions are evaluated before any network call, in a fixed order
    -- flag off, capability absent, transport unsupported, revision
    unresolvable, dirty tree, scope unresolvable -- so the trigger is a pure
    function of the environment rather than of what happened to fail first.

    Raising here would be a bug, not a state: this is an optional input to a
    coding job, and an optional input that can abort its consumer is not
    optional. Every failure path returns ``status="fallback"`` with a trigger
    and a reason.
    """
    active = DEFAULT_RUNTIME if runtime is None else runtime
    revision = UNRESOLVED_REVISION
    try:
        env = active.environ

        # D9: the flag gates everything, before git, the bridge, or the network.
        if not injection_enabled(env):
            raise _FallbackSignal("unavailable", "injection_disabled")

        flags = active.detect() or {}
        if not flags.get("CAN_CODE_SEARCH"):
            raise _FallbackSignal("unavailable", "capability_absent")
        # D13: MCP-only coordination never reports a usable index, so injection
        # is HTTP-only and says so rather than pretending the tool's existence
        # is evidence the index can answer.
        if flags.get("COORDINATION_TRANSPORT") != "http":
            raise _FallbackSignal("unavailable", "transport_unsupported")

        root, revision = resolve_revision(request.repository, active)
        scopes, read_allow, deny = resolve_scope(request, root, active)
        namespace = resolve_namespace(request, root, revision, active)
        budget = request.resolved_budget(env)

        body = build_request_body(request, revision, namespace, read_allow, deny, budget)
        try:
            envelope = active.search(body)
        except Exception as error:  # noqa: BLE001 - the transport must not escape
            raise _FallbackSignal("unavailable", "bridge_failed") from error
        if not isinstance(envelope, Mapping) or envelope.get("status") != "ok":
            reason = (
                _envelope_failure_reason(envelope)
                if isinstance(envelope, Mapping)
                else "bridge_failed"
            )
            raise _FallbackSignal("unavailable", reason)

        response = envelope.get("response")
        if not isinstance(response, Mapping):
            raise _FallbackSignal("unavailable", "bridge_failed")

        state = str(response.get("state") or "")
        if state != "ready":
            trigger, reason = fallback_for_state(state)
            known = state if state in SERVICE_STATES else None
            raise _FallbackSignal(trigger, reason, known)

        hits = _parse_hits(response, revision)
        kept, omissions = select_hits(hits, budget, scopes)
        if not kept:
            # Nothing renderable survived, and an empty `injected` section is
            # unrepresentable by the contract. Which fallback that is depends on
            # WHY nothing survived, and the three causes have different remedies.
            if hits and all(o.reason == "scope_filtered" for o in omissions):
                # A scope decision, not a relevance one. Reporting it as
                # `no_context` would hide a scope event behind a relevance one.
                raise _FallbackSignal("out_of_scope", "all_hits_scope_filtered", "ready")
            if hits:
                # The index answered with hits and this client's own dedup and
                # budget selection kept none. This is the only one of the three
                # that a larger budget could have changed.
                raise _FallbackSignal(*NO_CONTEXT_ALL_OMITTED, "ready")
            # The index held nothing similar enough inside the declared scope.
            # The service is healthy and current; saying `unavailable` here (as
            # this did before D14) reports a working service as broken.
            raise _FallbackSignal(*NO_CONTEXT_EMPTY_INDEX, "ready")

        provenance = _build_provenance(request, response, namespace, read_allow, deny)
        return SemanticContextResult(
            status="injected",
            consumer=request.consumer,
            requested_revision=revision,
            hits=kept,
            omissions=omissions,
            provenance=provenance,
        )
    except _FallbackSignal as signal:
        return _fallback_result(
            request, revision, signal.trigger, signal.reason, signal.service_state
        )
    except Exception:  # noqa: BLE001 - the never-raises guarantee of D8
        return _fallback_result(request, revision, *UNKNOWN_STATE_FALLBACK)


__all__ = [
    "BUDGET_ENV_VARS",
    "BUDGET_REASON_ORDER",
    "ContextBudget",
    "ContextFallback",
    "DEFAULT_BUDGET",
    "DEFAULT_REPO_SLUG",
    "DEFAULT_RUNTIME",
    "FALLBACK_REASONS",
    "FALLBACK_TRIGGERS",
    "FULL_REVISION_RE",
    "GIT_TIMEOUT_SECONDS",
    "INJECTION_FLAG",
    "InjectedHit",
    "MAX_QUERY_LIMIT",
    "OMISSION_REASONS",
    "Omission",
    "QUERY_LIMIT_MULTIPLIER",
    "SAFE_RELATIVE_PATH_RE",
    "SCHEMA_VERSION",
    "SCORE_PRECISION",
    "SERVICE_STATES",
    "STATE_FALLBACKS",
    "SectionProvenance",
    "SemanticContextRequest",
    "SemanticContextResult",
    "SemanticContextRuntime",
    "TRUTHY_VALUES",
    "UNKNOWN_STATE_FALLBACK",
    "UNRESOLVED_REVISION",
    "UUID_RE",
    "apply_budget",
    "build_request_body",
    "collect_semantic_context",
    "deduplicate",
    "fallback_for_state",
    "filter_scope",
    "injection_enabled",
    "rank_hits",
    "rank_key",
    "resolve_namespace",
    "resolve_revision",
    "resolve_scope",
    "select_hits",
]
