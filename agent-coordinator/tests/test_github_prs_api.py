"""Tests for GET /github/prs endpoint — tasks 2.1–2.7.

Uses FastAPI TestClient with mocked httpx to avoid network calls.
All tests are unit-level (no e2e/integration markers).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.coordination_api import create_coordination_api

_TEST_KEY = "github-prs-test-key-001"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TEST_KEY}"}


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import reset_config

    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.delenv("GITHUB_REPOS", raising=False)
    reset_config()
    yield
    reset_config()


@pytest.fixture()
def client(_api_config: None) -> TestClient:
    app = create_coordination_api()
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helper: build a minimal GitHub REST PR payload
# ---------------------------------------------------------------------------

def _make_rest_pr(
    number: int = 1,
    head_ref: str = "openspec/test-change",
    author_login: str = "alice",
    draft: bool = False,
    updated_at: str = "2025-06-01T12:00:00Z",
    created_at: str = "2025-06-01T10:00:00Z",
) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"PR #{number}",
        "body": "",
        "head": {"ref": head_ref},
        "base": {"ref": "main"},
        "user": {"login": author_login},
        "labels": [],
        "draft": draft,
        "html_url": f"https://github.com/owner/repo/pull/{number}",
        "created_at": created_at,
        "updated_at": updated_at,
        "state": "open",
    }


# ---------------------------------------------------------------------------
# 2.1 — 503 when GITHUB_PAT is not set
# ---------------------------------------------------------------------------


class TestMissingPat:
    def test_503_when_pat_missing(self, client: TestClient) -> None:
        """GET /github/prs without GITHUB_PAT returns 503 with structured error."""
        response = client.get("/github/prs", headers=_auth_headers())
        assert response.status_code == 503
        body = response.json()
        assert body["error"] == "github_pat_missing"

    def test_401_when_no_auth(self, client: TestClient) -> None:
        """Unauthenticated request returns 401 before PAT check."""
        response = client.get("/github/prs")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# 2.2 — Cache TTL + refresh=true
# ---------------------------------------------------------------------------


class TestCacheBehavior:
    def test_cache_hit_on_second_request(
        self, monkeypatch: pytest.MonkeyPatch, _api_config: None
    ) -> None:
        """Two requests within 60s: second returns source=cache, mock called once."""
        monkeypatch.setenv("GITHUB_PAT", "ghp_test_token")
        monkeypatch.setenv("GITHUB_REPOS", "owner/repo")

        call_count = 0

        async def mock_fetch_prs_for_repo(
            repo: str, pat: str
        ) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            return [_make_rest_pr()]

        from src import github_prs_api
        # Reset cache before the test
        github_prs_api._cache.clear()  # type: ignore[attr-defined]

        with patch.object(
            github_prs_api, "_fetch_prs_for_repo", side_effect=mock_fetch_prs_for_repo
        ):
            app = create_coordination_api()
            with TestClient(app, raise_server_exceptions=False) as test_client:
                r1 = test_client.get("/github/prs", headers=_auth_headers())
                r2 = test_client.get("/github/prs", headers=_auth_headers())

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["source"] == "live"
        assert r2.json()["source"] == "cache"
        assert call_count == 1

    def test_refresh_true_busts_cache(
        self, monkeypatch: pytest.MonkeyPatch, _api_config: None
    ) -> None:
        """?refresh=true forces a re-fetch even within the 60s window."""
        monkeypatch.setenv("GITHUB_PAT", "ghp_test_token")
        monkeypatch.setenv("GITHUB_REPOS", "owner/repo")

        call_count = 0

        async def mock_fetch_prs_for_repo(
            repo: str, pat: str
        ) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            return [_make_rest_pr()]

        from src import github_prs_api
        github_prs_api._cache.clear()  # type: ignore[attr-defined]

        with patch.object(
            github_prs_api, "_fetch_prs_for_repo", side_effect=mock_fetch_prs_for_repo
        ):
            app = create_coordination_api()
            with TestClient(app, raise_server_exceptions=False) as test_client:
                r1 = test_client.get("/github/prs", headers=_auth_headers())
                r2 = test_client.get("/github/prs?refresh=true", headers=_auth_headers())

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["source"] == "live"
        assert call_count == 2


# ---------------------------------------------------------------------------
# 2.3 — review-summary reducer
# ---------------------------------------------------------------------------


class TestReduceReviews:
    def _make_review(
        self, state: str, user_login: str = "reviewer", dismissed: bool = False
    ) -> dict[str, Any]:
        return {
            "state": "DISMISSED" if dismissed else state.upper(),
            "user": {"login": user_login},
            "submitted_at": "2025-06-01T11:00:00Z",
        }

    def test_approved_state(self) -> None:
        from src.github_prs_api import reduce_reviews

        reviews = [self._make_review("APPROVED", "alice")]
        result = reduce_reviews(reviews)
        assert result["state"] == "approved"
        assert result["reviewer_count"] == 1
        assert result["last_reviewed_at_iso"] is not None

    def test_changes_requested_wins_over_approved(self) -> None:
        from src.github_prs_api import reduce_reviews

        # Reviewer first approved, then requested changes
        reviews = [
            self._make_review("APPROVED", "alice"),
            self._make_review("CHANGES_REQUESTED", "alice"),
        ]
        result = reduce_reviews(reviews)
        assert result["state"] == "changes_requested"

    def test_no_reviews_returns_none_state(self) -> None:
        from src.github_prs_api import reduce_reviews

        result = reduce_reviews([])
        assert result["state"] == "none"
        assert result["reviewer_count"] == 0
        assert result["last_reviewed_at_iso"] is None

    def test_dismissed_reviews_excluded(self) -> None:
        from src.github_prs_api import reduce_reviews

        reviews = [self._make_review("APPROVED", "alice", dismissed=True)]
        result = reduce_reviews(reviews)
        assert result["state"] == "none"
        assert result["reviewer_count"] == 0

    def test_multi_reviewer_latest_per_reviewer(self) -> None:
        from src.github_prs_api import reduce_reviews

        # alice approved, bob requested changes → changes_requested wins
        reviews = [
            self._make_review("APPROVED", "alice"),
            self._make_review("CHANGES_REQUESTED", "bob"),
        ]
        result = reduce_reviews(reviews)
        assert result["state"] == "changes_requested"
        assert result["reviewer_count"] == 2

    def test_commented_state(self) -> None:
        from src.github_prs_api import reduce_reviews

        reviews = [self._make_review("COMMENTED", "alice")]
        result = reduce_reviews(reviews)
        assert result["state"] == "commented"


# ---------------------------------------------------------------------------
# 2.6 — PRCard.status derivation
# ---------------------------------------------------------------------------


class TestPrStatusDerivation:
    def test_draft_takes_precedence(self) -> None:
        from src.github_prs_api import derive_pr_status

        review = {"state": "approved", "reviewer_count": 1, "last_reviewed_at_iso": None}
        assert derive_pr_status(is_draft=True, review_summary=review) == "draft"

    def test_changes_requested_after_non_draft(self) -> None:
        from src.github_prs_api import derive_pr_status

        review = {"state": "changes_requested", "reviewer_count": 1, "last_reviewed_at_iso": None}
        assert derive_pr_status(is_draft=False, review_summary=review) == "changes_requested"

    def test_approved(self) -> None:
        from src.github_prs_api import derive_pr_status

        review = {"state": "approved", "reviewer_count": 1, "last_reviewed_at_iso": None}
        assert derive_pr_status(is_draft=False, review_summary=review) == "approved"

    def test_has_reviews_but_only_commented(self) -> None:
        from src.github_prs_api import derive_pr_status

        review = {"state": "commented", "reviewer_count": 1, "last_reviewed_at_iso": None}
        assert derive_pr_status(is_draft=False, review_summary=review) == "review"

    def test_no_reviews_is_open(self) -> None:
        from src.github_prs_api import derive_pr_status

        review = {"state": "none", "reviewer_count": 0, "last_reviewed_at_iso": None}
        assert derive_pr_status(is_draft=False, review_summary=review) == "open"


# ---------------------------------------------------------------------------
# 2.7 — GITHUB_REPOS handling
# ---------------------------------------------------------------------------


class TestGithubReposEnv:
    def test_defaults_to_agentic_coding_tools(
        self, monkeypatch: pytest.MonkeyPatch, _api_config: None
    ) -> None:
        """Unset GITHUB_REPOS defaults to jankneumann/agentic-coding-tools."""
        monkeypatch.setenv("GITHUB_PAT", "ghp_test_token")
        monkeypatch.delenv("GITHUB_REPOS", raising=False)

        captured_repos: list[str] = []

        async def mock_fetch_prs_for_repo(repo: str, pat: str) -> list[dict]:
            captured_repos.append(repo)
            return []

        from src import github_prs_api
        github_prs_api._cache.clear()  # type: ignore[attr-defined]

        with patch.object(
            github_prs_api, "_fetch_prs_for_repo", side_effect=mock_fetch_prs_for_repo
        ):
            app = create_coordination_api()
            with TestClient(app, raise_server_exceptions=False) as test_client:
                r = test_client.get("/github/prs", headers=_auth_headers())

        assert r.status_code == 200
        assert captured_repos == ["jankneumann/agentic-coding-tools"]

    def test_invalid_repos_entry_returns_503(
        self, monkeypatch: pytest.MonkeyPatch, _api_config: None
    ) -> None:
        """A repo entry that doesn't match owner/name pattern → 503."""
        monkeypatch.setenv("GITHUB_PAT", "ghp_test_token")
        monkeypatch.setenv("GITHUB_REPOS", "valid/repo,not_a_valid_entry")

        from src import github_prs_api
        github_prs_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()
        with TestClient(app, raise_server_exceptions=False) as test_client:
            r = test_client.get("/github/prs", headers=_auth_headers())

        assert r.status_code == 503
        assert r.json()["error"] == "github_repos_invalid"

    def test_multi_repo_fan_out(
        self, monkeypatch: pytest.MonkeyPatch, _api_config: None
    ) -> None:
        """Two valid repos → results are union-sorted by updated_at descending."""
        monkeypatch.setenv("GITHUB_PAT", "ghp_test_token")
        monkeypatch.setenv("GITHUB_REPOS", "a/b,c/d")

        def _make_pr_card(number: int, repo: str, updated_at: str) -> dict[str, Any]:
            return {
                "kind": "pr",
                "id": f"pr:{repo}:{number}",
                "change_id": None,
                "repo": repo,
                "number": number,
                "title": f"PR #{number}",
                "author": "alice",
                "head_branch": "feature/test",
                "base_branch": "main",
                "origin": "manual",
                "status": "open",
                "review_summary": {
                    "state": "none",
                    "reviewer_count": 0,
                    "last_reviewed_at_iso": None,
                },
                "is_draft": False,
                "url": f"https://github.com/{repo}/pull/{number}",
                "created_at_iso": "2025-06-01T10:00:00Z",
                "updated_at_iso": updated_at,
            }

        async def mock_fetch_prs_for_repo(repo: str, pat: str) -> list[dict]:
            if repo == "a/b":
                return [_make_pr_card(1, "a/b", "2025-01-01T10:00:00Z")]
            else:  # c/d
                return [_make_pr_card(2, "c/d", "2025-01-02T10:00:00Z")]

        from src import github_prs_api
        github_prs_api._cache.clear()  # type: ignore[attr-defined]

        with patch.object(
            github_prs_api, "_fetch_prs_for_repo", side_effect=mock_fetch_prs_for_repo
        ):
            app = create_coordination_api()
            with TestClient(app, raise_server_exceptions=False) as test_client:
                r = test_client.get("/github/prs", headers=_auth_headers())

        assert r.status_code == 200
        prs = r.json()["prs"]
        assert len(prs) == 2
        # Sorted newest first (c/d PR has later updated_at)
        assert prs[0]["number"] == 2
        assert prs[1]["number"] == 1


# ---------------------------------------------------------------------------
# 2.5 — Route registration smoke test
# ---------------------------------------------------------------------------


def test_github_prs_route_is_registered() -> None:
    """Smoke: the /github/prs route must be registered in the app."""
    app = create_coordination_api()
    paths = [r.path for r in app.routes]  # type: ignore[attr-defined]
    assert "/github/prs" in paths
