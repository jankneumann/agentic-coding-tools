"""wp-dispatch policy tests (tasks 4.3, 4.5) — OpenSpec add-adaptive-model-router.

Covers the catalog-aware cost model (D7, replacing the hardcoded stub) with its
static fallback + source labelling, and roadmap exploration gating (D6).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "autopilot-roadmap" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_RUNTIME = Path(__file__).resolve().parents[2] / "roadmap-runtime" / "scripts"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

import policy as policy_mod  # noqa: E402
from models import Policy  # noqa: E402
from policy import (  # noqa: E402
    _estimate_cost_delta_with_source,
    set_catalog_pricing,
    should_allow_exploration,
)


# ── D7: catalog-priced cost model with static fallback + source labelling ─────

def test_static_fallback_when_no_catalog():
    delta, source = _estimate_cost_delta_with_source("antigravity", "openai")
    assert source == "static"
    assert delta == 0.6  # 1.2 - 0.6


def test_catalog_pricing_used_when_available():
    prices = {"claude": 3.0, "codex": 1.0}
    delta, source = _estimate_cost_delta_with_source(
        "claude", "codex", pricing=prices.get
    )
    assert source == "catalog"
    assert delta == -2.0  # codex cheaper than claude by 2.0


def test_catalog_miss_falls_back_to_static():
    # Catalog knows neither vendor → fall back to static tiers.
    delta, source = _estimate_cost_delta_with_source(
        "claude", "codex", pricing=lambda v: None
    )
    assert source == "static"
    assert delta == -0.2  # 0.8 - 1.0


def test_unknown_vendor_yields_none():
    delta, source = _estimate_cost_delta_with_source("claude", "mystery-vendor")
    assert delta is None
    assert source == "unknown"


def test_module_level_catalog_hook_roundtrip():
    try:
        set_catalog_pricing({"claude": 5.0, "antigravity": 2.0}.get)
        delta, source = _estimate_cost_delta_with_source("claude", "antigravity")
        assert source == "catalog"
        assert delta == -3.0
        # Legacy entrypoint reflects the wired catalog too.
        assert policy_mod._estimate_cost_delta("claude", "antigravity") == -3.0
    finally:
        set_catalog_pricing(None)  # restore default (Rule 4 safe default)
    # After reset, static tiers apply again.
    _, source = _estimate_cost_delta_with_source("claude", "antigravity")
    assert source == "static"


# ── D6: roadmap exploration gating ───────────────────────────────────────────

def test_default_policy_allows_exploration():
    assert should_allow_exploration(Policy()) is True


def test_preferred_vendor_disables_exploration():
    assert should_allow_exploration(Policy(preferred_vendor="claude")) is False


def test_zero_cost_ceiling_disables_exploration():
    assert should_allow_exploration(Policy(cost_ceiling_usd=0.0)) is False


def test_positive_cost_ceiling_allows_exploration():
    assert should_allow_exploration(Policy(cost_ceiling_usd=5.0)) is True
