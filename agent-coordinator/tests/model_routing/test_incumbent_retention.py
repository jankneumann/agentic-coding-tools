"""Incumbent retention until routing evidence (retain-static-model-until-routing-evidence).

Pure unit tests over the resolver's evidence predicate (D1) and retention rule
(D2/D3). No DB, no network.
"""

from __future__ import annotations

import random

import pytest

from src.model_routing.exploration import ExplorationBudget, choose, choose_evidenced
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


# ── D4: exploration restricted to evidenced candidates ───────────────────────

def _ranked(*candidates: CandidateInput):
    ranked, _ = score_and_rank(list(candidates))
    return ranked


def _find(ranked, model: str):
    return next(c for c in ranked if c.model == model)


@pytest.mark.parametrize(
    "candidates",
    [
        # nothing evidenced
        (_cand("claude_code", "fable"), _cand("codex", "terra"), _cand("grok", "grok-5")),
        # exactly one evidenced candidate
        (
            _cand("claude_code", "fable"),
            _cand("codex", "terra", prior=0.3),
            _cand("grok", "grok-5"),
        ),
    ],
)
def test_exploration_never_fires_with_fewer_than_two_evidenced(candidates) -> None:
    ranked = _ranked(*candidates)
    base = _find(ranked, "fable")
    for seed in range(200):
        selection = choose_evidenced(base, ranked, epsilon=1.0, rng=random.Random(seed))
        assert selection.exploration is False
        assert selection.selected == base


def test_exploration_picks_only_evidenced_non_base_candidates() -> None:
    ranked = _ranked(
        _cand("claude_code", "fable"),
        _cand("codex", "terra", prior=0.2),
        _cand("antigravity", "gemini", prior=0.1),
        _cand("grok", "grok-5"),
    )
    base = _find(ranked, "fable")
    picks = set()
    for seed in range(200):
        selection = choose_evidenced(base, ranked, epsilon=1.0, rng=random.Random(seed))
        assert selection.exploration is True
        assert selection.selected.evidenced and selection.selected != base
        picks.add(selection.selected.model)
    assert picks == {"terra", "gemini"}


def test_evidenced_exploration_respects_the_existing_gates() -> None:
    ranked = _ranked(
        _cand("claude_code", "fable", prior=0.5), _cand("codex", "terra", prior=0.2)
    )
    base = _find(ranked, "fable")
    assert choose_evidenced(base, ranked, allow_exploration=False, epsilon=1.0).exploration is False
    exhausted = ExplorationBudget(pct_used=0.2, pct_cap=0.1)
    assert choose_evidenced(base, ranked, budget=exhausted, epsilon=1.0).exploration is False


def test_choose_is_unchanged_without_an_incumbent() -> None:
    # choose() itself is untouched: same pool, same seed, same outcome as before.
    ranked = _ranked(_cand("antigravity", "a"), _cand("codex", "b"), _cand("grok", "c"))
    outcomes = [choose(ranked, epsilon=0.5, rng=random.Random(s)) for s in range(50)]
    assert any(o.exploration for o in outcomes)
    assert all(o.selected in ranked for o in outcomes)
