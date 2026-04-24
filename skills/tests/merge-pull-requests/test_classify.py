"""Tests for PR origin classification in discover_prs.py.

Focuses on the claude/* branch classification fix: Claude Code cloud-session
branches are agent-authored OpenSpec work and must classify as origin=openspec
(rebase-merge default), not origin=other (squash default).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "merge-pull-requests" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from discover_prs import classify_pr  # noqa: E402


def _pr(
    branch: str,
    *,
    body: str = "",
    title: str = "",
    author: str = "someone",
    labels: list[str] | None = None,
) -> dict:
    return {
        "headRefName": branch,
        "body": body,
        "title": title,
        "author": {"login": author},
        "labels": [{"name": label} for label in (labels or [])],
    }


class TestOpenSpecBranch:
    def test_openspec_branch_yields_change_id_from_slug(self) -> None:
        result = classify_pr(_pr("openspec/add-decision-index"))
        assert result == {"origin": "openspec", "change_id": "add-decision-index"}

    def test_openspec_branch_body_marker_overrides_slug(self) -> None:
        result = classify_pr(
            _pr(
                "openspec/generic-branch",
                body="Implements OpenSpec: `canonical-change-id`",
            )
        )
        assert result == {"origin": "openspec", "change_id": "canonical-change-id"}


class TestClaudeBranch:
    """Regression: claude/* branches must classify as openspec, not other."""

    def test_claude_branch_without_body_marker(self) -> None:
        result = classify_pr(_pr("claude/fix-sanitizer-entropy-threshold-pZGgN"))
        assert result["origin"] == "openspec"
        assert result["change_id"] is None

    def test_claude_branch_with_body_marker(self) -> None:
        result = classify_pr(
            _pr(
                "claude/host-assisted-XYZ",
                body="Some description.\n\nImplements OpenSpec: host-assisted-curation",
            )
        )
        assert result == {"origin": "openspec", "change_id": "host-assisted-curation"}

    @pytest.mark.parametrize(
        "branch",
        [
            "claude/agentic-orchestration-research-f0IiG",
            "claude/conditional-worktree-generation-3gcmy",
            "claude/plan-roadmap-host-assisted-mode",
            "claude/improve-feature-planning-3c92l",
        ],
    )
    def test_real_world_claude_branches(self, branch: str) -> None:
        """Branches observed in the repo's live PR queue on 2026-04-24."""
        result = classify_pr(_pr(branch))
        assert result["origin"] == "openspec", (
            f"claude/* branch {branch!r} must classify as openspec "
            f"(got {result['origin']!r})"
        )


class TestBodyMarkerFallback:
    def test_arbitrary_branch_with_body_marker(self) -> None:
        """Body marker alone is enough to tag a PR as openspec."""
        result = classify_pr(
            _pr(
                "feature/some-branch",
                body="Implements OpenSpec: `my-change`",
            )
        )
        assert result == {"origin": "openspec", "change_id": "my-change"}


class TestOtherOrigins:
    def test_codex_author(self) -> None:
        result = classify_pr(_pr("some-branch", author="codex[bot]"))
        assert result["origin"] == "codex"

    def test_codex_branch(self) -> None:
        result = classify_pr(_pr("codex/some-fix"))
        assert result["origin"] == "codex"

    def test_dependabot_branch(self) -> None:
        result = classify_pr(_pr("dependabot/npm_and_yarn/lodash-4.17.21"))
        assert result["origin"] == "dependabot"

    def test_manual_branch_stays_other(self) -> None:
        result = classify_pr(_pr("feature/my-work"))
        assert result["origin"] == "other"
        assert result["change_id"] is None

    def test_jules_branch(self) -> None:
        result = classify_pr(_pr("sentinel/fix-xss"))
        assert result["origin"] == "sentinel"
