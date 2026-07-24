"""Central resource gates and isolated fixtures for code-search integration tests."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio


TESTS_ROOT = Path(__file__).resolve().parent
SAMPLE_REPO = TESTS_ROOT / "fixtures" / "sample_repo"
MIGRATIONS = TESTS_ROOT.parents[2] / "agent-coordinator" / "database" / "migrations"


@dataclass(frozen=True, slots=True)
class IndexE2ECase:
    repo: Path
    repo_slug: str
    dsn: str
    environment: dict[str, str]
    provider_args: tuple[str, ...]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_index_e2e: explicit scratch Postgres and embedding provider required",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    del config
    have_db = bool(os.environ.get("POSTGRES_DSN"))
    have_embedder = _cocoindex_importable()
    skip_db = pytest.mark.skip(reason="no POSTGRES_DSN — live ParadeDB required")
    skip_emb = pytest.mark.skip(
        reason="cocoindex/embedder not installed or unreachable"
    )
    e2e_reason = _index_e2e_unavailable_reason()
    skip_e2e = pytest.mark.skip(reason=e2e_reason or "index E2E unavailable")
    for item in items:
        if "requires_db" in item.keywords and not have_db:
            item.add_marker(skip_db)
        if "requires_embedder" in item.keywords and not have_embedder:
            item.add_marker(skip_emb)
        if "requires_index_e2e" in item.keywords and e2e_reason is not None:
            item.add_marker(skip_e2e)


def _cocoindex_importable() -> bool:
    return all(
        importlib.util.find_spec(package) is not None
        for package in ("cocoindex", "cocoindex_code")
    )


def _index_e2e_unavailable_reason() -> str | None:
    if os.environ.get("CODE_SEARCH_E2E_RUN") != "1":
        return "set CODE_SEARCH_E2E_RUN=1 to opt into live indexing"
    if os.environ.get("CODE_SEARCH_E2E_ALLOW_SCRATCH_MUTATIONS") != "1":
        return "scratch database mutation acknowledgement is required"
    if not os.environ.get("CODE_SEARCH_E2E_POSTGRES_DSN"):
        return "CODE_SEARCH_E2E_POSTGRES_DSN is not configured"
    if not _cocoindex_importable() or importlib.util.find_spec("asyncpg") is None:
        return "indexing dependencies are not installed"
    provider = os.environ.get("CODE_SEARCH_E2E_PROVIDER")
    if provider not in {"local", "openai_compatible"}:
        return "CODE_SEARCH_E2E_PROVIDER must be explicit"
    if not os.environ.get("CODE_SEARCH_E2E_MODEL"):
        return "CODE_SEARCH_E2E_MODEL is not configured"
    try:
        if int(os.environ.get("CODE_SEARCH_E2E_DIMENSION", "0")) <= 0:
            return "CODE_SEARCH_E2E_DIMENSION must be positive"
    except ValueError:
        return "CODE_SEARCH_E2E_DIMENSION must be an integer"
    if provider == "local":
        if importlib.util.find_spec("sentence_transformers") is None:
            return "local sentence-transformers dependency is unavailable"
    elif not (
        os.environ.get("CODE_SEARCH_E2E_BASE_URL")
        and os.environ.get("CODE_SEARCH_E2E_API_KEY")
    ):
        return "OpenAI-compatible base URL and API key are required"
    return None


@pytest.fixture
def sample_repo_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "sample-repo"
    shutil.copytree(SAMPLE_REPO, destination)
    return destination


def _initialize_git_repo(repo: Path) -> str:
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "e2e@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Code Search E2E"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "fixture revision"],
        check=True,
        capture_output=True,
    )
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest_asyncio.fixture
async def index_e2e_case(sample_repo_copy: Path) -> AsyncIterator[IndexE2ECase]:
    import asyncpg

    dsn = os.environ["CODE_SEARCH_E2E_POSTGRES_DSN"]
    repo_slug = f"e2e_{uuid.uuid4().hex[:16]}"
    _initialize_git_repo(sample_repo_copy)
    provider = os.environ["CODE_SEARCH_E2E_PROVIDER"]
    provider_args = [
        "--provider",
        provider,
        "--embedding-model",
        os.environ["CODE_SEARCH_E2E_MODEL"],
        "--embedding-dimension",
        os.environ["CODE_SEARCH_E2E_DIMENSION"],
    ]
    environment = dict(os.environ)
    environment["POSTGRES_DSN"] = dsn
    if provider == "openai_compatible":
        provider_args.extend(
            [
                "--embedding-base-url",
                os.environ["CODE_SEARCH_E2E_BASE_URL"],
                "--embedding-credential-ref",
                "env:CODE_SEARCH_E2E_API_KEY",
            ]
        )
    connection = await asyncpg.connect(dsn)
    for migration in (
        "028_code_search_registry.sql",
        "029_revision_aware_code_search_indexes.sql",
        "030_incremental_code_search_indexes.sql",
    ):
        await connection.execute((MIGRATIONS / migration).read_text(encoding="utf-8"))
    await connection.close()
    case = IndexE2ECase(
        repo=sample_repo_copy,
        repo_slug=repo_slug,
        dsn=dsn,
        environment=environment,
        provider_args=tuple(provider_args),
    )
    try:
        yield case
    finally:
        await _cleanup_e2e_case(case)


async def _cleanup_e2e_case(case: IndexE2ECase) -> None:
    import asyncpg

    from code_search_pkg.identifiers import (
        attempt_chunk_table_name,
        index_chunk_table_name,
    )

    connection = await asyncpg.connect(case.dsn)
    rows = await connection.fetch(
        "SELECT index_id, storage_key, attempt_count "
        "FROM code_search_indexes WHERE repo_slug = $1",
        case.repo_slug,
    )
    for row in rows:
        await connection.execute(
            f"DROP TABLE IF EXISTS {index_chunk_table_name(row['storage_key'])}"
        )
        for attempt in range(1, int(row["attempt_count"]) + 1):
            await connection.execute(
                f"DROP TABLE IF EXISTS "
                f"{attempt_chunk_table_name(row['index_id'], attempt)}"
            )
    await connection.execute(
        "UPDATE code_search_registry SET canonical_index_id = NULL "
        "WHERE repo_slug = $1",
        case.repo_slug,
    )
    await connection.execute(
        "DELETE FROM code_search_indexes WHERE repo_slug = $1",
        case.repo_slug,
    )
    await connection.execute(
        "DELETE FROM code_search_registry WHERE repo_slug = $1",
        case.repo_slug,
    )
    await connection.close()
