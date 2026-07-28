"""Retrieval relevance, and the two confusions it exists to prevent.

**A win is measured, not labelled.** The archived evaluation defined its second
gate clause twice — ``run_eval.py:161`` counted baseline misses observed in the
run, its corpus header called the same clause ``category=semantic-win``. Under
the label reading, a corpus author manufactures wins by editing a string. These
tests hold the measured reading in place two ways: an experiment where the only
difference between two runs is the label, and a structural check that the string
``category`` appears nowhere in the scoring modules at all.

**Coverage is not hit rate.** Finding one of three required files is a top-k hit
and is one third of the coverage. A harness that collapsed them would report a
task as solved because a file that mentions the right words turned up.

Thresholds are read from ``corpus/manifest.yaml`` and never typed here. A test
that restated ``>= 7`` would keep passing after someone lowered the bar.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"
SCORING = SRC / "context_eval" / "scoring"

if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))

from context_eval.loader import load_corpus  # noqa: E402
from context_eval.models import Case, CaseLabels, Scope  # noqa: E402
from context_eval.scoring import relevance  # noqa: E402
from context_eval.scoring.arms import Arm, RenderedHit, fallback_arm  # noqa: E402


def _corpus():
    return load_corpus(PACKAGE_ROOT / "corpus")


def _retrieval_thresholds():
    """The declared bar, from the manifest. Never restated in this file."""
    gate = next(g for g in _corpus().gates if g.kind == "retrieval_quality")
    return gate.thresholds


def _arm(*files: str, name: str = "semantic") -> Arm:
    """A rendered arm over *files*, one four-line excerpt each, in the given order."""
    return Arm(
        arm=name,
        status="injected",
        hits=tuple(RenderedHit(path, 1, 4) for path in files),
    )


def _case(
    *,
    case_id: str = "C1",
    expected_files: tuple[str, ...] = ("a.py",),
    must_touch: tuple[str, ...] = ("a.py",),
    category: str = "control",
) -> Case:
    return Case(
        case_id=case_id,
        consumer="implement-feature",
        query="anything",
        category=category,
        scope=Scope(read_allow=("**",), deny=()),
        labels=CaseLabels(
            expected_files=expected_files,
            must_touch=must_touch,
            evidence_spans=(),
        ),
        rationale="fixture",
        source_path=f"cases/{case_id}.yaml",
    )


def _relevance(
    *, semantic_hit: bool, baseline_hit: bool, case_id: str = "C1"
) -> relevance.CaseRelevance:
    return relevance.CaseRelevance(
        case_id=case_id,
        consumer="implement-feature",
        semantic_hit_at_k=semantic_hit,
        baseline_hit_at_k=baseline_hit,
        semantic_must_touch_coverage=1.0 if semantic_hit else 0.0,
        baseline_must_touch_coverage=1.0 if baseline_hit else 0.0,
    )


# --------------------------------------------------------------------------
# hit@k preserves the archived definition
# --------------------------------------------------------------------------


def test_any_expected_file_in_the_top_k_is_a_hit() -> None:
    arm = _arm("x.py", "a.py", "y.py")
    assert relevance.hit_at_k(arm, ("a.py", "b.py"), k=3) is True


def test_a_file_ranked_below_k_is_not_a_hit() -> None:
    """The k in hit@k is a bound on what the reader actually sees."""
    arm = _arm("x.py", "y.py", "a.py")
    assert relevance.hit_at_k(arm, ("a.py",), k=2) is False


def test_a_fallback_arm_is_scored_as_a_miss_not_skipped() -> None:
    arm = fallback_arm("semantic", "stale", "revision_not_indexed")
    assert relevance.hit_at_k(arm, ("a.py",), k=5) is False
    assert relevance.must_touch_coverage(arm, ("a.py",)) == 0.0


def test_hit_at_k_refuses_a_case_with_no_labelled_expected_files() -> None:
    with pytest.raises(relevance.ScoringError):
        relevance.hit_at_k(_arm("a.py"), (), k=5)


# --------------------------------------------------------------------------
# coverage is a different measure from hit rate
# --------------------------------------------------------------------------


def test_finding_one_of_three_required_files_is_a_hit_but_not_full_coverage() -> None:
    """The spec scenario, literally: a task needing three files is not solved by one."""
    arm = _arm("a.py")
    expected = ("a.py", "b.py", "c.py")
    assert relevance.hit_at_k(arm, expected, k=5) is True
    assert relevance.must_touch_coverage(arm, expected) == pytest.approx(1 / 3)


def test_full_coverage_requires_every_required_file() -> None:
    arm = _arm("a.py", "b.py", "c.py")
    assert relevance.must_touch_coverage(arm, ("a.py", "b.py", "c.py")) == 1.0


def test_coverage_counts_required_files_not_rendered_files() -> None:
    """Rendering ten irrelevant files does not improve coverage of the two needed."""
    arm = _arm("a.py", *[f"noise{n}.py" for n in range(9)])
    assert relevance.must_touch_coverage(arm, ("a.py", "b.py")) == 0.5


def test_coverage_refuses_a_case_with_no_required_files() -> None:
    """Neither 0.0 nor 1.0 may be chosen silently for "nothing was required"."""
    with pytest.raises(relevance.ScoringError):
        relevance.must_touch_coverage(_arm("a.py"), ())


# --------------------------------------------------------------------------
# wins are measured, not labelled
# --------------------------------------------------------------------------


def test_a_win_requires_the_baseline_to_have_missed_in_this_run() -> None:
    assert _relevance(semantic_hit=True, baseline_hit=False).measured_win_over_baseline is True
    assert _relevance(semantic_hit=True, baseline_hit=True).measured_win_over_baseline is False
    assert _relevance(semantic_hit=False, baseline_hit=False).measured_win_over_baseline is False


def test_the_category_label_cannot_manufacture_a_win() -> None:
    """Same measurements, opposite labels, identical result.

    ``semantic-win`` is the archived corpus's own label and is the one an
    implementation reading labels would key on. Here the baseline HITS, so the
    measured answer is "no win" regardless of what the label predicted.
    """
    semantic = _arm("a.py")
    baseline = _arm("a.py", name="baseline")

    labelled = relevance.score_case(
        _case(category="semantic-win"), semantic=semantic, baseline=baseline, k=5
    )
    unlabelled = relevance.score_case(
        _case(category="control"), semantic=semantic, baseline=baseline, k=5
    )

    assert labelled == unlabelled
    assert labelled.measured_win_over_baseline is False


def test_no_scoring_module_reads_a_case_category() -> None:
    """Structural, not behavioural. A label no scoring path can see cannot leak.

    Checked as source text rather than by experiment because an implementation
    could read the label on a path no fixture happens to exercise, and the
    experiment above would stay green.
    """
    modules = sorted(SCORING.rglob("*.py"))
    assert modules, f"no scoring modules found under {SCORING}"
    offenders: list[str] = []
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "category":
                offenders.append(f"{module.name}:{node.lineno}: reads .category")
            if isinstance(node, ast.Constant) and node.value == "category":
                offenders.append(f"{module.name}:{node.lineno}: names 'category'")
    assert not offenders, "\n".join(offenders)


# --------------------------------------------------------------------------
# the gate, judged against manifest thresholds
# --------------------------------------------------------------------------


def test_the_gate_passes_when_both_declared_thresholds_are_met() -> None:
    thresholds = _retrieval_thresholds()
    hits = int(thresholds[relevance.MIN_HIT_AT_K_COUNT])
    wins = int(thresholds[relevance.MIN_MEASURED_WINS])

    per_case = [
        _relevance(semantic_hit=True, baseline_hit=index >= wins, case_id=f"T{index}")
        for index in range(hits)
    ]
    result = relevance.score_relevance(per_case, thresholds)
    assert result.verdict == "pass"
    assert result.fail_reasons == ()
    assert result.measured["hit_at_k_count"] == hits
    assert result.measured["measured_wins_over_baseline"] == wins


def test_one_hit_short_of_the_declared_count_fails() -> None:
    thresholds = _retrieval_thresholds()
    hits = int(thresholds[relevance.MIN_HIT_AT_K_COUNT]) - 1
    wins = int(thresholds[relevance.MIN_MEASURED_WINS])
    per_case = [
        _relevance(semantic_hit=True, baseline_hit=index >= wins, case_id=f"T{index}")
        for index in range(hits)
    ]
    result = relevance.score_relevance(per_case, thresholds)
    assert result.verdict == "fail"
    assert result.fail_reasons == (relevance.RETRIEVAL_BELOW_THRESHOLD,)


def test_plenty_of_hits_with_too_few_measured_wins_still_fails() -> None:
    """The second clause is independent: beating the bar on volume is not enough."""
    thresholds = _retrieval_thresholds()
    hits = int(thresholds[relevance.MIN_HIT_AT_K_COUNT])
    wins = int(thresholds[relevance.MIN_MEASURED_WINS]) - 1
    per_case = [
        _relevance(semantic_hit=True, baseline_hit=index >= wins, case_id=f"T{index}")
        for index in range(hits)
    ]
    result = relevance.score_relevance(per_case, thresholds)
    assert result.verdict == "fail"


def test_the_gate_carries_the_thresholds_it_was_judged_against() -> None:
    """A reader must not need the harness source to interpret a gate result."""
    thresholds = _retrieval_thresholds()
    result = relevance.score_relevance(
        [_relevance(semantic_hit=True, baseline_hit=False)], thresholds
    )
    assert dict(result.thresholds) == dict(thresholds)


def test_a_missing_threshold_is_an_error_not_a_default() -> None:
    with pytest.raises(relevance.ScoringError):
        relevance.score_relevance([_relevance(semantic_hit=True, baseline_hit=False)], {})


def test_scoring_zero_cases_is_an_error_not_a_vacuous_pass() -> None:
    with pytest.raises(relevance.ScoringError):
        relevance.score_relevance([], _retrieval_thresholds())


# --------------------------------------------------------------------------
# which cases the gate is computed over
# --------------------------------------------------------------------------


def test_retrieval_cases_are_the_ones_that_assert_no_specific_outcome() -> None:
    corpus = _corpus()
    selected = relevance.retrieval_cases(corpus.cases)
    assert {case.case_id for case in selected} == {f"T{n}" for n in range(1, 11)}
    assert all(case.expectation is None for case in selected)


def test_every_retrieval_case_carries_the_labels_the_measures_need() -> None:
    """Otherwise the gate would raise mid-run on a corpus that loaded cleanly."""
    for case in relevance.retrieval_cases(_corpus().cases):
        assert case.labels.expected_files, f"{case.case_id} has no expected_files"
        assert case.labels.must_touch, f"{case.case_id} has no must_touch"
