"""Tests for github_classifier module — task 1.1.

Covers classify_pr, to_pr_card_origin.
The _pr() helper mirrors the shape from skills/tests/merge-pull-requests/test_classify.py
so the two fixture sets stay in sync.
"""
from __future__ import annotations

import pytest

from src.github_classifier import classify_pr, to_pr_card_origin


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


# =============================================================================
# classify_pr — openspec
# =============================================================================


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


class TestBodyMarkerFallback:
    def test_arbitrary_branch_with_body_marker(self) -> None:
        result = classify_pr(
            _pr(
                "feature/some-branch",
                body="Implements OpenSpec: `my-change`",
            )
        )
        assert result == {"origin": "openspec", "change_id": "my-change"}


# =============================================================================
# classify_pr — dependabot / renovate
# =============================================================================


class TestDependabotRenovate:
    def test_dependabot_branch(self) -> None:
        result = classify_pr(_pr("dependabot/npm_and_yarn/lodash-4.17.21"))
        assert result == {"origin": "dependabot", "change_id": None}

    def test_dependabot_author(self) -> None:
        result = classify_pr(_pr("some-branch", author="dependabot[bot]"))
        assert result == {"origin": "dependabot", "change_id": None}

    def test_renovate_branch(self) -> None:
        result = classify_pr(_pr("renovate/lodash-4.17.21"))
        assert result == {"origin": "renovate", "change_id": None}

    def test_renovate_author(self) -> None:
        result = classify_pr(_pr("some-branch", author="renovate[bot]"))
        assert result == {"origin": "renovate", "change_id": None}


# =============================================================================
# classify_pr — Jules sub-types
# =============================================================================


class TestJulesClassification:
    def test_sentinel_label(self) -> None:
        result = classify_pr(_pr("fix/security-issue", labels=["sentinel"]))
        assert result == {"origin": "sentinel", "change_id": None}

    def test_bolt_label(self) -> None:
        result = classify_pr(_pr("fix/perf-thing", labels=["bolt"]))
        assert result == {"origin": "bolt", "change_id": None}

    def test_palette_label(self) -> None:
        result = classify_pr(_pr("fix/ux-thing", labels=["palette"]))
        assert result == {"origin": "palette", "change_id": None}

    def test_sentinel_branch(self) -> None:
        result = classify_pr(_pr("sentinel/fix-xss"))
        assert result == {"origin": "sentinel", "change_id": None}

    def test_bolt_branch(self) -> None:
        result = classify_pr(_pr("bolt/optimize-query"))
        assert result == {"origin": "bolt", "change_id": None}

    def test_palette_branch(self) -> None:
        result = classify_pr(_pr("palette/improve-a11y"))
        assert result == {"origin": "palette", "change_id": None}

    def test_jules_author_no_subtype_is_generic_jules(self) -> None:
        result = classify_pr(_pr("fix/something", author="jules[bot]"))
        assert result == {"origin": "jules", "change_id": None}


# =============================================================================
# classify_pr — codex / other
# =============================================================================


class TestCodexAndOther:
    def test_codex_author(self) -> None:
        result = classify_pr(_pr("some-branch", author="codex[bot]"))
        assert result["origin"] == "codex"

    def test_codex_branch(self) -> None:
        result = classify_pr(_pr("codex/some-fix"))
        assert result["origin"] == "codex"

    def test_manual_branch_stays_other(self) -> None:
        result = classify_pr(_pr("feature/my-work"))
        assert result == {"origin": "other", "change_id": None}


# =============================================================================
# to_pr_card_origin — fold to 6-value enum
# =============================================================================


class TestToPrCardOrigin:
    @pytest.mark.parametrize("raw", ["sentinel", "bolt", "palette", "jules"])
    def test_jules_subtypes_fold_to_jules(self, raw: str) -> None:
        assert to_pr_card_origin(raw) == "jules"

    def test_other_folds_to_manual(self) -> None:
        assert to_pr_card_origin("other") == "manual"

    @pytest.mark.parametrize("raw", ["openspec", "codex", "dependabot", "renovate"])
    def test_passthrough_origins(self, raw: str) -> None:
        assert to_pr_card_origin(raw) == raw

    def test_all_nine_classifier_outputs_are_handled(self) -> None:
        all_raw = [
            "openspec", "codex", "dependabot", "renovate",
            "sentinel", "bolt", "palette", "jules", "other",
        ]
        expected_card_origins = {"openspec", "codex", "dependabot", "renovate", "jules", "manual"}
        for raw in all_raw:
            result = to_pr_card_origin(raw)
            assert result in expected_card_origins, f"{raw} → {result} not in allowed set"
