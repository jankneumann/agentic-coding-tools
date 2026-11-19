"""The audit guide agrees with the table, and older statements agree with both.

The guide is hand-written (design D1), so this checks that it names every
vendor and lane in the table and says which mechanics are not yet observed.
The two documents that stated subscription terms before the audit are checked
for the corrections the audit required (design D7).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
_GUIDES = _REPO / "docs" / "guides"
_TABLE = _GUIDES / "vendor-auth-audit.yaml"
_GUIDE = _GUIDES / "vendor-auth-audit.md"
_INDEX = _GUIDES / "documentation.md"
_STRATEGY = _REPO / "openspec" / "roadmaps" / "sandboxed-flow" / "claude-auth-strategy.md"
_FACTORY = _REPO / "docs" / "proposals" / "factory-local-cloud-split.md"

MECHANICS = ("credential_material", "refresh_writes", "hosts", "proxy_override")


def _flat(text: str) -> str:
    return " ".join(text.split())


@pytest.fixture(scope="module")
def table() -> dict[str, Any]:
    assert _TABLE.is_file(), "docs/guides/vendor-auth-audit.yaml is missing"
    return yaml.safe_load(_TABLE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def guide() -> str:
    assert _GUIDE.is_file(), "docs/guides/vendor-auth-audit.md is missing"
    return _GUIDE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def strategy() -> str:
    return _flat(_STRATEGY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def factory() -> str:
    return _flat(_FACTORY.read_text(encoding="utf-8"))


# --- Scenario: The guide covers every vendor and lane ---


def test_guide_names_every_vendor(table: dict[str, Any], guide: str) -> None:
    for vendor in table["vendors"]:
        assert f"`{vendor}`" in guide, vendor


def test_guide_names_every_lane(table: dict[str, Any], guide: str) -> None:
    lanes = {lane for vendor in table["vendors"].values() for lane in vendor["lanes"]}
    for lane in lanes:
        assert f"`{lane}`" in guide, lane


def test_guide_states_each_verdict_from_the_table(
    table: dict[str, Any], guide: str
) -> None:
    """One table row per vendor and lane, carrying the table's verdict."""
    for vendor, record in table["vendors"].items():
        for lane, lane_record in record["lanes"].items():
            row = re.search(
                rf"^\|\s*`{vendor}`\s*\|\s*`{lane}`\s*\|\s*(\w+)\s*\|", guide, re.MULTILINE
            )
            assert row, f"no row for {vendor} {lane}"
            assert row.group(1) == lane_record["subscription"], f"{vendor} {lane}"


def test_guide_states_which_mechanics_are_not_observed(
    table: dict[str, Any], guide: str
) -> None:
    flat = _flat(guide)
    assert "not yet observed" in flat
    for vendor, record in table["vendors"].items():
        for name in MECHANICS:
            if record["mechanics"][name]["evidence"] == "observed":
                continue
            row = re.search(
                rf"^\|\s*`{vendor}`\s*\|\s*`{name}`\s*\|\s*(\w+)\s*\|", guide, re.MULTILINE
            )
            assert row, f"no mechanics row for {vendor} {name}"
            assert row.group(1) == record["mechanics"][name]["evidence"]


def test_guide_states_the_retrieval_date(table: dict[str, Any], guide: str) -> None:
    assert str(table["retrieved"]) in guide


def test_guide_does_not_present_summarised_quotes_as_verified(guide: str) -> None:
    flat = _flat(guide)
    assert "`summarised`" in flat
    assert "not verified" in flat


def test_guide_points_to_the_observation_script(guide: str) -> None:
    assert "skills/vendor-status/scripts/observe_vendor_auth.py" in guide


def test_guide_is_indexed() -> None:
    assert "(vendor-auth-audit.md)" in _INDEX.read_text(encoding="utf-8")


# --- Scenario: The Claude strategy note records its verification ---


def test_strategy_states_the_date_its_quotes_were_checked(
    table: dict[str, Any], strategy: str
) -> None:
    assert f"checked against the live pages on {table['retrieved']}" in strategy


def test_strategy_does_not_say_quotes_are_still_to_be_verified(strategy: str) -> None:
    lowered = strategy.lower()
    assert "must re-verify" not in lowered
    assert "still to be verified" not in lowered
    assert "still to be audited" not in lowered
    assert "the raw html was not inspected" not in lowered


def test_strategy_points_to_the_audit(strategy: str) -> None:
    assert "docs/guides/vendor-auth-audit.md" in strategy


# --- Scenario: The factory proposal no longer cites the wrong reason ---


def test_factory_does_not_cite_the_subscription_terms_as_the_reason(
    factory: str,
) -> None:
    assert "in line with the subscription terms" not in factory


def test_factory_references_the_audit(factory: str) -> None:
    assert "docs/guides/vendor-auth-audit.md" in factory
