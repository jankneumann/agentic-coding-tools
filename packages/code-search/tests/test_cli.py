from __future__ import annotations

import json
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from code_search_pkg.cli import (
    PIPELINE_FINGERPRINT,
    CliDependencies,
    _parse_args,
    _run,
)
from code_search_pkg.embedding_config import build_embedding_provider
from code_search_pkg.indexing_runtime import (
    IndexExecutionCounts,
    IndexExecutionError,
    IndexExecutionResult,
    IndexExecutionStatus,
)
from code_search_pkg.registry_models import NamespaceKind


REVISION = "a" * 40
INDEX_ID = UUID("11111111-1111-4111-8111-111111111111")


def argv(repo_root: Path, *extra: str) -> list[str]:
    return [
        "--repo-root",
        str(repo_root),
        "--repo-slug",
        "example",
        "--source-revision",
        REVISION,
        "--namespace-kind",
        "main",
        "--namespace-key",
        "main",
        "--provider",
        "local",
        "--embedding-model",
        "sentence-transformers/example",
        "--embedding-dimension",
        "3",
        "--lease-owner",
        "test-worker",
        *extra,
    ]


def result(
    status: IndexExecutionStatus,
    *,
    durable: bool | None = None,
    reused: bool = False,
) -> IndexExecutionResult:
    if durable is None:
        durable = status is not IndexExecutionStatus.FAILED
    ready = status is IndexExecutionStatus.READY
    return IndexExecutionResult(
        status=status,
        durable=durable,
        reused=reused,
        repo_slug="example",
        source_revision=REVISION,
        namespace_kind=NamespaceKind.MAIN,
        namespace_key="main",
        index_id=INDEX_ID if durable else None,
        storage_key=f"i_{INDEX_ID.hex}" if durable else None,
        counts=IndexExecutionCounts(chunks=2 if ready else 0),
        error=None
        if ready
        else IndexExecutionError(
            f"{status.value}_error",
            f"sanitized {status.value} result",
        ),
    )


class FakePool:
    def __init__(self) -> None:
        self.closed = False
        self.close_error: Exception | None = None
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_result: dict[str, object] | None = {"repo_slug": "example"}

    async def execute(self, query: str, *args: object) -> str:
        self.executions.append((query, args))
        return "INSERT 0 1"

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.executions.append((query, args))
        return self.fetchrow_result

    async def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


@dataclass
class Harness:
    operation_result: IndexExecutionResult
    operation_error: Exception | None = None

    def __post_init__(self) -> None:
        self.output = StringIO()
        self.pool = FakePool()
        self.calls: list[str] = []
        self.context: Any | None = None
        self.provider_contract = None

    async def create_pool(self, dsn: str) -> FakePool:
        self.calls.append(f"pool:{dsn}")
        return self.pool

    async def ensure_repository(
        self,
        pool: FakePool,
        repo_slug: str,
        repo_root: Path,
        embedder_model: str,
        embedding_dim: int,
        git_common_dir_fingerprint: str,
    ) -> None:
        assert pool is self.pool
        assert len(git_common_dir_fingerprint) == 64
        self.calls.append("repository")

    def registry_factory(self, pool: FakePool) -> object:
        assert pool is self.pool
        self.calls.append("registry")
        return object()

    def storage_factory(self, pool: FakePool, *, manifest_publisher: object) -> object:
        assert pool is self.pool
        self.calls.append("storage")
        return {"manifest_publisher": manifest_publisher}

    def provider_factory(self, contract, **kwargs):
        self.calls.append("provider")
        self.provider_contract = contract
        return build_embedding_provider(contract, **kwargs)

    async def execute_operation(self, context):
        self.calls.append("execute")
        self.context = context
        if self.operation_error is not None:
            raise self.operation_error
        return self.operation_result

    def dependencies(
        self, *, environment: dict[str, str] | None = None
    ) -> CliDependencies:
        return CliDependencies(
            environment={} if environment is None else environment,
            output=self.output,
            create_pool=self.create_pool,
            ensure_repository=self.ensure_repository,
            registry_factory=self.registry_factory,
            storage_factory=self.storage_factory,
            provider_factory=self.provider_factory,
            execute_operation=self.execute_operation,
        )


def payload(harness: Harness) -> dict[str, object]:
    lines = harness.output.getvalue().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def test_parser_accepts_exact_namespace_scope_and_embedding_contract(
    tmp_path: Path,
) -> None:
    args = _parse_args(
        argv(
            tmp_path,
            "--include",
            "src/**",
            "--exclude",
            "src/generated/**",
            "--read-allow",
            "src/**",
            "--deny",
            "**/*.pem",
            "--embedding-input-type",
            "document",
            "--embedding-prompt-name",
            "code",
            "--embedding-truncate",
            "end",
            "--embedding-normalize",
            "--lease-duration",
            "180",
            "--full-rebuild",
        )
    )

    assert args.source_revision == REVISION
    assert (args.namespace_kind, args.namespace_key) == ("main", "main")
    assert args.include == ["src/**"]
    assert args.exclude == ["src/generated/**"]
    assert args.read_allow == ["src/**"]
    assert args.deny == ["**/*.pem"]
    assert args.embedding_normalize is True
    assert args.full_rebuild is True


def test_pipeline_fingerprint_is_explicit_and_non_legacy() -> None:
    assert (
        PIPELINE_FINGERPRINT
        == "608b2c763798f0bb2f7cfdfa3ec58d1305857e90c1de0028f5f93c968ecc2e1d"
    )


@pytest.mark.parametrize("seconds", ["29", "3601"])
def test_parser_rejects_lease_duration_outside_contract(
    tmp_path: Path,
    seconds: str,
) -> None:
    with pytest.raises(SystemExit):
        _parse_args(argv(tmp_path, "--lease-duration", seconds))


@pytest.mark.asyncio
async def test_scope_file_and_repeatable_flags_are_merged(
    tmp_path: Path,
) -> None:
    scope_file = tmp_path / "scope.json"
    scope_file.write_text(
        json.dumps(
            {
                "include": ["packages/**"],
                "exclude": ["**/fixtures/**"],
                "read_allow": ["packages/**"],
                "deny": ["**/*.key"],
                "respect_gitignore": True,
                "secret_scan": "local_required",
            }
        )
    )
    harness = Harness(result(IndexExecutionStatus.READY))

    exit_code = await _run(
        _parse_args(
            argv(
                tmp_path,
                "--scope-file",
                str(scope_file),
                "--include",
                "docs/**",
                "--deny",
                ".env*",
            )
        ),
        harness.dependencies(environment={"POSTGRES_DSN": "postgres://db"}),
    )

    assert exit_code == 0
    assert harness.context.policy.include == ("docs/**", "packages/**")
    assert harness.context.policy.exclude == ("**/fixtures/**",)
    assert harness.context.policy.read_allow == ("packages/**",)
    assert harness.context.policy.deny == ("**/*.key", ".env*")


@pytest.mark.asyncio
async def test_missing_dsn_is_ephemeral_not_configured_without_pool(
    tmp_path: Path,
) -> None:
    harness = Harness(result(IndexExecutionStatus.READY))

    exit_code = await _run(
        _parse_args(argv(tmp_path)),
        harness.dependencies(),
    )

    assert exit_code == 2
    assert payload(harness)["status"] == "not_configured"
    assert payload_from_output(harness)["durable"] is False
    assert payload_from_output(harness)["error"]["code"] == "missing_database"
    assert harness.calls == []


@pytest.mark.asyncio
async def test_registry_connection_failure_is_ephemeral_failed(
    tmp_path: Path,
) -> None:
    harness = Harness(result(IndexExecutionStatus.READY))

    async def unavailable_pool(_dsn: str) -> FakePool:
        raise OSError("secret connection detail")

    dependencies = harness.dependencies(environment={"POSTGRES_DSN": "postgres://db"})
    dependencies.create_pool = unavailable_pool

    exit_code = await _run(_parse_args(argv(tmp_path)), dependencies)

    assert exit_code == 1
    output = payload_from_output(harness)
    assert output["status"] == "failed"
    assert output["durable"] is False
    assert output["error"]["code"] == "registry_unavailable"
    assert "secret connection detail" not in harness.output.getvalue()


@pytest.mark.asyncio
async def test_missing_embedding_contract_is_ephemeral_without_pool_or_provider(
    tmp_path: Path,
) -> None:
    harness = Harness(result(IndexExecutionStatus.READY))
    incomplete = argv(tmp_path)
    model_index = incomplete.index("--embedding-model")
    del incomplete[model_index : model_index + 2]
    dimension_index = incomplete.index("--embedding-dimension")
    del incomplete[dimension_index : dimension_index + 2]

    exit_code = await _run(
        _parse_args(incomplete),
        harness.dependencies(environment={"POSTGRES_DSN": "postgres://db"}),
    )

    assert exit_code == 2
    assert payload(harness)["error"]["code"] == "missing_embedding_contract"
    assert harness.calls == []


@pytest.mark.asyncio
async def test_scope_rule_count_and_length_are_bounded_before_pool(
    tmp_path: Path,
) -> None:
    harness = Harness(result(IndexExecutionStatus.READY))
    too_many = [
        item for number in range(1001) for item in ("--include", f"src/{number}.py")
    ]

    exit_code = await _run(
        _parse_args(argv(tmp_path, *too_many)),
        harness.dependencies(environment={"POSTGRES_DSN": "postgres://db"}),
    )

    assert exit_code == 1
    assert payload(harness)["error"]["code"] == "invalid_request"
    assert harness.calls == []


@pytest.mark.asyncio
async def test_local_execution_assembles_operation_and_closes_pool(
    tmp_path: Path,
) -> None:
    harness = Harness(result(IndexExecutionStatus.READY))

    exit_code = await _run(
        _parse_args(argv(tmp_path, "--dsn", "postgres://argument")),
        harness.dependencies(environment={"POSTGRES_DSN": "postgres://environment"}),
    )

    assert exit_code == 0
    assert harness.calls == [
        "pool:postgres://argument",
        "registry",
        "storage",
        "provider",
        "execute",
    ]
    assert harness.pool.closed is True
    assert harness.context.storage["manifest_publisher"] is harness.context.registry
    assert harness.context.request.identity.embedder_fingerprint == (
        harness.provider_contract.fingerprint
    )
    assert harness.context.request.identity.policy_fingerprint == (
        harness.context.policy.fingerprint
    )
    assert harness.context.request.full_rebuild is False
    assert payload(harness)["status"] == "ready"


@pytest.mark.asyncio
async def test_remote_gateway_is_opt_in_and_missing_env_credential_is_durable(
    tmp_path: Path,
) -> None:
    harness = Harness(result(IndexExecutionStatus.NOT_CONFIGURED))
    remote = argv(tmp_path)
    remote[remote.index("local")] = "openai_compatible"
    remote.extend(
        [
            "--embedding-base-url",
            "https://gateway.example.test/v1",
            "--embedding-credential-ref",
            "env:MISSING_GATEWAY_KEY",
        ]
    )

    async def execute(context):
        await context.ensure_repository(
            context.pool,
            context.request.identity.repo_slug,
            context.repo_root,
            context.request.identity.embedder_model,
            context.request.identity.embedding_dim,
            "f" * 64,
        )
        harness.calls.append("execute")
        harness.context = context
        readiness = await context.provider.check_readiness()
        assert readiness.error_code == "missing_credential"
        return harness.operation_result

    dependencies = harness.dependencies(environment={"POSTGRES_DSN": "postgres://db"})
    dependencies.execute_operation = execute
    exit_code = await _run(_parse_args(remote), dependencies)

    assert exit_code == 2
    output = payload(harness)
    assert output["durable"] is True
    assert output["status"] == "not_configured"
    assert harness.calls.index("repository") < harness.calls.index("execute")
    assert harness.provider_contract.base_url == "https://gateway.example.test/v1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_exit"),
    [
        (IndexExecutionStatus.READY, 0),
        (IndexExecutionStatus.NOT_CONFIGURED, 2),
        (IndexExecutionStatus.CONFLICT, 3),
        (IndexExecutionStatus.FAILED, 1),
    ],
)
async def test_result_status_has_deterministic_exit_code(
    tmp_path: Path,
    status: IndexExecutionStatus,
    expected_exit: int,
) -> None:
    harness = Harness(result(status, durable=status is not IndexExecutionStatus.FAILED))

    exit_code = await _run(
        _parse_args(argv(tmp_path)),
        harness.dependencies(environment={"POSTGRES_DSN": "postgres://db"}),
    )

    assert exit_code == expected_exit
    assert payload(harness)["status"] == status.value


@pytest.mark.asyncio
async def test_pool_closes_and_exception_becomes_sanitized_json(
    tmp_path: Path,
) -> None:
    harness = Harness(
        result(IndexExecutionStatus.READY),
        operation_error=RuntimeError("secret database detail"),
    )

    exit_code = await _run(
        _parse_args(argv(tmp_path)),
        harness.dependencies(environment={"POSTGRES_DSN": "postgres://db"}),
    )

    assert exit_code == 1
    assert harness.pool.closed is True
    output = payload(harness)
    assert output["status"] == "failed"
    assert output["durable"] is False
    assert "secret database detail" not in json.dumps(output)


@pytest.mark.asyncio
async def test_pool_close_failure_does_not_escape_or_duplicate_json(
    tmp_path: Path,
) -> None:
    harness = Harness(result(IndexExecutionStatus.READY))
    harness.pool.close_error = RuntimeError("secret close detail")

    exit_code = await _run(
        _parse_args(argv(tmp_path)),
        harness.dependencies(environment={"POSTGRES_DSN": "postgres://db"}),
    )

    assert exit_code == 0
    assert harness.pool.closed is True
    assert payload(harness)["status"] == "ready"
    assert "secret close detail" not in harness.output.getvalue()


@pytest.mark.asyncio
async def test_full_rebuild_reaches_runtime_for_ready_no_op(
    tmp_path: Path,
) -> None:
    harness = Harness(result(IndexExecutionStatus.READY, reused=True))

    exit_code = await _run(
        _parse_args(argv(tmp_path, "--full-rebuild")),
        harness.dependencies(environment={"POSTGRES_DSN": "postgres://db"}),
    )

    assert exit_code == 0
    assert harness.context.request.full_rebuild is True
    assert payload(harness)["reused"] is True
    assert "repository" not in harness.calls


def payload_from_output(harness: Harness) -> dict[str, Any]:
    return json.loads(harness.output.getvalue())
