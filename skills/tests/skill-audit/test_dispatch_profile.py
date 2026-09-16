"""Dispatch profile follows the roster (spec scenario; design D4)."""
from __future__ import annotations

from pathlib import Path

import yaml

from archetype_roster import clear_archetypes_raw_cache, resolve_tier_for_provider
from dispatch_profile import (
    archetypes_for_skill,
    archetypes_from_text,
    build_dispatch_profile,
    load_dispatch_map,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROSTER = FIXTURES / "archetypes.yaml"
RAW = yaml.safe_load(ROSTER.read_text())


def setup_module(module):
    clear_archetypes_raw_cache()


def test_every_provider_in_the_file_appears():
    rows = build_dispatch_profile("autopilot", "", roster_path=ROSTER)
    assert {r["provider"] for r in rows} == set(RAW["model_aliases"].keys())


def test_tuples_equal_archetype_roster_resolution():
    rows = build_dispatch_profile("autopilot", "", roster_path=ROSTER)
    assert rows, "autopilot runs every phase"
    for row in rows:
        expected_tier = RAW["archetypes"][row["archetype"]]["model"]
        assert row["tier"] == expected_tier
        model, thinking = resolve_tier_for_provider(row["provider"], row["tier"], path=ROSTER)
        assert (row["model"], row["thinking"]) == (model, thinking)
    # Both roster shapes are exercised: bare ids and {model, thinking}.
    codex_architect = next(r for r in rows if r["archetype"] == "architect" and r["provider"] == "codex")
    assert codex_architect["thinking"] == "xhigh"
    claude_impl = next(r for r in rows if r["archetype"] == "implementer" and r["provider"] == "claude_code")
    assert (claude_impl["model"], claude_impl["thinking"]) == ("sonnet", None)


def test_missing_frontier_degrades_to_premium_with_note():
    rows = build_dispatch_profile("autopilot", "", roster_path=ROSTER)
    ag = next(r for r in rows if r["archetype"] == "architect" and r["provider"] == "antigravity")
    assert ag["model"] == RAW["model_aliases"]["antigravity"]["premium"]
    assert ag["degraded_from"] == "frontier"
    cc = next(r for r in rows if r["archetype"] == "architect" and r["provider"] == "claude_code")
    assert cc["degraded_from"] is None
    # A provider lacking the tier altogether gets no row for that archetype.
    assert not any(r["archetype"] == "architect" and r["provider"] == "local" for r in rows)


def test_procedure_mode_reported_when_present_else_null():
    rows = build_dispatch_profile("autopilot", "", roster_path=ROSTER)
    by_archetype = {r["archetype"]: r["procedure_mode"] for r in rows}
    assert by_archetype["runner"] == RAW["archetypes"]["runner"]["procedure_mode"]
    assert by_archetype["architect"] == RAW["archetypes"]["architect"]["procedure_mode"]
    assert by_archetype["implementer"] is None


def test_phases_are_listed_per_archetype():
    profile = archetypes_for_skill("autopilot", "", roster_path=ROSTER)
    assert sorted(profile["runner"]) == ["INIT", "SUBMIT_PR"]
    assert sorted(profile["reviewer"]) == ["IMPL_REVIEW", "PLAN_REVIEW"]
    plan = archetypes_for_skill("plan-feature", "", roster_path=ROSTER)
    assert plan["architect"] == ["PLAN"]  # PLAN_ITERATE unknown to the fixture roster
    assert plan["analyst"] == []  # direct dispatch


def test_dispatch_map_parses_from_reference():
    table = load_dispatch_map()
    assert table["autopilot"]["phases"] == ["*"]
    assert table["fix-scrub"] == {"phases": [], "direct": ["implementer"]}


def test_non_lifecycle_skill_reads_its_own_dispatch_tokens():
    text = (
        "```python\nTask(subagent_type='Explore', model=analyst_model, prompt='x')\n```\n"
        "archetype: implementer\narchetype=\"nonexistent\"\n"
    )
    assert archetypes_from_text(text, {"analyst", "implementer"}) == ["implementer", "analyst"]
    rows = build_dispatch_profile("some-skill", text, roster_path=ROSTER)
    assert {r["archetype"] for r in rows} == {"analyst", "implementer"}
    assert build_dispatch_profile("quiet-skill", "no dispatch here", roster_path=ROSTER) == []
