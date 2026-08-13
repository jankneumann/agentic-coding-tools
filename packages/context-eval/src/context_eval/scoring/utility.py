"""Coding-context utility: three independent conditions, never a blended score.

Acceptance outcome 1 names "context utility" without defining it. Design D7
defines it as three deterministic per-case measures, compared per consumer
against that consumer's own exact-search baseline:

``answer_coverage``
    Fraction of the case's labelled ``must_touch`` files the arm rendered. *Did
    the job get everything it needs?* This is the same measure the relevance gate
    calls ``must_touch_coverage``, and it is deliberately the same *function* —
    two implementations of one measure would eventually disagree and no reader
    would know which number the report meant.

``evidence_density``
    Rendered lines falling inside a labelled evidence span, over all rendered
    lines. *How much of what it got was worth reading?* This is where a
    right-but-bloated section loses, and it is comparable only because both arms
    are rendered under one budget (design D5).

``steps_to_evidence``
    How many files must be opened before the answer appears — the 1-based
    position, in the arm's own file order, of the first file whose rendered
    excerpt intersects labelled evidence. **Censored to ``max_files + 1``** when
    no rendered excerpt ever does. Never ``null``, never absent, never dropped
    from the mean: a null there is a silent skip, and a case that quietly stops
    contributing to its consumer's mean is the shrinking denominator design D3
    forbids. Censoring keeps the failure in the arithmetic, as the worst
    achievable score.

    *Files, not hits.* The report schema says "rendered result", which is looser,
    but the censoring constant it names — ``max_files + 1`` — only makes sense
    against a file position: with ``max_hits`` above ``max_files``, a hit index
    could exceed the value that is supposed to be the worst possible outcome.
    D7's own gloss, "how many files must be opened", agrees.

**Per consumer, all four conditions must hold.** There is no weighted sum, and
rejecting one was explicit: a blended score lets a coverage regression hide
behind a density improvement, which is precisely the trade a reader of this
report must be able to see.

**Do-no-harm is separate and absolute.** Any consumer whose semantic coverage
falls strictly below its own baseline fails with ``consumer_regression``, with no
margin and no offset. ri-12 kept the ``consumer`` field so this evaluation could
say "injection helps debugging and hurts review"; averaging across consumers
would discard exactly that, on the one metric where it matters most.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from ..models import Budget, Case, CaseLabels, ConsumerSlice, EvidenceSpan
from .arms import Arm
from .relevance import ScoringError, must_touch_coverage

PASS = "pass"
FAIL = "fail"

#: Threshold keys the manifest declares for this gate.
COVERAGE_MARGIN = "coverage_margin"
MIN_WINS_PER_CONSUMER = "min_wins_per_consumer"
REQUIRED_THRESHOLDS: tuple[str, ...] = (COVERAGE_MARGIN, MIN_WINS_PER_CONSUMER)

#: From the report contract's closed ``FailReason`` vocabulary.
UTILITY_BELOW_THRESHOLD = "utility_gate_below_threshold"
CONSUMER_REGRESSION = "consumer_regression"
UNMEASURED = "unmeasured"

#: The four named conditions, reported individually so a reader sees which one
#: failed rather than a single number that lost the distinction.
CONDITION_COVERAGE = "coverage_beats_baseline_by_margin"
CONDITION_STEPS = "read_cost_does_not_increase"
CONDITION_DENSITY = "evidence_density_does_not_decrease"
CONDITION_WINS = "wins_outright_somewhere"
CONDITIONS: tuple[str, ...] = (
    CONDITION_COVERAGE,
    CONDITION_STEPS,
    CONDITION_DENSITY,
    CONDITION_WINS,
)

#: One measure, one implementation. ``answer_coverage`` is D7's name for the
#: quantity D6 calls ``must_touch_coverage``; binding the name rather than
#: reimplementing it means the two gates can never quietly diverge.
answer_coverage = must_touch_coverage


def utility_cases(cases: Iterable[Case], slice_: ConsumerSlice) -> tuple[Case, ...]:
    """The cases in *slice_* that utility can actually be computed over.

    A case is a utility case when it makes no fixed-outcome claim and carries
    both labels the measures need. Fail-closed and adversarial cases are excluded
    because their subject is an outcome, not a comparison — and a case with no
    required files or no evidence spans has no defined coverage or density, so
    including it would mean inventing a number for a consumer's mean.
    """
    by_id = {case.case_id: case for case in cases}
    selected = []
    for case_id in slice_.cases:
        case = by_id.get(case_id)
        if case is None:
            raise ScoringError(f"{slice_.consumer} names {case_id}, which has no case")
        if case.expectation is not None:
            continue
        if case.labels.must_touch and case.labels.evidence_spans:
            selected.append(case)
    return tuple(selected)


def evidence_density(arm: Arm, spans: Sequence[EvidenceSpan]) -> float:
    """Rendered lines inside labelled evidence, over all rendered lines.

    An arm that rendered nothing scores ``0.0`` rather than raising or scoring
    ``1.0``: a fallback delivered no evidence, and ``0/0`` interpreted as perfect
    density would make "nothing was injected" the highest-scoring outcome.
    """
    if not spans:
        raise ScoringError("evidence_density needs at least one labelled evidence span")
    total = arm.rendered_lines
    if total == 0:
        return 0.0

    by_file: dict[str, list[EvidenceSpan]] = {}
    for span in spans:
        by_file.setdefault(span.file_path, []).append(span)

    useful = 0
    for hit in arm.hits:
        for line in range(hit.start_line, hit.end_line + 1):
            if any(
                span.start_line <= line <= span.end_line
                for span in by_file.get(hit.file_path, ())
            ):
                useful += 1
    return useful / total


def steps_to_evidence(arm: Arm, spans: Sequence[EvidenceSpan], budget: Budget) -> int:
    """Files opened before the answer appears, censored when it never does."""
    if not spans:
        raise ScoringError("steps_to_evidence needs at least one labelled evidence span")
    censored = budget.max_files + 1

    by_file: dict[str, list[EvidenceSpan]] = {}
    for span in spans:
        by_file.setdefault(span.file_path, []).append(span)

    reached: dict[str, None] = {}
    for hit in arm.hits:
        reached.setdefault(hit.file_path, None)
        if any(
            hit.intersects(span.start_line, span.end_line)
            for span in by_file.get(hit.file_path, ())
        ):
            return min(len(reached), censored)
    return censored


def covers_a_required_file_the_baseline_missed(
    semantic: Arm, baseline: Arm, labels: CaseLabels
) -> bool:
    """A win, measured: some required file the semantic arm rendered and the other did not."""
    rendered = set(semantic.rendered_files)
    missed = set(baseline.rendered_files)
    return any(path in rendered and path not in missed for path in labels.must_touch)


@dataclass(frozen=True)
class CaseUtility:
    """One case's three measures, in both arms."""

    case_id: str
    consumer: str
    semantic_answer_coverage: float
    baseline_answer_coverage: float
    semantic_evidence_density: float
    baseline_evidence_density: float
    semantic_steps_to_evidence: int
    baseline_steps_to_evidence: int
    win_over_baseline: bool


@dataclass(frozen=True)
class ConsumerUtility:
    """One consumer's verdict over its own case slice. Never averaged with another."""

    consumer: str
    utility_applicable: bool
    cases_declared: int
    cases_scored: int
    verdict: str
    fail_reasons: tuple[str, ...] = ()
    metrics: Mapping[str, float] | None = None
    conditions: Mapping[str, bool] | None = None
    utility_not_applicable_reason: str | None = None


@dataclass(frozen=True)
class UtilityGateResult:
    """The coding-context-utility gate, composed with no averaging across consumers."""

    verdict: str
    measured: Mapping[str, float]
    thresholds: Mapping[str, float]
    fail_reasons: tuple[str, ...]
    per_consumer: tuple[ConsumerUtility, ...]


def score_case(case: Case, *, semantic: Arm, baseline: Arm, budget: Budget) -> CaseUtility:
    """Measure one case's utility in both arms, under the one declared budget."""
    labels = case.labels
    return CaseUtility(
        case_id=case.case_id,
        consumer=case.consumer,
        semantic_answer_coverage=answer_coverage(semantic, labels.must_touch),
        baseline_answer_coverage=answer_coverage(baseline, labels.must_touch),
        semantic_evidence_density=evidence_density(semantic, labels.evidence_spans),
        baseline_evidence_density=evidence_density(baseline, labels.evidence_spans),
        semantic_steps_to_evidence=steps_to_evidence(semantic, labels.evidence_spans, budget),
        baseline_steps_to_evidence=steps_to_evidence(baseline, labels.evidence_spans, budget),
        win_over_baseline=covers_a_required_file_the_baseline_missed(semantic, baseline, labels),
    )


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def score_consumer(
    slice_: ConsumerSlice,
    per_case: Sequence[CaseUtility],
    thresholds: Mapping[str, float],
) -> ConsumerUtility:
    """One consumer's four conditions, each evaluated and reported separately."""
    missing = [key for key in REQUIRED_THRESHOLDS if key not in thresholds]
    if missing:
        raise ScoringError(f"the utility gate was given no {missing!r} threshold")

    declared = len(slice_.cases)

    if not slice_.utility_applicable:
        if per_case:
            raise ScoringError(
                f"{slice_.consumer} declares utility_applicable: false but was given "
                f"{len(per_case)} utility cases; a declared exemption cannot also be measured"
            )
        if not slice_.utility_not_applicable_reason:
            raise ScoringError(
                f"{slice_.consumer} declares utility inapplicable without saying why"
            )
        # Visible in the output, and excluded by declaration rather than by
        # absence. It cannot fail this gate, and it cannot vanish from it either.
        return ConsumerUtility(
            consumer=slice_.consumer,
            utility_applicable=False,
            cases_declared=declared,
            cases_scored=0,
            verdict=PASS,
            utility_not_applicable_reason=slice_.utility_not_applicable_reason,
        )

    if not per_case:
        # Applicable and unmeasured is a failure, not a quiet exclusion.
        return ConsumerUtility(
            consumer=slice_.consumer,
            utility_applicable=True,
            cases_declared=declared,
            cases_scored=0,
            verdict=FAIL,
            fail_reasons=(UNMEASURED,),
        )

    coverage_semantic = _mean([entry.semantic_answer_coverage for entry in per_case])
    coverage_baseline = _mean([entry.baseline_answer_coverage for entry in per_case])
    density_semantic = _mean([entry.semantic_evidence_density for entry in per_case])
    density_baseline = _mean([entry.baseline_evidence_density for entry in per_case])
    steps_semantic = _mean([entry.semantic_steps_to_evidence for entry in per_case])
    steps_baseline = _mean([entry.baseline_steps_to_evidence for entry in per_case])
    wins = sum(1 for entry in per_case if entry.win_over_baseline)

    conditions = {
        CONDITION_COVERAGE: coverage_semantic
        >= coverage_baseline + thresholds[COVERAGE_MARGIN],
        CONDITION_STEPS: steps_semantic <= steps_baseline,
        CONDITION_DENSITY: density_semantic >= density_baseline,
        CONDITION_WINS: wins >= thresholds[MIN_WINS_PER_CONSUMER],
    }

    reasons: list[str] = []
    # Absolute, separate, and evaluated on its own: strictly below the baseline
    # is a regression whatever the other three conditions say.
    if coverage_semantic < coverage_baseline:
        reasons.append(CONSUMER_REGRESSION)
    # Every condition must hold. No weighting, no substitution, no offsetting.
    if not all(conditions.values()):
        reasons.append(UTILITY_BELOW_THRESHOLD)

    ordered = tuple(dict.fromkeys(reasons))
    return ConsumerUtility(
        consumer=slice_.consumer,
        utility_applicable=True,
        cases_declared=declared,
        cases_scored=len(per_case),
        verdict=FAIL if ordered else PASS,
        fail_reasons=ordered,
        metrics={
            "answer_coverage_semantic": coverage_semantic,
            "answer_coverage_baseline": coverage_baseline,
            "evidence_density_semantic": density_semantic,
            "evidence_density_baseline": density_baseline,
            "steps_to_evidence_semantic": steps_semantic,
            "steps_to_evidence_baseline": steps_baseline,
            "wins_over_baseline": wins,
        },
        conditions=conditions,
    )


def score_utility(
    per_consumer: Sequence[ConsumerUtility], thresholds: Mapping[str, float]
) -> UtilityGateResult:
    """Compose the gate. One failing consumer fails it; nothing offsets anything.

    Deliberately not a mean over consumers, not a pass rate over consumers, and
    not a count of how many passed. Any of those would let a strong consumer buy
    a weak one's regression, which is the one comparison this evaluation exists
    to keep visible.
    """
    missing = [key for key in REQUIRED_THRESHOLDS if key not in thresholds]
    if missing:
        raise ScoringError(f"the utility gate was given no {missing!r} threshold")
    if not per_consumer:
        raise ScoringError("the utility gate scored no consumers; a vacuous pass is unwritable")

    failing = [entry for entry in per_consumer if entry.verdict == FAIL]
    applicable = [entry for entry in per_consumer if entry.utility_applicable]
    if not applicable:
        raise ScoringError("no consumer declares utility applicable; nothing would be measured")

    reasons = tuple(
        dict.fromkeys(reason for entry in failing for reason in entry.fail_reasons)
    )
    measured: dict[str, float] = {
        "consumers_declared": len(per_consumer),
        "consumers_measured": len(applicable),
        "consumers_failing": len(failing),
        "cases_scored": sum(entry.cases_scored for entry in per_consumer),
    }
    return UtilityGateResult(
        verdict=FAIL if failing else PASS,
        measured=measured,
        thresholds=dict(thresholds),
        fail_reasons=reasons,
        per_consumer=tuple(per_consumer),
    )
