"""Statistic primitives of ``test_oracle_audit.analysis`` (design D10, standard library only).

Spec scenarios: test-oracle-audit.42 (Perfect agreement yields kappa 1),
test-oracle-audit.46 (Bootstrap is reproducible).

API assumed (the tests define it):

* ``cohen_kappa(a, b) -> float``: two equal-length label sequences.
* ``brier(probs, outcomes) -> float``: ``outcomes`` are 0/1 (or bool).
* ``bootstrap_ci(fn, data, *, seed, n_resamples=2000) -> (lo, hi)``: ``fn`` maps a list of
  data items (resampled with replacement) to a float; 95% percentile interval.
* ``cliffs_delta(xs, ys) -> float``: ``(#x>y - #x<y) / (len(xs) * len(ys))``.
* ``auc(scores, labels) -> float``: probability a positive outscores a negative; ties count 0.5.

Expected values below are computed by hand in comments.
"""

from __future__ import annotations

import pytest
from test_oracle_audit.analysis import auc, bootstrap_ci, brier, cliffs_delta, cohen_kappa


def _mean(xs):
    return sum(xs) / len(xs)


# --- Cohen's kappa ---------------------------------------------------------


def test_kappa_is_one_on_perfect_agreement():
    """Scenario test-oracle-audit.42: identical label sequences spanning two classes give kappa 1.0."""
    labels = ["spec"] * 10 + ["current_impl_output"] * 15
    assert cohen_kappa(labels, list(labels)) == pytest.approx(1.0)


def test_kappa_matches_hand_computed_two_by_two_table():
    """Scenario test-oracle-audit.42 (kappa definition).

    Table (rater a x rater b): yes/yes 20, yes/no 5, no/yes 10, no/no 15, n = 50.
    po = 35/50 = 0.7; a says yes 25/50, b says yes 30/50 -> pe = .5*.6 + .5*.4 = 0.5;
    kappa = (0.7 - 0.5) / (1 - 0.5) = 0.4.
    """
    a = ["yes"] * 20 + ["yes"] * 5 + ["no"] * 10 + ["no"] * 15
    b = ["yes"] * 20 + ["no"] * 5 + ["yes"] * 10 + ["no"] * 15
    assert cohen_kappa(a, b) == pytest.approx(0.4)


def test_kappa_is_zero_when_agreement_equals_chance():
    """Scenario test-oracle-audit.42 (kappa definition).

    yes/yes 5, yes/no 5, no/yes 5, no/no 5: po = 0.5, pe = 0.5 -> kappa 0.
    """
    a = ["yes"] * 10 + ["no"] * 10
    b = ["yes"] * 5 + ["no"] * 5 + ["yes"] * 5 + ["no"] * 5
    assert cohen_kappa(a, b) == pytest.approx(0.0)


def test_kappa_is_symmetric():
    """Scenario test-oracle-audit.42 (kappa definition): swapping the raters does not change kappa."""
    a = ["spec", "spec", "none", "property", "none", "spec", "property", "none"]
    b = ["spec", "none", "none", "property", "spec", "spec", "none", "none"]
    assert cohen_kappa(a, b) == pytest.approx(cohen_kappa(b, a))


# --- Brier ----------------------------------------------------------------


def test_brier_matches_hand_computed_value():
    """Scenario test-oracle-audit.43/.44 (Brier definition).

    probs [0.9, 0.2, 0.6, 0.5], outcomes [1, 0, 1, 0]:
    (0.01 + 0.04 + 0.16 + 0.25) / 4 = 0.115.
    """
    assert brier([0.9, 0.2, 0.6, 0.5], [1, 0, 1, 0]) == pytest.approx(0.115)


def test_brier_of_perfect_and_worst_forecasts():
    """Scenario test-oracle-audit.44 (Brier bounds): perfect forecasts score 0, inverted ones score 1."""
    assert brier([1.0, 0.0, 1.0], [1, 0, 1]) == pytest.approx(0.0)
    assert brier([0.0, 1.0], [1, 0]) == pytest.approx(1.0)


def test_brier_accepts_boolean_outcomes():
    """Scenario test-oracle-audit.43 (rename survival is boolean): bool outcomes equal 0/1 outcomes."""
    assert brier([0.7, 0.3], [True, False]) == pytest.approx(brier([0.7, 0.3], [1, 0]))


# --- Cliff's delta --------------------------------------------------------


def test_cliffs_delta_is_one_when_every_x_exceeds_every_y():
    """Scenario test-oracle-audit.45 (Cliff's delta definition): complete dominance gives +1 / -1."""
    assert cliffs_delta([3, 4, 5], [1, 2]) == pytest.approx(1.0)
    assert cliffs_delta([1, 2], [3, 4]) == pytest.approx(-1.0)


def test_cliffs_delta_is_zero_for_symmetric_overlap():
    """Scenario test-oracle-audit.45: xs=[1,2,3], ys=[2]: one greater, one smaller, one tie -> 0."""
    assert cliffs_delta([1, 2, 3], [2]) == pytest.approx(0.0)


def test_cliffs_delta_counts_ties_as_neither():
    """Scenario test-oracle-audit.45: xs=[2,3,4], ys=[1,3].

    Pairs: 2 vs (1,3) -> 1 greater, 1 smaller; 3 vs (1,3) -> 1 greater, 1 tie; 4 vs (1,3) -> 2 greater.
    greater = 4, smaller = 1 over 6 pairs -> (4 - 1) / 6 = 0.5.
    """
    assert cliffs_delta([2, 3, 4], [1, 3]) == pytest.approx(0.5)


def test_cliffs_delta_is_antisymmetric():
    """Scenario test-oracle-audit.45: swapping the groups negates delta."""
    xs, ys = [0.1, 0.4, 0.9, 0.9], [0.2, 0.5, 0.7]
    assert cliffs_delta(xs, ys) == pytest.approx(-cliffs_delta(ys, xs))


# --- AUC ------------------------------------------------------------------


def test_auc_matches_hand_computed_value():
    """Scenario test-oracle-audit.42 family (AUC for continuous predictors).

    scores [0.1, 0.4, 0.35, 0.8], labels [0, 0, 1, 1]: positives {0.35, 0.8}, negatives {0.1, 0.4}.
    Pairs where the positive outscores the negative: 0.35>0.1, 0.8>0.1, 0.8>0.4 = 3 of 4 -> 0.75.
    """
    assert auc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]) == pytest.approx(0.75)


def test_auc_is_one_for_perfect_separation_and_zero_for_inverted():
    """Scenario test-oracle-audit.42 family (AUC bounds)."""
    assert auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == pytest.approx(1.0)
    assert auc([0.8, 0.9, 0.1, 0.2], [0, 0, 1, 1]) == pytest.approx(0.0)


def test_auc_counts_tied_scores_as_half():
    """Scenario test-oracle-audit.42 family (AUC ties): one positive tied with one negative -> 0.5."""
    assert auc([0.5, 0.5], [0, 1]) == pytest.approx(0.5)


# --- bootstrap ------------------------------------------------------------


def test_bootstrap_is_reproducible_for_a_fixed_seed():
    """Scenario test-oracle-audit.46: the same seed and inputs give an identical interval."""
    data = [float(i % 7) for i in range(40)]
    assert bootstrap_ci(_mean, data, seed=11) == bootstrap_ci(_mean, data, seed=11)


def test_bootstrap_interval_depends_on_the_seed():
    """Scenario test-oracle-audit.46: the seed is actually used (different seeds, different resamples)."""
    data = [float(i % 7) for i in range(40)]
    assert bootstrap_ci(_mean, data, seed=1) != bootstrap_ci(_mean, data, seed=2)


def test_bootstrap_of_constant_data_is_a_point_interval():
    """Scenario test-oracle-audit.46 (sanity): resampling constant data cannot vary."""
    lo, hi = bootstrap_ci(_mean, [5.0] * 30, seed=3)
    assert (lo, hi) == (pytest.approx(5.0), pytest.approx(5.0))


def test_bootstrap_interval_brackets_the_estimate_with_plausible_width():
    """Scenario test-oracle-audit.46 (sanity).

    50 zeros and 50 ones: the mean is 0.5 with standard error 0.05, so the 95% interval is about
    (0.40, 0.60). Allow generous slack around that.
    """
    data = [0.0] * 50 + [1.0] * 50
    lo, hi = bootstrap_ci(_mean, data, seed=5)
    assert 0.35 < lo < 0.46
    assert 0.54 < hi < 0.65


def test_bootstrap_honours_the_resample_count():
    """Scenario test-oracle-audit.46: ``n_resamples`` is the number of times ``fn`` is evaluated on a resample."""
    calls = []

    def fn(sample):
        calls.append(len(sample))
        return _mean(sample)

    data = [float(i) for i in range(20)]
    bootstrap_ci(fn, data, seed=0, n_resamples=50)
    # fn may also be evaluated once on the full data; the resamples are all the size of the data.
    assert 50 <= len(calls) <= 51
    assert set(calls) == {20}


def test_bootstrap_default_is_two_thousand_resamples():
    """Scenario test-oracle-audit.46 / design D10: the default is 2,000 resamples."""
    calls = []

    def fn(sample):
        calls.append(1)
        return _mean(sample)

    bootstrap_ci(fn, [1.0, 2.0, 3.0, 4.0], seed=0)
    assert 2000 <= len(calls) <= 2001
