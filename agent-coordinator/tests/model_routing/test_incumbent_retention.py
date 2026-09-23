"""Incumbent retention until routing evidence (retain-static-model-until-routing-evidence).

Pure unit tests over the resolver's evidence predicate (D1) and retention rule
(D2/D3). No DB, no network.
"""

from __future__ import annotations

import pytest

from src.model_routing.resolver import (
    CandidateInput,
    IncumbentIdentity,
    Posterior,
    apply_incumbent_retention,
    has_evidence,
    score_and_rank,
)

INCUMBENT = IncumbentIdentity(vendor="claude_code", model="fable")


def _cand(
    vendor: str,
    model: str,
    *,
    prior: float = 0.0,
    samples: float = 0.0,
    quality: float | None = None,
    endpoint_kind: str = "vendor-cli",
    available: bool = True,
) -> CandidateInput:
    return CandidateInput(
        vendor=vendor,
        model=model,
        endpoint_kind=endpoint_kind,
        benchmark_prior=prior,
        posterior=Posterior(quality=quality, sample_size=samples),
        available=available,
    )


def _retain(candidates: list[CandidateInput], margin: float = 0.05, incumbent=INCUMBENT):
    ranked, excluded = score_and_rank(candidates)
    excluded_identities = [(c.vendor, c.model) for c, _reason in excluded]
    return ranked, apply_incumbent_retention(ranked, excluded_identities, incumbent, margin)


# ── D1: evidence predicate ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("prior", "samples", "expected"),
    [
        (0.0, 0.0, False),   # neither
        (0.4, 0.0, True),    # prior only
        (0.0, 1.0, True),    # samples only
        (0.4, 3.0, True),    # both
        (0.0, 0.5, False),   # a fractional sample is not an observed outcome
    ],
)
def test_has_evidence(prior: float, samples: float, expected: bool) -> None:
    assert has_evidence(_cand("codex", "terra", prior=prior, samples=samples)) is expected


def test_score_and_rank_marks_evidenced_candidates() -> None:
    ranked, _ = score_and_rank(
        [_cand("codex", "terra", prior=0.5), _cand("grok", "grok-5")]
    )
    flags = {(c.vendor, c.model): c.evidenced for c in ranked}
    assert flags == {("codex", "terra"): True, ("grok", "grok-5"): False}


# ── D3: retention table ──────────────────────────────────────────────────────

def test_empty_catalog_evidence_keeps_incumbent_despite_alphabetical_order() -> None:
    # The motivating failure: every candidate scores the same, and "antigravity"
    # sorts first. The incumbent must still win.
    ranked, decision = _retain(
        [
            _cand("antigravity", "gemini-3.6-flash-low"),
            _cand("claude_code", "fable"),
            _cand("codex", "terra"),
        ]
    )
    assert len({c.score for c in ranked}) == 1  # precondition: a three-way tie
    assert decision.retained is True
    assert decision.reason == "no-evidence"
    assert decision.selected is not None
    assert (decision.selected.vendor, decision.selected.model) == ("claude_code", "fable")


def test_evidenced_challenger_below_margin_keeps_incumbent() -> None:
    _, decision = _retain(
        [_cand("claude_code", "fable"), _cand("codex", "terra", prior=0.05)], margin=0.05
    )
    assert decision.retained is True
    assert decision.reason == "below-margin"
    assert decision.selected is not None and decision.selected.model == "fable"


def test_evidenced_challenger_above_margin_displaces_incumbent() -> None:
    _, decision = _retain(
        [_cand("claude_code", "fable"), _cand("codex", "terra", prior=0.9)], margin=0.05
    )
    assert decision.retained is False
    assert decision.reason == "challenger-evidenced-above-margin"
    assert decision.selected is not None and decision.selected.model == "terra"
    assert decision.incumbent_score is not None


def test_exact_tie_at_zero_margin_goes_to_incumbent() -> None:
    _, decision = _retain(
        [_cand("claude_code", "fable", prior=0.5), _cand("codex", "terra", prior=0.5)],
        margin=0.0,
    )
    assert decision.retained is True
    assert decision.reason == "below-margin"
    assert decision.selected is not None and decision.selected.model == "fable"


def test_unevidenced_higher_scorer_never_displaces_incumbent() -> None:
    # A challenger may outscore the incumbent on cost/latency alone; without
    # evidence it still must not win.
    challenger = CandidateInput(
        vendor="codex", model="terra", endpoint_kind="vendor-cli",
        prompt_usd_per_mtok=0.1, completion_usd_per_mtok=0.1,
    )
    incumbent = CandidateInput(
        vendor="claude_code", model="fable", endpoint_kind="vendor-cli",
        prompt_usd_per_mtok=10.0, completion_usd_per_mtok=10.0,
    )
    ranked, decision = _retain([challenger, incumbent], margin=0.0)
    assert ranked[0].model == "terra"
    assert decision.retained is True
    assert decision.reason == "no-evidence"


def test_unresolvable_incumbent_keeps_static_with_null_selection() -> None:
    _, decision = _retain(
        [_cand("codex", "terra", prior=0.9)],
        incumbent=IncumbentIdentity(vendor=None, model="premium"),
    )
    assert decision.retained is True
    assert decision.reason == "incumbent-unresolved"
    assert decision.selected is None
    assert decision.incumbent_score is None


def test_incumbent_missing_from_catalog_is_unresolved() -> None:
    _, decision = _retain([_cand("codex", "terra", prior=0.9)])
    assert decision.reason == "incumbent-unresolved"
    assert decision.selected is None


def test_infeasible_incumbent_with_evidenced_alternative_switches() -> None:
    _, decision = _retain(
        [
            _cand("claude_code", "fable", available=False),
            _cand("codex", "terra", prior=0.3),
            _cand("grok", "grok-5"),
        ]
    )
    assert decision.retained is False
    assert decision.reason == "incumbent-infeasible-evidenced-alternative"
    assert decision.selected is not None and decision.selected.model == "terra"


def test_infeasible_incumbent_without_evidenced_alternative_keeps_static() -> None:
    _, decision = _retain(
        [_cand("claude_code", "fable", available=False), _cand("codex", "terra")]
    )
    assert decision.retained is True
    assert decision.reason == "incumbent-infeasible-no-evidenced-alternative"
    assert decision.selected is None


def test_duplicate_incumbent_rows_use_the_best_score() -> None:
    _, decision = _retain(
        [
            _cand("claude_code", "fable", prior=0.2, endpoint_kind="vendor-cli"),
            _cand("claude_code", "fable", prior=0.6, endpoint_kind="vendor-sdk"),
            _cand("codex", "terra", prior=0.62),
        ],
        margin=0.05,
    )
    # Against the SDK row's 0.6 prior the challenger's 0.62 is inside the margin.
    assert decision.reason == "below-margin"
    assert decision.selected is not None and decision.selected.endpoint_kind == "vendor-sdk"
