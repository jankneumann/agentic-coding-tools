"""Tests for github_openspec_fetcher.py — tasks 3.1, 3.1a, 3.2, 3.3.

Covers:
  - Basic fetch: 3 ProposalCards from a source, correct field shapes.
  - REST field-shape adapter: fixture-driven sentinel for html_url / type filtering.
  - Budget cap: 80 changes + default cap=50 → truncated + warning.
  - Degraded modes: 404, 401/403, timeout.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.openspec_sources import SourceDescriptor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "github_contents_openspec_changes.json"

_PAT = "ghp_test_token"


def _make_source(spec: str = "owner/repo") -> SourceDescriptor:
    return SourceDescriptor(kind="github", spec=spec, repo=spec)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def _proposal_content_response(change_id: str) -> dict[str, Any]:
    """Simulate a /contents/openspec/changes/{change_id}/proposal.md response."""
    return {
        "name": "proposal.md",
        "path": f"openspec/changes/{change_id}/proposal.md",
        "sha": f"sha-{change_id}",
        "size": 100,
        "url": f"https://api.github.com/repos/owner/repo/contents/openspec/changes/{change_id}/proposal.md",
        "html_url": f"https://github.com/owner/repo/blob/main/openspec/changes/{change_id}/proposal.md",
        "git_url": f"https://api.github.com/repos/owner/repo/git/blobs/sha-{change_id}",
        "download_url": f"https://raw.githubusercontent.com/owner/repo/main/openspec/changes/{change_id}/proposal.md",
        "type": "file",
        "content": _b64(f"# {change_id} Proposal\n\nSome text.\n"),
        "encoding": "base64",
    }


def _change_dir_listing(change_id: str) -> list[dict[str, Any]]:
    """Return a minimal /contents/openspec/changes/{change_id} listing."""
    return [
        {
            "name": "proposal.md",
            "path": f"openspec/changes/{change_id}/proposal.md",
            "sha": f"sha-{change_id}-pm",
            "size": 100,
            "url": f"https://api.github.com/repos/owner/repo/contents/openspec/changes/{change_id}/proposal.md",
            "html_url": f"https://github.com/owner/repo/blob/main/openspec/changes/{change_id}/proposal.md",
            "git_url": "...",
            "download_url": None,
            "type": "file",
            "content": _b64(f"# {change_id} Proposal\n\nSome text.\n"),
            "encoding": "base64",
        }
    ]


def _branch_not_found() -> dict[str, Any]:
    return {"message": "Branch not found"}


def _branch_found(change_id: str) -> dict[str, Any]:
    return {
        "name": f"openspec/{change_id}",
        "commit": {"sha": "abc123", "url": "..."},
    }


def _compare_response(ahead_by: int = 0, files_outside: int = 0) -> dict[str, Any]:
    """Simulate a /compare response."""
    files = []
    for i in range(files_outside):
        files.append({"filename": f"src/file_{i}.py", "status": "modified"})
    # Add a file INSIDE the proposal dir (should not count)
    files.append({"filename": "openspec/changes/foo/proposal.md", "status": "modified"})
    return {
        "ahead_by": ahead_by,
        "files": files,
    }


# ---------------------------------------------------------------------------
# Async mock context manager for httpx.AsyncClient
# ---------------------------------------------------------------------------


class _MockResponse:
    def __init__(self, status_code: int, json_data: Any = None) -> None:
        self.status_code = status_code
        self._json_data = json_data

    def json(self) -> Any:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=MagicMock(),
                response=MagicMock(status_code=self.status_code),
            )


# ---------------------------------------------------------------------------
# Task 3.1 — test_fetch_proposals_basic
# ---------------------------------------------------------------------------


class TestFetchProposalsBasic:
    @pytest.mark.asyncio
    async def test_three_proposals_returned(self) -> None:
        """3 change dirs in listing → 3 ProposalCards, all with repo set."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")
        change_ids = ["add-langfuse-tracing", "fix-auth", "refactor-db"]

        # directory listing returns 3 dirs + archive (to be excluded) + a file
        directory_listing = [
            {
                "name": cid,
                "path": f"openspec/changes/{cid}",
                "sha": f"sha-{cid}",
                "size": 0,
                "url": f"https://api.github.com/repos/owner/repo/contents/openspec/changes/{cid}",
                "html_url": f"https://github.com/owner/repo/tree/main/openspec/changes/{cid}",
                "git_url": "...",
                "download_url": None,
                "type": "dir",
            }
            for cid in change_ids
        ] + [
            {
                "name": "archive",
                "path": "openspec/changes/archive",
                "sha": "dead",
                "size": 0,
                "url": "...",
                "html_url": "...",
                "git_url": "...",
                "download_url": None,
                "type": "dir",
            },
            {
                "name": "README.md",
                "path": "openspec/changes/README.md",
                "sha": "cafe",
                "size": 10,
                "url": "...",
                "html_url": "...",
                "git_url": "...",
                "download_url": "...",
                "type": "file",
            },
        ]

        call_log: list[str] = []

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            call_log.append(url)
            if url.endswith("/contents/openspec/changes"):
                return _MockResponse(200, directory_listing)
            # Per-change dir listing
            for cid in change_ids:
                if url.endswith(f"/contents/openspec/changes/{cid}"):
                    return _MockResponse(200, _change_dir_listing(cid))
            # Branch check → 404 (no branch)
            if "/branches/" in url:
                return _MockResponse(404, _branch_not_found())
            # Default fallback
            return _MockResponse(404, {"message": "Not found"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, warnings = await fetch_proposals_from_github(
                source, _PAT, budget=50
            )

        assert len(proposals) == 3
        assert warnings == []

        for card in proposals:
            assert card["repo"] == "owner/repo"
            assert card["kind"] == "proposal"
            assert "proposal_path" in card
            # proposal_path must be the html_url of the proposal.md entry
            assert "github.com/owner/repo/blob/main/openspec/changes" in card["proposal_path"]

    @pytest.mark.asyncio
    async def test_has_branch_true_when_branch_exists(self) -> None:
        """Branch exists → has_branch=True, branch_name set."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")
        change_id = "my-change"

        directory_listing = [
            {
                "name": change_id,
                "path": f"openspec/changes/{change_id}",
                "sha": "sha1",
                "size": 0,
                "url": "...",
                "html_url": f"https://github.com/owner/repo/tree/main/openspec/changes/{change_id}",
                "git_url": "...",
                "download_url": None,
                "type": "dir",
            }
        ]

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            if url.endswith("/contents/openspec/changes"):
                return _MockResponse(200, directory_listing)
            if url.endswith(f"/contents/openspec/changes/{change_id}"):
                return _MockResponse(200, _change_dir_listing(change_id))
            if f"/branches/openspec/{change_id}" in url:
                return _MockResponse(200, _branch_found(change_id))
            if "/compare/" in url:
                return _MockResponse(200, _compare_response(ahead_by=3, files_outside=2))
            return _MockResponse(404, {})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, warnings = await fetch_proposals_from_github(
                source, _PAT, budget=50
            )

        assert len(proposals) == 1
        card = proposals[0]
        assert card["has_branch"] is True
        assert change_id in card["branch_name"]


# ---------------------------------------------------------------------------
# Task 3.1a — test_rest_field_shape_adapter (fixture-driven)
# ---------------------------------------------------------------------------


class TestRestFieldShapeAdapter:
    @pytest.mark.asyncio
    async def test_fixture_filters_type_dir_only(self) -> None:
        """Only type==dir entries (excluding archive/) should be processed."""
        fixture = json.loads(_FIXTURE_PATH.read_text())

        # Verify fixture shape: dirs are add-langfuse-tracing, fix-auth, refactor-db, archive
        dirs = [e for e in fixture if e["type"] == "dir"]
        non_archive_dirs = [e for e in dirs if e["name"] != "archive"]
        files = [e for e in fixture if e["type"] == "file"]

        assert len(dirs) == 4
        assert len(non_archive_dirs) == 3
        assert len(files) == 1

        # The fetcher must skip archive and file entries
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")

        proposal_content: dict[str, Any] = _proposal_content_response("placeholder")

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            if url.endswith("/contents/openspec/changes"):
                return _MockResponse(200, fixture)
            # Per-change dir listing
            for name in ["add-langfuse-tracing", "fix-auth", "refactor-db"]:
                if url.endswith(f"/contents/openspec/changes/{name}"):
                    listing = [dict(proposal_content)]
                    listing[0]["path"] = f"openspec/changes/{name}/proposal.md"
                    listing[0]["html_url"] = f"https://github.com/owner/repo/blob/main/openspec/changes/{name}/proposal.md"
                    listing[0]["content"] = _b64(f"# {name}\n\nText.\n")
                    return _MockResponse(200, listing)
            if "/branches/" in url:
                return _MockResponse(404, {})
            return _MockResponse(404, {})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, warnings = await fetch_proposals_from_github(
                source, _PAT, budget=50
            )

        # Only 3 non-archive dirs should produce proposals
        assert len(proposals) == 3
        change_ids = {p["change_id"] for p in proposals}
        assert change_ids == {"add-langfuse-tracing", "fix-auth", "refactor-db"}

    @pytest.mark.asyncio
    async def test_proposal_path_is_html_url_not_concatenated(self) -> None:
        """proposal_path must come from html_url, NOT manual concatenation."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")

        # Simulate a non-standard branch name — html_url would differ from
        # manually concatenated path
        expected_html_url = "https://github.com/owner/repo/blob/feature-branch/openspec/changes/my-change/proposal.md"

        directory_listing = [
            {
                "name": "my-change",
                "path": "openspec/changes/my-change",
                "sha": "abc",
                "size": 0,
                "url": "...",
                "html_url": "https://github.com/owner/repo/tree/feature-branch/openspec/changes/my-change",
                "git_url": "...",
                "download_url": None,
                "type": "dir",
            }
        ]

        proposal_content = {
            "name": "proposal.md",
            "path": "openspec/changes/my-change/proposal.md",
            "sha": "abc",
            "size": 100,
            "url": "...",
            "html_url": expected_html_url,
            "git_url": "...",
            "download_url": None,
            "type": "file",
            "content": _b64("# My Change\n\nText.\n"),
            "encoding": "base64",
        }

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            if url.endswith("/contents/openspec/changes"):
                return _MockResponse(200, directory_listing)
            if url.endswith("/contents/openspec/changes/my-change"):
                return _MockResponse(200, [proposal_content])
            if "/branches/" in url:
                return _MockResponse(404, {})
            return _MockResponse(404, {})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, _ = await fetch_proposals_from_github(source, _PAT, budget=50)

        assert len(proposals) == 1
        # CRITICAL: must use html_url, not manual concatenation
        assert proposals[0]["proposal_path"] == expected_html_url

    @pytest.mark.asyncio
    async def test_title_parsed_from_base64_content(self) -> None:
        """H1 title must be extracted from base64-decoded content field."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")
        expected_title = "My Fantastic Proposal"

        directory_listing = [
            {
                "name": "my-proposal",
                "path": "openspec/changes/my-proposal",
                "sha": "abc",
                "size": 0,
                "url": "...",
                "html_url": "https://github.com/owner/repo/tree/main/openspec/changes/my-proposal",
                "git_url": "...",
                "download_url": None,
                "type": "dir",
            }
        ]

        proposal_listing = [
            {
                "name": "proposal.md",
                "path": "openspec/changes/my-proposal/proposal.md",
                "sha": "abc",
                "size": 100,
                "url": "...",
                "html_url": "https://github.com/owner/repo/blob/main/openspec/changes/my-proposal/proposal.md",
                "git_url": "...",
                "download_url": None,
                "type": "file",
                "content": _b64(f"# {expected_title}\n\nBody text.\n"),
                "encoding": "base64",
            }
        ]

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            if url.endswith("/contents/openspec/changes"):
                return _MockResponse(200, directory_listing)
            if url.endswith("/contents/openspec/changes/my-proposal"):
                return _MockResponse(200, proposal_listing)
            if "/branches/" in url:
                return _MockResponse(404, {})
            return _MockResponse(404, {})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, _ = await fetch_proposals_from_github(source, _PAT, budget=50)

        assert len(proposals) == 1
        assert proposals[0]["title"] == expected_title


# ---------------------------------------------------------------------------
# Task 3.2 — test_budget_cap
# ---------------------------------------------------------------------------


class TestBudgetCap:
    @pytest.mark.asyncio
    async def test_default_cap_50_truncates_80_changes(self) -> None:
        """80 changes + default cap=50 → 50 proposals + github_budget_exceeded warning."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")
        # Create 80 change directories (alphabetically sorted)
        change_ids = [f"change-{i:03d}" for i in range(80)]

        directory_listing = [
            {
                "name": cid,
                "path": f"openspec/changes/{cid}",
                "sha": f"sha-{cid}",
                "size": 0,
                "url": "...",
                "html_url": f"https://github.com/owner/repo/tree/main/openspec/changes/{cid}",
                "git_url": "...",
                "download_url": None,
                "type": "dir",
            }
            for cid in change_ids
        ]

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            if url.endswith("/contents/openspec/changes"):
                return _MockResponse(200, directory_listing)
            # Per-change dir listing
            for cid in change_ids:
                if url.endswith(f"/contents/openspec/changes/{cid}"):
                    return _MockResponse(200, _change_dir_listing(cid))
            if "/branches/" in url:
                return _MockResponse(404, {})
            return _MockResponse(404, {})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, warnings = await fetch_proposals_from_github(
                source, _PAT, budget=50
            )

        assert len(proposals) == 50
        assert any(w["error"] == "github_budget_exceeded" for w in warnings)
        # Warning message mentions 30 changes truncated
        budget_warn = next(w for w in warnings if w["error"] == "github_budget_exceeded")
        assert "30" in budget_warn.get("message", "")

    @pytest.mark.asyncio
    async def test_cap_100_returns_all_80_changes(self) -> None:
        """OPENSPEC_SOURCES_GITHUB_CAP=100 → all 80 changes returned, no budget warning."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")
        change_ids = [f"change-{i:03d}" for i in range(80)]

        directory_listing = [
            {
                "name": cid,
                "path": f"openspec/changes/{cid}",
                "sha": f"sha-{cid}",
                "size": 0,
                "url": "...",
                "html_url": f"https://github.com/owner/repo/tree/main/openspec/changes/{cid}",
                "git_url": "...",
                "download_url": None,
                "type": "dir",
            }
            for cid in change_ids
        ]

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            if url.endswith("/contents/openspec/changes"):
                return _MockResponse(200, directory_listing)
            for cid in change_ids:
                if url.endswith(f"/contents/openspec/changes/{cid}"):
                    return _MockResponse(200, _change_dir_listing(cid))
            if "/branches/" in url:
                return _MockResponse(404, {})
            return _MockResponse(404, {})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, warnings = await fetch_proposals_from_github(
                source, _PAT, budget=100
            )

        assert len(proposals) == 80
        assert not any(w["error"] == "github_budget_exceeded" for w in warnings)

    @pytest.mark.asyncio
    async def test_alphabetical_sort_before_truncation(self) -> None:
        """Alphabetically first 50 change_ids are returned when budget is 50."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")
        # Create names that would sort differently if not sorted
        change_ids = [f"z-change-{i:03d}" for i in range(40)] + [
            f"a-change-{i:03d}" for i in range(40)
        ]

        directory_listing = [
            {
                "name": cid,
                "path": f"openspec/changes/{cid}",
                "sha": f"sha-{cid}",
                "size": 0,
                "url": "...",
                "html_url": f"https://github.com/owner/repo/tree/main/openspec/changes/{cid}",
                "git_url": "...",
                "download_url": None,
                "type": "dir",
            }
            for cid in change_ids
        ]

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            if url.endswith("/contents/openspec/changes"):
                return _MockResponse(200, directory_listing)
            for cid in change_ids:
                if url.endswith(f"/contents/openspec/changes/{cid}"):
                    return _MockResponse(200, _change_dir_listing(cid))
            if "/branches/" in url:
                return _MockResponse(404, {})
            return _MockResponse(404, {})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, _ = await fetch_proposals_from_github(source, _PAT, budget=50)

        # Should return the alphabetically first 50 (all a-change-* + 10 z-change-*)
        returned_ids = {p["change_id"] for p in proposals}
        assert all(cid in returned_ids for cid in [f"a-change-{i:03d}" for i in range(40)])
        # z-change entries should only partially appear (10 of 40)
        z_count = sum(1 for cid in returned_ids if cid.startswith("z-"))
        assert z_count == 10


# ---------------------------------------------------------------------------
# Task 3.3 — test_degraded_modes
# ---------------------------------------------------------------------------


class TestDegradedModes:
    @pytest.mark.asyncio
    async def test_404_returns_github_404_warning(self) -> None:
        """404 on directory listing → github_404 warning, no exception."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/nonexistent")

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse(404, {"message": "Not Found"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, warnings = await fetch_proposals_from_github(
                source, _PAT, budget=50
            )

        assert proposals == []
        assert any(w["error"] == "github_404" for w in warnings)
        w = next(w for w in warnings if w["error"] == "github_404")
        assert w["source"] == "github:owner/nonexistent"

    @pytest.mark.asyncio
    async def test_401_returns_github_pat_denied_warning(self) -> None:
        """401 → github_pat_denied warning."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse(401, {"message": "Bad credentials"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, warnings = await fetch_proposals_from_github(
                source, _PAT, budget=50
            )

        assert proposals == []
        assert any(w["error"] == "github_pat_denied" for w in warnings)

    @pytest.mark.asyncio
    async def test_403_returns_github_pat_denied_warning(self) -> None:
        """403 → github_pat_denied warning."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse(403, {"message": "Forbidden"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, warnings = await fetch_proposals_from_github(
                source, _PAT, budget=50
            )

        assert proposals == []
        assert any(w["error"] == "github_pat_denied" for w in warnings)

    @pytest.mark.asyncio
    async def test_timeout_returns_github_timeout_warning(self) -> None:
        """Timeout → github_timeout warning, no exception bubbles."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            raise httpx.TimeoutException("Request timed out")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            proposals, warnings = await fetch_proposals_from_github(
                source, _PAT, budget=50
            )

        assert proposals == []
        assert any(w["error"] == "github_timeout" for w in warnings)

    @pytest.mark.asyncio
    async def test_failed_source_does_not_bubble_exception(self) -> None:
        """Any source failure should return empty list + warning, never raise."""
        from src.github_openspec_fetcher import fetch_proposals_from_github

        source = _make_source("owner/repo")

        async def _mock_get(url: str, **kwargs: Any) -> _MockResponse:
            raise Exception("Unexpected network error")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Must not raise
            proposals, warnings = await fetch_proposals_from_github(
                source, _PAT, budget=50
            )

        assert proposals == []
        assert len(warnings) >= 1
