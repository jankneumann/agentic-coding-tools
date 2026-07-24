"""Structured ``index_repo`` command for one exact semantic-index revision.

Only standard-library and identifier helpers are imported at module load time.
Database, provider, source-planning, and CocoIndex imports remain behind
successful configuration preflight so ``--help`` and not-configured exits stay
light and side-effect free.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol, TextIO

from .cli_models import PIPELINE_FINGERPRINT
from .cli_models import ephemeral_result as _ephemeral_result
from .identifiers import slugify, validate_slug

_REVISION_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_EXIT_CODES = {"ready": 0, "not_configured": 2, "conflict": 3, "failed": 1}
_SCOPE_FIELDS = ("include", "exclude", "read_allow", "deny")


class RepositoryIdentityMismatch(RuntimeError):
    """A repository slug is already bound to different canonical metadata."""


class ExecutionResult(Protocol):
    @property
    def status(self) -> object: ...

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(slots=True)
class CliExecutionContext:
    dsn: str
    pool: Any
    repo_root: Path
    policy: Any
    provider: Any
    registry: Any
    storage: Any
    request: Any
    environment: Mapping[str, str]
    ensure_repository: Callable[..., Awaitable[None]]
    pipeline_fingerprint: str = PIPELINE_FINGERPRINT


@dataclass(slots=True)
class CliDependencies:
    """Injectable operational seams; defaults load production code lazily."""

    environment: Mapping[str, str] | None = None
    output: TextIO | None = None
    create_pool: Callable[[str], Awaitable[Any]] | None = None
    ensure_repository: Callable[..., Awaitable[None]] | None = None
    registry_factory: Callable[[Any], Any] | None = None
    storage_factory: Callable[..., Any] | None = None
    provider_factory: Callable[..., Any] | None = None
    execute_operation: (
        Callable[[CliExecutionContext], Awaitable[ExecutionResult]] | None
    ) = None


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _lease_duration(value: str) -> int:
    parsed = _positive_int(value)
    if not 30 <= parsed <= 3600:
        raise argparse.ArgumentTypeError(
            "lease duration must be between 30 and 3600 seconds"
        )
    return parsed


def _source_revision(value: str) -> str:
    if not _REVISION_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "source revision must be a full lowercase Git object ID"
        )
    return value


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="index_repo",
        description="Build one immutable semantic index for an exact Git revision.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--repo-slug")
    parser.add_argument(
        "--source-revision",
        required=True,
        type=_source_revision,
    )
    parser.add_argument(
        "--namespace-kind",
        choices=("main", "feature", "work_package"),
        default="main",
    )
    parser.add_argument("--namespace-key")
    parser.add_argument("--scope-file", type=Path)
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--read-allow", action="append", default=[])
    parser.add_argument("--deny", action="append", default=[])

    parser.add_argument(
        "--provider",
        choices=("local", "openai_compatible"),
    )
    parser.add_argument("--embedding-model")
    parser.add_argument("--embedding-dimension", type=_positive_int)
    parser.add_argument("--embedding-base-url")
    parser.add_argument("--embedding-credential-ref")
    parser.add_argument("--embedding-input-type")
    parser.add_argument("--embedding-prompt-name")
    parser.add_argument(
        "--embedding-truncate",
        choices=("start", "end", "none"),
    )
    parser.add_argument(
        "--embedding-normalize",
        action=argparse.BooleanOptionalAction,
        default=None,
    )

    parser.add_argument("--lease-owner", required=True)
    parser.add_argument(
        "--lease-duration",
        type=_lease_duration,
        default=300,
        metavar="SECONDS",
    )
    parser.add_argument("--full-rebuild", action="store_true")
    parser.add_argument("--dsn")
    return parser.parse_args(argv)


def resolve_slug(args: argparse.Namespace) -> str:
    if args.repo_slug:
        return validate_slug(args.repo_slug)
    return slugify(Path(args.repo_root).resolve().name)


async def _run(
    args: argparse.Namespace,
    dependencies: CliDependencies | None = None,
) -> int:
    dependencies = dependencies or CliDependencies()
    environment = (
        os.environ if dependencies.environment is None else dependencies.environment
    )
    output = dependencies.output or sys.stdout
    repo_slug = resolve_slug(args)
    namespace_key = args.namespace_key
    if namespace_key is None and args.namespace_kind == "main":
        namespace_key = "main"
    base = {
        "repo_slug": repo_slug,
        "source_revision": args.source_revision,
        "namespace_kind": args.namespace_kind,
        "namespace_key": namespace_key or "<missing>",
    }

    dsn = args.dsn or environment.get("POSTGRES_DSN")
    if not dsn:
        return _emit(
            output,
            _ephemeral_result(
                **base,
                status="not_configured",
                code="missing_database",
                message="Postgres DSN is not configured",
            ),
        )
    if args.embedding_model is None and args.embedding_dimension is None:
        return _emit(
            output,
            _ephemeral_result(
                **base,
                status="not_configured",
                code="missing_embedding_contract",
                message="embedding model and dimension are not configured",
            ),
        )

    try:
        configuration = _build_configuration(args, environment, namespace_key)
    except Exception:
        return _emit(
            output,
            _ephemeral_result(
                **base,
                status="failed",
                code="invalid_request",
                message="index request configuration is invalid",
            ),
        )

    create_pool = dependencies.create_pool or _create_pool
    try:
        pool = await create_pool(dsn)
    except Exception:
        return _emit(
            output,
            _ephemeral_result(
                **base,
                status="failed",
                code="registry_unavailable",
                message="the semantic index registry is unavailable",
            ),
        )

    try:
        registry_factory = dependencies.registry_factory or _registry_factory
        registry = registry_factory(pool)
        storage_factory = dependencies.storage_factory or _storage_factory
        storage = storage_factory(pool, manifest_publisher=registry)
        provider_factory = dependencies.provider_factory or _provider_factory
        provider = provider_factory(
            configuration.contract,
            environment=environment,
        )
        request = configuration.request_factory(
            repo_slug,
            provider.fingerprint,
        )
        context = CliExecutionContext(
            dsn=dsn,
            pool=pool,
            repo_root=configuration.repo_root,
            policy=configuration.policy,
            provider=provider,
            registry=registry,
            storage=storage,
            request=request,
            environment=environment,
            ensure_repository=(dependencies.ensure_repository or _ensure_repository),
        )
        execute_operation = dependencies.execute_operation or _execute_operation
        result = await execute_operation(context)
        payload = result.to_dict()
    except Exception:
        payload = _ephemeral_result(
            **base,
            status="failed",
            code="execution_failed",
            message="semantic indexing could not execute",
        )
    finally:
        try:
            await pool.close()
        except Exception:
            pass
    return _emit(output, payload)


@dataclass(frozen=True, slots=True)
class _Configuration:
    repo_root: Path
    contract: Any
    policy: Any
    request_factory: Callable[[str, str], Any]


def _build_configuration(
    args: argparse.Namespace,
    environment: Mapping[str, str],
    namespace_key: str | None,
) -> _Configuration:
    del environment
    if namespace_key is None:
        raise ValueError("non-main namespace requires --namespace-key")
    if (
        args.provider is None
        or args.embedding_model is None
        or args.embedding_dimension is None
    ):
        raise ValueError("embedding contract is incomplete")
    if not 1 <= len(args.lease_owner) <= 255:
        raise ValueError("lease owner is outside the request contract")

    from .embedding_protocol import (
        CredentialRef,
        EmbeddingContract,
        EmbeddingProviderKind,
    )
    from .indexing_policy import IndexingPolicy
    from .registry_models import IndexIdentity, NamespaceKind

    provider_kind = EmbeddingProviderKind(args.provider)
    credential_ref = (
        None
        if args.embedding_credential_ref is None
        else CredentialRef.parse(args.embedding_credential_ref)
    )
    indexing_parameters = {
        key: value
        for key, value in {
            "input_type": args.embedding_input_type,
            "prompt_name": args.embedding_prompt_name,
            "truncate": args.embedding_truncate,
            "normalize": args.embedding_normalize,
        }.items()
        if value is not None
    }
    contract = EmbeddingContract(
        provider_kind=provider_kind,
        model_id=args.embedding_model,
        dimension=args.embedding_dimension,
        base_url=args.embedding_base_url,
        credential_ref=credential_ref,
        indexing_params=indexing_parameters,
    )
    repo_root = Path(args.repo_root).expanduser().resolve(strict=True)
    policy_values = _load_scope(args.scope_file)
    for cli_name, field_name in (
        ("include", "include"),
        ("exclude", "exclude"),
        ("read_allow", "read_allow"),
        ("deny", "deny"),
    ):
        policy_values[field_name] = sorted(
            set(policy_values[field_name]) | set(getattr(args, cli_name))
        )
        if len(policy_values[field_name]) > 1000 or any(
            not 1 <= len(pattern) <= 512 for pattern in policy_values[field_name]
        ):
            raise ValueError("scope rules are outside the request contract")
    policy = IndexingPolicy(**policy_values)

    def request_factory(repo_slug: str, embedder_fingerprint: str) -> Any:
        from .indexing_runtime import IndexExecutionRequest

        identity = IndexIdentity(
            repo_slug=repo_slug,
            namespace_kind=NamespaceKind(args.namespace_kind),
            namespace_key=namespace_key,
            source_revision=args.source_revision,
            embedder_model=contract.model_id,
            embedding_dim=contract.dimension,
            policy_fingerprint=policy.fingerprint,
            pipeline_fingerprint=PIPELINE_FINGERPRINT,
            embedder_fingerprint=embedder_fingerprint,
        )
        return IndexExecutionRequest(
            identity=identity,
            repo_root=str(repo_root),
            lease_owner=args.lease_owner,
            lease_duration=timedelta(seconds=args.lease_duration),
            full_rebuild=args.full_rebuild,
        )

    return _Configuration(repo_root, contract, policy, request_factory)


def _load_scope(path: Path | None) -> dict[str, Any]:
    values: dict[str, Any] = {
        "include": [],
        "exclude": [],
        "read_allow": [],
        "deny": [],
        "respect_gitignore": True,
        "secret_scan": "local_required",
    }
    if path is None:
        return values
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or set(parsed) - set(values):
        raise ValueError("scope file contains unsupported fields")
    for field in _SCOPE_FIELDS:
        candidate = parsed.get(field, [])
        if not isinstance(candidate, list) or any(
            not isinstance(item, str) for item in candidate
        ):
            raise ValueError("scope rules must be string arrays")
        values[field] = candidate
    if parsed.get("respect_gitignore", True) is not True:
        raise ValueError("scope must respect Git ignore rules")
    if parsed.get("secret_scan", "local_required") != "local_required":
        raise ValueError("scope must require local secret scanning")
    return values


async def _create_pool(dsn: str) -> Any:
    from .cli_runtime import create_pool

    return await create_pool(dsn)


async def _ensure_repository(
    pool: Any,
    repo_slug: str,
    repo_root: Path,
    embedder_model: str,
    embedding_dim: int,
    git_common_dir_fingerprint: str,
) -> None:
    from .cli_runtime import ensure_repository
    from .registry_models import RepositoryIdentityConflictError

    try:
        await ensure_repository(
            pool,
            repo_slug,
            repo_root,
            embedder_model,
            embedding_dim,
            git_common_dir_fingerprint,
        )
    except RepositoryIdentityConflictError as error:
        raise RepositoryIdentityMismatch(
            "repository slug is bound to different canonical metadata"
        ) from error


def _registry_factory(pool: Any) -> Any:
    from .cli_runtime import registry_factory

    return registry_factory(pool)


def _storage_factory(pool: Any, *, manifest_publisher: Any) -> Any:
    from .cli_runtime import storage_factory

    return storage_factory(pool, manifest_publisher=manifest_publisher)


def _provider_factory(contract: Any, **kwargs: Any) -> Any:
    from .cli_runtime import provider_factory

    return provider_factory(contract, **kwargs)


async def _execute_operation(context: CliExecutionContext) -> ExecutionResult:
    from .cli_runtime import execute_operation

    return await execute_operation(context)


def _emit(output: TextIO, payload: dict[str, Any]) -> int:
    status = str(payload["status"])
    output.write(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    output.write("\n")
    return _EXIT_CODES.get(status, 1)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
