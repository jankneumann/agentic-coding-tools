"""``disagreement.classify_disagreements`` (design D11).

Spec scenarios: test-oracle-audit.47 (Weak assertion is listed), test-oracle-audit.48 (Static blind
spot is listed).

API assumed:

``classify_disagreements(joined, labels, *, kill_rate_cuts, thresholds) -> dict[str, list[str]]``

* ``joined``: ``dict[node_id, dict[stage, StageRecord]]``; ``labels``: ``dict[node_id, LabelEntry]``;
* ``kill_rate_cuts``: ``(t1, t2)`` from ``thresholds.tercile_cutpoints``; bottom tercile means
  ``tercile_of(rate, cuts) == "bottom"``; an ``insufficient`` kill rate is never bottom;
* ``thresholds``: dict with ``co_change_high`` (strictly "above" qualifies);
* the result has exactly the five D11 keys, each a list of node ids.

"Intent-derived" is judged or human: the human label when the test has one, otherwise the judged
top label (D11 "judged or human"). Tests in these cases keep judged and human consistent unless the
case is about their disagreement.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "analysis"))

import analysis_builders as b
from test_oracle_audit.disagreement import classify_disagreements

CLASSES = {"weak_assertions", "static_blind_spot", "coupled_spec_test", "judge_vs_human", "rubber_stamp"}
CUTS = (0.3, 0.6)  # bottom <= 0.3 < middle <= 0.6 < top
THRESHOLDS = {"judged_impl_derived_p": 0.5, "co_change_high": 0.5}


def classify(recs, human=None, thresholds=THRESHOLDS):
    return classify_disagreements(
        b.join(recs), b.labels_for(human or {}), kill_rate_cuts=CUTS, thresholds=thresholds
    )


def test_result_has_exactly_the_five_named_classes_even_when_empty():
    """Scenarios test-oracle-audit.47/.48 (design D11): five classes, each a list, none missing."""
    out = classify([b.mutation_rec(0, 0.9)], {0: "spec"})
    assert set(out) == CLASSES
    assert all(isinstance(v, list) for v in out.values())
    assert all(v == [] for v in out.values())


# --- weak_assertions ------------------------------------------------------


def test_human_spec_test_with_bottom_tercile_kill_rate_is_a_weak_assertion():
    """Scenario test-oracle-audit.47: human-labelled ``spec`` and kill rate in the bottom tercile."""
    out = classify([b.mutation_rec(0, 0.1)], {0: "spec"})
    assert out["weak_assertions"] == [b.nid(0)]


@pytest.mark.parametrize(
    ("kill_rate", "human"),
    [(0.9, "spec"), (0.45, "spec"), ("insufficient", "spec"), (0.1, "current_impl_output")],
)
def test_weak_assertions_requires_intent_derived_and_bottom_tercile(kill_rate, human):
    """Scenario test-oracle-audit.47 (negative cases): top/middle/insufficient kill rate, or a non-intent label."""
    out = classify([b.mutation_rec(0, kill_rate), b.judged_rec(0, human)], {0: human})
    assert out["weak_assertions"] == []


def test_judged_intent_without_a_human_label_counts_as_intent_derived():
    """Scenario test-oracle-audit.47 / design D11 ("judged or human"): no label, judged ``property``."""
    out = classify([b.mutation_rec(0, 0.05), b.judged_rec(0, "property")])
    assert out["weak_assertions"] == [b.nid(0)]


def test_tercile_boundary_is_inclusive_on_the_low_side():
    """Scenario test-oracle-audit.47 (shared tercile_of semantics): a rate equal to the first cut is bottom."""
    out = classify([b.mutation_rec(0, CUTS[0]), b.mutation_rec(1, 0.31)], {0: "spec", 1: "spec"})
    assert out["weak_assertions"] == [b.nid(0)]


# --- static_blind_spot ----------------------------------------------------


def test_unflagged_current_impl_output_test_is_a_static_blind_spot():
    """Scenario test-oracle-audit.48: no static rule fires and the human label is ``current_impl_output``."""
    out = classify([b.static_rec(0, [])], {0: "current_impl_output"})
    assert out["static_blind_spot"] == [b.nid(0)]


def test_judged_current_impl_output_without_a_label_is_a_static_blind_spot():
    """Scenario test-oracle-audit.48 / design D11 ("judged or human")."""
    out = classify([b.static_rec(0, []), b.judged_rec(0, "current_impl_output", p=0.9)])
    assert out["static_blind_spot"] == [b.nid(0)]


@pytest.mark.parametrize(
    ("rules", "human"),
    [
        (["private_import"], "current_impl_output"),  # a rule did fire: not a blind spot
        ([], "spec"),  # intent-derived: nothing for the rules to see
        ([], "characterization"),  # declared characterization is not an undeclared restatement
    ],
)
def test_static_blind_spot_negative_cases(rules, human):
    """Scenario test-oracle-audit.48 (negative cases)."""
    out = classify([b.static_rec(0, rules)], {0: human})
    assert out["static_blind_spot"] == []


# --- coupled_spec_test ----------------------------------------------------


def test_intent_derived_test_broken_by_the_rename_is_a_coupled_spec_test():
    """Design D11 ``coupled_spec_test``: labelled intent-derived and the rename broke it."""
    out = classify([b.rename_rec(0, survives=False)], {0: "spec"})
    assert out["coupled_spec_test"] == [b.nid(0)]


@pytest.mark.parametrize(
    ("survives", "low_confidence", "human"),
    [
        (True, False, "spec"),  # survived
        (False, False, "current_impl_output"),  # not intent-derived: expected to be coupled
        (False, True, "spec"),  # low-confidence rename is excluded from this class (design D10)
    ],
)
def test_coupled_spec_test_negative_cases(survives, low_confidence, human):
    """Design D11 / D10 (negative cases for ``coupled_spec_test``)."""
    out = classify([b.rename_rec(0, survives, low_confidence=low_confidence)], {0: human})
    assert out["coupled_spec_test"] == []


# --- judge_vs_human -------------------------------------------------------


def test_judge_and_human_with_different_binary_classes_disagree():
    """Design D11 ``judge_vs_human``: judged top ``spec`` (intent) against human ``current_impl_output``."""
    out = classify([b.judged_rec(0, "spec")], {0: "current_impl_output"})
    assert out["judge_vs_human"] == [b.nid(0)]


@pytest.mark.parametrize(
    ("judged", "human"),
    [
        ("spec", "property"),  # seven-class differ, binary class equal (both intent-derived)
        ("current_impl_output", "none"),  # binary class equal (both not intent-derived)
        ("spec", "spec"),
    ],
)
def test_judge_vs_human_compares_binary_classes_not_seven_class_labels(judged, human):
    """Design D11 / D2 binary split: same binary class is not a disagreement."""
    out = classify([b.judged_rec(0, judged)], {0: human})
    assert out["judge_vs_human"] == []


def test_judge_vs_human_needs_both_signals():
    """Design D11: a test with only a human label, or only a judged answer, is not a disagreement."""
    out = classify([b.judged_rec(1, "spec"), b.judged_rec(2, "spec", status="degraded")], {0: "none", 2: "none"})
    assert out["judge_vs_human"] == []


# --- rubber_stamp ---------------------------------------------------------


def test_high_co_change_with_a_surviving_kill_rate_is_a_rubber_stamp():
    """Design D11 ``rubber_stamp``: co-change above threshold while the kill rate is not bottom tercile."""
    out = classify([b.history_rec(0, 0.9), b.mutation_rec(0, 0.9)])
    assert out["rubber_stamp"] == [b.nid(0)]


@pytest.mark.parametrize(
    ("ratio", "kill"),
    [
        (0.9, 0.1),  # kill rate is bottom tercile: not a rubber stamp (weak, not stamped)
        (0.5, 0.9),  # equal to the threshold is not "above"
        (0.2, 0.9),  # below threshold
        ("insufficient", 0.9),  # no usable co-change ratio
    ],
)
def test_rubber_stamp_negative_cases(ratio, kill):
    """Design D11 (negative cases for ``rubber_stamp``)."""
    out = classify([b.history_rec(0, ratio), b.mutation_rec(0, kill)])
    assert out["rubber_stamp"] == []


def test_rubber_stamp_threshold_comes_from_the_thresholds_argument():
    """Design D1 / D7: no threshold literal; ``co_change_high`` is read from the ``thresholds`` mapping."""
    recs = [b.history_rec(0, 0.7), b.mutation_rec(0, 0.9), b.history_rec(1, 0.9), b.mutation_rec(1, 0.9)]
    strict = classify(recs, thresholds={**THRESHOLDS, "co_change_high": 0.8})
    lax = classify(recs, thresholds={**THRESHOLDS, "co_change_high": 0.6})
    assert strict["rubber_stamp"] == [b.nid(1)]
    assert sorted(lax["rubber_stamp"]) == [b.nid(0), b.nid(1)]


# --- combined -------------------------------------------------------------


def test_one_test_can_appear_under_several_classes_and_ids_are_unique():
    """Scenarios test-oracle-audit.47/.48: classes are independent views; each list has unique node ids.

    Test 0: human ``spec``, bottom kill rate, rename broke it, judged ``current_impl_output``:
    weak_assertions, coupled_spec_test and judge_vs_human all apply.
    """
    recs = [b.mutation_rec(0, 0.1), b.rename_rec(0, survives=False), b.judged_rec(0, "current_impl_output")]
    out = classify(recs, {0: "spec"})
    for cls in ("weak_assertions", "coupled_spec_test", "judge_vs_human"):
        assert out[cls] == [b.nid(0)]
    assert all(len(v) == len(set(v)) for v in out.values())


def test_classification_is_deterministic():
    """Design D11 (determinism): the same inputs give the same lists in the same order."""
    joined, labels = b.mixed_suite(40)
    args = {"kill_rate_cuts": CUTS, "thresholds": THRESHOLDS}
    assert classify_disagreements(joined, labels, **args) == classify_disagreements(joined, labels, **args)
