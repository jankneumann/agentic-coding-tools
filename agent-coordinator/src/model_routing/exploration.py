"""Exploration selection under a dual-ceiling budget (design D6).

Pure policy layer on top of ``resolver.score_and_rank``. Exploration = choosing a
lower-ranked candidate to gather posterior data, gated by two ceilings (share of
eligible tasks + monthly USD) and disabled for premium-ineligible phases. When
either ceiling is exhausted (or exploration is disallowed) selection is pure
exploitation — the top-ranked candidate.

Randomness is injected via ``rng`` so tests are deterministic (the workflow
Math.random ban does not apply to normal runtime code, but seedability keeps the
selection reproducible for provenance replay).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .resolver import ScoredCandidate

DEFAULT_EPSILON = 0.10


@dataclass(frozen=True)
class ExplorationBudget:
    """Dual-ceiling budget state (design D6)."""

    pct_used: float = 0.0        # 0..1 share of eligible tasks already explored
    pct_cap: float = 0.10
    usd_used: float = 0.0
    usd_cap: float = 0.0         # 0 disables the USD ceiling (pct-only)

    def exhausted(self) -> bool:
        if self.pct_cap > 0 and self.pct_used >= self.pct_cap:
            return True
        if self.usd_cap > 0 and self.usd_used >= self.usd_cap:
            return True
        return False


@dataclass(frozen=True)
class Selection:
    selected: ScoredCandidate
    exploration: bool
    reason: str  # provenance: why this selection path was taken


def choose(
    ranked: list[ScoredCandidate],
    *,
    allow_exploration: bool = True,
    premium_ineligible: bool = False,
    budget: ExplorationBudget | None = None,
    epsilon: float = DEFAULT_EPSILON,
    rng: random.Random | None = None,
) -> Selection | None:
    """Pick a candidate, exploiting by default and exploring within budget.

    Returns None only when ``ranked`` is empty (no feasible candidate).
    """
    if not ranked:
        return None

    top = ranked[0]
    if not allow_exploration:
        return Selection(top, False, "exploit:disallowed")
    if premium_ineligible:
        return Selection(top, False, "exploit:premium-ineligible")
    if budget is not None and budget.exhausted():
        return Selection(top, False, "exploit:budget-exhausted")
    if len(ranked) < 2:
        return Selection(top, False, "exploit:no-alternative")

    r = rng or random.Random()
    if r.random() < epsilon:
        # Explore: pick uniformly among the non-top candidates.
        idx = r.randrange(1, len(ranked))
        return Selection(ranked[idx], True, "explore:epsilon")
    return Selection(top, False, "exploit:epsilon")
