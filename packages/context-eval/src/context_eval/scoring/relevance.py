"""Retrieval relevance: top-k hit rate, required-file coverage, measured wins.

Three measures, all against hand labels, and the distinctions between them are
the point (design D6).

``hit_at_k`` is the archived definition, preserved byte-for-byte in meaning so
the ten rescued cases stay comparable with the numbers they were originally
measured under: *any* labelled ``expected_files`` entry appearing in the arm's
top-k file list. ``must_touch_coverage`` is strictly stronger — a task that
needs three files is not answered by finding one — and the spec requires both to
exist precisely so that "found something relevant" cannot be reported as "got
what it needed".

``wins_over_baseline`` is **measured, never labelled.** The archived evaluation
defined this clause twice and differently: ``run_eval.py:161`` computed it from
baseline misses observed in that run, while ``eval-set.yaml``'s header described
it as ``category=semantic-win``, a hand-applied label. Under the label
definition a corpus author manufactures wins by relabelling, with no measurement
involved. The spec text — *"tasks the ripgrep baseline misses"* — agrees with
the code, and the manifest names the threshold ``min_measured_wins_over_baseline``
to settle it.

So this module never reads a case's ``category``. Not "reads it and ignores it":
the field does not appear here at all, and ``test_relevance_scorer.py`` fails if
it ever does. A label that no scoring path can see cannot become a verdict by
accident.

Every bound arrives from ``corpus/manifest.yaml``. A threshold key this module
expects and does not receive is an error, never a default — a gate judged
against nothing passes everything.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from ..models import Case
from .arms import Arm

PASS = "pass"
FAIL = "fail"

#: Threshold keys this gate requires from the manifest.
MIN_HIT_AT_K_COUNT = "min_hit_at_k_count"
MIN_MEASURED_WINS = "min_measured_wins_over_baseline"
REQUIRED_THRESHOLDS: tuple[str, ...] = (MIN_HIT_AT_K_COUNT, MIN_MEASURED_WINS)

#: From the report contract's closed ``FailReason`` vocabulary.
RETRIEVAL_BELOW_THRESHOLD = "retrieval_gate_below_threshold"


class ScoringError(ValueError):
    """The measurement is not well defined for the inputs it was given."""


@dataclass(frozen=True)
class CaseRelevance:
    """One case's relevance measurements, for both arms."""

    case_id: str
    consumer: str
    semantic_hit_at_k: bool
    baseline_hit_at_k: bool
    semantic_must_touch_coverage: float
    baseline_must_touch_coverage: float

    @property
    def measured_win_over_baseline(self) -> bool:
        """The semantic arm hit and the baseline arm, in THIS run, did not."""
        return self.semantic_hit_at_k and not self.baseline_hit_at_k


@dataclass(frozen=True)
class RelevanceGateResult:
    """The retrieval-quality gate's outcome, self-describing per the contract."""

    verdict: str
    measured: Mapping[str, float]
    thresholds: Mapping[str, float]
    fail_reasons: tuple[str, ...]
    per_case: tuple[CaseRelevance, ...]


def retrieval_cases(cases: Iterable[Case]) -> tuple[Case, ...]:
    """The cases whose job is to measure retrieval, in corpus order.

    A case carrying an ``expectation`` block is asserting a specific outcome —
    a fail-closed fallback, or an adversarial response's scope handling. Those
    are scored by their own gates. Selecting on the presence of that block
    rather than on an id prefix means a new measurement case is included the day
    it is added, with nothing to remember.
    """
    return tuple(case for case in cases if case.expectation is None)


def hit_at_k(arm: Arm, expected_files: Sequence[str], k: int) -> bool:
    """Does any labelled expected file appear in this arm's top-k file list?

    Computed over what the arm actually *rendered*, for both arms, which is only
    a fair comparison because both were rendered under one budget (design D5).
    """
    if not expected_files:
        raise ScoringError("hit_at_k needs at least one labelled expected file")
    top = set(arm.top_k_files(k))
    return any(path in top for path in expected_files)


def must_touch_coverage(arm: Arm, must_touch: Sequence[str]) -> float:
    """Fraction of the labelled required files this arm rendered.

    An empty ``must_touch`` is an error rather than ``0.0`` or ``1.0``. Both of
    those are defensible readings of "no required files", which is exactly why
    neither may be chosen silently: a case with nothing required is not a
    coverage case, and letting it score would put a meaningless number into a
    consumer's mean.
    """
    if not must_touch:
        raise ScoringError("must_touch_coverage needs at least one labelled required file")
    rendered = set(arm.rendered_files)
    covered = sum(1 for path in must_touch if path in rendered)
    return covered / len(must_touch)


def score_case(case: Case, *, semantic: Arm, baseline: Arm, k: int) -> CaseRelevance:
    """Measure one case in both arms.

    Note what is *not* read: ``case.category``. See this module's docstring.
    """
    return CaseRelevance(
        case_id=case.case_id,
        consumer=case.consumer,
        semantic_hit_at_k=hit_at_k(semantic, case.labels.expected_files, k),
        baseline_hit_at_k=hit_at_k(baseline, case.labels.expected_files, k),
        semantic_must_touch_coverage=must_touch_coverage(semantic, case.labels.must_touch),
        baseline_must_touch_coverage=must_touch_coverage(baseline, case.labels.must_touch),
    )


def score_relevance(
    per_case: Sequence[CaseRelevance], thresholds: Mapping[str, float]
) -> RelevanceGateResult:
    """Compose the retrieval-quality gate from per-case measurements."""
    missing = [key for key in REQUIRED_THRESHOLDS if key not in thresholds]
    if missing:
        raise ScoringError(f"the retrieval gate was given no {missing!r} threshold")
    if not per_case:
        raise ScoringError("the retrieval gate scored no cases; a vacuous pass is unwritable")

    hits = sum(1 for entry in per_case if entry.semantic_hit_at_k)
    baseline_hits = sum(1 for entry in per_case if entry.baseline_hit_at_k)
    wins = sum(1 for entry in per_case if entry.measured_win_over_baseline)
    total = len(per_case)

    measured: dict[str, float] = {
        "hit_at_k_count": hits,
        "hit_at_k_rate": hits / total,
        "baseline_hit_at_k_count": baseline_hits,
        "measured_wins_over_baseline": wins,
        "cases_scored": total,
    }

    failed = hits < thresholds[MIN_HIT_AT_K_COUNT] or wins < thresholds[MIN_MEASURED_WINS]
    return RelevanceGateResult(
        verdict=FAIL if failed else PASS,
        measured=measured,
        thresholds=dict(thresholds),
        fail_reasons=(RETRIEVAL_BELOW_THRESHOLD,) if failed else (),
        per_case=tuple(per_case),
    )
