"""Compose one verdict from scored cases and declared gates. Nothing else.

Read :func:`compose_verdict`'s signature first, because the signature *is* the
design (D15). It takes the corpus — the declaration of what was supposed to be
measured — the cases the run actually produced, and the conditions the
measurement was taken under. There is **no judge parameter**, and no type
reachable from that signature has a field for one. ``agent-scenarios`` states
the rule as "the judge never overrides the deterministic verdict", which is a
promise a later edit can break silently; here letting a qualitative review
affect an outcome requires changing a function signature, which is a reviewable
diff. The advisory block is attached to the report by the emitter *after* this
function has returned.

Four things this module refuses to do, each because the archived evaluation or
the runner design D2 rejected did it:

**The denominator is declared.** ``cases_declared`` comes from the corpus
manifest and ``cases_scored`` from the run. A case that raised, timed out, or
found no index stays in the results with ``scored=False`` and a reason; it does
not shrink the denominator. gen-eval drops an invalid scenario, a malformed
file, a gather-exception and an exhausted budget out of ``verdicts`` without
lowering ``pass_rate`` — a gate whose thesis is "could not measure is a FAIL"
cannot be built on that, and it must not reproduce it either.

**The gate list is declared, not discovered.** Every gate the manifest names
must produce a result. One that does not is :data:`MISSING_REQUIRED_GATE`, named
in the report. ``fail_closed_regression`` was declared required by phase 2 with
no task assigning its composition; that omission was fail-closed rather than
fail-open precisely because of this rule, which is why it could have survived to
the measurement phase and been misread there as a measured failure.

**There is no waiver.** Not a parameter, not a field, not an environment
variable. An operator who believes a threshold is wrong edits the corpus
manifest, which moves the corpus digest and invalidates every existing report.

**A precondition failure is not a measurement.** An index tier below what a gate
declares, a code-search service that was disabled while a retrieval measurement
was taken, and a degraded scope adapter each fail their gate whatever the
numbers say. The numbers in those states describe something other than what the
gate claims to measure.

No threshold value appears in this module. Every bound arrives from
``corpus/manifest.yaml`` as data, and
``test_thresholds_are_not_readable_from_the_scoring_modules`` fails if one is
written here as a literal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .models import Case, Corpus, GateDeclaration
from .scoring import relevance, scope, utility
from .scoring.arms import Arm
from .scoring.relevance import ScoringError
from .scoring.utility import ConsumerUtility

PASS = "pass"
FAIL = "fail"

#: The report contract's closed ``FailReason`` vocabulary, in the order a report
#: lists them. Mirrored rather than read from the schema at import time so this
#: module has no I/O; ``test_verdict_failclosed`` cross-checks the two, so
#: widening one without the other fails.
UNMEASURED = "unmeasured"
RETRIEVAL_GATE_BELOW_THRESHOLD = "retrieval_gate_below_threshold"
UTILITY_GATE_BELOW_THRESHOLD = "utility_gate_below_threshold"
CONSUMER_REGRESSION = "consumer_regression"
SCOPE_VIOLATION = "scope_violation"
DENOMINATOR_MISMATCH = "denominator_mismatch"
MISSING_REQUIRED_GATE = "missing_required_gate"
INDEX_TIER_INSUFFICIENT = "index_tier_insufficient"
CORPUS_DIGEST_MISMATCH = "corpus_digest_mismatch"
REVISION_MISMATCH = "revision_mismatch"
SERVICE_DISABLED_DURING_MEASUREMENT = "service_disabled_during_measurement"
APPARATUS_FAILURE = "apparatus_failure"

FAIL_REASONS: tuple[str, ...] = (
    UNMEASURED,
    RETRIEVAL_GATE_BELOW_THRESHOLD,
    UTILITY_GATE_BELOW_THRESHOLD,
    CONSUMER_REGRESSION,
    SCOPE_VIOLATION,
    DENOMINATOR_MISMATCH,
    MISSING_REQUIRED_GATE,
    INDEX_TIER_INSUFFICIENT,
    CORPUS_DIGEST_MISMATCH,
    REVISION_MISMATCH,
    SERVICE_DISABLED_DURING_MEASUREMENT,
    APPARATUS_FAILURE,
)

#: The five values ``CaseResult.unscored_reason`` may take. Every one of them is
#: a failure — none is a skip, an exclusion, or a not-applicable.
UNSCORED_REASONS: tuple[str, ...] = (
    "apparatus_failure",
    "invalid_document",
    "no_index_at_revision",
    "producer_error",
    "timeout",
)

#: The three index tiers, weakest first. Comparison is by position: a gate
#: declaring ``live`` and receiving ``seeded`` or ``none`` fails (design D9).
INDEX_TIERS: tuple[str, ...] = ("none", "seeded", "live")

#: The tier at which a measurement needed the code-search service to answer. A
#: gate declaring it is the gate a disabled service invalidates (design D17).
LIVE_TIER = "live"

RESOLVED = "resolved"
DEGRADED = "degraded"

#: The four measurement families the report contract knows.
RETRIEVAL_QUALITY = "retrieval_quality"
CODING_CONTEXT_UTILITY = "coding_context_utility"
SCOPE_COMPLIANCE = "scope_compliance"
FAIL_CLOSED_REGRESSION = "fail_closed_regression"

#: Threshold key the fail-closed gate is judged against, from the manifest.
MIN_EXPECTATION_MATCH_RATE = "min_expectation_match_rate"


class CompositionError(ValueError):
    """The composer was given inputs it cannot interpret as a run."""


# ---------------------------------------------------------------------------
# what a run hands the composer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseOutcome:
    """One declared case's outcome, scored or not.

    An unscored case is still an outcome. It carries a reason from
    :data:`UNSCORED_REASONS` and no arms, exactly as the report contract
    requires, and it keeps its place in the denominator.
    """

    case_id: str
    consumer: str
    scored: bool
    unscored_reason: str | None = None
    semantic: Arm | None = None
    baseline: Arm | None = None
    naive_phrase: Arm | None = None
    #: The outbound request body ri-12 built, when this case reached the wire.
    #: ``None`` is a fact about the case — an empty declared scope short-circuits
    #: before any request — not a missing measurement.
    request_body: Mapping[str, Any] | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.scored:
            if self.unscored_reason is not None:
                raise CompositionError(f"{self.case_id} is scored and carries an unscored reason")
            if self.semantic is None or self.baseline is None:
                raise CompositionError(
                    f"{self.case_id} is scored without both arms; a semantic result with no "
                    "baseline is not a comparison"
                )
        else:
            if self.unscored_reason not in UNSCORED_REASONS:
                raise CompositionError(
                    f"{self.case_id} is unscored and must name one of {UNSCORED_REASONS!r}, "
                    f"got {self.unscored_reason!r}"
                )
            if self.semantic is not None or self.baseline is not None:
                raise CompositionError(f"{self.case_id} is unscored and cannot carry arms")


@dataclass(frozen=True)
class MeasurementContext:
    """The conditions in force while the run was taken.

    Recorded rather than assumed, and each field is a clause the composer
    evaluates: a measurement taken in the wrong state measured something other
    than what it claims.
    """

    index_tier: str
    code_search_enabled: bool
    semantic_context_injection: bool
    coordination_transport: str
    scope_adapter: str

    def __post_init__(self) -> None:
        if self.index_tier not in INDEX_TIERS:
            raise CompositionError(f"index_tier must be one of {INDEX_TIERS!r}")
        if self.scope_adapter not in (RESOLVED, DEGRADED):
            raise CompositionError("scope_adapter must be resolved or degraded")

    def satisfies(self, min_index_tier: str) -> bool:
        if min_index_tier not in INDEX_TIERS:
            raise CompositionError(f"unknown declared tier {min_index_tier!r}")
        return INDEX_TIERS.index(self.index_tier) >= INDEX_TIERS.index(min_index_tier)


# ---------------------------------------------------------------------------
# what the composer produces
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateOutcome:
    """One gate's result, carrying the threshold it was judged against."""

    id: str
    kind: str
    required: bool
    min_index_tier: str
    verdict: str
    thresholds: Mapping[str, float]
    measured: Mapping[str, float]
    fail_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComposedVerdict:
    """The composed outcome and everything the report needs to record it."""

    verdict: str
    fail_reasons: tuple[str, ...]
    gates: tuple[GateOutcome, ...]
    per_consumer: tuple[ConsumerUtility, ...]
    cases: tuple[CaseOutcome, ...]
    cases_declared: int
    cases_scored: int
    missing_gates: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------


def compose_verdict(
    corpus: Corpus,
    cases: Sequence[CaseOutcome],
    measurement: MeasurementContext,
) -> ComposedVerdict:
    """Compose the run's single verdict.

    Args:
        corpus: The declaration — every case, every gate, every threshold, every
            consumer slice. This is the denominator's only source.
        cases: What the run produced, one entry per declared case including the
            ones it could not measure.
        measurement: The index tier, service state and adapter state the run was
            taken under.

    Returns:
        A :class:`ComposedVerdict` whose ``verdict`` is ``pass`` only if every
        declared case was scored, every declared gate produced a passing result,
        and every precondition held.

    Note:
        There is deliberately no judge, review, or advisory parameter, and
        adding one would be a signature change (design D15).
    """
    reasons: list[str] = []

    declared_ids = tuple(case.case_id for case in corpus.cases)
    outcomes = _aligned(declared_ids, cases, reasons)
    scored = {outcome.case_id: outcome for outcome in outcomes if outcome.scored}

    if len(scored) != len(declared_ids):
        # Every declared case that was not scored, for any reason. The run fails
        # and the surviving cases do not become the denominator.
        reasons.append(UNMEASURED)
        reasons.append(DENOMINATOR_MISMATCH)

    if measurement.scope_adapter == DEGRADED:
        reasons.append(APPARATUS_FAILURE)

    per_consumer = _score_consumers(corpus, scored)
    composed: list[GateOutcome] = []
    missing: list[str] = []

    for declaration in corpus.gates:
        outcome = _compose_gate(declaration, corpus, scored, per_consumer, measurement)
        if outcome is None:
            missing.append(declaration.id)
            continue
        composed.append(outcome)
        reasons.extend(outcome.fail_reasons)

    if missing:
        reasons.append(MISSING_REQUIRED_GATE)

    ordered = _ordered_reasons(reasons)
    return ComposedVerdict(
        verdict=FAIL if ordered else PASS,
        fail_reasons=ordered,
        gates=tuple(composed),
        per_consumer=per_consumer,
        cases=tuple(outcomes),
        cases_declared=len(declared_ids),
        cases_scored=len(scored),
        missing_gates=tuple(missing),
    )


def _aligned(
    declared_ids: Sequence[str],
    cases: Sequence[CaseOutcome],
    reasons: list[str],
) -> tuple[CaseOutcome, ...]:
    """Line the run up against the declaration, in declared order.

    A declared case absent from the run and a run entry the corpus never
    declared are both ``denominator_mismatch``. The second matters as much as
    the first: dropping one declared case and adding one undeclared one leaves
    the counts equal, which is exactly how a derived denominator hides a
    substitution.
    """
    by_id: dict[str, CaseOutcome] = {}
    for outcome in cases:
        if outcome.case_id in by_id:
            raise CompositionError(f"{outcome.case_id} appears twice in the run")
        by_id[outcome.case_id] = outcome

    declared = tuple(declared_ids)
    aligned = [by_id[case_id] for case_id in declared if case_id in by_id]

    undeclared = [outcome.case_id for outcome in cases if outcome.case_id not in set(declared)]
    if len(aligned) != len(declared) or undeclared:
        reasons.append(DENOMINATOR_MISMATCH)
    return tuple(aligned)


def _score_consumers(
    corpus: Corpus, scored: Mapping[str, CaseOutcome]
) -> tuple[ConsumerUtility, ...]:
    """Every declared consumer's utility verdict, over its own case slice.

    Never averaged, never aggregated. ri-12 kept the ``consumer`` field so this
    evaluation could say "injection helps debugging and hurts review", and a mean
    would discard exactly that.
    """
    results: list[ConsumerUtility] = []
    for slice_ in corpus.consumers:
        per_case = [
            utility.score_case(
                case,
                semantic=_arm(scored[case.case_id].semantic),
                baseline=_arm(scored[case.case_id].baseline),
                budget=corpus.budget,
            )
            for case in utility.utility_cases(corpus.cases, slice_)
            if case.case_id in scored
        ]
        results.append(utility.score_consumer(slice_, per_case, _utility_thresholds(corpus)))
    return tuple(results)


def _utility_thresholds(corpus: Corpus) -> Mapping[str, float]:
    for declaration in corpus.gates:
        if declaration.kind == CODING_CONTEXT_UTILITY:
            return declaration.thresholds
    raise CompositionError("the corpus declares no coding-context-utility gate")


def _arm(value: Arm | None) -> Arm:
    if value is None:  # pragma: no cover - CaseOutcome forbids this for a scored case
        raise CompositionError("a scored case must carry both arms")
    return value


# ---------------------------------------------------------------------------
# one gate
# ---------------------------------------------------------------------------


def _compose_gate(
    declaration: GateDeclaration,
    corpus: Corpus,
    scored: Mapping[str, CaseOutcome],
    per_consumer: Sequence[ConsumerUtility],
    measurement: MeasurementContext,
) -> GateOutcome | None:
    """Compose one declared gate, or return ``None`` when nothing can compose it.

    ``None`` becomes ``missing_required_gate``. That is the fail-closed answer to
    a gate the manifest declares and no scorer implements — including a gate
    somebody stopped composing.
    """
    builder = _BUILDERS.get(declaration.kind)
    if builder is None:
        return None

    try:
        verdict, thresholds, measured, reasons = builder(
            declaration, corpus, scored, per_consumer
        )
    except ScoringError:
        # A gate that could not be measured is a failing gate with no numbers,
        # never an absent one and never a pass.
        verdict, thresholds, measured, reasons = (
            FAIL,
            dict(declaration.thresholds),
            {},
            [UNMEASURED],
        )

    # Preconditions, applied after the numbers exist so the report still shows
    # what was measured while stating that the measurement does not count.
    if not measurement.satisfies(declaration.min_index_tier):
        reasons.append(INDEX_TIER_INSUFFICIENT)
    if declaration.min_index_tier == LIVE_TIER and not measurement.code_search_enabled:
        reasons.append(SERVICE_DISABLED_DURING_MEASUREMENT)

    ordered = _ordered_reasons(reasons)
    return GateOutcome(
        id=declaration.id,
        kind=declaration.kind,
        required=declaration.required,
        min_index_tier=declaration.min_index_tier,
        verdict=FAIL if ordered else verdict,
        thresholds=dict(thresholds),
        measured=dict(measured),
        fail_reasons=ordered,
    )


_GateComposition = tuple[str, Mapping[str, float], Mapping[str, float], list[str]]


def _retrieval_gate(
    declaration: GateDeclaration,
    corpus: Corpus,
    scored: Mapping[str, CaseOutcome],
    per_consumer: Sequence[ConsumerUtility],
) -> _GateComposition:
    del per_consumer
    per_case = [
        relevance.score_case(
            case,
            semantic=_arm(scored[case.case_id].semantic),
            baseline=_arm(scored[case.case_id].baseline),
            k=corpus.k,
        )
        for case in relevance.retrieval_cases(corpus.cases)
        if case.case_id in scored
    ]
    result = relevance.score_relevance(per_case, declaration.thresholds)
    return (result.verdict, result.thresholds, result.measured, list(result.fail_reasons))


def _utility_gate(
    declaration: GateDeclaration,
    corpus: Corpus,
    scored: Mapping[str, CaseOutcome],
    per_consumer: Sequence[ConsumerUtility],
) -> _GateComposition:
    del corpus, scored
    result = utility.score_utility(per_consumer, declaration.thresholds)
    return (result.verdict, result.thresholds, result.measured, list(result.fail_reasons))


def _scope_gate(
    declaration: GateDeclaration,
    corpus: Corpus,
    scored: Mapping[str, CaseOutcome],
    per_consumer: Sequence[ConsumerUtility],
) -> _GateComposition:
    del per_consumer
    per_case = [
        scope.score_case(
            case,
            _arm(scored[case.case_id].semantic),
            request_body=scored[case.case_id].request_body,
        )
        for case in corpus.cases
        if case.case_id in scored
    ]
    # The adapter state is a property of the run, and the scope scorer fails the
    # gate on `degraded` before considering any number. It is passed as resolved
    # here only because `compose_verdict` has already recorded the degraded case
    # as an apparatus failure of the whole run — a stricter statement than
    # failing one gate.
    result = scope.score_scope(per_case, declaration.thresholds, scope_adapter=RESOLVED)
    return (result.verdict, result.thresholds, result.measured, list(result.fail_reasons))


def _fail_closed_gate(
    declaration: GateDeclaration,
    corpus: Corpus,
    scored: Mapping[str, CaseOutcome],
    per_consumer: Sequence[ConsumerUtility],
) -> _GateComposition:
    """Every fail-closed case honoured the exact outcome it declared.

    Composed from phase 3's :func:`scope.expectation_honored` rather than from a
    second predicate. The alternative — a fresh implementation of "did the
    fallback match" — would eventually disagree with the scope gate's version of
    the same question, and no reader would know which one the report meant.
    """
    del per_consumer
    honored: list[bool] = []
    for case in _expectation_cases(corpus.cases):
        outcome = scored.get(case.case_id)
        if outcome is None:
            continue
        matched = scope.expectation_honored(case, _arm(outcome.semantic))
        if matched is not None:
            honored.append(matched)

    if not honored:
        raise ScoringError("the fail-closed gate scored no cases; a vacuous pass is unwritable")

    matches = sum(1 for value in honored if value)
    rate = matches / len(honored)
    measured: dict[str, float] = {
        "expectation_match_rate": rate,
        "expectations_honored": matches,
        "cases_scored": len(honored),
    }
    if MIN_EXPECTATION_MATCH_RATE not in declaration.thresholds:
        raise ScoringError(
            f"the fail-closed gate was given no {MIN_EXPECTATION_MATCH_RATE!r} threshold"
        )
    failed = rate < declaration.thresholds[MIN_EXPECTATION_MATCH_RATE]
    return (
        FAIL if failed else PASS,
        declaration.thresholds,
        measured,
        [UNMEASURED] if failed else [],
    )


def _expectation_cases(cases: Sequence[Case]) -> tuple[Case, ...]:
    """The cases that assert an outcome rather than measure a comparison."""
    return tuple(case for case in cases if case.expectation is not None)


#: Gate kind -> composition. Keyed by kind rather than by id so a corpus that
#: renames a gate still composes it, and a corpus that declares a kind no scorer
#: implements gets ``missing_required_gate`` instead of silence.
_BUILDERS: Mapping[str, Any] = {
    RETRIEVAL_QUALITY: _retrieval_gate,
    CODING_CONTEXT_UTILITY: _utility_gate,
    SCOPE_COMPLIANCE: _scope_gate,
    FAIL_CLOSED_REGRESSION: _fail_closed_gate,
}


def _ordered_reasons(reasons: Sequence[str]) -> tuple[str, ...]:
    """Deduplicate and order by the contract's vocabulary, never by arrival.

    Two runs that failed for the same reasons must produce the same list, or a
    report diff would show noise where there was no change (design D16).
    """
    unknown = [reason for reason in reasons if reason not in FAIL_REASONS]
    if unknown:
        raise CompositionError(f"fail reasons outside the closed vocabulary: {sorted(unknown)}")
    present = set(reasons)
    return tuple(reason for reason in FAIL_REASONS if reason in present)
