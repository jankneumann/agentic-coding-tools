"""Degradable semantic-index adapter (ri-07 D4).

The semantic index (ri-01/ri-02) is a coordinator service backed by Postgres and
CocoIndex — not an in-process function a skill can call. So the refresh
orchestrator treats it as the one *degradable* producer: when the service is
reachable it records a ``SUCCEEDED`` :class:`SemanticIndexReference` pinned to the
exact revision; when it is unconfigured or errors, it records a non-succeeded
reference carrying the canonical ``exact-search`` fallback and **never raises**.

This module owns only the mapping from an indexing attempt to the ri-06
``SemanticIndexReference``. It defines no result model and performs no durable
persistence (the orchestrator records the reference through the ri-06 store).

Design:

* :class:`SemanticIndexOutcome` — the minimal success descriptor an indexer
  returns (the coordinator operation id, its registry record id, and the exact
  revision that was indexed).
* :class:`SemanticIndexUnavailable` — an indexer raises this when the service is
  configured but unreachable (no DB, no coordinator); it maps to ``failed`` with a
  fallback rather than propagating.
* :data:`SemanticIndexer` — the injectable seam: ``(repository, requested_revision)
  -> SemanticIndexOutcome``.
* :func:`resolve_semantic_index` — run the indexer (if any) and return a validated
  reference. With no indexer configured the result is ``not-configured``; any
  indexer failure becomes ``failed``. Both carry an ``exact-search`` fallback.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

# Importing _runtime first inserts the ri-06 runtime scripts dir onto sys.path.
from _runtime import Fallback, FallbackKind, ensure_git_revision
from models import SemanticIndexReference, SemanticIndexStatus

_MAX_REASON = 300
_EXACT_SEARCH_REASON_UNCONFIGURED = (
    "Semantic index is not configured in this context; use exact search until an "
    "index completes for the requested revision."
)

# --------------------------------------------------------------------------- #
# Production indexer configuration
# --------------------------------------------------------------------------- #
#: The code-search indexer is a separate distribution (``packages/code-search``)
#: that pins ``asyncpg<0.31`` against the coordinator's ``>=0.31``, so it cannot
#: be imported into this process. It is driven as a subprocess through its
#: ``index_repo`` console script, which emits one compact JSON line on stdout.
_INDEX_EXECUTABLE = "index_repo"
_INDEX_MODULE = "code_search_pkg.cli"

#: Exit/status contract of ``index_repo`` (``cli.py`` ``_EXIT_CODES``).
_STATUS_READY = "ready"

#: Repository identity override, shared with ri-04's ``provenance.repository_id``
#: and the orchestrator, so one clone yields one slug.
_ENV_REPO_ID = "PROJECT_CONTEXT_REPO_ID"
#: Postgres DSN — code-search treats its absence as ``not_configured``.
_ENV_DSN = "POSTGRES_DSN"
#: The embedding contract. code-search never guesses these: without a model *and*
#: a dimension it returns ``not_configured``/``missing_embedding_contract``.
_ENV_MODEL = "PROJECT_CONTEXT_EMBEDDING_MODEL"
_ENV_DIMENSION = "PROJECT_CONTEXT_EMBEDDING_DIMENSION"
_ENV_PROVIDER = "PROJECT_CONTEXT_EMBEDDING_PROVIDER"
_ENV_CREDENTIAL_REF = "PROJECT_CONTEXT_EMBEDDING_CREDENTIAL_REF"
#: Wall-clock ceiling for one indexing run; a full rebuild is minutes, not seconds.
_ENV_TIMEOUT = "PROJECT_CONTEXT_INDEX_TIMEOUT"
_DEFAULT_TIMEOUT = 1800.0
_DEFAULT_PROVIDER = "local"
_LEASE_DURATION_SECONDS = 900

_SLUG_UNSAFE = re.compile(r"[^a-z0-9]+")


class SemanticIndexUnavailable(Exception):
    """Raised by an indexer when the service is configured but unreachable.

    Distinct from an arbitrary error: it signals a clean degradation (no DB, no
    coordinator) rather than an indexing bug, but both map to a non-succeeded
    reference with an exact-search fallback.
    """


@dataclass(frozen=True, slots=True)
class SemanticIndexOutcome:
    """Minimal success descriptor returned by a semantic indexer.

    ``indexed_revision`` MUST equal the requested revision — the ri-06
    ``SemanticIndexReference`` rejects a succeeded index whose indexed revision
    differs, so a mismatch is a caller bug surfaced here as ``failed``.
    """

    operation_id: str
    registry_record_id: str
    indexed_revision: str


# The injectable seam. A real indexer reaches the coordinator; tests supply a fake.
SemanticIndexer = Callable[[Path, str], SemanticIndexOutcome]


def _bounded_reason(exc: BaseException) -> str:
    """Reduce an exception to a bounded, machine-safe fallback reason."""
    summary = str(exc).strip() or exc.__class__.__name__
    text = f"Semantic index unavailable ({exc.__class__.__name__}): {summary}"
    if len(text) > _MAX_REASON:
        text = text[: _MAX_REASON - 3] + "..."
    return text


def _degraded(
    status: SemanticIndexStatus, requested_revision: str, reason: str
) -> SemanticIndexReference:
    """Build a non-succeeded reference with the canonical exact-search fallback."""
    return SemanticIndexReference(
        status=status,
        requested_revision=requested_revision,
        fallback=Fallback(kind=FallbackKind.EXACT_SEARCH, reason=reason),
    )


def resolve_semantic_index(
    repository: Path,
    requested_revision: str,
    *,
    indexer: SemanticIndexer | None = None,
) -> SemanticIndexReference:
    """Attempt the semantic index and return a validated reference.

    For a valid ``requested_revision`` (the orchestrator pre-validates it) this
    never raises — every indexer outcome maps to a reference:

    * No indexer configured → ``not-configured`` + exact-search fallback.
    * Indexer raises :class:`SemanticIndexUnavailable` or any other exception →
      ``failed`` + exact-search fallback with a bounded reason.
    * Indexer returns an outcome → ``succeeded`` pinned to the exact revision.

    An invalid revision is a caller (programming) error and raises before dispatch.
    """
    ensure_git_revision(requested_revision)
    if indexer is None:
        return _degraded(
            SemanticIndexStatus.NOT_CONFIGURED,
            requested_revision,
            _EXACT_SEARCH_REASON_UNCONFIGURED,
        )
    try:
        outcome = indexer(Path(repository), requested_revision)
    except Exception as exc:  # noqa: BLE001 - degradation must never propagate
        return _degraded(
            SemanticIndexStatus.FAILED, requested_revision, _bounded_reason(exc)
        )

    try:
        return SemanticIndexReference(
            status=SemanticIndexStatus.SUCCEEDED,
            requested_revision=requested_revision,
            operation_id=outcome.operation_id,
            registry_record_id=outcome.registry_record_id,
            indexed_revision=outcome.indexed_revision,
        )
    except Exception as exc:  # noqa: BLE001 - a bad success descriptor degrades
        return _degraded(
            SemanticIndexStatus.FAILED,
            requested_revision,
            _bounded_reason(exc),
        )


# --------------------------------------------------------------------------- #
# Production indexer (subprocess seam)
# --------------------------------------------------------------------------- #
def _slug(value: str) -> str:
    """Reduce a repository identity to a code-search-safe slug."""
    return _SLUG_UNSAFE.sub("-", value.strip().lower()).strip("-") or "repository"


def _index_command(environ: Mapping[str, str]) -> list[str] | None:
    """Return the argv prefix that runs the indexer, or ``None`` when absent.

    Prefers the installed ``index_repo`` console script and falls back to running
    the module with the current interpreter, which covers a venv that has the
    package but no scripts directory on ``PATH``.
    """
    executable = shutil.which(_INDEX_EXECUTABLE)
    if executable:
        return [executable]
    probe = subprocess.run(
        [sys.executable, "-c", f"import {_INDEX_MODULE}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", _INDEX_MODULE]
    return None


def semantic_index_configuration(
    environ: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    """Return the resolved indexer configuration, or ``None`` when unconfigured.

    Configuration is *complete or absent* — a half-set contract is treated as
    unconfigured rather than dispatched, because code-search would only reject it
    as ``not_configured`` after paying process-start cost. Requires a DSN, an
    embedding model, and an embedding dimension.
    """
    env = os.environ if environ is None else environ
    dsn = env.get(_ENV_DSN, "").strip()
    model = env.get(_ENV_MODEL, "").strip()
    dimension = env.get(_ENV_DIMENSION, "").strip()
    if not (dsn and model and dimension):
        return None
    config = {
        "dsn": dsn,
        "model": model,
        "dimension": dimension,
        "provider": env.get(_ENV_PROVIDER, "").strip() or _DEFAULT_PROVIDER,
    }
    credential_ref = env.get(_ENV_CREDENTIAL_REF, "").strip()
    if credential_ref:
        config["credential_ref"] = credential_ref
    return config


def _timeout(environ: Mapping[str, str]) -> float:
    raw = environ.get(_ENV_TIMEOUT, "").strip()
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT
    return value if value > 0 else _DEFAULT_TIMEOUT


def _parse_result(stdout: str) -> dict:
    """Parse the single compact JSON line ``index_repo`` writes to stdout."""
    for line in reversed([ln.strip() for ln in stdout.splitlines() if ln.strip()]):
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise SemanticIndexUnavailable("indexer produced no JSON result line")


def build_subprocess_indexer(
    environ: Mapping[str, str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> SemanticIndexer:
    """Build an indexer that drives ``index_repo`` as a subprocess.

    The returned callable raises :class:`SemanticIndexUnavailable` for every
    non-``ready`` outcome; :func:`resolve_semantic_index` converts that into a
    ``failed`` reference with an exact-search fallback, so a broken or absent
    indexing service degrades the refresh instead of failing it.

    ``runner`` is injectable so the mapping can be tested without a database, an
    embedder, or the code-search distribution installed.
    """
    env = dict(os.environ if environ is None else environ)
    run = runner or subprocess.run

    def indexer(repository: Path, requested_revision: str) -> SemanticIndexOutcome:
        config = semantic_index_configuration(env)
        if config is None:
            raise SemanticIndexUnavailable(
                f"set {_ENV_DSN}, {_ENV_MODEL} and {_ENV_DIMENSION} to enable indexing"
            )
        prefix = _index_command(env)
        if prefix is None:
            raise SemanticIndexUnavailable(
                f"{_INDEX_EXECUTABLE} is not installed in this environment"
            )

        # The lease owner doubles as the operation id: code-search has no
        # operation concept, but it does persist ``lease_owner`` on the index
        # row, so a synthesized id stays traceable back to this refresh. On a
        # ``reused`` result no fresh lease is taken and the id identifies this
        # attempt only.
        operation_id = f"refresh-{uuid.uuid4().hex}"
        slug = _slug(env.get(_ENV_REPO_ID, "") or Path(repository).resolve().name)
        argv = [
            *prefix,
            "--repo-root", str(Path(repository).resolve()),
            "--repo-slug", slug,
            "--source-revision", requested_revision,
            "--namespace-kind", "main",
            "--namespace-key", "main",
            "--provider", config["provider"],
            "--embedding-model", config["model"],
            "--embedding-dimension", config["dimension"],
            "--lease-owner", operation_id,
            "--lease-duration", str(_LEASE_DURATION_SECONDS),
            "--dsn", config["dsn"],
        ]
        if "credential_ref" in config:
            argv += ["--embedding-credential-ref", config["credential_ref"]]

        try:
            completed = run(
                argv, capture_output=True, text=True, check=False,
                timeout=_timeout(env), env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise SemanticIndexUnavailable(
                f"indexing exceeded {_timeout(env):.0f}s"
            ) from exc
        except OSError as exc:
            raise SemanticIndexUnavailable(f"could not run indexer: {exc}") from exc

        result = _parse_result(completed.stdout or "")
        status = result.get("status")
        if status != _STATUS_READY:
            error = result.get("error") or {}
            code = error.get("code") if isinstance(error, dict) else None
            raise SemanticIndexUnavailable(
                f"indexer returned {status!r}" + (f" ({code})" if code else "")
            )

        index_id = result.get("index_id")
        indexed_revision = result.get("source_revision")
        if not index_id or not indexed_revision:
            raise SemanticIndexUnavailable(
                "ready result is missing index_id/source_revision"
            )
        return SemanticIndexOutcome(
            operation_id=operation_id,
            registry_record_id=str(index_id),
            indexed_revision=str(indexed_revision),
        )

    return indexer


def default_semantic_indexer(
    environ: Mapping[str, str] | None = None,
) -> SemanticIndexer | None:
    """Return the production indexer, or ``None`` when indexing is unconfigured.

    ``None`` is the honest answer for an environment with no database or no
    embedding contract: :func:`resolve_semantic_index` maps it to
    ``not-configured`` with an exact-search fallback, which is exactly how a
    developer machine without the indexing stack should behave. Callers pass the
    result straight through to ``orchestrator.generate(semantic_indexer=...)``.
    """
    env = os.environ if environ is None else environ
    if semantic_index_configuration(env) is None:
        return None
    return build_subprocess_indexer(env)


__all__ = [
    "SemanticIndexOutcome",
    "SemanticIndexUnavailable",
    "SemanticIndexer",
    "build_subprocess_indexer",
    "default_semantic_indexer",
    "resolve_semantic_index",
    "semantic_index_configuration",
]
