"""Tests for the progressive-disclosure query CLI (R4, design D5).

The point of the CLI is that a consumer never pays for a level it did not ask
for. These tests assert the level boundaries hold: an L2 request must not leak
L3 detail, and an L3 request must return exactly one unit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from handbook_query import (
    locate,
    query_l1,
    query_l2,
    query_l3,
)
from verify_locators import DRIFTED, VERIFIED, normalized_span_digest

SRC_A = "def claim_task(agent_id):\n    return lock(agent_id)\n"
SRC_B = "def render_report():\n    return html\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "api.py").write_text(SRC_A, encoding="utf-8")
    (src / "report.py").write_text(SRC_B, encoding="utf-8")
    return tmp_path


@pytest.fixture
def handbook(repo: Path) -> dict[str, Any]:
    claim_digest = normalized_span_digest(repo / "src/api.py", 1, 2)
    report_digest = normalized_span_digest(repo / "src/report.py", 1, 2)
    return {
        "snapshot": {"generated_at": "2026-08-05T00:00:00+00:00", "git_sha": "abc",
                     "handbook_version": "1.0.0"},
        "system_flows": [
            {"id": "fl:task-claiming", "title": "Task claiming",
             "entry": "py:api.claim_task", "stages": ["receive", "lock"],
             "state_handoffs": [], "terminal_actions": []},
        ],
        "behavior_units": [
            {"id": "bh:task-claiming", "title": "Task claiming",
             "responsibility": "Assign a queued task to one agent atomically.",
             "inputs": ["agent id"], "outputs": ["lock"], "depends_on": [],
             "member_nodes": ["py:api.claim_task"]},
            {"id": "bh:reporting", "title": "Reporting",
             "responsibility": "Render the HTML status report.",
             "inputs": [], "outputs": ["html"], "depends_on": [],
             "member_nodes": ["py:report.render_report"]},
        ],
        "unit_details": {
            "bh:task-claiming": {
                "triggers": ["POST /tasks/claim"],
                "state_changes": ["task queued -> claimed"],
                "execution_paths": [{"summary": "claim succeeds", "evidence": [
                    {"node_id": "py:api.claim_task", "file": "src/api.py",
                     "span": {"start": 1, "end": 2},
                     "content_digest": claim_digest, "role": "execution_path"}]}],
                "exception_paths": [],
                "evidence": [
                    {"node_id": "py:api.claim_task", "file": "src/api.py",
                     "span": {"start": 1, "end": 2},
                     "content_digest": claim_digest, "role": "member"}],
            },
            "bh:reporting": {
                "triggers": ["GET /report"],
                "state_changes": [],
                "execution_paths": [],
                "exception_paths": [],
                "evidence": [
                    {"node_id": "py:report.render_report", "file": "src/report.py",
                     "span": {"start": 1, "end": 2},
                     "content_digest": report_digest, "role": "member"}],
            },
        },
        "uncovered": [],
    }


# --------------------------------------------------------------------------- #
# L1
# --------------------------------------------------------------------------- #
def test_l1_returns_system_flows_only(handbook: dict[str, Any]) -> None:
    out = query_l1(handbook)

    assert out["level"] == "l1"
    assert [f["id"] for f in out["system_flows"]] == ["fl:task-claiming"]
    assert "unit_details" not in out
    assert "behavior_units" not in out


def test_l1_reports_its_token_cost(handbook: dict[str, Any]) -> None:
    out = query_l1(handbook)
    assert out["tokens"] > 0
    assert out["budget"] > 0


# --------------------------------------------------------------------------- #
# L2
# --------------------------------------------------------------------------- #
def test_l2_returns_all_cards_without_details(handbook: dict[str, Any]) -> None:
    out = query_l2(handbook)

    assert {c["id"] for c in out["cards"]} == {"bh:task-claiming", "bh:reporting"}
    assert all("triggers" not in c for c in out["cards"]), "L2 must not leak L3 content"


def test_l2_filters_by_touched_files(handbook: dict[str, Any], repo: Path) -> None:
    out = query_l2(handbook, files=["src/api.py"], repo_root=repo)

    assert [c["id"] for c in out["cards"]] == ["bh:task-claiming"]


def test_l2_filters_by_free_text(handbook: dict[str, Any]) -> None:
    out = query_l2(handbook, text="report")

    assert [c["id"] for c in out["cards"]] == ["bh:reporting"]


def test_l2_unknown_filter_returns_empty_not_error(handbook: dict[str, Any]) -> None:
    out = query_l2(handbook, text="nothing matches this")
    assert out["cards"] == []


# --------------------------------------------------------------------------- #
# L3
# --------------------------------------------------------------------------- #
def test_l3_returns_one_unit_with_verified_evidence(
    handbook: dict[str, Any], repo: Path
) -> None:
    out = query_l3(handbook, "bh:task-claiming", repo_root=repo)

    assert out["unit"]["id"] == "bh:task-claiming"
    assert out["detail"]["triggers"] == ["POST /tasks/claim"]
    statuses = {e["status"] for e in out["evidence_status"]}
    assert statuses == {VERIFIED}


def test_l3_does_not_include_other_units(handbook: dict[str, Any], repo: Path) -> None:
    out = query_l3(handbook, "bh:task-claiming", repo_root=repo)

    payload = json.dumps(out)
    assert "bh:reporting" not in payload


def test_l3_marks_drifted_evidence_but_still_returns_detail(
    handbook: dict[str, Any], repo: Path
) -> None:
    (repo / "src/api.py").write_text("def claim_task(agent_id):\n    return None\n",
                                     encoding="utf-8")

    out = query_l3(handbook, "bh:task-claiming", repo_root=repo)

    assert out["detail"]["triggers"] == ["POST /tasks/claim"]
    assert DRIFTED in {e["status"] for e in out["evidence_status"]}


def test_l3_unknown_unit_returns_error_payload(
    handbook: dict[str, Any], repo: Path
) -> None:
    out = query_l3(handbook, "bh:nope", repo_root=repo)
    assert out["error"] == "unknown_unit"


# --------------------------------------------------------------------------- #
# --locate (BGPD entry point)
# --------------------------------------------------------------------------- #
def test_locate_ranks_relevant_units_first(handbook: dict[str, Any]) -> None:
    out = locate(handbook, "claim a queued task for an agent")

    assert out["candidates"][0]["id"] == "bh:task-claiming"
    assert out["candidates"][0]["score"] > 0


def test_locate_includes_member_nodes_as_evidence(handbook: dict[str, Any]) -> None:
    out = locate(handbook, "claim task")

    top = out["candidates"][0]
    assert "py:api.claim_task" in top["primary_nodes"]
    assert top["member_node_count"] == 1


def test_cards_preview_membership_rather_than_inlining_it() -> None:
    """A card carries a count plus a bounded preview, never full membership.

    Inlining every node ID is what made real cards 700+ tokens and defeated the
    L2 budget; ranking still sees full membership, the reader does not.
    """
    from handbook_schema import CARD_PRIMARY_NODE_LIMIT, card_projection

    unit = {
        "id": "bh:big", "title": "Big", "responsibility": "r",
        "inputs": [], "outputs": [], "depends_on": [],
        "member_nodes": [f"py:mod.fn{i}" for i in range(40)],
    }

    card = card_projection(unit)

    assert "member_nodes" not in card
    assert card["member_node_count"] == 40
    assert len(card["primary_nodes"]) == CARD_PRIMARY_NODE_LIMIT


def test_locate_still_ranks_on_full_membership() -> None:
    """Ranking must see nodes the card does not preview."""
    hb = {
        "snapshot": {}, "system_flows": [], "unit_details": {}, "uncovered": [],
        "behavior_units": [{
            "id": "bh:big", "title": "Big", "responsibility": "generic",
            "inputs": [], "outputs": [], "depends_on": [],
            "member_nodes": [f"py:mod.fn{i}" for i in range(10)] + ["py:mod.telemetry"],
        }],
    }

    out = locate(hb, "telemetry")

    assert out["candidates"], "a node outside the preview must still be findable"
    assert "py:mod.telemetry" not in out["candidates"][0]["primary_nodes"]


def test_locate_does_not_return_l3_detail(handbook: dict[str, Any]) -> None:
    out = locate(handbook, "claim task")
    assert all("execution_paths" not in c for c in out["candidates"])


def test_locate_with_no_match_returns_empty_candidates(handbook: dict[str, Any]) -> None:
    out = locate(handbook, "zzzzz qqqqq")
    assert out["candidates"] == []


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_emits_json(handbook: dict[str, Any], repo: Path, capsys: Any) -> None:
    from handbook_query import main

    hb_path = repo / "architecture.behaviors.json"
    hb_path.write_text(json.dumps(handbook), encoding="utf-8")

    rc = main(["--handbook", str(hb_path), "--repo-root", str(repo), "--level", "l1"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["level"] == "l1"


def test_cli_locate_mode(handbook: dict[str, Any], repo: Path, capsys: Any) -> None:
    from handbook_query import main

    hb_path = repo / "architecture.behaviors.json"
    hb_path.write_text(json.dumps(handbook), encoding="utf-8")

    rc = main(["--handbook", str(hb_path), "--repo-root", str(repo),
               "--locate", "claim task"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["candidates"][0]["id"] == "bh:task-claiming"


def test_cli_missing_handbook_is_an_error(tmp_path: Path) -> None:
    from handbook_query import main

    rc = main(["--handbook", str(tmp_path / "nope.json"),
               "--repo-root", str(tmp_path), "--level", "l1"])
    assert rc == 1
