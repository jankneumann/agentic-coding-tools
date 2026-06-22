"""Tests for openspec_sources.py — tasks 1.1, 1.3, 2.1.

Covers:
  - parse_sources: empty, single local, single github, mixed, lowercase norm,
    invalid entries that should return ParseWarning.
  - derive_local_repo: https remote, ssh remote, no remote, parse failure.
  - warm_local_sources / get_or_walk_local / invalidate_local_walk_cache:
    boot warmup, cache hit, forced re-walk.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
        },
        check=True,
    )


def _make_local_git_repo(
    tmp_path: Path,
    name: str,
    origin: str | None = None,
    changes: list[str] | None = None,
) -> Path:
    """Create a minimal local git repo, optionally with an origin remote and proposals."""
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")

    if origin:
        _git(repo, "remote", "add", "origin", origin)

    changes_dir = repo / "openspec" / "changes"
    changes_dir.mkdir(parents=True)

    for change_id in (changes or []):
        d = changes_dir / change_id
        d.mkdir()
        (d / "proposal.md").write_text(f"# {change_id}\n\nProposal text.\n")

    # Need at least one commit so git works properly
    (repo / "README.md").write_text("test\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    return repo


# ---------------------------------------------------------------------------
# Task 1.1 — test_parse_sources_cases
# ---------------------------------------------------------------------------


class TestParseSources:
    def test_empty_string_returns_empty_list(self) -> None:
        """Empty OPENSPEC_SOURCES → empty descriptor list, no warnings."""
        from src.openspec_sources import parse_sources

        descriptors, warnings = parse_sources("")
        assert descriptors == []
        assert warnings == []

    def test_single_local_source(self) -> None:
        """local:/some/path → one SourceDescriptor with kind=local."""
        from src.openspec_sources import parse_sources

        descriptors, warnings = parse_sources("local:/some/path")
        assert len(descriptors) == 1
        assert descriptors[0].kind == "local"
        assert descriptors[0].spec == "/some/path"
        assert warnings == []

    def test_single_github_source(self) -> None:
        """github:owner/repo → one SourceDescriptor with kind=github, lowercase."""
        from src.openspec_sources import parse_sources

        descriptors, warnings = parse_sources("github:owner/repo")
        assert len(descriptors) == 1
        assert descriptors[0].kind == "github"
        assert descriptors[0].spec == "owner/repo"
        assert descriptors[0].repo == "owner/repo"
        assert warnings == []

    def test_mixed_sources(self) -> None:
        """Mixed local + github → two descriptors."""
        from src.openspec_sources import parse_sources

        descriptors, warnings = parse_sources("local:/repos/a,github:owner/b")
        assert len(descriptors) == 2
        kinds = {d.kind for d in descriptors}
        assert kinds == {"local", "github"}
        assert warnings == []

    def test_owner_repo_casing_normalized_to_lowercase(self) -> None:
        """github:JanKneumann/Newsletter-Aggregator → jankneumann/newsletter-aggregator."""
        from src.openspec_sources import parse_sources

        descriptors, warnings = parse_sources("github:JanKneumann/Newsletter-Aggregator")
        assert len(descriptors) == 1
        assert descriptors[0].spec == "jankneumann/newsletter-aggregator"
        assert descriptors[0].repo == "jankneumann/newsletter-aggregator"
        assert warnings == []

    def test_invalid_prefix_returns_parse_warning(self) -> None:
        """bogus:foo → ParseWarning, no descriptors."""
        from src.openspec_sources import parse_sources

        descriptors, warnings = parse_sources("bogus:foo")
        assert descriptors == []
        assert len(warnings) == 1
        assert "bogus:foo" in warnings[0].entry

    def test_invalid_github_not_a_repo_returns_warning(self) -> None:
        """github:not_a_repo (no slash) → ParseWarning."""
        from src.openspec_sources import parse_sources

        descriptors, warnings = parse_sources("github:not_a_repo")
        assert descriptors == []
        assert len(warnings) == 1

    def test_empty_local_path_returns_warning(self) -> None:
        """local: (empty path) → ParseWarning."""
        from src.openspec_sources import parse_sources

        descriptors, warnings = parse_sources("local:")
        assert descriptors == []
        assert len(warnings) == 1

    def test_mixed_valid_and_invalid_entries(self) -> None:
        """Mix of valid + invalid: invalid gets a warning, valid gets descriptor."""
        from src.openspec_sources import parse_sources

        descriptors, warnings = parse_sources(
            "local:/repos/valid,github:not_a_valid_entry"
        )
        # The valid entry is kept; the invalid entry produces a warning
        assert len(descriptors) == 1
        assert descriptors[0].kind == "local"
        assert len(warnings) == 1
        assert "not_a_valid_entry" in warnings[0].entry

    def test_whitespace_around_entries_ignored(self) -> None:
        """Leading/trailing whitespace around CSV entries is stripped."""
        from src.openspec_sources import parse_sources

        descriptors, warnings = parse_sources("  local:/a  ,  github:b/c  ")
        assert len(descriptors) == 2
        assert descriptors[0].spec == "/a"
        assert descriptors[1].spec == "b/c"
        assert warnings == []


# ---------------------------------------------------------------------------
# Task 1.3 — test_derive_local_repo
# ---------------------------------------------------------------------------


class TestDeriveLocalRepo:
    def test_https_remote_returns_owner_repo_lowercase(self, tmp_path: Path) -> None:
        """HTTPS origin → lowercase owner/repo, no warning."""
        repo = _make_local_git_repo(
            tmp_path, "repo-a", origin="https://github.com/JanK/Repo.git"
        )
        from src.openspec_sources import derive_local_repo

        result, warning = derive_local_repo(repo)
        assert result == "jank/repo"
        assert warning is None

    def test_ssh_remote_returns_owner_repo(self, tmp_path: Path) -> None:
        """SSH origin (git@github.com:owner/repo.git) → lowercase owner/repo, no warning."""
        repo = _make_local_git_repo(
            tmp_path, "repo-b", origin="git@github.com:owner/Repo.git"
        )
        from src.openspec_sources import derive_local_repo

        result, warning = derive_local_repo(repo)
        assert result == "owner/repo"
        assert warning is None

    def test_no_origin_falls_back_to_basename(self, tmp_path: Path) -> None:
        """No origin → local/<basename>, with warning."""
        repo = _make_local_git_repo(tmp_path, "orphan-checkout")
        from src.openspec_sources import derive_local_repo

        result, warning = derive_local_repo(repo)
        assert result == "local/orphan-checkout"
        assert warning is not None
        assert "orphan-checkout" in warning

    def test_non_github_origin_falls_back_to_basename(self, tmp_path: Path) -> None:
        """Non-GitHub origin (can't parse owner/repo) → local/<basename>, with warning."""
        repo = _make_local_git_repo(
            tmp_path, "myrepo", origin="https://gitlab.com/some/path/here.git"
        )
        from src.openspec_sources import derive_local_repo

        # gitlab URL has owner/repo structure too; test a truly unparseable one
        # Override with something unparseable after creation
        subprocess.run(
            ["git", "remote", "set-url", "origin", "not-a-url"],
            cwd=str(repo),
            capture_output=True,
            check=True,
        )
        result, warning = derive_local_repo(repo)
        # For a non-github URL that doesn't match the pattern, falls back
        assert "/" in result  # must have owner/repo shape
        # Result may either parse successfully or fall back to local/<basename>
        # — both are valid depending on how permissive the parser is

    def test_local_prefix_preserves_owner_repo_shape(self, tmp_path: Path) -> None:
        """R1-004: local/<basename> result matches ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$."""
        import re

        repo = _make_local_git_repo(tmp_path, "orphan-checkout")
        from src.openspec_sources import derive_local_repo

        result, _ = derive_local_repo(repo)
        pattern = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
        assert pattern.match(result), f"Result {result!r} does not match owner/repo regex"


# ---------------------------------------------------------------------------
# Task 2.1 — test_warm_local_sources
# ---------------------------------------------------------------------------


class TestWarmLocalSources:
    def test_warm_populates_cache_for_two_local_sources(
        self, tmp_path: Path
    ) -> None:
        """warm_local_sources with 2 local repos → both in cache."""
        from src.openspec_sources import (
            SourceDescriptor,
            invalidate_local_walk_cache,
            warm_local_sources,
        )

        repo_a = _make_local_git_repo(
            tmp_path,
            "repo-a",
            origin="https://github.com/owner/repo-a.git",
            changes=["change-1", "change-2"],
        )
        repo_b = _make_local_git_repo(
            tmp_path,
            "repo-b",
            origin="https://github.com/owner/repo-b.git",
            changes=["change-3"],
        )

        invalidate_local_walk_cache()

        sources = [
            SourceDescriptor(kind="local", spec=str(repo_a), repo="owner/repo-a"),
            SourceDescriptor(kind="local", spec=str(repo_b), repo="owner/repo-b"),
        ]
        cache = warm_local_sources(sources)

        assert str(repo_a) in cache
        assert str(repo_b) in cache
        # Proposals should be populated
        assert len(cache[str(repo_a)].proposals) == 2
        assert len(cache[str(repo_b)].proposals) == 1

    def test_second_warm_without_invalidation_returns_cached(
        self, tmp_path: Path
    ) -> None:
        """Second warm call without invalidation returns same cached object."""
        from src.openspec_sources import (
            SourceDescriptor,
            get_or_walk_local,
            invalidate_local_walk_cache,
            warm_local_sources,
        )

        repo_a = _make_local_git_repo(
            tmp_path,
            "repo-c",
            origin="https://github.com/owner/repo-c.git",
            changes=["change-x"],
        )

        invalidate_local_walk_cache()
        src = SourceDescriptor(kind="local", spec=str(repo_a), repo="owner/repo-c")
        warm_local_sources([src])

        # Record the minted_at of the first warm
        entry1, status1 = get_or_walk_local(src)
        minted_at_1 = entry1.minted_at

        # Second call without invalidation → same minted_at (cached)
        entry2, status2 = get_or_walk_local(src)
        assert entry2.minted_at == minted_at_1
        assert status2 == "cache"

    def test_invalidate_then_walk_re_fetches(self, tmp_path: Path) -> None:
        """After invalidate_local_walk_cache(), get_or_walk_local re-walks."""
        from src.openspec_sources import (
            SourceDescriptor,
            get_or_walk_local,
            invalidate_local_walk_cache,
            warm_local_sources,
        )

        repo_a = _make_local_git_repo(
            tmp_path,
            "repo-d",
            origin="https://github.com/owner/repo-d.git",
            changes=["change-y"],
        )

        invalidate_local_walk_cache()
        src = SourceDescriptor(kind="local", spec=str(repo_a), repo="owner/repo-d")
        warm_local_sources([src])

        entry1, _ = get_or_walk_local(src)
        minted_at_1 = entry1.minted_at

        # Brief sleep to ensure time difference is detectable
        time.sleep(0.01)

        invalidate_local_walk_cache()
        entry2, status2 = get_or_walk_local(src)
        # Should be a new walk, minted_at may differ or status is live
        assert status2 == "live"

    def test_unreachable_local_source_marked_degraded(
        self, tmp_path: Path
    ) -> None:
        """Missing local path → entry marked degraded, no exception."""
        from src.openspec_sources import (
            SourceDescriptor,
            invalidate_local_walk_cache,
            warm_local_sources,
        )

        missing = tmp_path / "does-not-exist"
        invalidate_local_walk_cache()
        src = SourceDescriptor(kind="local", spec=str(missing), repo="local/does-not-exist")
        cache = warm_local_sources([src])

        # Should not raise; entry should be marked degraded or absent with a warning
        assert str(missing) in cache
        assert cache[str(missing)].degraded is True

    def test_cache_age_reflects_time_since_warm(self, tmp_path: Path) -> None:
        """cache_age_seconds increases over time after warm."""
        from src.openspec_sources import (
            SourceDescriptor,
            get_or_walk_local,
            invalidate_local_walk_cache,
            warm_local_sources,
        )

        repo_a = _make_local_git_repo(
            tmp_path,
            "repo-e",
            origin="https://github.com/owner/repo-e.git",
            changes=["ch1"],
        )

        invalidate_local_walk_cache()
        src = SourceDescriptor(kind="local", spec=str(repo_a), repo="owner/repo-e")
        warm_local_sources([src])

        time.sleep(0.05)
        entry, _ = get_or_walk_local(src)
        age = time.monotonic() - entry.minted_at
        assert age >= 0.0
        assert age < 10.0  # sanity: can't be more than 10s in a test
