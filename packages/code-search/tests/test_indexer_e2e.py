"""Resource-gated end-to-end evidence for immutable incremental code indexes."""

from __future__ import annotations

import asyncio
import ast
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, cast

import pytest


LIVE = pytest.mark.requires_index_e2e


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(repo: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message],
        check=True,
        capture_output=True,
    )
    return _head(repo)


def _cli_command(
    case: Any,
    revision: str,
    *,
    namespace_kind: str = "main",
    namespace_key: str = "main",
    extra: tuple[str, ...] = (),
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "code_search_pkg.cli",
        "--repo-root",
        str(case.repo),
        "--repo-slug",
        case.repo_slug,
        "--source-revision",
        revision,
        "--namespace-kind",
        namespace_kind,
        "--namespace-key",
        namespace_key,
        "--lease-owner",
        f"e2e-{uuid.uuid4().hex}",
        "--lease-duration",
        "120",
        "--dsn",
        case.dsn,
        *case.provider_args,
        *extra,
    ]


async def _run_cli(
    case: Any,
    revision: str,
    *,
    namespace_kind: str = "main",
    namespace_key: str = "main",
    extra: tuple[str, ...] = (),
) -> dict[str, Any]:
    completed = await asyncio.to_thread(
        subprocess.run,
        _cli_command(
            case,
            revision,
            namespace_kind=namespace_kind,
            namespace_key=namespace_key,
            extra=extra,
        ),
        check=False,
        capture_output=True,
        text=True,
        env=case.environment,
        timeout=300,
    )
    json_lines = [
        line for line in completed.stdout.splitlines() if line.startswith("{")
    ]
    assert json_lines, completed.stderr
    payload = json.loads(json_lines[-1])
    assert completed.returncode == 0, payload
    assert payload["status"] == "ready", payload
    return payload


async def _connect(case: Any) -> Any:
    import asyncpg

    return await asyncpg.connect(case.dsn)


@LIVE
@pytest.mark.asyncio
async def test_cli_creates_hnsw_table_with_exact_line_provenance(
    index_e2e_case: Any,
) -> None:
    from code_search_pkg.identifiers import index_chunk_table_name

    revision = _head(index_e2e_case.repo)
    payload = await _run_cli(index_e2e_case, revision)
    table = index_chunk_table_name(payload["storage_key"])
    connection = await _connect(index_e2e_case)
    try:
        hnsw = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_indexes "
            "WHERE schemaname = current_schema() AND tablename = $1 "
            "AND indexdef ILIKE '%USING hnsw%' "
            "AND indexdef ILIKE '%vector_cosine_ops%')",
            table,
        )
        chunks = await connection.fetch(
            f"SELECT file_path, content, start_line, end_line FROM {table} "
            "ORDER BY file_path, start_line"
        )
    finally:
        await connection.close()
    assert hnsw is True
    assert chunks
    assert all(row["start_line"] >= 1 for row in chunks)
    sample = next(row for row in chunks if row["file_path"] == "src/math_utils.py")
    source_lines = (
        (index_e2e_case.repo / sample["file_path"])
        .read_text(encoding="utf-8")
        .splitlines()
    )
    source_slice = "\n".join(
        source_lines[sample["start_line"] - 1 : sample["end_line"]]
    )
    assert sample["content"].strip() in source_slice


@LIVE
@pytest.mark.asyncio
async def test_duplicate_ready_cli_request_is_a_storage_noop(
    index_e2e_case: Any,
) -> None:
    from code_search_pkg.identifiers import index_chunk_table_name

    revision = _head(index_e2e_case.repo)
    first = await _run_cli(index_e2e_case, revision)
    table = index_chunk_table_name(first["storage_key"])
    connection = await _connect(index_e2e_case)
    try:
        before = await connection.fetch(
            f"SELECT id, file_path, content FROM {table} ORDER BY id"
        )
        second = await _run_cli(index_e2e_case, revision)
        after = await connection.fetch(
            f"SELECT id, file_path, content FROM {table} ORDER BY id"
        )
        identities = await connection.fetchval(
            "SELECT count(*) FROM code_search_indexes "
            "WHERE repo_slug = $1 AND source_revision = $2",
            index_e2e_case.repo_slug,
            revision,
        )
    finally:
        await connection.close()
    assert second["reused"] is True
    assert second["index_id"] == first["index_id"]
    assert [tuple(row.values()) for row in after] == [
        tuple(row.values()) for row in before
    ]
    assert identities == 1


@LIVE
@pytest.mark.asyncio
async def test_one_file_delta_copies_unchanged_and_removes_deleted_file(
    index_e2e_case: Any,
) -> None:
    from code_search_pkg.identifiers import index_chunk_table_name

    first_revision = _head(index_e2e_case.repo)
    first = await _run_cli(index_e2e_case, first_revision)
    math_file = index_e2e_case.repo / "src" / "math_utils.py"
    math_file.write_text(
        math_file.read_text(encoding="utf-8") + "\nDELTA_MARKER = 2\n",
        encoding="utf-8",
    )
    (index_e2e_case.repo / "src" / "delete_me.py").unlink()
    second_revision = _commit(index_e2e_case.repo, "one file delta and deletion")
    second = await _run_cli(index_e2e_case, second_revision)
    connection = await _connect(index_e2e_case)
    try:
        table = index_chunk_table_name(second["storage_key"])
        deleted_chunks = await connection.fetchval(
            f"SELECT count(*) FROM {table} WHERE file_path = 'src/delete_me.py'"
        )
        changed_content = await connection.fetchval(
            f"SELECT string_agg(content, E'\\n') FROM {table} "
            "WHERE file_path = 'src/math_utils.py'"
        )
    finally:
        await connection.close()
    assert second["parent_index_id"] == first["index_id"]
    assert second["counts"]["changed_files"] == 1
    assert second["counts"]["copied_files"] >= 1
    assert second["counts"]["removed_files"] == 1
    assert deleted_chunks == 0
    assert "DELTA_MARKER" in changed_content


@LIVE
@pytest.mark.asyncio
async def test_scope_and_hard_secret_paths_never_reach_chunks(
    index_e2e_case: Any,
) -> None:
    revision = _head(index_e2e_case.repo)
    payload = await _run_cli(
        index_e2e_case,
        revision,
        extra=("--deny", "src/private/**"),
    )
    connection = await _connect(index_e2e_case)
    try:
        manifest = await connection.fetch(
            "SELECT file_path, eligible, eligibility_reason "
            "FROM code_search_index_files WHERE index_id = $1::uuid",
            payload["index_id"],
        )
    finally:
        await connection.close()
    decisions = {row["file_path"]: dict(row) for row in manifest}
    assert decisions["src/private/internal.py"]["eligible"] is False
    assert decisions["src/private/internal.py"]["eligibility_reason"] == "denied"
    assert decisions[".env.local"]["eligible"] is False
    assert decisions[".env.local"]["eligibility_reason"] == "hard_secret_path"
    assert decisions["generated/client.py"]["eligible"] is False


@LIVE
@pytest.mark.asyncio
async def test_namespace_and_revision_storage_are_isolated(
    index_e2e_case: Any,
) -> None:
    revision = _head(index_e2e_case.repo)
    main = await _run_cli(index_e2e_case, revision)
    feature = await _run_cli(
        index_e2e_case,
        revision,
        namespace_kind="feature",
        namespace_key="feature/e2e",
    )
    connection = await _connect(index_e2e_case)
    try:
        canonical = await connection.fetchval(
            "SELECT canonical_index_id FROM code_search_registry WHERE repo_slug = $1",
            index_e2e_case.repo_slug,
        )
    finally:
        await connection.close()
    assert feature["index_id"] != main["index_id"]
    assert feature["storage_key"] != main["storage_key"]
    assert feature["promoted"] is False
    assert str(canonical) == main["index_id"]


@LIVE
@pytest.mark.asyncio
async def test_expired_partial_attempt_is_retried_in_a_new_generation(
    index_e2e_case: Any,
) -> None:
    from datetime import timedelta

    from code_search_pkg import cli
    from code_search_pkg.registry import RepositoryIdentity, SemanticIndexRegistry
    from code_search_pkg.source_proof import prove_source
    from code_search_pkg.storage_pg import ManifestPublisher, StoragePublisher

    revision = _head(index_e2e_case.repo)
    arguments = cli._parse_args(_cli_command(index_e2e_case, revision)[3:])
    configuration = cli._build_configuration(
        arguments, index_e2e_case.environment, "main"
    )
    provider = cli._provider_factory(
        configuration.contract,
        environment=index_e2e_case.environment,
    )
    request = configuration.request_factory(
        index_e2e_case.repo_slug, provider.fingerprint
    )
    proof = prove_source(index_e2e_case.repo, revision)
    connection = await _connect(index_e2e_case)
    try:
        registry = SemanticIndexRegistry(connection)
        await registry.ensure_repository_identity(
            RepositoryIdentity(
                index_e2e_case.repo_slug,
                proof.repo_root,
                proof.git_common_dir_fingerprint,
            ),
            embedder_model=request.identity.embedder_model,
            embedding_dim=request.identity.embedding_dim,
        )
        record = await registry.ensure_index(request.identity)
        claimed = await registry.claim_index(
            record.index_id,
            lease_owner="crashed-e2e-worker",
            lease_duration=timedelta(minutes=5),
        )
        storage = StoragePublisher(
            connection,
            manifest_publisher=cast(ManifestPublisher, registry),
        )
        stale_attempt = await storage.prepare_attempt(
            claimed,
            embedding_dim=request.identity.embedding_dim,
        )
        await connection.execute(
            f"INSERT INTO {stale_attempt.table_name} "
            "(id, file_path, language, content, start_line, end_line, embedding) "
            "VALUES ('stale', 'stale.py', 'python', 'stale', 1, 1, $1::vector)",
            "[" + ",".join(["0"] * request.identity.embedding_dim) + "]",
        )
        await connection.execute(
            "UPDATE code_search_indexes SET lease_expires_at = now() - interval '1 second' "
            "WHERE index_id = $1",
            record.index_id,
        )
    finally:
        await connection.close()

    result = await _run_cli(index_e2e_case, revision)
    connection = await _connect(index_e2e_case)
    try:
        persisted = await connection.fetchrow(
            "SELECT status, attempt_count FROM code_search_indexes WHERE index_id = $1",
            record.index_id,
        )
    finally:
        await connection.close()
    assert result["index_id"] == str(record.index_id)
    assert persisted is not None
    assert persisted["status"] == "ready"
    assert persisted["attempt_count"] == 2


def test_checked_in_fixture_is_real_and_copied_before_mutation(
    sample_repo_copy: Path,
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "sample_repo"
    assert not (fixture / ".git").exists()
    assert sample_repo_copy != fixture
    assert (sample_repo_copy / "src" / "math_utils.py").is_file()
    assert (sample_repo_copy / ".env.local").is_file()
    assert len(list(sample_repo_copy.rglob("*"))) >= 10
    (sample_repo_copy / "src" / "math_utils.py").write_text("copy only\n")
    assert "deterministic functions" in (fixture / "src" / "math_utils.py").read_text(
        encoding="utf-8"
    )


def test_live_scenarios_are_centrally_gated_without_unconditional_skips() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    conftest = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")
    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
        and node.func.attr == "skip"
    ]
    assert calls == []
    assert source.count("@LIVE") >= 6
    assert "CODE_SEARCH_E2E_POSTGRES_DSN" in conftest
    assert "CODE_SEARCH_E2E_ALLOW_SCRATCH_MUTATIONS" in conftest
    assert "CODE_SEARCH_E2E_PROVIDER" in conftest
