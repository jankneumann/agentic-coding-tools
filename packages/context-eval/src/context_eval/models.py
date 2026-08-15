"""Typed, frozen views of the corpus documents.

Frozen on purpose. Everything downstream of the loader — the exact-search
producer, the three scorers, the verdict composer — is required to be a pure
function of ``(documents, corpus, thresholds)`` (design D16). A mutable corpus
object would make that a convention; an immutable one makes it a property, and
an accidental ``corpus.gates[0].thresholds[...] = x`` in a scorer becomes a
``TypeError`` at the moment it is written rather than a number nobody can
account for three phases later.

Sequences are tuples and threshold maps are ``MappingProxyType`` for the same
reason. Note what is deliberately *not* here: no defaults that could stand in
for a missing document field. The schemas decide what is required; a default
here would silently repair a corpus the contract already rejected.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class Budget:
    """The single context budget both arms are rendered under (design D5)."""

    max_hits: int
    max_files: int
    max_total_lines: int
    max_hit_lines: int


@dataclass(frozen=True)
class GateDeclaration:
    """One declared gate, its minimum index tier, and its thresholds.

    ``required`` is modelled even though the schema pins it to ``true``: a
    report copies these declarations verbatim, and a field that exists in the
    document but not in the model would be dropped on the way through.
    """

    id: str
    kind: str
    required: bool
    min_index_tier: str
    thresholds: Mapping[str, float]
    description: str | None = None


@dataclass(frozen=True)
class ConsumerSlice:
    """One consumer's declared case slice and its utility applicability."""

    consumer: str
    utility_applicable: bool
    cases: tuple[str, ...]
    utility_not_applicable_reason: str | None = None


@dataclass(frozen=True)
class EvidenceSpan:
    """A labelled line range that carries the answer. 1-based, inclusive."""

    file_path: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class CaseLabels:
    """The hand labels every measure is computed against.

    All three are present even when empty. An absent label set and an empty one
    are different statements, and only one of them is deliberate.
    """

    expected_files: tuple[str, ...]
    must_touch: tuple[str, ...]
    evidence_spans: tuple[EvidenceSpan, ...]


@dataclass(frozen=True)
class Scope:
    """The read scope a case declares, in the shape ri-12 sends.

    ``read_allow`` may legitimately be empty: that is a fail-closed case
    asserting ``out_of_scope`` / ``no_declared_scope``, not a missing field.
    """

    read_allow: tuple[str, ...]
    deny: tuple[str, ...]


@dataclass(frozen=True)
class Expectation:
    """The exact outcome a fail-closed case asserts (design D12)."""

    status: str
    trigger: str | None = None
    reason: str | None = None
    rendered_hits: int | None = None


@dataclass(frozen=True)
class RecordedResponse:
    """A recorded service response driving a case at index tier ``none``."""

    path: str
    service_state: str | None = None
    adversarial: bool = False


@dataclass(frozen=True)
class ExactSearchBaseline:
    """The archived baseline command, kept for provenance and never executed."""

    ripgrep_baseline: str
    recorded_at_revision: str | None = None


@dataclass(frozen=True)
class Provenance:
    """Where a carried-forward case came from (design D10)."""

    rescued_from: str
    original_case_id: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class Case:
    """One evaluation case, plus the corpus-relative file it was loaded from."""

    case_id: str
    consumer: str
    query: str
    category: str
    scope: Scope
    labels: CaseLabels
    rationale: str
    source_path: str
    expectation: Expectation | None = None
    recorded_response: RecordedResponse | None = None
    exact_search_baseline: ExactSearchBaseline | None = None
    provenance: Provenance | None = None

    @property
    def is_fail_closed(self) -> bool:
        """True when this case asserts an outcome instead of measuring retrieval."""
        return self.expectation is not None


@dataclass(frozen=True)
class Corpus:
    """A loaded, schema-valid, cross-checked corpus and its digest."""

    corpus_id: str
    k: int
    budget: Budget
    consumers: tuple[ConsumerSlice, ...]
    gates: tuple[GateDeclaration, ...]
    cases: tuple[Case, ...]
    digest: str
    root: Path
    description: str | None = None

    def case_by_id(self, case_id: str) -> Case:
        for case in self.cases:
            if case.case_id == case_id:
                return case
        raise KeyError(case_id)

    def slice_for(self, consumer: str) -> ConsumerSlice:
        for slice_ in self.consumers:
            if slice_.consumer == consumer:
                return slice_
        raise KeyError(consumer)

    def cases_for(self, consumer: str) -> tuple[Case, ...]:
        """That consumer's cases, in the order its slice declares them.

        Slice order, not file order: the slice is the declaration, and a
        consumer's results should read in the order its author arranged them.
        """
        return tuple(self.case_by_id(case_id) for case_id in self.slice_for(consumer).cases)


def freeze_thresholds(values: Mapping[str, float]) -> Mapping[str, float]:
    """Return a read-only view of a threshold map."""
    return MappingProxyType(dict(values))
