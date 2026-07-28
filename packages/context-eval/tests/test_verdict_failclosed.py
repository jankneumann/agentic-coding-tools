"""The five clauses that make a verdict impossible to talk out of failing.

Each clause gets its own test, and every one of them is a *single mutation of a
run that otherwise passes*. That shape is deliberate. A test that builds a
broken run from scratch and asserts "fail" proves almost nothing — a composer
that returned ``fail`` unconditionally would satisfy it. Here the control
(:func:`test_a_complete_run_at_the_declared_tier_passes`) fixes everything else,
so each clause test proves that *this* clause is what flipped the verdict.

The clauses, and what each one is defending against:

1. **An unscored declared case fails the run.** gen-eval's runner drops an
   invalid scenario, a malformed file, a gather-exception and an exhausted
   budget out of ``verdicts`` without lowering ``pass_rate`` (design D2). Here a
   case that could not be measured stays in the denominator and fails the run.
2. **A declared-vs-scored mismatch is named.** The denominator comes from the
   manifest, never from what happened to survive.
3. **A declared gate with no composed result is ``missing_required_gate``.** The
   gate list is declared, not discovered — a gate that never ran is a failure
   rather than an absence nobody notices. ``fail_closed_regression`` was declared
   required by phase 2 with no task composing it, and this is the test that would
   have caught that before phase 6 misread it as a measured failure.
4. **A disabled service measured nothing.** Production
   ``GET /search/code/status`` returns ``{"available": false, "state":
   "disabled"}`` purely because ``CODE_SEARCH_ENABLED`` is unset —
   ``coordination_api.py:3418`` short-circuits before touching the database or an
   embedder (verified at this revision). A retrieval number taken in that state
   is a number about nothing, so it is a failure and not a result (design D17).
5. **A report produced below a gate's declared index tier fails that gate.**
   hit@5 over a hand-written vector is arithmetic about a fixture (design D9).

The corpus is the real one. Synthesising a corpus here would let this file drift
from the evidence the harness is actually judged against; mutating a real run is
the only version of this test that stays true.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"
CORPUS_ROOT = PACKAGE_ROOT / "corpus"
REPORT_SCHEMA = (
    REPO_ROOT
    / "openspec"
    / "contracts"
    / "semantic-context-evaluation"
    / "schemas"
    / "context-eval-report.schema.json"
)

if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))

from context_eval.loader import load_corpus  # noqa: E402
from context_eval.models import Case, Corpus, GateDeclaration  # noqa: E402
from context_eval.scoring.arms import Arm, RenderedHit, fallback_arm  # noqa: E402

#: The vocabulary is asserted as the CONTRACT's strings, not as the composer's
#: own constants. A test that imported the names it checks would agree with the
#: implementation by construction; these are the values a reader of the report
#: schema would look for.
PASS = "pass"
FAIL = "fail"
UNMEASURED = "unmeasured"
DENOMINATOR_MISMATCH = "denominator_mismatch"
MISSING_REQUIRED_GATE = "missing_required_gate"
INDEX_TIER_INSUFFICIENT = "index_tier_insufficient"
SERVICE_DISABLED_DURING_MEASUREMENT = "service_disabled_during_measurement"
APPARATUS_FAILURE = "apparatus_failure"

LIVE = "live"
NONE = "none"
RESOLVED = "resolved"
HTTP = "http"


def _verdict_module() -> Any:
    """The composer, or an ordinary test failure saying it does not exist yet.

    Imported through a helper rather than at module scope so the RED state of
    task 4.1 reads as "these N properties are unproven" instead of one opaque
    collection error — the same shape phase 2 used for the loader.
    """
    try:
        from context_eval import verdict
    except Exception as exc:  # noqa: BLE001 - any import problem is one failure
        pytest.fail(f"context_eval.verdict is not importable: {exc!r}")
    return verdict


# --------------------------------------------------------------------------
# a run that passes, so that one mutation at a time is what fails it
# --------------------------------------------------------------------------


def _corpus() -> Corpus:
    return load_corpus(CORPUS_ROOT)


def _measurement(**overrides: object) -> Any:
    fields: dict[str, object] = {
        "index_tier": LIVE,
        "code_search_enabled": True,
        "semantic_context_injection": True,
        "coordination_transport": HTTP,
        "scope_adapter": RESOLVED,
    }
    fields.update(overrides)
    return _verdict_module().MeasurementContext(**fields)


def _compose(corpus: Corpus, outcomes: list[Any], measurement: Any) -> Any:
    return _verdict_module().compose_verdict(corpus, outcomes, measurement)


def _span_hits(case: Case) -> tuple[RenderedHit, ...]:
    """One rendered excerpt per labelled evidence span, in label order.

    Every ``must_touch`` file of every case carries at least one span (asserted
    below), so an arm built this way covers every required file and renders
    nothing outside labelled evidence: coverage 1.0, density 1.0, first evidence
    at step 1. That is a deliberately ideal semantic arm — the point of the
    control is that the composer says ``pass`` when everything is right.
    """
    return tuple(
        RenderedHit(span.file_path, span.start_line, span.end_line)
        for span in case.labels.evidence_spans
    )


def _semantic_arm(case: Case) -> Arm:
    expectation = case.expectation
    if expectation is None:
        return Arm(arm="semantic", status="injected", hits=_span_hits(case))
    if expectation.status == "fallback":
        return fallback_arm("semantic", str(expectation.trigger), str(expectation.reason))

    # An injected expectation names an exact rendered-hit count (the adversarial
    # cases: three results recorded, two survive). Repeat the labelled spans up
    # to that count rather than inventing paths, so the arm stays inside scope.
    spans = _span_hits(case)
    wanted = expectation.rendered_hits or len(spans)
    hits = tuple(spans[index % len(spans)] for index in range(wanted))
    return Arm(arm="semantic", status="injected", hits=hits)


def _baseline_arm(case: Case) -> Arm:
    """The exact-search control, rendering nothing useful.

    A fallback is a legitimate scored outcome and gives coverage 0, density 0,
    censored read cost and no top-k hit — so every "semantic beats baseline"
    condition holds in the control and each clause test is free to move exactly
    one other thing.
    """
    del case
    return fallback_arm("baseline", "no_context", "index_returned_no_hits")


def _request_body(case: Case) -> dict[str, object] | None:
    """The outbound body ri-12 would build, or ``None`` when it never asked.

    A case with an empty ``read_allow`` short-circuits at
    ``out_of_scope``/``no_declared_scope`` before the wire, so there is no
    request to measure fidelity against — which the scope scorer models as
    ``None`` rather than as a failure.
    """
    if not case.scope.read_allow:
        return None
    return {
        "query": case.query,
        "scope": {
            "kind": "explicit",
            "read_allow": list(case.scope.read_allow),
            "deny": list(case.scope.deny),
        },
    }


def _outcome(case: Case) -> Any:
    return _verdict_module().CaseOutcome(
        case_id=case.case_id,
        consumer=case.consumer,
        scored=True,
        semantic=_semantic_arm(case),
        baseline=_baseline_arm(case),
        request_body=_request_body(case),
    )


def _complete_run(corpus: Corpus) -> list[Any]:
    return [_outcome(case) for case in corpus.cases]


def _by_id(outcomes: list[Any], case_id: str) -> int:
    for index, outcome in enumerate(outcomes):
        if outcome.case_id == case_id:
            return index
    raise AssertionError(f"{case_id} is not in the run")


def test_every_must_touch_file_carries_a_span() -> None:
    """The precondition the ideal arm above is built on, asserted not assumed."""
    for case in _corpus().cases:
        spanned = {span.file_path for span in case.labels.evidence_spans}
        assert set(case.labels.must_touch) <= spanned, case.case_id


# --------------------------------------------------------------------------
# the control
# --------------------------------------------------------------------------


def test_a_complete_run_at_the_declared_tier_passes() -> None:
    """Without this, every clause test below could pass on a composer that always fails."""
    corpus = _corpus()
    composed = _compose(corpus, _complete_run(corpus), _measurement())
    assert composed.verdict == PASS, composed.fail_reasons
    assert composed.fail_reasons == ()
    assert composed.cases_declared == composed.cases_scored == len(corpus.cases)


def test_the_control_composes_every_gate_the_manifest_declares() -> None:
    """All four, including ``fail_closed_regression`` — the one with no owning task."""
    corpus = _corpus()
    composed = _compose(corpus, _complete_run(corpus), _measurement())
    assert {gate.id for gate in composed.gates} == {gate.id for gate in corpus.gates}
    assert "fail_closed_regression" in {gate.id for gate in composed.gates}
    assert all(gate.verdict == PASS for gate in composed.gates), composed.gates


def test_every_composed_gate_carries_its_thresholds_and_measurements() -> None:
    """A gate a reader needs the harness source to interpret is not self-describing."""
    corpus = _corpus()
    composed = _compose(corpus, _complete_run(corpus), _measurement())
    declared = {gate.id: gate for gate in corpus.gates}
    for gate in composed.gates:
        assert dict(gate.thresholds) == dict(declared[gate.id].thresholds)
        assert gate.measured, gate.id
        assert gate.required is True


# --------------------------------------------------------------------------
# clause 1 — an unscored declared case
# --------------------------------------------------------------------------


def test_an_unscored_declared_case_fails_the_run() -> None:
    corpus = _corpus()
    outcomes = _complete_run(corpus)
    index = _by_id(outcomes, "T5")
    outcomes[index] = _verdict_module().CaseOutcome(
        case_id="T5",
        consumer=outcomes[index].consumer,
        scored=False,
        unscored_reason="producer_error",
    )

    composed = _compose(corpus, outcomes, _measurement())
    assert composed.verdict == FAIL
    assert UNMEASURED in composed.fail_reasons
    assert composed.cases_declared == len(corpus.cases)
    assert composed.cases_scored == len(corpus.cases) - 1


def test_the_pass_rate_is_never_computed_over_the_surviving_cases_alone() -> None:
    """The gen-eval failure mode, asserted directly (design D2, D3).

    Every retrieval case but one is dropped from the run. Under a derived
    denominator the survivor is a perfect 1/1 and the gate passes; under a
    declared denominator the run is missing eighteen measurements and fails.
    """
    corpus = _corpus()
    survivor = "T5"
    outcomes = [
        outcome if outcome.case_id == survivor
        else _verdict_module().CaseOutcome(
            case_id=outcome.case_id,
            consumer=outcome.consumer,
            scored=False,
            unscored_reason="producer_error",
        )
        for outcome in _complete_run(corpus)
    ]

    composed = _compose(corpus, outcomes, _measurement())
    assert composed.verdict == FAIL
    assert composed.cases_scored == 1
    assert composed.cases_declared == len(corpus.cases)


# --------------------------------------------------------------------------
# clause 2 — a declared-vs-scored denominator mismatch
# --------------------------------------------------------------------------


def test_a_declared_case_absent_from_the_run_is_a_denominator_mismatch() -> None:
    corpus = _corpus()
    outcomes = _complete_run(corpus)
    del outcomes[_by_id(outcomes, "T3")]

    composed = _compose(corpus, outcomes, _measurement())
    assert composed.verdict == FAIL
    assert DENOMINATOR_MISMATCH in composed.fail_reasons
    assert composed.cases_declared == len(corpus.cases)
    assert composed.cases_scored == len(corpus.cases) - 1


def test_a_case_the_corpus_never_declared_is_a_denominator_mismatch() -> None:
    """A mismatch in the other direction, and it must not cancel out.

    Dropping one declared case and adding one undeclared one leaves the counts
    equal, which is exactly how a derived denominator hides a substitution.
    """
    corpus = _corpus()
    outcomes = _complete_run(corpus)
    dropped = outcomes.pop(_by_id(outcomes, "T3"))
    outcomes.append(
        _verdict_module().CaseOutcome(
            case_id="T99-NOT-DECLARED",
            consumer=dropped.consumer,
            scored=True,
            semantic=dropped.semantic,
            baseline=dropped.baseline,
            request_body=dropped.request_body,
        )
    )

    composed = _compose(corpus, outcomes, _measurement())
    assert composed.verdict == FAIL
    assert DENOMINATOR_MISMATCH in composed.fail_reasons


# --------------------------------------------------------------------------
# clause 3 — a declared gate with no composed result
# --------------------------------------------------------------------------


def test_a_declared_gate_the_composer_cannot_compose_is_named() -> None:
    corpus = _corpus()
    extra = GateDeclaration(
        id="a_gate_nothing_implements",
        kind="a_kind_no_scorer_knows",
        required=True,
        min_index_tier=NONE,
        thresholds={"min_something": 0.5},
    )
    widened = dataclasses.replace(corpus, gates=(*corpus.gates, extra))

    composed = _compose(widened, _complete_run(corpus), _measurement())
    assert composed.verdict == FAIL
    assert MISSING_REQUIRED_GATE in composed.fail_reasons
    assert composed.missing_gates == ("a_gate_nothing_implements",)


def test_dropping_a_declared_gate_from_the_manifest_cannot_hide_it() -> None:
    """Every gate the corpus declares must appear in the composed result.

    This is the assertion that a composer which silently stopped composing
    ``fail_closed_regression`` would fail, rather than reporting three green
    gates and a pass.
    """
    corpus = _corpus()
    composed = _compose(corpus, _complete_run(corpus), _measurement())
    assert composed.missing_gates == ()
    for declaration in corpus.gates:
        assert declaration.id in {gate.id for gate in composed.gates}


# --------------------------------------------------------------------------
# clause 4 — the service was disabled while the measurement was taken
# --------------------------------------------------------------------------


def test_a_disabled_code_search_service_fails_the_retrieval_gate() -> None:
    corpus = _corpus()
    composed = _compose(corpus, _complete_run(corpus), _measurement(code_search_enabled=False))
    assert composed.verdict == FAIL
    assert SERVICE_DISABLED_DURING_MEASUREMENT in composed.fail_reasons

    retrieval = next(gate for gate in composed.gates if gate.kind == "retrieval_quality")
    assert retrieval.verdict == FAIL
    assert SERVICE_DISABLED_DURING_MEASUREMENT in retrieval.fail_reasons


def test_a_disabled_service_does_not_fail_the_client_side_gates() -> None:
    """Scope and fail-closed are measured from recorded responses (design D9).

    If a disabled service failed them too, the clause would be indistinguishable
    from "fail everything", and the report would stop naming which measurement
    was invalidated.
    """
    corpus = _corpus()
    composed = _compose(corpus, _complete_run(corpus), _measurement(code_search_enabled=False))
    for gate in composed.gates:
        if gate.min_index_tier == NONE:
            assert SERVICE_DISABLED_DURING_MEASUREMENT not in gate.fail_reasons, gate.id


# --------------------------------------------------------------------------
# clause 5 — a report produced below a gate's declared index tier
# --------------------------------------------------------------------------


def test_an_index_tier_below_a_gates_declaration_fails_that_gate() -> None:
    corpus = _corpus()
    composed = _compose(corpus, _complete_run(corpus), _measurement(index_tier=NONE))
    assert composed.verdict == FAIL
    assert INDEX_TIER_INSUFFICIENT in composed.fail_reasons

    for gate in composed.gates:
        if gate.min_index_tier == LIVE:
            assert gate.verdict == FAIL
            assert INDEX_TIER_INSUFFICIENT in gate.fail_reasons


def test_a_seeded_index_does_not_satisfy_a_gate_declaring_live() -> None:
    """"Seeded" is a registry row with no embedder ever contacted (design D9)."""
    corpus = _corpus()
    composed = _compose(corpus, _complete_run(corpus), _measurement(index_tier="seeded"))
    assert composed.verdict == FAIL
    assert INDEX_TIER_INSUFFICIENT in composed.fail_reasons


def test_a_tier_at_or_above_the_declaration_is_not_a_tier_failure() -> None:
    corpus = _corpus()
    composed = _compose(corpus, _complete_run(corpus), _measurement(index_tier=LIVE))
    assert INDEX_TIER_INSUFFICIENT not in composed.fail_reasons


# --------------------------------------------------------------------------
# the apparatus clause the scope gate already owns, at composition level
# --------------------------------------------------------------------------


def test_a_degraded_scope_adapter_fails_the_run() -> None:
    """Design D8: a compliance number computed under different glob semantics
    than the report claims is worse than no number at all."""
    corpus = _corpus()
    composed = _compose(
        corpus, _complete_run(corpus), _measurement(scope_adapter="degraded")
    )
    assert composed.verdict == FAIL
    assert APPARATUS_FAILURE in composed.fail_reasons


# --------------------------------------------------------------------------
# the closed vocabulary
# --------------------------------------------------------------------------


def test_every_fail_reason_comes_from_the_contracts_closed_vocabulary() -> None:
    """A reason invented at write time is a waiver with better spelling."""
    schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    allowed = set(schema["$defs"]["FailReason"]["enum"])

    corpus = _corpus()
    for measurement in (
        _measurement(),
        _measurement(index_tier=NONE),
        _measurement(code_search_enabled=False),
        _measurement(scope_adapter="degraded"),
    ):
        composed = _compose(corpus, _complete_run(corpus), measurement)
        assert set(composed.fail_reasons) <= allowed
        for gate in composed.gates:
            assert set(gate.fail_reasons) <= allowed


def test_the_verdict_has_exactly_two_values() -> None:
    corpus = _corpus()
    for measurement in (_measurement(), _measurement(index_tier=NONE)):
        composed = _compose(corpus, _complete_run(corpus), measurement)
        assert composed.verdict in (PASS, FAIL)


def test_a_failing_verdict_always_names_at_least_one_reason() -> None:
    """The schema requires it; the composer must never produce a bare failure."""
    corpus = _corpus()
    outcomes = _complete_run(corpus)
    del outcomes[0]
    composed = _compose(corpus, outcomes, _measurement())
    assert composed.verdict == FAIL
    assert len(composed.fail_reasons) >= 1


def test_a_passing_verdict_carries_no_reasons() -> None:
    corpus = _corpus()
    composed = _compose(corpus, _complete_run(corpus), _measurement())
    assert composed.verdict == PASS
    assert composed.fail_reasons == ()
