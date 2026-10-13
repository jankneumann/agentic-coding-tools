"""``analysis.analyze`` over synthetic joined records (design D10, D1 shared cut-points).

Spec scenarios: test-oracle-audit.38 (Explanation never feeds analysis), .42 (Perfect agreement
yields kappa 1), .43 (Small n is insufficient), .44 (Low-agreement question is excluded),
.45 (Non-predictive static rule is marked), .46 (Bootstrap is reproducible).

API assumed:

``analyze(joined, labels, *, seed=0, suites=[...]) -> dict`` where

* ``joined``: ``dict[node_id, dict[stage, StageRecord]]`` (stage in static/judged/mutation/
  rename/history/explain; any stage may be absent for any test);
* ``labels``: ``dict[node_id, LabelEntry]`` (current labels, e.g. ``LabelLedger.current_labels``);
* the result validates against ``analysis-report.schema.json``.

Naming conventions the tests pin (schema leaves them free):

* judged-question subjects: ``oracle_source`` (kappa_7 / kappa_binary, comparison ``human_label``),
  ``survives_refactor`` (brier / brier_base_rate, comparison ``rename_survival``);
* static-rule subjects are the rule id (cliffs_delta vs ``kill_rate``; precision / recall vs
  ``human_label``, positive class = human label is NOT intent-derived);
* AUC subjects: ``co_change_ratio`` (positive = human label NOT intent-derived) and
  ``p_intent_derived`` (judged probability mass on the intent-derived labels; positive =
  human label intent-derived); AUC metrics carry ``threshold`` (Youden's J) and ``provisional: true``;
* a rule or question that fails its decision rule appears in ``excluded`` with a ``reason`` naming
  the cause (``0.7`` floor, ``base rate``, ``not_predictive``); one that passes appears in
  ``linter_candidates``; an ``insufficient`` metric yields neither;
* ``approach_coverage`` has exactly the five measured approaches static/judged/mutation/rename/
  history; ``ok`` counts ok records with a usable value, ``insufficient`` counts ok records whose
  value is ``insufficient`` (kill rate, co-change) or rename records with ``low_confidence``,
  ``degraded`` counts degraded records, ``not_run`` is true when no record is ok or insufficient.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "analysis"))

import analysis_builders as b
from test_oracle_audit.analysis import analyze
from test_oracle_audit.disagreement import classify_disagreements

from test_oracle_audit.records import StageRecord
from test_oracle_audit.thresholds import load_thresholds, tercile_cutpoints

SUITES = [b.SUITE]


def run(joined, labels, **kw):
    return analyze(joined, labels, seed=kw.pop("seed", 0), suites=kw.pop("suites", SUITES), **kw)


def metrics(doc, subject, metric):
    found = [m for m in doc["metrics"] if m["subject"] == subject and m["metric"] == metric]
    assert len(found) == 1, f"expected one {metric} for {subject}, got {found}"
    return found[0]


def subjects(entries):
    return {c["subject"] for c in entries}


def judged_vs_human(pairs):
    """pairs: list of (judged_top, human_label); one test per pair."""
    recs = [b.judged_rec(i, top) for i, (top, _) in enumerate(pairs)]
    return b.join(recs), b.labels_for({i: human for i, (_, human) in enumerate(pairs)})


# --- document shape -------------------------------------------------------


def test_document_is_advisory_and_validates_against_the_schema(schema_validator):
    """Contract analysis-report.schema.json; scenario test-oracle-audit.42 (output shape, D10)."""
    joined, labels = b.mixed_suite(40)
    doc = run(joined, labels, seed=7)
    schema_validator(doc, "analysis-report")
    assert doc["advisory"] is True
    assert doc["seed"] == 7
    assert doc["suites"] == SUITES
    assert doc["schema_version"] == 1


def test_every_metric_carries_n_and_a_confidence_interval(schema_validator):
    """Scenario test-oracle-audit.46 (every metric carries n and a bootstrap 95% interval)."""
    joined, labels = b.mixed_suite(40)
    doc = run(joined, labels)
    ok = [m for m in doc["metrics"] if m["status"] == "ok"]
    assert len(ok) >= 3
    for m in doc["metrics"]:
        assert isinstance(m["n"], int)
    for m in ok:
        lo, hi = m["ci95"]
        assert lo <= hi, m


def test_analysis_tolerates_a_judged_only_run(schema_validator):
    """Scenario test-oracle-audit.43 (stages are independent; absent stages never raise)."""
    joined, labels = judged_vs_human([("spec", "spec")] * 12 + [("none", "none")] * 12)
    doc = run(joined, labels)
    schema_validator(doc, "analysis-report")
    assert doc["approach_coverage"]["static"]["not_run"] is True


# --- kappa ----------------------------------------------------------------


def test_perfect_agreement_gives_kappa_one():
    """Scenario test-oracle-audit.42: judged top labels equal human labels on 25 tests, three classes."""
    pairs = [("spec", "spec")] * 10 + [("characterization", "characterization")] * 8
    pairs += [("current_impl_output", "current_impl_output")] * 7
    doc = run(*judged_vs_human(pairs))
    m7 = metrics(doc, "oracle_source", "kappa_7")
    assert m7["comparison"] == "human_label"
    assert m7["n"] == 25
    assert m7["status"] == "ok"
    assert m7["value"] == pytest.approx(1.0)
    assert m7["ci95"] == [pytest.approx(1.0), pytest.approx(1.0)]
    assert metrics(doc, "oracle_source", "kappa_binary")["value"] == pytest.approx(1.0)


def test_binary_kappa_collapses_intent_derived_classes():
    """Scenario test-oracle-audit.42 / design D2 split.

    10 tests judged ``spec`` but human-labelled ``property`` (both intent-derived) and 10 judged and
    labelled ``current_impl_output``. Binary agreement is perfect (kappa 1.0). Seven-class: po = 0.5,
    judged marginals {spec .5, cio .5}, human marginals {property .5, cio .5}, pe = .5*.5 = 0.25,
    kappa_7 = (0.5 - 0.25) / 0.75 = 1/3. n = 20 is not below the floor of 20.
    """
    pairs = [("spec", "property")] * 10 + [("current_impl_output", "current_impl_output")] * 10
    doc = run(*judged_vs_human(pairs))
    assert metrics(doc, "oracle_source", "kappa_binary")["status"] == "ok"
    assert metrics(doc, "oracle_source", "kappa_binary")["value"] == pytest.approx(1.0)
    assert metrics(doc, "oracle_source", "kappa_7")["value"] == pytest.approx(1 / 3)


def test_kappa_n_counts_only_tests_with_both_a_label_and_a_judged_answer():
    """Scenario test-oracle-audit.43: n counts tests having BOTH a current human label and a judged answer.

    30 tests are human-labelled; only 12 have an ok judged record (the rest are dry-run degraded).
    """
    recs = [b.judged_rec(i, "spec") for i in range(12)]
    recs += [b.judged_rec(i, "spec", status="degraded") for i in range(12, 30)]
    doc = run(b.join(recs), b.labels_for({i: "spec" for i in range(30)}))
    assert metrics(doc, "oracle_source", "kappa_7")["n"] == 12


# --- insufficient ---------------------------------------------------------


def test_twelve_paired_tests_are_insufficient_with_no_point_estimate(schema_validator):
    """Scenario test-oracle-audit.43: only 12 tests have a label and a judged answer."""
    pairs = [("spec", "spec")] * 6 + [("current_impl_output", "current_impl_output")] * 6
    doc = run(*judged_vs_human(pairs))
    schema_validator(doc, "analysis-report")
    for name in ("kappa_7", "kappa_binary"):
        m = metrics(doc, "oracle_source", name)
        assert m["status"] == "insufficient"
        assert m["n"] == 12
        assert "value" not in m
    assert "oracle_source" not in subjects(doc["linter_candidates"])


def test_twenty_is_the_smallest_sufficient_n():
    """Scenario test-oracle-audit.43: the floor is n < 20 (19 insufficient, 20 sufficient)."""
    for n, expected in ((19, "insufficient"), (20, "ok")):
        pairs = [("spec", "spec")] * (n // 2) + [("none", "none")] * (n - n // 2)
        m = metrics(run(*judged_vs_human(pairs)), "oracle_source", "kappa_binary")
        assert (m["n"], m["status"]) == (n, expected)


def test_cliffs_delta_with_few_tests_is_insufficient():
    """Scenario test-oracle-audit.43: a Cliff's-delta cell over 12 tests has no point estimate."""
    recs = []
    for i in range(12):
        recs += [b.static_rec(i, ["private_import"] if i < 6 else []), b.mutation_rec(i, 0.1 if i < 6 else 0.9)]
    doc = run(b.join(recs), {})
    m = metrics(doc, "private_import", "cliffs_delta")
    assert m["status"] == "insufficient" and "value" not in m and m["n"] == 12
    assert "private_import" not in subjects(doc["linter_candidates"])


# --- excluded judged questions -------------------------------------------


def test_low_binary_kappa_excludes_the_question_citing_the_floor():
    """Scenario test-oracle-audit.44: binary kappa 0.55 puts ``oracle_source`` under excluded, citing 0.7.

    40 tests: judged-intent/human-intent 16, judged-intent/human-not 4, judged-not/human-intent 5,
    judged-not/human-not 15. po = 31/40 = 0.775; both raters' marginals are near .5 so
    pe = .5*.525 + .5*.475 = 0.5; kappa = 0.275 / 0.5 = 0.55.
    """
    pairs = [("spec", "spec")] * 16 + [("spec", "none")] * 4
    pairs += [("current_impl_output", "spec")] * 5 + [("current_impl_output", "current_impl_output")] * 15
    doc = run(*judged_vs_human(pairs))
    m = metrics(doc, "oracle_source", "kappa_binary")
    assert m["status"] == "ok" and m["n"] == 40
    assert m["value"] == pytest.approx(0.55)
    excluded = [c for c in doc["excluded"] if c["subject"] == "oracle_source"]
    assert len(excluded) == 1
    assert excluded[0]["kind"] == "judged_question"
    assert "0.7" in excluded[0]["reason"]
    assert "oracle_source" not in subjects(doc["linter_candidates"])


def test_high_binary_kappa_keeps_the_question_as_a_linter_candidate():
    """Scenario test-oracle-audit.44 (converse): perfect binary agreement is not excluded."""
    pairs = [("spec", "spec")] * 12 + [("current_impl_output", "current_impl_output")] * 12
    doc = run(*judged_vs_human(pairs))
    assert "oracle_source" not in subjects(doc["excluded"])
    cands = [c for c in doc["linter_candidates"] if c["subject"] == "oracle_source"]
    assert len(cands) == 1 and cands[0]["kind"] == "judged_question"


def _survival_suite(p_survivor: float, p_breaker: float):
    recs = []
    for i in range(20):
        survives = i < 10
        recs += [
            b.judged_rec(i, survives=p_survivor if survives else p_breaker),
            b.rename_rec(i, survives=survives),
        ]
    return b.join(recs)


def test_brier_is_compared_with_the_base_rate_brier():
    """Scenario test-oracle-audit.44 (Brier vs base rate).

    10 tests survive the rename, 10 break. Forecasts 0.9 / 0.1: each squared error is 0.01 -> 0.01.
    Base rate is 0.5, each squared error 0.25 -> 0.25.
    """
    doc = run(_survival_suite(0.9, 0.1), {})
    br = metrics(doc, "survives_refactor", "brier")
    base = metrics(doc, "survives_refactor", "brier_base_rate")
    assert br["comparison"] == base["comparison"] == "rename_survival"
    assert br["n"] == base["n"] == 20
    assert br["value"] == pytest.approx(0.01)
    assert base["value"] == pytest.approx(0.25)
    assert "survives_refactor" in subjects(doc["linter_candidates"])
    assert "survives_refactor" not in subjects(doc["excluded"])


@pytest.mark.parametrize(
    ("p_survivor", "p_breaker", "why"),
    [
        (0.1, 0.9, "inverted forecasts: Brier 0.81 vs base rate 0.25"),
        (0.5, 0.5, "uninformative forecasts: Brier 0.25 equals base rate, which is not better"),
    ],
)
def test_brier_not_better_than_base_rate_excludes_the_question(p_survivor, p_breaker, why):
    """Scenario test-oracle-audit.44 (design D10): Brier not better than the base rate -> excluded.

    Parametrized cases: inverted forecasts (Brier 0.81 vs 0.25) and uninformative forecasts (Brier 0.25
    equals the base rate, which is not better).
    """
    doc = run(_survival_suite(p_survivor, p_breaker), {})
    excluded = [c for c in doc["excluded"] if c["subject"] == "survives_refactor"]
    assert len(excluded) == 1 and excluded[0]["kind"] == "judged_question"
    assert "base rate" in excluded[0]["reason"].lower().replace("_", " ")
    assert "survives_refactor" not in subjects(doc["linter_candidates"])


def test_low_confidence_rename_records_are_excluded_from_brier():
    """Design D10: low_confidence rename records leave the Brier comparison; the count is in coverage.

    20 usable tests plus 5 low-confidence tests whose forecasts would wreck the score.
    """
    recs = []
    for i in range(20):
        recs += [b.judged_rec(i, survives=0.9 if i < 10 else 0.1), b.rename_rec(i, survives=i < 10)]
    for i in range(20, 25):
        recs += [b.judged_rec(i, survives=0.0), b.rename_rec(i, survives=True, low_confidence=True)]
    doc = run(b.join(recs), {})
    assert metrics(doc, "survives_refactor", "brier")["n"] == 20
    assert metrics(doc, "survives_refactor", "brier")["value"] == pytest.approx(0.01)
    assert doc["approach_coverage"]["rename"]["insufficient"] == 5


# --- Cliff's delta / static rules ----------------------------------------


def _rule_suite(flagged_kills, unflagged_kills, rule="private_import"):
    recs = []
    for i, k in enumerate(flagged_kills):
        recs += [b.static_rec(i, [rule]), b.mutation_rec(i, k)]
    offset = len(flagged_kills)
    for j, k in enumerate(unflagged_kills):
        recs += [b.static_rec(offset + j, []), b.mutation_rec(offset + j, k)]
    return b.join(recs)


def test_predictive_rule_has_a_cliffs_delta_interval_excluding_zero():
    """Scenario test-oracle-audit.45 (converse): flagged tests all have lower kill rates than unflagged.

    10 flagged (0.00-0.18), 20 unflagged (0.60-0.98): every flagged < every unflagged -> delta = -1.
    """
    doc = run(_rule_suite([i / 50 for i in range(10)], [0.6 + i / 50 for i in range(20)]), {})
    m = metrics(doc, "private_import", "cliffs_delta")
    assert m["comparison"] == "kill_rate"
    assert m["n"] == 30
    assert m["status"] == "ok"
    assert m["value"] == pytest.approx(-1.0)
    lo, hi = m["ci95"]
    assert hi < 0 or lo > 0
    assert "private_import" in subjects(doc["linter_candidates"])
    assert "private_import" not in subjects(doc["excluded"])


def test_rule_whose_delta_interval_spans_zero_is_marked_not_predictive():
    """Scenario test-oracle-audit.45: flagged and unflagged kill rates are identical multisets (delta 0)."""
    rates = [round(0.05 + i * 0.09, 2) for i in range(10)]
    doc = run(_rule_suite(rates, rates + rates), {})
    m = metrics(doc, "private_import", "cliffs_delta")
    assert m["status"] == "ok" and m["n"] == 30
    assert m["value"] == pytest.approx(0.0)
    lo, hi = m["ci95"]
    assert lo <= 0 <= hi
    excluded = [c for c in doc["excluded"] if c["subject"] == "private_import"]
    assert len(excluded) == 1 and excluded[0]["kind"] == "static_rule"
    assert "not_predictive" in excluded[0]["reason"]
    assert "private_import" not in subjects(doc["linter_candidates"])


def test_each_rule_is_judged_on_its_own_interval():
    """Scenario test-oracle-audit.45: one predictive and one non-predictive rule in the same run."""
    recs = []
    for i in range(30):
        low = i < 10  # first ten tests: assertion_free and low kill rate
        rules = ["assertion_free"] if low else []
        if i % 2 == 0:
            rules = rules + ["unscoped_patch"]  # patch flag alternates regardless of kill rate
        kill = 0.05 * i / 10 if low else 0.6 + (i - 10) / 100
        recs += [b.static_rec(i, rules), b.mutation_rec(i, round(kill, 4))]
    doc = run(b.join(recs), {})
    assert "assertion_free" in subjects(doc["linter_candidates"])
    assert "unscoped_patch" in subjects(doc["excluded"])
    assert "assertion_free" not in subjects(doc["excluded"])


def test_static_rule_precision_and_recall_against_the_human_binary_label():
    """Design D10 table (precision / recall, reported only). Positive class: human label NOT intent-derived.

    24 labelled tests: 14 are ``current_impl_output``; the rule flags exactly 10 of those 14 and no
    intent-derived test. precision = 10/10 = 1.0, recall = 10/14.
    """
    recs, human = [], {}
    for i in range(24):
        weak = i < 14
        human[i] = "current_impl_output" if weak else "spec"
        recs.append(b.static_rec(i, ["private_import"] if i < 10 else []))
    doc = run(b.join(recs), b.labels_for(human))
    p = metrics(doc, "private_import", "precision")
    r = metrics(doc, "private_import", "recall")
    assert p["comparison"] == r["comparison"] == "human_label"
    assert p["n"] == r["n"] == 24
    assert p["value"] == pytest.approx(1.0)
    assert r["value"] == pytest.approx(10 / 14)
    assert "private_import" not in subjects(doc["excluded"])  # reported only, never an exclusion


# --- AUC / provisional thresholds ----------------------------------------


def test_co_change_auc_has_a_provisional_youden_threshold():
    """Design D10 table (co_change_ratio AUC, Youden's J, provisional); scenario test-oracle-audit.43 family.

    12 non-intent tests with ratios 0.60-0.82 and 12 intent tests with ratios 0.05-0.27: perfect
    separation, AUC 1.0, and any Youden threshold lies between the groups.
    """
    recs, human = [], {}
    for i in range(12):
        recs.append(b.history_rec(i, round(0.6 + i * 0.02, 2)))
        human[i] = "current_impl_output"
    for i in range(12, 24):
        recs.append(b.history_rec(i, round(0.05 + (i - 12) * 0.02, 2)))
        human[i] = "spec"
    doc = run(b.join(recs), b.labels_for(human))
    m = metrics(doc, "co_change_ratio", "auc")
    assert m["comparison"] == "human_label" and m["n"] == 24 and m["status"] == "ok"
    assert m["value"] == pytest.approx(1.0)
    assert m["provisional"] is True
    assert 0.27 <= m["threshold"] <= 0.60


def test_judged_intent_probability_auc_has_a_provisional_youden_threshold():
    """Design D10 table (Jev P(intent-derived) AUC, Youden's J, provisional). Positive: human intent-derived."""
    pairs = [("spec", "spec")] * 12 + [("current_impl_output", "current_impl_output")] * 12
    doc = run(*judged_vs_human(pairs))
    m = metrics(doc, "p_intent_derived", "auc")
    assert m["value"] == pytest.approx(1.0) and m["provisional"] is True
    assert b.p_intent("current_impl_output") <= m["threshold"] <= b.p_intent("spec")


def test_auc_with_few_labelled_tests_is_insufficient():
    """Scenario test-oracle-audit.43: AUC over 12 labelled tests has no point estimate and no threshold claim."""
    recs, human = [], {}
    for i in range(12):
        recs.append(b.history_rec(i, 0.9 if i < 6 else 0.1))
        human[i] = "none" if i < 6 else "spec"
    doc = run(b.join(recs), b.labels_for(human))
    m = metrics(doc, "co_change_ratio", "auc")
    assert m["status"] == "insufficient" and "value" not in m


# --- coverage counts ------------------------------------------------------


def test_approach_coverage_counts_ok_degraded_and_insufficient(schema_validator):
    """Scenario test-oracle-audit.43 / design D10 (approach-coverage table); feeds scenario .54.

    Judged ran in dry-run (7 degraded, none ok) -> not_run. Mutation has 6 numeric and 2 insufficient
    kill rates. Explanation records are present but are not a measured approach.
    """
    recs = [b.judged_rec(i, status="degraded") for i in range(7)]
    recs += [b.static_rec(i, []) for i in range(10)]
    recs += [b.mutation_rec(i, 0.5) for i in range(6)] + [b.mutation_rec(i, "insufficient") for i in (6, 7)]
    recs += [b.explain_rec(i, "keep") for i in range(3)]
    doc = run(b.join(recs), {})
    schema_validator(doc, "analysis-report")
    cov = doc["approach_coverage"]
    assert set(cov) == {"static", "judged", "mutation", "rename", "history"}
    assert cov["judged"] == {"ok": 0, "degraded": 7, "insufficient": 0, "not_run": True}
    assert cov["static"]["ok"] == 10 and cov["static"]["not_run"] is False
    assert cov["mutation"]["ok"] == 6 and cov["mutation"]["insufficient"] == 2
    assert cov["rename"]["not_run"] is True and cov["history"]["not_run"] is True


# --- explanations are never read -----------------------------------------


class _Trap(dict):
    """An explain payload that fails the test if analysis looks at the explanation's content."""

    def _boom(self, *a, **k):
        raise AssertionError("analysis read an explanation payload")

    __getitem__ = get = items = values = keys = __iter__ = __contains__ = _boom  # type: ignore[assignment]


def _strip_volatile(doc):
    return {k: v for k, v in doc.items() if k != "generated_at"}


def test_explanation_actions_never_influence_the_analysis():
    """Scenario test-oracle-audit.38: with and without explanations, every metric and list is identical."""
    joined, labels = b.mixed_suite(40)
    baseline = _strip_volatile(run(joined, labels, seed=3))
    for action in ("keep", "delete_candidate"):
        with_explain = {nid: dict(stages) for nid, stages in joined.items()}
        for i in range(0, 40, 2):
            with_explain[b.nid(i)]["explain"] = b.explain_rec(i, action)
        assert _strip_volatile(run(with_explain, labels, seed=3)) == baseline


def test_explanation_payloads_are_not_even_opened():
    """Scenario test-oracle-audit.38: analysis does not read the explanation's action or prose."""
    joined, labels = b.mixed_suite(40)
    trapped = {nid: dict(stages) for nid, stages in joined.items()}
    for i in range(0, 40, 2):
        rec = b.explain_rec(i)
        trapped[b.nid(i)]["explain"] = StageRecord(rec.test_id, "explain", "ok", _Trap(rec.payload))
    run(trapped, labels)  # raises AssertionError if the payload is touched


def test_explanation_is_not_a_measured_approach_or_metric_subject():
    """Scenario test-oracle-audit.38: explain appears in neither approach_coverage nor any metric subject."""
    joined, labels = b.mixed_suite(40)
    for i in range(40):
        joined[b.nid(i)]["explain"] = b.explain_rec(i, "delete_candidate")
    doc = run(joined, labels)
    assert "explain" not in doc["approach_coverage"]
    assert not any("explain" in m["subject"] for m in doc["metrics"])


# --- reproducibility ------------------------------------------------------


def test_same_seed_gives_identical_confidence_intervals():
    """Scenario test-oracle-audit.46: running the analysis twice with the same seed and inputs."""
    joined, labels = b.mixed_suite(40)
    first, second = run(joined, labels, seed=5), run(joined, labels, seed=5)
    assert len([m for m in first["metrics"] if m["status"] == "ok"]) >= 3
    assert [m.get("ci95") for m in first["metrics"]] == [m.get("ci95") for m in second["metrics"]]
    assert _strip_volatile(first) == _strip_volatile(second)


def test_different_seeds_change_at_least_one_interval():
    """Scenario test-oracle-audit.46 (sanity): the analysis seed reaches the bootstrap."""
    joined, labels = b.mixed_suite(40)
    first, second = run(joined, labels, seed=1), run(joined, labels, seed=2)
    assert [m.get("ci95") for m in first["metrics"]] != [m.get("ci95") for m in second["metrics"]]


# --- shared cut-points, disagreements, open decisions --------------------


def test_tercile_cutpoints_are_written_per_suite_from_the_shared_helper():
    """Design D1 shared cut-points / D10: ``tercile_cutpoints[suite]`` equals thresholds.tercile_cutpoints
    over the numeric kill rates."""
    joined, labels = b.mixed_suite(40)
    rates = [r["mutation"].payload["kill_rate"] for r in joined.values()]
    expected = tercile_cutpoints([float(x) for x in rates if x != "insufficient"])
    doc = run(joined, labels)
    assert doc["tercile_cutpoints"][b.SUITE] == [pytest.approx(expected[0]), pytest.approx(expected[1])]


def test_disagreements_in_the_document_come_from_the_shared_classifier():
    """Scenario test-oracle-audit.47 / .48 via design D11: analysis embeds classify_disagreements output
    computed with the same cut-points and the configured thresholds."""
    joined, labels = b.mixed_suite(40)
    rates = [float(r["mutation"].payload["kill_rate"]) for r in joined.values()]
    expected = classify_disagreements(
        joined, labels, kill_rate_cuts=tercile_cutpoints(rates), thresholds=load_thresholds()
    )
    doc = run(joined, labels)
    assert {k: sorted(v) for k, v in doc["disagreements"].items()} == {k: sorted(v) for k, v in expected.items()}


def test_open_decisions_record_the_ratchet_options_and_the_marker_question():
    """Scenario test-oracle-audit.55 (design D13): analysis carries the fixed open decisions."""
    joined, labels = b.mixed_suite(20)
    decisions = run(joined, labels)["open_decisions"]
    assert len(decisions) >= 2
    ratchet = next(d for d in decisions if "ratchet" in d["id"])
    text = " ".join(ratchet["options"]).lower()
    assert "keep" in text
    assert "deletion manifest" in text
    assert "mutation-score ratchet" in text
    marker = next(d for d in decisions if "marker" in d["id"])
    assert "--strict-markers" in " ".join([marker["question"], marker["evidence"], *marker["options"]])
