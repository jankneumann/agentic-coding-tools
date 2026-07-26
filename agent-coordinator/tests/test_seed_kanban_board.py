"""Tests for the kanban demo seeder roster (add-agy-grok-pi-harnesses task 2.7).

The seeder plants demo cards with `vendor:<name>` swimlane labels. After the
roster migration it must exercise the full five-vendor board — claude, codex,
antigravity, grok, pi — and never seed the retired gemini vendor.
"""

from __future__ import annotations

import scripts.seed_kanban_board as seed

EXPECTED_VENDORS = {"claude", "codex", "antigravity", "grok", "pi"}


def test_vendors_are_the_five_vendor_roster() -> None:
    assert set(seed.VENDORS) == EXPECTED_VENDORS
    assert "gemini" not in seed.VENDORS


def test_seed_set_swimlanes_cover_every_vendor() -> None:
    """Every vendor swimlane is populated so the demo board shows all five."""
    seeded_vendors = {
        issue.vendor for issue in seed.SEED_SET if issue.vendor is not None
    }
    assert seeded_vendors == EXPECTED_VENDORS


def test_seed_set_never_references_a_retired_vendor() -> None:
    seeded_vendors = {
        issue.vendor for issue in seed.SEED_SET if issue.vendor is not None
    }
    assert seeded_vendors <= set(seed.VENDORS)
    assert "gemini" not in seeded_vendors
