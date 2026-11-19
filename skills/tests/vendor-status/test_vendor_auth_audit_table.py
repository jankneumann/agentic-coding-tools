"""The vendor auth audit table carries a verdict and its evidence per lane.

The table is the source for the audit guide and for later roadmap items that
decide which credential a lane may use, so its shape is checked here rather
than trusted: a verdict without its governing sentence, or a mechanics claim
without an evidence level, fails.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
_TABLE = _REPO / "docs" / "guides" / "vendor-auth-audit.yaml"

VENDORS = ("claude", "codex", "antigravity", "grok")
LANES = ("interactive", "attended_headless", "unattended_daemon", "ci")
UNATTENDED = ("unattended_daemon", "ci")
VERDICTS = {"permitted", "prohibited", "unaddressed"}
KEYED_LANES = {"api-key", "gateway-key"}
MECHANICS = ("credential_material", "refresh_writes", "hosts", "proxy_override")
EVIDENCE = {"observed", "documented", "not_observed"}


@pytest.fixture(scope="module")
def table() -> dict[str, Any]:
    assert _TABLE.is_file(), "docs/guides/vendor-auth-audit.yaml is missing"
    loaded = yaml.safe_load(_TABLE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _lane_records(table: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (vendor, lane, table["vendors"][vendor]["lanes"][lane])
        for vendor in VENDORS
        for lane in LANES
    ]


def _mechanics_fields(table: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (vendor, name, table["vendors"][vendor]["mechanics"][name])
        for vendor in VENDORS
        for name in MECHANICS
    ]


def _is_https(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://") and len(value) > 8


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


# --- Scenario: Every vendor has every lane ---


def test_table_has_exactly_the_four_vendors(table: dict[str, Any]) -> None:
    assert sorted(table["vendors"]) == sorted(VENDORS)


def test_every_vendor_has_every_lane(table: dict[str, Any]) -> None:
    for vendor in VENDORS:
        assert sorted(table["vendors"][vendor]["lanes"]) == sorted(LANES), vendor


def test_every_verdict_is_one_of_three(table: dict[str, Any]) -> None:
    for vendor, lane, record in _lane_records(table):
        assert record["subscription"] in VERDICTS, f"{vendor}.{lane}"


# --- Scenario: A verdict carries its governing sentence ---


def test_a_verdict_carries_quote_source_and_provenance(table: dict[str, Any]) -> None:
    decided = [
        (vendor, lane, record)
        for vendor, lane, record in _lane_records(table)
        if record["subscription"] in {"permitted", "prohibited"}
    ]
    assert decided, "no lane has a verdict; the table says nothing"
    for vendor, lane, record in decided:
        where = f"{vendor}.{lane}"
        assert _is_text(record.get("quote")), where
        assert _is_https(record.get("source")), where
        assert record.get("quote_evidence") in {"raw", "summarised"}, where


# --- Scenario: An unaddressed lane lists what was searched ---


def test_an_unaddressed_lane_lists_what_was_searched(table: dict[str, Any]) -> None:
    for vendor, lane, record in _lane_records(table):
        if record["subscription"] != "unaddressed":
            continue
        searched = record.get("searched")
        assert isinstance(searched, list) and searched, f"{vendor}.{lane}"
        assert all(_is_https(url) for url in searched), f"{vendor}.{lane}"


# --- Scenario: The table is dated ---


def test_the_table_is_dated(table: dict[str, Any]) -> None:
    retrieved = str(table["retrieved"])
    year, month, day = retrieved.split("-")
    assert (len(year), len(month), len(day)) == (4, 2, 2)
    assert year.isdigit() and month.isdigit() and day.isdigit()


# --- Scenario: Prohibited or unaddressed unattended use is marked ---


def test_unattended_lane_without_permission_names_a_keyed_lane(
    table: dict[str, Any],
) -> None:
    for vendor, lane, record in _lane_records(table):
        if lane not in UNATTENDED or record["subscription"] == "permitted":
            continue
        assert record.get("required_lane") in KEYED_LANES, f"{vendor}.{lane}"


def test_any_required_lane_is_a_keyed_lane(table: dict[str, Any]) -> None:
    for vendor, lane, record in _lane_records(table):
        if "required_lane" in record:
            assert record["required_lane"] in KEYED_LANES, f"{vendor}.{lane}"


# --- Scenario: Every mechanics field has an evidence level ---


def test_every_mechanics_field_has_an_evidence_level(table: dict[str, Any]) -> None:
    for vendor in VENDORS:
        mechanics = table["vendors"][vendor]["mechanics"]
        for name in MECHANICS:
            assert name in mechanics, f"{vendor}.{name}"
            assert mechanics[name]["evidence"] in EVIDENCE, f"{vendor}.{name}"


# --- Scenario: Observed is claimed only with a host and date ---


def test_observed_is_claimed_only_with_host_and_date(table: dict[str, Any]) -> None:
    for vendor, name, field in _mechanics_fields(table):
        if field["evidence"] != "observed":
            continue
        assert field.get("observed_on"), f"{vendor}.{name}"
        assert _is_text(field.get("observed_host_os")), f"{vendor}.{name}"


# --- Scenario: Documented is claimed only with a source ---


def test_documented_is_claimed_only_with_a_source(table: dict[str, Any]) -> None:
    for vendor, name, field in _mechanics_fields(table):
        if field["evidence"] != "documented":
            continue
        assert _is_https(field.get("source")), f"{vendor}.{name}"


def test_not_observed_says_what_is_missing(table: dict[str, Any]) -> None:
    """A gap is stated, not left as an empty record (design D4)."""
    for vendor, name, field in _mechanics_fields(table):
        if field["evidence"] != "not_observed":
            continue
        assert _is_text(field.get("value")), f"{vendor}.{name}"
