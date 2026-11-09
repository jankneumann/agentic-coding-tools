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


# --- Codex review PR #552 thread 3: local provider resolution ------------------
# Two facts the profile must state correctly, which it previously got right only
# by accident (an unresolvable tier fell through `model is None: continue`).


def test_local_is_excluded_from_trust_boundary_archetypes(tmp_path):
    """`local` never appears for architect/reviewer/gatekeeper.

    agent-archetypes "Local Provider Archetype Trust Boundary": resolution for
    those archetypes MUST NOT return provider `local`. This must hold even when
    the roster defines every tier for `local`, so the exclusion cannot depend on
    the tier failing to resolve.
    """
    roster = tmp_path / "archetypes.yaml"
    roster.write_text(
        "schema_version: 4\n"
        "model_aliases:\n"
        "  local:\n"
        "    frontier: local-frontier\n"
        "    premium: local-premium\n"
        "    standard: local-standard\n"
        "    economy: local-economy\n"
        "archetypes:\n"
        "  architect:\n"
        "    model: frontier\n"
        "    system_prompt: a\n"
        "    write_capable: true\n"
        "  runner:\n"
        "    model: economy\n"
        "    system_prompt: r\n"
        "    write_capable: true\n"
        "phase_mapping:\n"
        "  PLAN: {archetype: architect}\n"
        "  INIT: {archetype: runner}\n",
        encoding="utf-8",
    )
    rows = build_dispatch_profile(
        "autopilot", "", roster_path=roster, dispatch_map={"autopilot": {"phases": ["*"], "direct": []}}
    )
    local_architect = [r for r in rows if r["provider"] == "local" and r["archetype"] == "architect"]
    assert local_architect == [], "trust boundary: local must not run architect"
    local_runner = [r for r in rows if r["provider"] == "local" and r["archetype"] == "runner"]
    assert local_runner, "runner is permitted on local and must still be listed"


def test_permitted_archetype_degrades_to_best_defined_tier(tmp_path):
    """A permitted archetype whose tier `local` omits degrades, it does not vanish.

    agent-archetypes: "Tiers omitted by the local roster SHALL resolve through
    the existing graceful-degradation rule (an omitted tier resolves to the
    provider's best defined tier)." Dropping the row would under-report which
    tiers actually run the skill.
    """
    roster = tmp_path / "archetypes.yaml"
    roster.write_text(
        "schema_version: 4\n"
        "model_aliases:\n"
        "  local:\n"
        "    standard: local-standard\n"
        "    economy: local-economy\n"
        "archetypes:\n"
        "  validator:\n"
        "    model: premium\n"
        "    system_prompt: v\n"
        "    write_capable: true\n"
        "phase_mapping:\n"
        "  VALIDATE: {archetype: validator}\n",
        encoding="utf-8",
    )
    rows = build_dispatch_profile(
        "autopilot", "", roster_path=roster, dispatch_map={"autopilot": {"phases": ["*"], "direct": []}}
    )
    local = [r for r in rows if r["provider"] == "local"]
    assert len(local) == 1, f"expected one degraded local row, got {local}"
    assert local[0]["model"] == "local-standard"
    assert local[0]["degraded_from"] == "premium"
