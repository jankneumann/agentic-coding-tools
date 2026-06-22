"""Tests for GET /openspec/proposals multi-source extension — tasks 4.1–4.4a.

These NEW tests extend (but don't replace) the existing test_openspec_proposals_api.py.
All new tests live here to keep scope-of-change clear.

Covers:
  - Multi-source fan-out (local + github sources)
  - All sources fail → 200, proposals:[], _warnings non-empty
  - github_pat_missing when mixed-mode without GITHUB_PAT
  - Implicit local source when OPENSPEC_SOURCES unset
"""
from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.coordination_api import create_coordination_api

_TEST_KEY = "multi-source-test-key-001"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TEST_KEY}"}


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


# ---------------------------------------------------------------------------
# Git repo helper (reused from test_openspec_proposals_api.py)
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    return result.stdout.strip()


def _make_test_repo(
    tmp_path: Path,
    name: str = "testrepo",
    change_id: str = "my-change",
    origin: str | None = "https://github.com/testowner/testrepo.git",
) -> Path:
    """Create a minimal test repo with one proposal and optional origin."""
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    if origin:
        _git(repo, "remote", "add", "origin", origin)

    proposal_dir = repo / "openspec" / "changes" / change_id
    proposal_dir.mkdir(parents=True)
    (proposal_dir / "proposal.md").write_text(
        f"# {change_id.title()} Proposal\n\nDetails here.\n"
    )

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")
    return repo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import reset_config
    from src import openspec_proposals_api

    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    monkeypatch.delenv("OPENSPEC_REPO_ROOT", raising=False)
    monkeypatch.delenv("OPENSPEC_SOURCES", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    reset_config()
    openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]
    openspec_proposals_api._github_cache.clear()  # type: ignore[attr-defined]
    yield
    reset_config()
    openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]
    openspec_proposals_api._github_cache.clear()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Helpers for mock httpx
# ---------------------------------------------------------------------------


class _MockResponse:
    def __init__(self, status_code: int, json_data: Any = None) -> None:
        self.status_code = status_code
        self._json_data = json_data

    def json(self) -> Any:
        return self._json_data


def _make_github_mock(change_ids: list[str], owner_repo: str = "owner/b") -> Any:
    """Create an async mock httpx client for a github source with given changes."""

    listing = [
        {
            "name": cid,
            "path": f"openspec/changes/{cid}",
            "sha": f"sha-{cid}",
            "size": 0,
            "url": "...",
            "html_url": f"https://github.com/{owner_repo}/tree/main/openspec/changes/{cid}",
            "git_url": "...",
            "download_url": None,
            "type": "dir",
        }
        for cid in change_ids
    ]

    async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
        if url.endswith("/contents/openspec/changes"):
            return _MockResponse(200, listing)
        for cid in change_ids:
            if url.endswith(f"/contents/openspec/changes/{cid}"):
                return _MockResponse(
                    200,
                    [
                        {
                            "name": "proposal.md",
                            "path": f"openspec/changes/{cid}/proposal.md",
                            "sha": f"sha-{cid}-pm",
                            "size": 100,
                            "url": "...",
                            "html_url": f"https://github.com/{owner_repo}/blob/main/openspec/changes/{cid}/proposal.md",
                            "git_url": "...",
                            "download_url": None,
                            "type": "file",
                            "content": _b64(f"# {cid}\n\nText.\n"),
                            "encoding": "base64",
                        }
                    ],
                )
        if "/branches/" in url:
            return _MockResponse(404, {})
        return _MockResponse(404, {})

    return _mock_get


# ---------------------------------------------------------------------------
# Task 4.1 — test_multi_source_fan_out
# ---------------------------------------------------------------------------


class TestMultiSourceFanOut:
    def test_local_and_github_proposals_merged(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _api_config: None,
    ) -> None:
        """local:/ + github: sources → both proposal sets in response."""
        repo_a = _make_test_repo(tmp_path, "repo-a", "local-change")
        monkeypatch.setenv(
            "OPENSPEC_SOURCES", f"local:{repo_a},github:owner/b"
        )
        monkeypatch.setenv("GITHUB_PAT", "ghp_test")

        mock_get = _make_github_mock(["github-change-1"], "owner/b")

        from src import openspec_proposals_api, openspec_sources
        openspec_sources.invalidate_local_walk_cache()
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with TestClient(app, raise_server_exceptions=False) as client:
                r = client.get("/openspec/proposals", headers=_auth_headers())

        assert r.status_code == 200
        body = r.json()
        proposals = body["proposals"]
        change_ids = {p["change_id"] for p in proposals}
        assert "local-change" in change_ids
        assert "github-change-1" in change_ids

    def test_response_has_warnings_key(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _api_config: None,
    ) -> None:
        """Response always has _warnings key (even if empty)."""
        repo_a = _make_test_repo(tmp_path, "repo-a2", "change-x")
        monkeypatch.setenv("OPENSPEC_SOURCES", f"local:{repo_a}")

        from src import openspec_proposals_api, openspec_sources
        openspec_sources.invalidate_local_walk_cache()
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/openspec/proposals", headers=_auth_headers())

        assert r.status_code == 200
        body = r.json()
        assert "_warnings" in body

    def test_refresh_true_busts_local_and_github_cache(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _api_config: None,
    ) -> None:
        """?refresh=true forces re-walk of local and re-fetch of github."""
        repo_a = _make_test_repo(tmp_path, "repo-a3", "ch-refresh")
        monkeypatch.setenv("OPENSPEC_SOURCES", f"local:{repo_a},github:owner/b")
        monkeypatch.setenv("GITHUB_PAT", "ghp_test")

        mock_get = _make_github_mock(["gh-ch"], "owner/b")
        call_count = {"n": 0}

        async def _counting_mock_get(url: str, **kwargs: Any) -> _MockResponse:
            call_count["n"] += 1
            return await mock_get(url, **kwargs)

        from src import openspec_proposals_api, openspec_sources
        openspec_sources.invalidate_local_walk_cache()
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = _counting_mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with TestClient(app, raise_server_exceptions=False) as client:
                r1 = client.get("/openspec/proposals", headers=_auth_headers())
                count_after_first = call_count["n"]
                r2 = client.get(
                    "/openspec/proposals?refresh=true", headers=_auth_headers()
                )
                count_after_second = call_count["n"]

        assert r1.status_code == 200
        assert r2.status_code == 200
        # refresh=true should trigger more github calls
        assert count_after_second > count_after_first


# ---------------------------------------------------------------------------
# Task 4.2 — test_all_sources_fail
# ---------------------------------------------------------------------------


class TestAllSourcesFail:
    def test_all_fail_returns_200_with_warnings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _api_config: None,
    ) -> None:
        """All sources fail → 200 OK, proposals:[], _warnings non-empty."""
        missing = tmp_path / "does-not-exist"
        monkeypatch.setenv("OPENSPEC_SOURCES", f"local:{missing},github:owner/b")
        monkeypatch.setenv("GITHUB_PAT", "ghp_test")

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse(404, {"message": "Not Found"})

        from src import openspec_proposals_api, openspec_sources
        openspec_sources.invalidate_local_walk_cache()
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with TestClient(app, raise_server_exceptions=False) as client:
                r = client.get("/openspec/proposals", headers=_auth_headers())

        assert r.status_code == 200
        body = r.json()
        assert body["proposals"] == []
        assert len(body.get("_warnings", [])) >= 1


# ---------------------------------------------------------------------------
# Task 4.3 — test_github_pat_missing_mixed_mode
# ---------------------------------------------------------------------------


class TestGithubPatMissing:
    def test_mixed_mode_without_pat_returns_503(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _api_config: None,
    ) -> None:
        """Mixed-mode config (local + github) with GITHUB_PAT unset → 503."""
        repo_a = _make_test_repo(tmp_path, "repo-b1", "ch-local")
        monkeypatch.setenv("OPENSPEC_SOURCES", f"local:{repo_a},github:owner/x")
        monkeypatch.delenv("GITHUB_PAT", raising=False)

        from src import openspec_proposals_api, openspec_sources
        openspec_sources.invalidate_local_walk_cache()
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/openspec/proposals", headers=_auth_headers())

        assert r.status_code == 503
        body = r.json()
        assert body["error"] == "github_pat_missing"

    def test_local_only_without_pat_serves_normally(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _api_config: None,
    ) -> None:
        """Local-only config without GITHUB_PAT → 200 OK."""
        repo_a = _make_test_repo(tmp_path, "repo-b2", "ch-local2")
        monkeypatch.setenv("OPENSPEC_SOURCES", f"local:{repo_a}")
        monkeypatch.delenv("GITHUB_PAT", raising=False)

        from src import openspec_proposals_api, openspec_sources
        openspec_sources.invalidate_local_walk_cache()
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/openspec/proposals", headers=_auth_headers())

        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Task 4.4a — test_implicit_local_source_unset_env
# ---------------------------------------------------------------------------


class TestImplicitLocalSource:
    def test_openspec_sources_unset_uses_own_repo(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _api_config: None,
    ) -> None:
        """When OPENSPEC_SOURCES unset, coordinator's own checkout is implicit source."""
        repo = _make_test_repo(
            tmp_path,
            "own-repo",
            "implicit-change",
            origin="https://github.com/myowner/myrepo.git",
        )
        monkeypatch.setenv("OPENSPEC_REPO_ROOT", str(repo))
        monkeypatch.delenv("OPENSPEC_SOURCES", raising=False)

        from src import openspec_proposals_api, openspec_sources
        openspec_sources.invalidate_local_walk_cache()
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/openspec/proposals", headers=_auth_headers())

        assert r.status_code == 200
        body = r.json()
        proposals = body["proposals"]
        assert len(proposals) >= 1

        # All proposals must have repo derived from origin (myowner/myrepo)
        for p in proposals:
            assert p.get("repo") == "myowner/myrepo", (
                f"Expected repo=myowner/myrepo, got {p.get('repo')!r}"
            )

    def test_implicit_local_source_proposals_have_namespaced_id(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _api_config: None,
    ) -> None:
        """Implicit source proposals have change_id_namespaced set."""
        repo = _make_test_repo(
            tmp_path,
            "own-repo2",
            "ns-change",
            origin="https://github.com/owner/repo.git",
        )
        monkeypatch.setenv("OPENSPEC_REPO_ROOT", str(repo))
        monkeypatch.delenv("OPENSPEC_SOURCES", raising=False)

        from src import openspec_proposals_api, openspec_sources
        openspec_sources.invalidate_local_walk_cache()
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/openspec/proposals", headers=_auth_headers())

        assert r.status_code == 200
        proposals = r.json()["proposals"]
        assert len(proposals) >= 1
        for p in proposals:
            assert p.get("change_id_namespaced") == f"owner/repo/{p['change_id']}"

    def test_invalid_openspec_sources_returns_503(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _api_config: None,
    ) -> None:
        """Invalid OPENSPEC_SOURCES entry → 503 with openspec_sources_invalid."""
        monkeypatch.setenv("OPENSPEC_SOURCES", "github:not_a_valid_entry")

        from src import openspec_proposals_api, openspec_sources
        openspec_sources.invalidate_local_walk_cache()
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/openspec/proposals", headers=_auth_headers())

        assert r.status_code == 503
        assert r.json()["error"] == "openspec_sources_invalid"
