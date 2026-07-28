"""Coding-context utility: the three measures and the two rules about combining them.

The measures are arithmetic and are pinned against hand-computed values. What
these tests actually defend is the *combination*, because that is where a
utility gate normally dies:

* **No blend.** A consumer whose coverage regressed while its density improved
  must fail. Under any weighted sum it can be made to pass by choosing weights,
  and nobody reviewing the report would see the trade that was made.
* **No offset across consumers.** One consumer regressing fails the composed
  gate even when every other consumer improved. ri-12 kept the ``consumer`` field
  precisely so this evaluation could say "helps debugging, hurts review".
* **No null.** ``steps_to_evidence`` is censored to ``max_files + 1`` when the
  answer never appears. A ``None`` there would drop the case from its consumer's
  mean and turn the worst possible outcome into no outcome at all.
* **No silent exemption.** ``quick-task`` declares ``utility_applicable: false``,
  and it must still be present in the output carrying that declaration and its
  reason. A consumer that vanishes is indistinguishable from one nobody noticed.

Thresholds come from ``corpus/manifest.yaml``. The margin is read, never typed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"

if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))

from context_eval.loader import load_corpus  # noqa: E402
from context_eval.models import (  # noqa: E402
    Budget,
    Case,
    CaseLabels,
    ConsumerSlice,
    EvidenceSpan,
    Scope,
)
from context_eval.scoring import utility  # noqa: E402
from context_eval.scoring.arms import Arm, RenderedHit, fallback_arm  # noqa: E402
from context_eval.scoring.relevance import ScoringError  # noqa: E402


def _corpus():
    return load_corpus(PACKAGE_ROOT / "corpus")


def _budget() -> Budget:
    return _corpus().budget


def _utility_thresholds():
    gate = next(g for g in _corpus().gates if g.kind == "coding_context_utility")
    return gate.thresholds


def _arm(*spans: tuple[str, int, int], name: str = "semantic") -> Arm:
    return Arm(
        arm=name,
        status="injected",
        hits=tuple(RenderedHit(path, start, end) for path, start, end in spans),
    )


def _case(
    *,
    case_id: str = "U1",
    consumer: str = "implement-feature",
    must_touch: tuple[str, ...] = ("a.py",),
    spans: tuple[EvidenceSpan, ...] = (EvidenceSpan("a.py", 10, 19),),
) -> Case:
    return Case(
        case_id=case_id,
        consumer=consumer,
        query="anything",
        category="control",
        scope=Scope(read_allow=("**",), deny=()),
        labels=CaseLabels(expected_files=must_touch, must_touch=must_touch, evidence_spans=spans),
        rationale="fixture",
        source_path=f"cases/{case_id}.yaml",
    )


def _measured(
    *,
    case_id: str = "U1",
    consumer: str = "implement-feature",
    coverage: tuple[float, float],
    density: tuple[float, float] = (1.0, 1.0),
    steps: tuple[int, int] = (1, 1),
    win: bool = True,
) -> utility.CaseUtility:
    """A per-case result built directly, so consumer composition is tested alone."""
    return utility.CaseUtility(
        case_id=case_id,
        consumer=consumer,
        semantic_answer_coverage=coverage[0],
        baseline_answer_coverage=coverage[1],
        semantic_evidence_density=density[0],
        baseline_evidence_density=density[1],
        semantic_steps_to_evidence=steps[0],
        baseline_steps_to_evidence=steps[1],
        win_over_baseline=win,
    )


def _slice(consumer: str = "implement-feature", cases: tuple[str, ...] = ("U1",)) -> ConsumerSlice:
    return ConsumerSlice(consumer=consumer, utility_applicable=True, cases=cases)


# --------------------------------------------------------------------------
# answer coverage is the relevance gate's measure, not a second implementation
# --------------------------------------------------------------------------


def test_answer_coverage_is_the_same_function_as_must_touch_coverage() -> None:
    from context_eval.scoring.relevance import must_touch_coverage

    assert utility.answer_coverage is must_touch_coverage


# --------------------------------------------------------------------------
# evidence density
# --------------------------------------------------------------------------


def test_density_counts_only_rendered_lines_inside_a_labelled_span() -> None:
    """Ten rendered lines, five of them inside the span, in the same file."""
    arm = _arm(("a.py", 6, 15))
    spans = (EvidenceSpan("a.py", 11, 20),)
    assert arm.rendered_lines == 10
    assert utility.evidence_density(arm, spans) == 0.5


def test_a_span_in_another_file_does_not_count() -> None:
    arm = _arm(("b.py", 11, 20))
    assert utility.evidence_density(arm, (EvidenceSpan("a.py", 11, 20),)) == 0.0


def test_padding_an_excerpt_lowers_density() -> None:
    """Why the producer emits tight spans: a bloated section is a worse section."""
    tight = _arm(("a.py", 10, 19))
    padded = _arm(("a.py", 10, 29))
    spans = (EvidenceSpan("a.py", 10, 19),)
    assert utility.evidence_density(tight, spans) == 1.0
    assert utility.evidence_density(padded, spans) == 0.5


def test_a_fallback_arm_has_zero_density_not_perfect_density() -> None:
    """``0/0`` read as 1.0 would make "nothing was injected" the best outcome."""
    arm = fallback_arm("semantic", "stale", "revision_not_indexed")
    assert utility.evidence_density(arm, (EvidenceSpan("a.py", 1, 2),)) == 0.0


def test_density_refuses_a_case_with_no_labelled_evidence() -> None:
    with pytest.raises(ScoringError):
        utility.evidence_density(_arm(("a.py", 1, 2)), ())


# --------------------------------------------------------------------------
# steps to evidence: censored, never null
# --------------------------------------------------------------------------


def test_steps_counts_files_opened_before_the_answer_appears() -> None:
    arm = _arm(("x.py", 1, 4), ("y.py", 1, 4), ("a.py", 10, 14))
    spans = (EvidenceSpan("a.py", 12, 20),)
    assert utility.steps_to_evidence(arm, spans, _budget()) == 3


def test_the_first_file_scores_one() -> None:
    arm = _arm(("a.py", 10, 14), ("x.py", 1, 4))
    assert utility.steps_to_evidence(arm, (EvidenceSpan("a.py", 12, 20),), _budget()) == 1


def test_two_excerpts_from_one_file_are_one_step() -> None:
    """The measure is files opened, so a second excerpt from an open file is free."""
    arm = _arm(("a.py", 1, 4), ("a.py", 10, 14))
    assert utility.steps_to_evidence(arm, (EvidenceSpan("a.py", 12, 20),), _budget()) == 1


def test_missing_evidence_is_censored_to_max_files_plus_one() -> None:
    """The spec scenario: never absent, never null, never out of the mean."""
    budget = _budget()
    arm = _arm(("x.py", 1, 4), ("y.py", 1, 4))
    value = utility.steps_to_evidence(arm, (EvidenceSpan("a.py", 12, 20),), budget)
    assert value == budget.max_files + 1
    assert value is not None


def test_a_fallback_arm_is_censored_rather_than_excluded() -> None:
    budget = _budget()
    arm = fallback_arm("semantic", "out_of_scope", "no_declared_scope")
    assert utility.steps_to_evidence(arm, (EvidenceSpan("a.py", 1, 2),), budget) == (
        budget.max_files + 1
    )


def test_the_censored_value_is_worse_than_any_measurable_value() -> None:
    """Otherwise a failure to find the answer could beat finding it late."""
    budget = _budget()
    reachable = _arm(*[(f"f{n}.py", 1, 4) for n in range(budget.max_files)])
    found = _arm(
        *[(f"f{n}.py", 1, 4) for n in range(budget.max_files - 1)], ("a.py", 10, 14)
    )
    spans = (EvidenceSpan("a.py", 12, 20),)
    censored = utility.steps_to_evidence(reachable, spans, budget)
    worst_measured = utility.steps_to_evidence(found, spans, budget)
    assert worst_measured < censored


def test_the_censored_value_still_enters_the_mean() -> None:
    """A censored case must weigh on its consumer, not disappear from it."""
    budget = _budget()
    thresholds = _utility_thresholds()
    good = _measured(case_id="A", coverage=(1.0, 0.0), steps=(1, 1))
    censored = _measured(
        case_id="B", coverage=(1.0, 0.0), steps=(budget.max_files + 1, 1)
    )
    result = utility.score_consumer(_slice(cases=("A", "B")), [good, censored], thresholds)
    assert result.metrics is not None
    assert result.metrics["steps_to_evidence_semantic"] > 1
    assert result.conditions is not None
    assert result.conditions[utility.CONDITION_STEPS] is False


def test_steps_refuses_a_case_with_no_labelled_evidence() -> None:
    with pytest.raises(ScoringError):
        utility.steps_to_evidence(_arm(("a.py", 1, 2)), (), _budget())


# --------------------------------------------------------------------------
# wins are measured against the baseline's own rendered set
# --------------------------------------------------------------------------


def test_a_win_needs_a_required_file_the_baseline_did_not_render() -> None:
    case = _case(must_touch=("a.py", "b.py"))
    semantic = _arm(("a.py", 1, 4), ("b.py", 1, 4))
    baseline = _arm(("a.py", 1, 4), name="baseline")
    assert utility.covers_a_required_file_the_baseline_missed(semantic, baseline, case.labels)


def test_rendering_the_same_required_files_is_not_a_win() -> None:
    case = _case(must_touch=("a.py",))
    semantic = _arm(("a.py", 1, 4))
    baseline = _arm(("a.py", 1, 4), name="baseline")
    assert not utility.covers_a_required_file_the_baseline_missed(semantic, baseline, case.labels)


def test_rendering_an_unrequired_file_the_baseline_missed_is_not_a_win() -> None:
    case = _case(must_touch=("a.py",))
    semantic = _arm(("a.py", 1, 4), ("extra.py", 1, 4))
    baseline = _arm(("a.py", 1, 4), name="baseline")
    assert not utility.covers_a_required_file_the_baseline_missed(semantic, baseline, case.labels)


# --------------------------------------------------------------------------
# per-case scoring end to end
# --------------------------------------------------------------------------


def test_score_case_measures_both_arms_under_one_budget() -> None:
    case = _case(must_touch=("a.py",), spans=(EvidenceSpan("a.py", 10, 19),))
    semantic = _arm(("a.py", 10, 19))
    baseline = _arm(("x.py", 1, 10), ("a.py", 30, 39), name="baseline")

    scored = utility.score_case(case, semantic=semantic, baseline=baseline, budget=_budget())
    assert scored.semantic_answer_coverage == 1.0
    assert scored.baseline_answer_coverage == 1.0
    assert scored.semantic_evidence_density == 1.0
    assert scored.baseline_evidence_density == 0.0
    assert scored.semantic_steps_to_evidence == 1
    assert scored.baseline_steps_to_evidence == _budget().max_files + 1
    assert scored.win_over_baseline is False


# --------------------------------------------------------------------------
# the four conditions, and the fact that they are not blended
# --------------------------------------------------------------------------


def test_all_four_conditions_holding_is_a_pass() -> None:
    thresholds = _utility_thresholds()
    entry = _measured(coverage=(1.0, 0.0), density=(1.0, 0.5), steps=(1, 3), win=True)
    result = utility.score_consumer(_slice(), [entry], thresholds)
    assert result.verdict == "pass"
    assert result.conditions == {name: True for name in utility.CONDITIONS}


def test_beating_the_baseline_by_less_than_the_declared_margin_fails() -> None:
    """"No worse than ripgrep" is not a reason to inject anything."""
    thresholds = _utility_thresholds()
    margin = float(thresholds[utility.COVERAGE_MARGIN])
    entry = _measured(coverage=(0.5 + margin / 2, 0.5))
    result = utility.score_consumer(_slice(), [entry], thresholds)
    assert result.verdict == "fail"
    assert result.conditions is not None
    assert result.conditions[utility.CONDITION_COVERAGE] is False
    assert utility.UTILITY_BELOW_THRESHOLD in result.fail_reasons
    assert utility.CONSUMER_REGRESSION not in result.fail_reasons


def test_an_increase_in_read_cost_fails_on_its_own() -> None:
    thresholds = _utility_thresholds()
    entry = _measured(coverage=(1.0, 0.0), steps=(4, 2))
    result = utility.score_consumer(_slice(), [entry], thresholds)
    assert result.verdict == "fail"
    assert result.conditions is not None
    assert result.conditions[utility.CONDITION_STEPS] is False


def test_a_drop_in_evidence_density_fails_on_its_own() -> None:
    thresholds = _utility_thresholds()
    entry = _measured(coverage=(1.0, 0.0), density=(0.2, 0.9))
    result = utility.score_consumer(_slice(), [entry], thresholds)
    assert result.verdict == "fail"
    assert result.conditions is not None
    assert result.conditions[utility.CONDITION_DENSITY] is False


def test_no_outright_win_fails_on_its_own() -> None:
    thresholds = _utility_thresholds()
    entry = _measured(coverage=(1.0, 0.0), win=False)
    result = utility.score_consumer(_slice(), [entry], thresholds)
    assert result.verdict == "fail"
    assert result.conditions is not None
    assert result.conditions[utility.CONDITION_WINS] is False


def test_a_huge_density_gain_cannot_buy_a_coverage_regression() -> None:
    """The blend that design D7 forbids, tested as the trade it would permit.

    Under any weighted sum with a non-trivial weight on density, this consumer
    passes: density triples while coverage falls by a fifth. Under three
    independent conditions it cannot.
    """
    thresholds = _utility_thresholds()
    entry = _measured(coverage=(0.4, 0.6), density=(0.9, 0.3), steps=(1, 5), win=True)
    result = utility.score_consumer(_slice(), [entry], thresholds)
    assert result.verdict == "fail"
    assert utility.CONSUMER_REGRESSION in result.fail_reasons
    assert result.conditions is not None
    assert result.conditions[utility.CONDITION_DENSITY] is True
    assert result.conditions[utility.CONDITION_STEPS] is True
    assert result.conditions[utility.CONDITION_COVERAGE] is False


def test_a_coverage_regression_is_reported_separately_from_a_missed_margin() -> None:
    """Two different failures: below the baseline, versus above it by too little."""
    thresholds = _utility_thresholds()
    regressed = utility.score_consumer(_slice(), [_measured(coverage=(0.4, 0.6))], thresholds)
    short = utility.score_consumer(_slice(), [_measured(coverage=(0.6, 0.6))], thresholds)
    assert utility.CONSUMER_REGRESSION in regressed.fail_reasons
    assert utility.CONSUMER_REGRESSION not in short.fail_reasons
    assert utility.UTILITY_BELOW_THRESHOLD in short.fail_reasons


# --------------------------------------------------------------------------
# composition: no offsetting across consumers
# --------------------------------------------------------------------------


def test_one_regressing_consumer_fails_the_gate_however_well_others_did() -> None:
    """The do-no-harm clause, at the level where averaging would hide it."""
    thresholds = _utility_thresholds()
    helped = utility.score_consumer(
        _slice("debugging-and-error-recovery"),
        [_measured(consumer="debugging-and-error-recovery", coverage=(1.0, 0.0))],
        thresholds,
    )
    hurt = utility.score_consumer(
        _slice("parallel-review-implementation"),
        [_measured(consumer="parallel-review-implementation", coverage=(0.2, 0.8))],
        thresholds,
    )
    assert helped.verdict == "pass"
    assert hurt.verdict == "fail"

    gate = utility.score_utility([helped, hurt], thresholds)
    assert gate.verdict == "fail"
    assert utility.CONSUMER_REGRESSION in gate.fail_reasons
    assert gate.measured["consumers_failing"] == 1


def test_the_gate_passes_only_when_every_applicable_consumer_passes() -> None:
    thresholds = _utility_thresholds()
    consumers = [
        utility.score_consumer(
            _slice(name), [_measured(consumer=name, coverage=(1.0, 0.0))], thresholds
        )
        for name in ("implement-feature", "validate-feature")
    ]
    assert utility.score_utility(consumers, thresholds).verdict == "pass"


def test_an_applicable_consumer_with_no_scored_cases_is_unmeasured_not_absent() -> None:
    thresholds = _utility_thresholds()
    empty = utility.score_consumer(_slice(), [], thresholds)
    assert empty.verdict == "fail"
    assert empty.fail_reasons == (utility.UNMEASURED,)
    assert utility.score_utility([empty], thresholds).verdict == "fail"


def test_a_gate_over_no_applicable_consumer_is_an_error() -> None:
    thresholds = _utility_thresholds()
    corpus = _corpus()
    exempt = utility.score_consumer(corpus.slice_for("quick-task"), [], thresholds)
    with pytest.raises(ScoringError):
        utility.score_utility([exempt], thresholds)


def test_a_missing_threshold_is_an_error_not_a_default() -> None:
    with pytest.raises(ScoringError):
        utility.score_consumer(_slice(), [_measured(coverage=(1.0, 0.0))], {})


# --------------------------------------------------------------------------
# a declared exemption is visible, not absent
# --------------------------------------------------------------------------


def test_quick_task_is_present_in_the_output_carrying_its_declaration() -> None:
    corpus = _corpus()
    slice_ = corpus.slice_for("quick-task")
    result = utility.score_consumer(slice_, [], _utility_thresholds())
    assert result.utility_applicable is False
    assert result.utility_not_applicable_reason
    assert result.cases_declared == len(slice_.cases)
    assert result.metrics is None


def test_a_declared_exemption_that_is_also_measured_is_a_contradiction() -> None:
    corpus = _corpus()
    with pytest.raises(ScoringError):
        utility.score_consumer(
            corpus.slice_for("quick-task"),
            [_measured(consumer="quick-task", coverage=(1.0, 0.0))],
            _utility_thresholds(),
        )


def test_an_exemption_without_a_reason_is_refused() -> None:
    silent = ConsumerSlice(consumer="quick-task", utility_applicable=False, cases=("X",))
    with pytest.raises(ScoringError):
        utility.score_consumer(silent, [], _utility_thresholds())


# --------------------------------------------------------------------------
# which cases each consumer's utility is computed over
# --------------------------------------------------------------------------


def test_utility_cases_exclude_fixed_outcome_cases() -> None:
    corpus = _corpus()
    expected = {
        "implement-feature": {"T2", "T5", "T6"},
        "iterate-on-implementation": {"T7", "T8"},
        "debugging-and-error-recovery": {"T1", "T10"},
        "validate-feature": {"T4", "T9"},
        "parallel-review-implementation": {"T3"},
        "quick-task": set(),
    }
    for slice_ in corpus.consumers:
        selected = utility.utility_cases(corpus.cases, slice_)
        assert {case.case_id for case in selected} == expected[slice_.consumer]


def test_every_utility_case_carries_both_labels_the_measures_need() -> None:
    corpus = _corpus()
    for slice_ in corpus.consumers:
        for case in utility.utility_cases(corpus.cases, slice_):
            assert case.labels.must_touch, f"{case.case_id} has no must_touch"
            assert case.labels.evidence_spans, f"{case.case_id} has no evidence_spans"


def test_every_applicable_consumer_can_arithmetically_reach_the_win_threshold() -> None:
    """A threshold a slice cannot reach would be unsatisfiable rather than strict."""
    corpus = _corpus()
    required = _utility_thresholds()[utility.MIN_WINS_PER_CONSUMER]
    for slice_ in corpus.consumers:
        if not slice_.utility_applicable:
            continue
        available = len(utility.utility_cases(corpus.cases, slice_))
        assert available >= required, f"{slice_.consumer} has {available} utility cases"
