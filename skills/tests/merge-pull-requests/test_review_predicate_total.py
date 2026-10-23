"""The merge review predicate is total.

``vendor_review_block_reason`` used to return ``None`` for every ineligible
review, so a missing, skipped or unknown eligibility let a merge through
without anyone deciding it should. It now returns ``None`` on exactly two
paths: a recorded waiver, or a bound, current-or-rebased, independent
consensus verdict with zero blocking findings. Every other input blocks.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from execution_safety import vendor_review_block_reason  # noqa: E402
from verdict_binding import POLICY_WAIVABLE_REASONS  # noqa: E402

HEAD = "a" * 40
MOVED = "b" * 40
PID = "1" * 40


def _binding(**overrides) -> dict:
    binding = {
        "head_sha": HEAD,
        "patch_id": PID,
        "reviewers": [{"vendor": "codex", "family": "openai", "model": "gpt-5", "agent_id": "codex-local"}],
        "author": {"login": "bot", "vendor": "claude_code", "session_id": "session_1"},
        "same_family": False,
        "bound_at": "2026-10-23T12:00:00Z",
    }
    binding.update(overrides)
    return binding


def _verified(**overrides) -> dict:
    review = {
        "eligibility": {"eligible": True, "reason": "needs_review"},
        "dispatched": True,
        "error": None,
        "vendors": [{"vendor": "codex", "success": True, "agent_id": "codex-local"}],
        "consensus": {"summary": {"blocking_count": 0}},
        "binding": _binding(),
    }
    review.update(overrides)
    return review


def _ineligible(reason: str) -> dict:
    return {"eligibility": {"eligible": False, "reason": reason}, "consensus": None}


def _waiver(source: str, eligibility_reason: str | None, **overrides) -> dict:
    waiver = {
        "reason": "recorded for the test",
        "source": source,
        "approver": "policy:merge-pull-requests" if source == "policy" else "jan",
        "recorded_at": "2026-10-23T12:00:00Z",
        "eligibility_reason": eligibility_reason,
    }
    waiver.update(overrides)
    return waiver


# --- the verified path ------------------------------------------------------


def test_bound_current_independent_clean_verdict_passes() -> None:
    assert vendor_review_block_reason(_verified(), live_head_sha=HEAD) is None


def test_rebased_verdict_passes() -> None:
    assert vendor_review_block_reason(_verified(), live_head_sha=MOVED, live_patch_id=PID) is None


def test_stale_verdict_blocks_naming_both_heads() -> None:
    reason = vendor_review_block_reason(_verified(), live_head_sha=MOVED, live_patch_id="2" * 40)
    assert reason == f"stale verdict: reviewed {HEAD[:7]}, live {MOVED[:7]}"


def test_unknown_live_head_is_stale() -> None:
    reason = vendor_review_block_reason(_verified())
    assert reason is not None and reason.startswith("stale verdict")


def test_unbound_verdict_blocks() -> None:
    review = _verified()
    del review["binding"]
    reason = vendor_review_block_reason(review, live_head_sha=HEAD)
    assert reason is not None and "not bound" in reason


def test_self_review_blocks() -> None:
    binding = _binding(
        reviewers=[{"vendor": "codex", "family": "openai", "model": "gpt-5", "agent_id": "s-9"}],
        author={"login": "bot", "vendor": "codex", "session_id": "s-9"},
    )
    reason = vendor_review_block_reason(_verified(binding=binding), live_head_sha=HEAD)
    assert reason is not None and "self-review" in reason


def test_same_vendor_unknown_session_blocks() -> None:
    binding = _binding(author={"login": "bot", "vendor": "codex", "session_id": None})
    reason = vendor_review_block_reason(_verified(binding=binding), live_head_sha=HEAD)
    assert reason is not None and "independence" in reason


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"error": "dispatch exploded"}, "dispatch exploded"),
        ({"dispatched": False}, "not dispatched"),
        ({"vendors": [{"vendor": "codex", "success": False}]}, "no successful reviewer"),
        ({"consensus": None}, "no consensus verdict"),
        ({"consensus": {"summary": {"blocking_count": 3}}}, "3 blocking finding"),
    ],
)
def test_eligible_review_without_a_clean_verdict_blocks(overrides: dict, fragment: str) -> None:
    reason = vendor_review_block_reason(_verified(**overrides), live_head_sha=HEAD)
    assert reason is not None and fragment in reason


# --- absence and ineligibility ----------------------------------------------


@pytest.mark.parametrize(
    "review",
    [None, {}, {"consensus": None}, {"skipped": True}, {"eligibility": "yes"}],
    ids=["none", "empty", "no-eligibility", "skipped", "malformed-eligibility"],
)
def test_absent_review_blocks(review) -> None:
    assert vendor_review_block_reason(review, live_head_sha=HEAD) is not None


@pytest.mark.parametrize(
    "reason",
    sorted(POLICY_WAIVABLE_REASONS) + ["draft_pr", "changes_requested", "skipped", "something_new"],
)
def test_ineligible_without_waiver_blocks_and_names_the_reason(reason: str) -> None:
    block = vendor_review_block_reason(_ineligible(reason), live_head_sha=HEAD)
    assert block is not None
    if reason == "changes_requested":
        assert "change requests" in block
    else:
        assert reason in block


@pytest.mark.parametrize("reason", sorted(POLICY_WAIVABLE_REASONS))
def test_policy_waiver_for_the_live_reason_passes(reason: str) -> None:
    waiver = _waiver("policy", reason)
    assert vendor_review_block_reason(_ineligible(reason), waiver=waiver, live_head_sha=HEAD) is None


@pytest.mark.parametrize("reason", ["draft_pr", "changes_requested", "something_new"])
def test_policy_waiver_outside_the_closed_set_blocks(reason: str) -> None:
    waiver = _waiver("policy", reason)
    assert vendor_review_block_reason(_ineligible(reason), waiver=waiver) is not None


def test_policy_waiver_for_a_different_reason_blocks() -> None:
    waiver = _waiver("policy", "small_pr")
    assert vendor_review_block_reason(_ineligible("draft_pr"), waiver=waiver) is not None


def test_policy_waiver_needs_the_policy_approver() -> None:
    waiver = _waiver("policy", "small_pr", approver="someone")
    assert vendor_review_block_reason(_ineligible("small_pr"), waiver=waiver) is not None


@pytest.mark.parametrize("reason", sorted(POLICY_WAIVABLE_REASONS) + ["draft_pr", "something_new"])
def test_operator_waiver_overrides_ineligibility(reason: str) -> None:
    waiver = _waiver("operator", reason)
    assert vendor_review_block_reason(_ineligible(reason), waiver=waiver) is None


@pytest.mark.parametrize(
    "review",
    [None, {}, {"skipped": True}, _verified(consensus={"summary": {"blocking_count": 2}})],
    ids=["none", "empty", "skipped", "blocking-findings"],
)
def test_operator_waiver_overrides_a_missing_or_failed_review(review) -> None:
    assert vendor_review_block_reason(review, waiver=_waiver("operator", None)) is None


def test_operator_waiver_does_not_override_changes_requested() -> None:
    waiver = _waiver("operator", "changes_requested")
    block = vendor_review_block_reason(_ineligible("changes_requested"), waiver=waiver)
    assert block is not None and "change requests" in block


@pytest.mark.parametrize(
    "overrides",
    [
        {"reason": ""},
        {"reason": "   "},
        {"approver": ""},
        {"source": "vendor"},
        {"recorded_at": ""},
        {"reason": None},
    ],
)
def test_malformed_waiver_is_not_a_waiver(overrides: dict) -> None:
    waiver = _waiver("operator", "draft_pr")
    waiver.update(overrides)
    assert vendor_review_block_reason(_ineligible("draft_pr"), waiver=waiver) is not None


def test_waiver_missing_eligibility_reason_key_is_not_a_waiver() -> None:
    waiver = _waiver("operator", "draft_pr")
    del waiver["eligibility_reason"]
    assert vendor_review_block_reason(_ineligible("draft_pr"), waiver=waiver) is not None
