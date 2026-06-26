"""Tests for the REST→classifier adapter — tasks 1.5, 1.6.

Verifies that from_rest_pr() maps GitHub REST payload field names into the
gh-CLI-shaped dict that classify_pr() expects, and that the round-trip
produces correct classification.
"""
from __future__ import annotations

from src.github_classifier import classify_pr, from_rest_pr


def _rest_pr(
    *,
    head_ref: str = "openspec/foo",
    author_login: str = "alice",
    labels: list[str] | None = None,
    body: str = "",
    title: str = "x",
    draft: bool = False,
    html_url: str = "https://github.com/owner/repo/pull/1",
    number: int = 1,
    base_ref: str = "main",
    created_at: str = "2025-01-01T00:00:00Z",
    updated_at: str = "2025-01-02T00:00:00Z",
) -> dict:
    return {
        "head": {"ref": head_ref},
        "user": {"login": author_login},
        "labels": [{"name": name} for name in (labels or [])],
        "body": body,
        "title": title,
        "draft": draft,
        "html_url": html_url,
        "number": number,
        "base": {"ref": base_ref},
        "created_at": created_at,
        "updated_at": updated_at,
    }


class TestFromRestPr:
    def test_head_ref_mapped_to_headRefName(self) -> None:  # noqa: N802
        adapted = from_rest_pr(_rest_pr(head_ref="openspec/bar"))
        assert adapted["headRefName"] == "openspec/bar"

    def test_user_login_mapped_to_author_login(self) -> None:
        adapted = from_rest_pr(_rest_pr(author_login="bob"))
        assert adapted["author"] == {"login": "bob"}

    def test_draft_mapped_to_isDraft(self) -> None:  # noqa: N802
        adapted = from_rest_pr(_rest_pr(draft=True))
        assert adapted["isDraft"] is True

    def test_draft_false_mapped(self) -> None:
        adapted = from_rest_pr(_rest_pr(draft=False))
        assert adapted["isDraft"] is False

    def test_created_at_mapped_to_createdAt(self) -> None:  # noqa: N802
        adapted = from_rest_pr(_rest_pr(created_at="2025-06-01T12:00:00Z"))
        assert adapted["createdAt"] == "2025-06-01T12:00:00Z"

    def test_updated_at_mapped_to_updatedAt(self) -> None:  # noqa: N802
        adapted = from_rest_pr(_rest_pr(updated_at="2025-06-01T13:00:00Z"))
        assert adapted["updatedAt"] == "2025-06-01T13:00:00Z"

    def test_html_url_mapped_to_url(self) -> None:
        adapted = from_rest_pr(_rest_pr(html_url="https://github.com/owner/repo/pull/42"))
        assert adapted["url"] == "https://github.com/owner/repo/pull/42"

    def test_base_ref_mapped_to_baseRefName(self) -> None:  # noqa: N802
        adapted = from_rest_pr(_rest_pr(base_ref="develop"))
        assert adapted["baseRefName"] == "develop"

    def test_passthrough_body(self) -> None:
        adapted = from_rest_pr(_rest_pr(body="hello"))
        assert adapted["body"] == "hello"

    def test_passthrough_title(self) -> None:
        adapted = from_rest_pr(_rest_pr(title="My PR"))
        assert adapted["title"] == "My PR"

    def test_passthrough_labels(self) -> None:
        adapted = from_rest_pr(_rest_pr(labels=["security"]))
        assert adapted["labels"] == [{"name": "security"}]

    def test_passthrough_number(self) -> None:
        adapted = from_rest_pr(_rest_pr(number=99))
        assert adapted["number"] == 99


class TestRoundTrip:
    def test_openspec_branch_round_trip(self) -> None:
        rest = _rest_pr(head_ref="openspec/foo")
        result = classify_pr(from_rest_pr(rest))
        assert result == {"origin": "openspec", "change_id": "foo"}

    def test_dependabot_round_trip(self) -> None:
        rest = _rest_pr(head_ref="dependabot/npm/lodash-4.0.0")
        result = classify_pr(from_rest_pr(rest))
        assert result == {"origin": "dependabot", "change_id": None}

    def test_other_round_trip(self) -> None:
        rest = _rest_pr(head_ref="feature/my-work")
        result = classify_pr(from_rest_pr(rest))
        assert result == {"origin": "other", "change_id": None}

    def test_raw_rest_without_adapter_returns_other(self) -> None:
        """Regression sentinel: raw REST payload MUST NOT be passed to classify_pr."""
        raw = _rest_pr(head_ref="openspec/foo")
        # Without the adapter, headRefName is missing; falls through to "other"
        result = classify_pr(raw)
        assert result == {"origin": "other", "change_id": None}
