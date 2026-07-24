from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from code_search_pkg.registry import (
    IndexNotFoundError,
    RepositoryIdentity,
    RepositoryIdentityConflictError,
    SemanticIndexRegistry,
)
from code_search_pkg.registry_models import LEGACY_FINGERPRINT


NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)
FINGERPRINT = "a" * 64


class RepositoryPool:
    def __init__(self) -> None:
        self.repositories: dict[str, dict[str, Any]] = {}

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        if "/* registry:get_repository_identity */" in query:
            row = self.repositories.get(args[0])
            return None if row is None else dict(row)
        if "/* registry:ensure_repository_identity */" in query:
            slug, root, fingerprint, model, dimension, _now = args
            row = self.repositories.get(slug)
            if row is None:
                row = {
                    "repo_slug": slug,
                    "repo_root": root,
                    "git_common_dir_fingerprint": fingerprint,
                    "embedder_model": model,
                    "embedding_dim": dimension,
                }
                self.repositories[slug] = row
                return dict(row)
            if row["repo_root"] != root or row["git_common_dir_fingerprint"] not in {
                fingerprint,
                LEGACY_FINGERPRINT,
            }:
                return None
            if row["git_common_dir_fingerprint"] == LEGACY_FINGERPRINT:
                row["git_common_dir_fingerprint"] = fingerprint
            return dict(row)
        raise AssertionError(query)

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        raise AssertionError(query)


def registry(pool: RepositoryPool) -> SemanticIndexRegistry:
    return SemanticIndexRegistry(pool, clock=lambda: NOW)


def test_ensure_repository_identity_is_idempotent_and_never_remaps_slug(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        pool = RepositoryPool()
        repo = registry(pool)
        identity = RepositoryIdentity("repo", str(tmp_path.resolve()), FINGERPRINT)

        created = await repo.ensure_repository_identity(
            identity,
            embedder_model="model",
            embedding_dim=384,
        )
        repeated = await repo.ensure_repository_identity(
            identity,
            embedder_model="model",
            embedding_dim=384,
        )

        assert created == repeated == identity
        with pytest.raises(RepositoryIdentityConflictError):
            await repo.ensure_repository_identity(
                RepositoryIdentity("repo", "/different", FINGERPRINT),
                embedder_model="model",
                embedding_dim=384,
            )
        with pytest.raises(RepositoryIdentityConflictError):
            await repo.ensure_repository_identity(
                RepositoryIdentity("repo", identity.repo_root, "b" * 64),
                embedder_model="model",
                embedding_dim=384,
            )
        assert await repo.get_repository_identity("repo") == identity

    asyncio.run(scenario())


def test_ensure_repository_identity_upgrades_same_root_legacy_sentinel(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        pool = RepositoryPool()
        root = str(tmp_path.resolve())
        pool.repositories["repo"] = {
            "repo_slug": "repo",
            "repo_root": root,
            "git_common_dir_fingerprint": LEGACY_FINGERPRINT,
            "embedder_model": "legacy",
            "embedding_dim": 1,
        }
        repo = registry(pool)

        upgraded = await repo.ensure_repository_identity(
            RepositoryIdentity("repo", root, FINGERPRINT),
            embedder_model="model",
            embedding_dim=384,
        )

        assert upgraded.git_common_dir_fingerprint == FINGERPRINT
        assert pool.repositories["repo"]["repo_root"] == root

    asyncio.run(scenario())


def test_repository_identity_read_distinguishes_missing_and_validates_shape(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        repo = registry(RepositoryPool())
        with pytest.raises(IndexNotFoundError):
            await repo.get_repository_identity("missing")

    asyncio.run(scenario())
    with pytest.raises(ValueError, match="absolute"):
        RepositoryIdentity("repo", "relative/path", FINGERPRINT)
    with pytest.raises(ValueError, match="fingerprint"):
        RepositoryIdentity("repo", str(tmp_path.resolve()), "invalid")
