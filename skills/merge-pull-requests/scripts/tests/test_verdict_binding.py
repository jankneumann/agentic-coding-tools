"""Verdict binding: what a stored review covered, and who wrote the code.

A vendor verdict used to carry neither the head it reviewed nor the PR
author, so execution could not tell a current verdict from one taken before
a later push, nor a self-review from an independent one. These tests pin the
pure binding helpers; the patch-id tests use a real throwaway repository
because the ``rebased`` path rests entirely on git's own ``patch-id``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from verdict_binding import (
    POLICY_WAIVABLE_REASONS,
    bind,
    derive_author,
    family_of,
    independence_violation,
    patch_id,
    patch_id_from_diff,
    stale_reason,
    validate_binding,
    verdict_currency,
)

SHA_A = "a" * 40
SHA_B = "b" * 40
PID_1 = "1" * 40
PID_2 = "2" * 40


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@test", *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """main with one file; ``feature`` adds a hunk far from main's later edit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "base.txt").write_text("".join(f"line {i}\n" for i in range(1, 41)))
    _git(repo, "add", "base.txt")
    _git(repo, "commit", "-m", "base")
    _git(repo, "checkout", "-b", "feature")
    (repo / "feature.txt").write_text("feature one\n")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-m", "feature")
    return repo


def _move_main(repo: Path) -> None:
    _git(repo, "checkout", "main")
    lines = (repo / "base.txt").read_text().splitlines(keepends=True)
    lines[0] = "line 1 changed on main\n"
    (repo / "base.txt").write_text("".join(lines))
    _git(repo, "commit", "-am", "main moves")
    _git(repo, "checkout", "feature")


def _binding(**overrides) -> dict:
    binding = {
        "head_sha": SHA_A,
        "patch_id": PID_1,
        "reviewers": [{"vendor": "codex", "family": "openai", "model": "gpt-5", "agent_id": "codex-local"}],
        "author": {"login": "bot", "vendor": "claude_code", "session_id": "session_1"},
        "same_family": False,
        "bound_at": "2026-10-23T12:00:00Z",
    }
    binding.update(overrides)
    return binding


# --- currency (1.1) --------------------------------------------------------


def test_unchanged_head_is_current() -> None:
    assert verdict_currency(_binding(), SHA_A, None) == "current"


def test_rebase_with_identical_diff_is_rebased(repo: Path) -> None:
    before_head = _git(repo, "rev-parse", "feature")
    before = patch_id(repo, "main", "feature")
    _move_main(repo)
    _git(repo, "rebase", "main")
    after_head = _git(repo, "rev-parse", "feature")
    after = patch_id(repo, "main", "feature")

    assert before_head != after_head
    assert before is not None and before == after
    binding = _binding(head_sha=before_head, patch_id=before)
    assert verdict_currency(binding, after_head, after) == "rebased"


def test_changed_diff_is_stale(repo: Path) -> None:
    before_head = _git(repo, "rev-parse", "feature")
    before = patch_id(repo, "main", "feature")
    (repo / "feature.txt").write_text("feature one\nfeature two\n")
    _git(repo, "commit", "-am", "more feature")
    after_head = _git(repo, "rev-parse", "feature")
    after = patch_id(repo, "main", "feature")

    assert before != after
    binding = _binding(head_sha=before_head, patch_id=before)
    assert verdict_currency(binding, after_head, after) == "stale"
    reason = stale_reason(binding, after_head)
    assert reason == f"stale verdict: reviewed {before_head[:7]}, live {after_head[:7]}"


def test_patch_id_from_diff_matches_local_patch_id(repo: Path) -> None:
    diff = _git(repo, "diff", "main...feature") + "\n"
    assert patch_id_from_diff(diff) == patch_id(repo, "main", "feature")


def test_empty_diff_has_no_patch_id() -> None:
    assert patch_id_from_diff("") is None
    assert patch_id_from_diff("   \n") is None


@pytest.mark.parametrize(
    ("stored", "live"),
    [(None, PID_1), (PID_1, None), (None, None)],
)
def test_uncomputable_patch_id_is_stale(stored: str | None, live: str | None) -> None:
    assert verdict_currency(_binding(patch_id=stored), SHA_B, live) == "stale"


def test_different_patch_ids_are_stale() -> None:
    assert verdict_currency(_binding(), SHA_B, PID_2) == "stale"


@pytest.mark.parametrize("binding", [None, {}, {"head_sha": None}, {"head_sha": ""}, "x"])
def test_missing_binding_is_stale(binding) -> None:
    assert verdict_currency(binding, SHA_A, PID_1) == "stale"


def test_stale_reason_names_unbound_verdict() -> None:
    assert stale_reason(None, SHA_B) == f"stale verdict: reviewed unbound, live {SHA_B[:7]}"


# --- independence and family (1.2) ----------------------------------------


def test_self_review_is_rejected() -> None:
    binding = _binding(
        reviewers=[{"vendor": "codex", "family": "openai", "model": "gpt-5", "agent_id": "s-9"}],
        author={"login": "bot", "vendor": "codex", "session_id": "s-9"},
    )
    reason = independence_violation(binding)
    assert reason is not None and "self-review" in reason


def test_same_vendor_with_unknown_author_session_is_rejected() -> None:
    binding = _binding(
        reviewers=[{"vendor": "codex", "family": "openai", "model": "gpt-5", "agent_id": "codex-local"}],
        author={"login": "bot", "vendor": "codex", "session_id": None},
    )
    reason = independence_violation(binding)
    assert reason is not None and "cannot be shown" in reason


def test_same_vendor_with_different_session_is_independent() -> None:
    binding = _binding(
        reviewers=[{"vendor": "codex", "family": "openai", "model": "gpt-5", "agent_id": "codex-local"}],
        author={"login": "bot", "vendor": "codex", "session_id": "s-1"},
    )
    assert independence_violation(binding) is None


def test_human_author_is_independent_of_every_reviewer() -> None:
    binding = _binding(author={"login": "alice", "vendor": None, "session_id": None})
    assert independence_violation(binding) is None


def test_same_family_reviewer_is_accepted_and_recorded() -> None:
    review = {
        "eligibility": {"eligible": True, "reason": "needs_review"},
        "dispatched": True,
        "vendors": [{"vendor": "codex", "success": True, "model_used": "claude-opus", "agent_id": "codex-x"}],
    }
    author = {"login": "bot", "vendor": "claude_code", "session_id": "s-1"}
    bound = bind(review, head_sha=SHA_A, patch_id=PID_1, author=author, now="2026-10-23T12:00:00Z")
    binding = bound["binding"]
    assert binding["same_family"] is True
    assert independence_violation(binding) is None


def test_bind_keeps_review_and_records_successful_reviewers_only() -> None:
    review = {
        "eligibility": {"eligible": True, "reason": "needs_review"},
        "dispatched": True,
        "vendors": [
            {"vendor": "codex", "success": True, "model_used": "gpt-5", "agent_id": "codex-local"},
            {"vendor": "gemini", "success": False, "model_used": None, "agent_id": "gemini-local"},
        ],
        "consensus": {"summary": {"blocking_count": 0}},
    }
    bound = bind(review, head_sha=SHA_A, patch_id=None, author=None, now="2026-10-23T12:00:00Z")
    assert bound is not review
    assert "binding" not in review
    assert bound["consensus"] == review["consensus"]
    binding = bound["binding"]
    assert binding["reviewers"] == [
        {"vendor": "codex", "family": "openai", "model": "gpt-5", "agent_id": "codex-local"},
    ]
    assert binding["author"] == {"login": None, "vendor": None, "session_id": None}
    assert binding["same_family"] is None
    assert binding["head_sha"] == SHA_A and binding["patch_id"] is None
    assert binding["bound_at"] == "2026-10-23T12:00:00Z"
    assert validate_binding(binding) == []


def test_validate_binding_reports_missing_fields() -> None:
    errors = validate_binding({"head_sha": "nope"})
    assert any("head_sha" in error for error in errors)
    assert any("reviewers" in error for error in errors)
    assert validate_binding(None) == ["binding is not an object"]


@pytest.mark.parametrize(
    ("vendor", "model", "family"),
    [
        (None, "claude-opus", "anthropic"),
        ("codex", "claude-sonnet", "anthropic"),
        (None, "gpt-5", "openai"),
        (None, "o3-mini", "openai"),
        (None, "gemini-2.5-pro", "google"),
        (None, "grok-4", "xai"),
        ("claude_code", None, "anthropic"),
        ("codex", None, "openai"),
        ("antigravity", None, "google"),
        ("gemini", "unknown-model", "google"),
        ("grok", None, "xai"),
        ("pi", None, None),
        (None, None, None),
    ],
)
def test_family_of(vendor, model, family) -> None:
    assert family_of(vendor=vendor, model=model) == family


# --- author derivation (1.2) ----------------------------------------------


def _commit(body: str, oid: str = "c" * 40) -> dict:
    return {"oid": oid, "messageHeadline": "feat: x", "messageBody": body}


def test_derive_author_from_claude_trailers() -> None:
    body = (
        "Details.\n\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>\n"
        "Claude-Session: https://claude.ai/code/session_abc123\n"
    )
    author = derive_author({"author": {"login": "jan"}, "commits": [_commit(body)]})
    assert author == {"login": "jan", "vendor": "claude_code", "session_id": "session_abc123"}


def test_derive_author_from_generic_session_trailer() -> None:
    body = "Codex-Session: https://example.test/sessions/xyz/\n"
    author = derive_author({"author": {"login": "bot"}, "commits": [_commit(body)]})
    assert author == {"login": "bot", "vendor": "codex", "session_id": "xyz"}


def test_derive_author_for_human_pr_is_all_null_vendor() -> None:
    author = derive_author({"author": {"login": "alice"}, "commits": [_commit("Plain message.")]})
    assert author == {"login": "alice", "vendor": None, "session_id": None}


def test_derive_author_latest_session_wins() -> None:
    older = _commit("Claude-Session: https://claude.ai/code/session_old\n", oid="1" * 40)
    newer = _commit("Claude-Session: https://claude.ai/code/session_new\n", oid="2" * 40)
    author = derive_author({"author": {"login": "jan"}, "commits": [older, newer, _commit("fixup")]})
    assert author["session_id"] == "session_new"
    assert author["vendor"] == "claude_code"


def test_derive_author_tolerates_missing_fields() -> None:
    assert derive_author({}) == {"login": None, "vendor": None, "session_id": None}


def test_policy_waivable_reasons_are_closed() -> None:
    assert POLICY_WAIVABLE_REASONS == frozenset({
        "skip_origin", "small_pr", "has_approval", "low_risk_judged", "automation_cheap_path",
    })
