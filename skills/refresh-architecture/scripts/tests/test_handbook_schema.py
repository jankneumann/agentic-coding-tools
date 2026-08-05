"""Tests for the behavior handbook schema validator (R1, design D1/D5).

The handbook references the canonical graph rather than restating structure,
so validation is mostly about referential integrity against
``architecture.graph.json`` plus the token budgets that make progressive
disclosure pay off.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from handbook_schema import (
    L1_TOKEN_BUDGET,
    L2_CARD_TOKEN_BUDGET,
    L3_TOKEN_BUDGET,
    estimate_tokens,
    validate_handbook,
)


def _graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "py:api.claim_task", "kind": "function", "language": "python",
             "name": "claim_task", "file": "src/api.py", "span": {"start": 10, "end": 40}},
            {"id": "py:api.release_task", "kind": "function", "language": "python",
             "name": "release_task", "file": "src/api.py", "span": {"start": 42, "end": 60}},
            {"id": "py:db.connect", "kind": "function", "language": "python",
             "name": "connect", "file": "src/db.py", "span": {"start": 1, "end": 12}},
        ],
        "edges": [],
        "entrypoints": [{"node_id": "py:api.claim_task", "kind": "route"}],
    }


def _handbook(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "snapshot": {
            "generated_at": "2026-08-05T00:00:00+00:00",
            "git_sha": "abc123",
            "handbook_version": "1.0.0",
        },
        "system_flows": [
            {
                "id": "fl:task-claim",
                "title": "Task claim request",
                "entry": "py:api.claim_task",
                "stages": ["receive", "lock", "persist"],
                "state_handoffs": ["request -> claim record"],
                "terminal_actions": ["task marked claimed"],
            }
        ],
        "behavior_units": [
            {
                "id": "bh:task-claiming",
                "title": "Task claiming",
                "responsibility": "Atomically assign a queued task to one agent.",
                "inputs": ["agent id", "task filter"],
                "outputs": ["claimed task record"],
                "depends_on": [],
                "member_nodes": ["py:api.claim_task", "py:db.connect"],
            }
        ],
        "unit_details": {
            "bh:task-claiming": {
                "triggers": ["POST /tasks/claim"],
                "state_changes": ["task.status queued -> claimed"],
                "execution_paths": [
                    {
                        "summary": "claim succeeds",
                        "evidence": [
                            {
                                "node_id": "py:api.claim_task",
                                "file": "src/api.py",
                                "span": {"start": 10, "end": 40},
                                "content_digest": "sha256:deadbeef",
                                "role": "execution_path",
                            }
                        ],
                    }
                ],
                "exception_paths": [],
                "evidence": [
                    {
                        "node_id": "py:db.connect",
                        "file": "src/db.py",
                        "span": {"start": 1, "end": 12},
                        "content_digest": "sha256:cafe",
                        "role": "state_change",
                    }
                ],
            }
        },
        "uncovered": [],
    }
    doc.update(overrides)
    return doc


# --------------------------------------------------------------------------- #
# R1 success path
# --------------------------------------------------------------------------- #
def test_validates_well_formed_handbook() -> None:
    dc = validate_handbook(_handbook(), _graph())
    assert dc.exit_code == 0, [d.to_dict() for d in dc.errors]
    assert not dc.errors


def test_accepts_handbook_loaded_from_disk(tmp_path: Path) -> None:
    hb_path = tmp_path / "architecture.behaviors.json"
    hb_path.write_text(json.dumps(_handbook()), encoding="utf-8")
    graph_path = tmp_path / "architecture.graph.json"
    graph_path.write_text(json.dumps(_graph()), encoding="utf-8")

    from handbook_schema import validate_handbook_files

    dc = validate_handbook_files(hb_path, graph_path)
    assert dc.exit_code == 0


# --------------------------------------------------------------------------- #
# R1 failure paths — referential integrity (D1)
# --------------------------------------------------------------------------- #
def test_rejects_unknown_member_node() -> None:
    hb = _handbook()
    hb["behavior_units"][0]["member_nodes"].append("py:ghost.function")

    dc = validate_handbook(hb, _graph())

    assert dc.exit_code == 1
    codes = {d.code for d in dc.errors}
    assert "HANDBOOK_UNKNOWN_NODE" in codes
    detail = " ".join(d.message for d in dc.errors)
    assert "py:ghost.function" in detail
    assert "bh:task-claiming" in detail


def test_rejects_unknown_evidence_node() -> None:
    hb = _handbook()
    hb["unit_details"]["bh:task-claiming"]["evidence"][0]["node_id"] = "py:nope"

    dc = validate_handbook(hb, _graph())

    assert dc.exit_code == 1
    assert "HANDBOOK_UNKNOWN_NODE" in {d.code for d in dc.errors}


def test_rejects_unknown_flow_entry() -> None:
    hb = _handbook()
    hb["system_flows"][0]["entry"] = "py:missing.entry"

    dc = validate_handbook(hb, _graph())

    assert "HANDBOOK_UNKNOWN_NODE" in {d.code for d in dc.errors}


def test_rejects_detail_for_undeclared_unit() -> None:
    hb = _handbook()
    hb["unit_details"]["bh:not-a-unit"] = {
        "triggers": [], "state_changes": [], "execution_paths": [],
        "exception_paths": [], "evidence": [],
    }

    dc = validate_handbook(hb, _graph())

    assert "HANDBOOK_ORPHAN_DETAIL" in {d.code for d in dc.errors}


def test_rejects_dangling_depends_on() -> None:
    hb = _handbook()
    hb["behavior_units"][0]["depends_on"] = ["bh:does-not-exist"]

    dc = validate_handbook(hb, _graph())

    assert "HANDBOOK_UNKNOWN_UNIT" in {d.code for d in dc.errors}


def test_rejects_duplicate_unit_ids() -> None:
    hb = _handbook()
    hb["behavior_units"].append(dict(hb["behavior_units"][0]))

    dc = validate_handbook(hb, _graph())

    assert "HANDBOOK_DUPLICATE_ID" in {d.code for d in dc.errors}


def test_rejects_malformed_unit_id_prefix() -> None:
    hb = _handbook()
    hb["behavior_units"][0]["id"] = "task-claiming"
    hb["unit_details"] = {"task-claiming": hb["unit_details"]["bh:task-claiming"]}

    dc = validate_handbook(hb, _graph())

    assert "HANDBOOK_BAD_ID" in {d.code for d in dc.errors}


def test_rejects_missing_snapshot() -> None:
    hb = _handbook()
    del hb["snapshot"]

    dc = validate_handbook(hb, _graph())

    assert "HANDBOOK_MISSING_SNAPSHOT" in {d.code for d in dc.errors}


def test_rejects_evidence_without_locator_fields() -> None:
    hb = _handbook()
    hb["unit_details"]["bh:task-claiming"]["evidence"][0].pop("content_digest")

    dc = validate_handbook(hb, _graph())

    assert "HANDBOOK_BAD_LOCATOR" in {d.code for d in dc.errors}


def test_unit_without_detail_is_an_error() -> None:
    hb = _handbook()
    hb["unit_details"] = {}

    dc = validate_handbook(hb, _graph())

    assert "HANDBOOK_MISSING_DETAIL" in {d.code for d in dc.errors}


# --------------------------------------------------------------------------- #
# D5 — token budgets are enforced, not advisory
# --------------------------------------------------------------------------- #
def test_estimate_tokens_uses_four_chars_per_token() -> None:
    assert estimate_tokens("a" * 400) == 100


def test_rejects_over_budget_l1() -> None:
    hb = _handbook()
    hb["system_flows"][0]["stages"] = ["x" * (L1_TOKEN_BUDGET * 4 + 100)]

    dc = validate_handbook(hb, _graph())

    assert "HANDBOOK_BUDGET_EXCEEDED" in {d.code for d in dc.errors}
    assert any("l1" in (d.details.get("level") or "") for d in dc.errors)


def test_rejects_over_budget_l2_card() -> None:
    hb = _handbook()
    hb["behavior_units"][0]["responsibility"] = "y" * (L2_CARD_TOKEN_BUDGET * 4 + 100)

    dc = validate_handbook(hb, _graph())

    errs = [d for d in dc.errors if d.code == "HANDBOOK_BUDGET_EXCEEDED"]
    assert errs
    assert any(d.details.get("level") == "l2" for d in errs)


def test_rejects_over_budget_l3_detail() -> None:
    hb = _handbook()
    hb["unit_details"]["bh:task-claiming"]["triggers"] = [
        "z" * (L3_TOKEN_BUDGET * 4 + 100)
    ]

    dc = validate_handbook(hb, _graph())

    errs = [d for d in dc.errors if d.code == "HANDBOOK_BUDGET_EXCEEDED"]
    assert errs
    assert any(d.details.get("level") == "l3" for d in errs)


def test_budget_estimate_recorded_when_valid() -> None:
    from handbook_schema import compute_budget_estimate

    est = compute_budget_estimate(_handbook())
    assert est["l1"] <= L1_TOKEN_BUDGET
    assert est["l2_max_card"] <= L2_CARD_TOKEN_BUDGET
    assert est["l3_max_unit"] <= L3_TOKEN_BUDGET
    assert est["l2_cards"] == 1


# --------------------------------------------------------------------------- #
# Structural guards
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("missing", ["system_flows", "behavior_units", "unit_details"])
def test_rejects_missing_top_level_section(missing: str) -> None:
    hb = _handbook()
    del hb[missing]

    dc = validate_handbook(hb, _graph())

    assert "HANDBOOK_MISSING_SECTION" in {d.code for d in dc.errors}


def test_rejects_non_object_document() -> None:
    dc = validate_handbook(["not", "an", "object"], _graph())  # type: ignore[arg-type]
    assert dc.exit_code == 1
