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

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
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


__all__ = [
    "FULL_REVISION_RE",
    "InjectedHit",
    "OMISSION_REASONS",
    "Omission",
    "SAFE_RELATIVE_PATH_RE",
    "SCHEMA_VERSION",
    "SCORE_PRECISION",
    "UUID_RE",
    "deduplicate",
    "rank_hits",
    "rank_key",
]
