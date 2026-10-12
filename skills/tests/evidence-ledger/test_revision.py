"""Cross-revision immutability (spec: "Recorded facts are immutable across ledger revisions")."""

from __future__ import annotations

from pathlib import Path

import pytest

import evidence_ledger  # on sys.path via conftest.py

REVISIONS = Path(__file__).resolve().parent / "fixtures" / "revisions"


def _load(name: str) -> dict:
    return evidence_ledger.load_ledger(REVISIONS / f"{name}.json")


def _check(name: str) -> list[evidence_ledger.Violation]:
    return evidence_ledger.check_revision(_load("base"), _load(name))


@pytest.mark.parametrize(
    "name",
    [
        "base",
        "edited_fact_in_place",
        "dispute_via_reverify",
        "removed_fact",
        "hypothesis_status_changed",
        "reverify_mutated",
        "reverify_removed",
        "ledger_id_changed",
    ],
)
def test_every_revision_fixture_is_individually_valid(name: str) -> None:
    """The revision check is the only reason any of these pairs fails."""
    assert evidence_ledger.validate_ledger(_load(name)) == []


def test_identical_revision_is_accepted() -> None:
    assert _check("base") == []


def test_in_place_edit_of_recorded_fact_is_rejected() -> None:
    (violation,) = _check("edited_fact_in_place")
    assert violation.code == "fact_mutated"
    assert violation.path == "/facts/F3"
    assert "observation" in violation.message


def test_same_dispute_as_reverify_request_plus_new_fact_is_accepted() -> None:
    current = _load("dispute_via_reverify")
    assert evidence_ledger.validate_ledger(current) == []
    assert evidence_ledger.check_revision(_load("base"), current) == []
    request = next(r for r in current["reverify_requests"] if r["id"] == "R2")
    assert request["fact_id"] == "F3"
    assert request["replacement_fact"] == "F5"


def test_removing_a_recorded_fact_is_rejected() -> None:
    (violation,) = _check("removed_fact")
    assert violation.code == "fact_removed"
    assert violation.path == "/facts/F4"


def test_hypothesis_status_change_is_accepted() -> None:
    assert _check("hypothesis_status_changed") == []


def test_editing_a_recorded_reverify_request_is_rejected() -> None:
    (violation,) = _check("reverify_mutated")
    assert violation.code == "reverify_mutated"
    assert violation.path == "/reverify_requests/R1"


def test_removing_a_recorded_reverify_request_is_rejected() -> None:
    (violation,) = _check("reverify_removed")
    assert violation.code == "reverify_removed"


def test_changing_ledger_id_is_rejected() -> None:
    codes = [v.code for v in _check("ledger_id_changed")]
    assert codes == ["ledger_id_changed"]


def test_key_order_does_not_count_as_mutation() -> None:
    base = _load("base")
    reordered = _load("base")
    reordered["facts"][0] = dict(reversed(list(reordered["facts"][0].items())))
    assert evidence_ledger.check_revision(base, reordered) == []


def test_fact_moved_to_another_position_is_not_a_mutation() -> None:
    base = _load("base")
    moved = _load("base")
    moved["facts"].reverse()
    assert evidence_ledger.check_revision(base, moved) == []
