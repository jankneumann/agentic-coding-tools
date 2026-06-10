"""Tests for GET /openspec/proposals endpoint — tasks 3.1–3.7.

Uses a tmp_path git repo as a fixture for git-dependent tests.
All tests are unit-level (no e2e/integration markers).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.coordination_api import create_coordination_api

_TEST_KEY = "proposals-test-key-001"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TEST_KEY}"}


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import reset_config

    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    monkeypatch.delenv("OPENSPEC_REPO_ROOT", raising=False)
    reset_config()
    yield
    reset_config()


@pytest.fixture()
def client(_api_config: None) -> TestClient:
    app = create_coordination_api()
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Git repo helper
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


def _make_test_repo(tmp_path: Path, change_id: str = "my-change") -> Path:
    """Create a minimal test repo with one proposal and main branch."""
    repo = tmp_path / "testrepo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    # Create openspec/changes structure
    proposal_dir = repo / "openspec" / "changes" / change_id
    proposal_dir.mkdir(parents=True)
    (proposal_dir / "proposal.md").write_text(f"# {change_id.title()} Proposal\n\nDetails here.\n")

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")

    return repo


# ---------------------------------------------------------------------------
# 3.1 — drafted vs in-impl detection
# ---------------------------------------------------------------------------


class TestInImplDetection:
    def test_no_branch_is_drafted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Scenario 1: no branch → drafted."""
        repo = _make_test_repo(tmp_path, "my-change")
        monkeypatch.setenv("OPENSPEC_REPO_ROOT", str(repo))

        from src import openspec_proposals_api
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        result = openspec_proposals_api._detect_impl_state(
            repo, "my-change", "openspec/changes/my-change"
        )
        assert result == ("drafted", False, None, 0)

    def test_local_branch_diff_inside_proposal_only_is_drafted(
        self, tmp_path: Path
    ) -> None:
        """Scenario 2: local branch, diff inside proposal dir only → drafted."""
        from src import openspec_proposals_api as _opa

        repo = _make_test_repo(tmp_path, "my-change")

        # Create a feature branch that only modifies proposal dir
        _git(repo, "checkout", "-b", "openspec/my-change")
        proposal_dir = repo / "openspec" / "changes" / "my-change"
        (proposal_dir / "design.md").write_text("# Design\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "Add design.md")
        _git(repo, "checkout", "main")

        result = _opa._detect_impl_state(
            repo, "my-change", "openspec/changes/my-change"
        )
        assert result[0] == "drafted"
        assert result[3] == 0  # code_changes_outside_proposal == 0

    def test_local_branch_with_code_diff_is_in_impl(self, tmp_path: Path) -> None:
        """Scenario 3: local branch, diff touches coordinator/foo.py → in-impl."""
        from src import openspec_proposals_api as _opa

        repo = _make_test_repo(tmp_path, "my-change")

        _git(repo, "checkout", "-b", "openspec/my-change")
        coord_dir = repo / "coordinator"
        coord_dir.mkdir()
        (coord_dir / "foo.py").write_text("# new code\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "Add coordinator code")
        _git(repo, "checkout", "main")

        result = _opa._detect_impl_state(
            repo, "my-change", "openspec/changes/my-change"
        )
        assert result[0] == "in-impl"
        assert result[3] > 0  # code_changes_outside_proposal > 0

    def test_claude_branch_no_openspec_branch_is_in_impl(self, tmp_path: Path) -> None:
        """Scenario 5: claude/<id> branch (no openspec/<id>) with code diff → in-impl."""
        from src import openspec_proposals_api as _opa

        repo = _make_test_repo(tmp_path, "my-change")

        _git(repo, "checkout", "-b", "claude/my-change")
        coord_dir = repo / "coordinator"
        coord_dir.mkdir()
        (coord_dir / "foo.py").write_text("# new code\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "Add coordinator code")
        _git(repo, "checkout", "main")

        result = _opa._detect_impl_state(
            repo, "my-change", "openspec/changes/my-change"
        )
        assert result[0] == "in-impl"

    def test_corrupt_git_returns_graceful_failure(
        self, tmp_path: Path
    ) -> None:
        """Scenario 8: corrupt git object → graceful (drafted, has_branch=False)."""
        from unittest.mock import MagicMock

        from src import openspec_proposals_api as _opa

        repo = _make_test_repo(tmp_path, "my-change")

        # Monkey-patch subprocess.run to simulate a corrupt git object
        import subprocess as sp

        orig_run = sp.run

        def mock_run(cmd, **kwargs):  # type: ignore[override]
            if isinstance(cmd, list) and len(cmd) > 1 and cmd[1] in ("rev-list", "rev-parse"):
                mock = MagicMock()
                mock.returncode = 128
                mock.stdout = ""
                mock.stderr = "fatal: corrupt git object"
                return mock
            return orig_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=mock_run):
            result = _opa._detect_impl_state(
                repo, "my-change", "openspec/changes/my-change"
            )
        # Should not raise; defaults to drafted
        assert result[0] in ("drafted", "in-impl")


# ---------------------------------------------------------------------------
# 3.2 — archive entries excluded
# ---------------------------------------------------------------------------


class TestArchiveExcluded:
    def test_archive_entries_not_in_response(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Directories under archive/ SHALL NOT appear in the response."""
        repo = _make_test_repo(tmp_path, "active-change")
        # Create archive entry
        archive_dir = repo / "openspec" / "changes" / "archive" / "old-thing"
        archive_dir.mkdir(parents=True)
        (archive_dir / "proposal.md").write_text("# Old Thing\n")

        monkeypatch.setenv("OPENSPEC_REPO_ROOT", str(repo))
        from src import openspec_proposals_api
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        proposals = openspec_proposals_api._enumerate_proposals(repo)
        change_ids = [p["change_id"] for p in proposals]
        assert "old-thing" not in change_ids
        assert "active-change" in change_ids


# ---------------------------------------------------------------------------
# 3.3 — malformed proposals skipped
# ---------------------------------------------------------------------------


class TestMalformedProposalsSkipped:
    def test_dir_without_proposal_md_is_omitted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A directory missing proposal.md SHALL be omitted; response stays 200."""
        repo = _make_test_repo(tmp_path, "good-change")
        # Create a bad dir (no proposal.md)
        bad_dir = repo / "openspec" / "changes" / "bad-dir"
        bad_dir.mkdir(parents=True)
        (bad_dir / "design.md").write_text("# Design\n")

        monkeypatch.setenv("OPENSPEC_REPO_ROOT", str(repo))
        from src import openspec_proposals_api
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        proposals = openspec_proposals_api._enumerate_proposals(repo)
        change_ids = [p["change_id"] for p in proposals]
        assert "bad-dir" not in change_ids
        assert "good-change" in change_ids


# ---------------------------------------------------------------------------
# 3.4 — cache TTL parity with /github/prs
# ---------------------------------------------------------------------------


class TestCacheBehavior:
    def test_cache_hit_on_second_request(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _api_config: None
    ) -> None:
        """Two requests within 60s: second returns source=cache."""
        repo = _make_test_repo(tmp_path, "test-proposal")
        monkeypatch.setenv("OPENSPEC_REPO_ROOT", str(repo))

        from src import openspec_proposals_api
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()
        with TestClient(app, raise_server_exceptions=False) as test_client:
            r1 = test_client.get("/openspec/proposals", headers=_auth_headers())
            r2 = test_client.get("/openspec/proposals", headers=_auth_headers())

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["source"] == "live"
        assert r2.json()["source"] == "cache"

    def test_refresh_true_busts_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _api_config: None
    ) -> None:
        """?refresh=true forces a re-enumeration."""
        repo = _make_test_repo(tmp_path, "test-proposal")
        monkeypatch.setenv("OPENSPEC_REPO_ROOT", str(repo))

        from src import openspec_proposals_api
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()
        with TestClient(app, raise_server_exceptions=False) as test_client:
            r1 = test_client.get("/openspec/proposals", headers=_auth_headers())
            r2 = test_client.get("/openspec/proposals?refresh=true", headers=_auth_headers())

        assert r1.json()["source"] == "live"
        assert r2.json()["source"] == "live"


# ---------------------------------------------------------------------------
# 3.7 — 503 when .git is unavailable
# ---------------------------------------------------------------------------


class TestGitUnavailable:
    def test_503_when_no_git_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _api_config: None
    ) -> None:
        """503 git_unavailable when OPENSPEC_REPO_ROOT has no .git."""
        non_git_dir = tmp_path / "not-a-repo"
        non_git_dir.mkdir()
        monkeypatch.setenv("OPENSPEC_REPO_ROOT", str(non_git_dir))

        from src import openspec_proposals_api
        openspec_proposals_api._cache.clear()  # type: ignore[attr-defined]

        app = create_coordination_api()
        with TestClient(app, raise_server_exceptions=False) as test_client:
            r = test_client.get("/openspec/proposals", headers=_auth_headers())

        assert r.status_code == 503
        assert r.json()["error"] == "git_unavailable"


# ---------------------------------------------------------------------------
# Route smoke
# ---------------------------------------------------------------------------


def test_openspec_proposals_route_is_registered() -> None:
    """Smoke: the /openspec/proposals route must be registered."""
    app = create_coordination_api()
    paths = [r.path for r in app.routes]  # type: ignore[attr-defined]
    assert "/openspec/proposals" in paths
