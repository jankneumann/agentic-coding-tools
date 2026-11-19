"""execute_plan reports the vendor review it acted on.

On 2026-09-14 PR #484 merged through an eligible vendor review with 23
findings, 7 of them critical, none confirmed across vendors, and two of four
vendors failed. The executor's JSON said only ``"action": "merged"``, so an
operator had to open ``merge-plan.json`` to learn that a review ran at all.
The result now carries a compact review record for every outcome that
consulted the review, whether the gate passed or blocked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
for path in (SCRIPTS, SCRIPTS / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from execute_plan import execute_node  # noqa: E402
from test_execute_plan import dependencies, persisted_plan  # noqa: E402
from test_merge_plan_contract import valid_plan  # noqa: E402

LONG_ERROR = "Vendor unavailable (billing/credits): " + "x" * 2000


def _review(blocking: int) -> dict:
    return {
        "eligibility": {"eligible": True, "reason": "needs_review"},
        "dispatched": True,
        "error": None,
        "vendors": [
            {"vendor": "antigravity", "success": True, "error": None,
             "findings_count": 8, "model_used": "m1", "elapsed_seconds": 276.2},
            {"vendor": "grok", "success": False, "error": LONG_ERROR,
             "findings_count": 0, "model_used": None, "elapsed_seconds": 2.0},
        ],
        "consensus": {"summary": {
            "blocking_count": blocking, "confirmed_count": 0,
            "unconfirmed_count": 23, "total_unique_findings": 23,
        }},
        "workspace_guard": {"new_untracked": ["pr484_review.json"],
                            "quarantined_to": "/tmp/q", "errors": []},
    }


def _reviewed_node_plan(tmp_path: Path) -> Path:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    node = plan["nodes"][1]
    node["origin"] = "other"
    node["auto_executable"] = False
    node["definition"]["kind"] = "implementation"
    node["definition"]["remediation_skill"] = "quick-task"
    node["definition"]["gates"] = ["required_review"]
    return persisted_plan(tmp_path, plan)


@pytest.mark.parametrize(("blocking", "action"), [(0, "merged"), (2, "vendor_review_gate")])
def test_result_carries_review_record(tmp_path: Path, blocking: int, action: str) -> None:
    result = execute_node(
        _reviewed_node_plan(tmp_path),
        11,
        approve_gate=True,
        dependencies=dependencies(review_vendor=lambda *_a: _review(blocking)),
    )

    assert result["action"] == action
    record = result["vendor_review"]
    assert record["eligible"] is True
    assert record["summary"]["unconfirmed_count"] == 23
    assert record["summary"]["blocking_count"] == blocking
    assert [v["vendor"] for v in record["vendors"]] == ["antigravity", "grok"]
    assert [v["success"] for v in record["vendors"]] == [True, False]
    assert record["vendors"][0]["findings_count"] == 8
    assert len(record["vendors"][1]["error"]) <= 200
    assert record["workspace_guard"]["new_untracked"] == ["pr484_review.json"]


def test_skipped_review_is_reported_as_skipped(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    result = execute_node(
        persisted_plan(tmp_path, plan),
        11,
        dependencies=dependencies(
            review_vendor=lambda *_a: pytest.fail("cheap path must not dispatch review"),
        ),
    )

    assert result["action"] == "merged"
    assert result["vendor_review"]["skipped"] is True
    assert result["vendor_review"]["vendors"] == []


# --- binding and waiver evidence (task 5.3a) --------------------------------


# Scenario ID: merge-pull-requests.policy-waiver-recorded
def test_policy_waiver_and_binding_ride_on_the_merged_result(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    result = execute_node(persisted_plan(tmp_path, plan), 11, dependencies=dependencies())

    assert result["action"] == "merged"
    record = result["vendor_review"]
    assert record["binding"]["head_sha"] == "c" * 40
    assert "patch_id" in record["binding"]
    assert record["review_waiver"]["source"] == "policy"
    assert record["review_waiver"]["reason"]


# Scenario ID: merge-pull-requests.operator-waiver-recorded
def test_operator_waiver_rides_on_the_merged_result(tmp_path: Path) -> None:
    result = execute_node(
        _reviewed_node_plan(tmp_path),
        11,
        approve_gate=True,
        waive_review="hotfix approved in incident channel",
        waiver_approver="jan",
        dependencies=dependencies(review_vendor=lambda *_a: {
            "eligibility": {"eligible": True, "reason": "needs_review"},
            "dispatched": False, "vendors": [], "consensus": None,
            "error": "review vendor unavailable",
        }),
    )

    assert result["action"] == "merged"
    waiver = result["vendor_review"]["review_waiver"]
    assert waiver["source"] == "operator"
    assert waiver["reason"] == "hotfix approved in incident channel"


def test_verified_merge_has_a_binding_and_no_waiver(tmp_path: Path) -> None:
    result = execute_node(
        _reviewed_node_plan(tmp_path),
        11,
        approve_gate=True,
        dependencies=dependencies(review_vendor=lambda *_a: _review(0)),
    )

    assert result["action"] == "merged"
    record = result["vendor_review"]
    assert record["binding"]["head_sha"] == "c" * 40
    assert record["binding"]["patch_id"] is not None
    assert "review_waiver" not in record
