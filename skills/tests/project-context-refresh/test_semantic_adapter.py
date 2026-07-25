"""Semantic-index adapter tests (ri-07 tasks 1.1-1.2).

The adapter must map every indexing attempt to a validated ri-06
``SemanticIndexReference`` without a database and without ever raising on a
degraded path.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from _runtime import FallbackKind
from models import SemanticIndexStatus
from semantic_adapter import (
    SemanticIndexOutcome,
    SemanticIndexUnavailable,
    build_subprocess_indexer,
    default_semantic_indexer,
    resolve_semantic_index,
    semantic_index_configuration,
)

FULL_SHA = "a" * 40
OTHER_SHA = "b" * 40


def test_no_indexer_is_not_configured_with_exact_search_fallback():
    ref = resolve_semantic_index(Path("/repo"), FULL_SHA, indexer=None)
    assert ref.status is SemanticIndexStatus.NOT_CONFIGURED
    assert ref.requested_revision == FULL_SHA
    assert ref.fallback is not None
    assert ref.fallback.kind is FallbackKind.EXACT_SEARCH
    assert ref.operation_id is None


def test_successful_index_is_pinned_to_the_exact_revision():
    def indexer(repo: Path, rev: str) -> SemanticIndexOutcome:
        return SemanticIndexOutcome(
            operation_id="op-123", registry_record_id="rec-9", indexed_revision=rev
        )

    ref = resolve_semantic_index(Path("/repo"), FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.SUCCEEDED
    assert ref.operation_id == "op-123"
    assert ref.registry_record_id == "rec-9"
    assert ref.indexed_revision == FULL_SHA
    assert ref.fallback is None


def test_unavailable_service_degrades_to_failed_without_raising():
    def indexer(repo: Path, rev: str) -> SemanticIndexOutcome:
        raise SemanticIndexUnavailable("no database connection")

    ref = resolve_semantic_index(Path("/repo"), FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.FAILED
    assert ref.fallback is not None
    assert ref.fallback.kind is FallbackKind.EXACT_SEARCH
    assert "no database connection" in ref.fallback.reason


def test_arbitrary_indexer_error_degrades_and_is_bounded():
    def indexer(repo: Path, rev: str) -> SemanticIndexOutcome:
        raise RuntimeError("x" * 5000)

    ref = resolve_semantic_index(Path("/repo"), FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.FAILED
    assert ref.fallback is not None
    assert len(ref.fallback.reason) <= 300


def test_mismatched_indexed_revision_degrades_not_raises():
    def indexer(repo: Path, rev: str) -> SemanticIndexOutcome:
        return SemanticIndexOutcome(
            operation_id="op-1", registry_record_id="rec-1", indexed_revision=OTHER_SHA
        )

    ref = resolve_semantic_index(Path("/repo"), FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.FAILED
    assert ref.fallback is not None


def test_invalid_requested_revision_is_a_caller_error():
    with pytest.raises(Exception):
        resolve_semantic_index(Path("/repo"), "not-a-sha", indexer=None)


# --------------------------------------------------------------------------- #
# Production indexer wiring (ri-07 merge-triage regression)
# --------------------------------------------------------------------------- #
BASE_ENV = {
    "POSTGRES_DSN": "postgresql://u@localhost/db",
    "PROJECT_CONTEXT_EMBEDDING_MODEL": "bge-small",
    "PROJECT_CONTEXT_EMBEDDING_DIMENSION": "384",
}


def _completed(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_configuration_is_complete_or_absent():
    assert semantic_index_configuration({}) is None
    # A half-set contract is unconfigured, not dispatched.
    assert semantic_index_configuration({"POSTGRES_DSN": "x"}) is None
    assert semantic_index_configuration(
        {"POSTGRES_DSN": "x", "PROJECT_CONTEXT_EMBEDDING_MODEL": "m"}
    ) is None

    config = semantic_index_configuration(BASE_ENV)
    assert config is not None
    assert config["dimension"] == "384"
    assert config["provider"] == "local"  # defaulted


def test_default_indexer_is_none_when_unconfigured():
    # The degradation contract: no stack configured -> not-configured, not a crash.
    assert default_semantic_indexer({}) is None
    ref = resolve_semantic_index(Path("/repo"), FULL_SHA, indexer=default_semantic_indexer({}))
    assert ref.status is SemanticIndexStatus.NOT_CONFIGURED


def test_default_indexer_is_built_when_configured():
    assert default_semantic_indexer(BASE_ENV) is not None


def test_ready_result_maps_to_outcome(monkeypatch, tmp_path):
    monkeypatch.setattr("semantic_adapter._index_command", lambda env: ["index_repo"])
    seen = {}

    def runner(argv, **kwargs):
        seen["argv"] = argv
        return _completed(json.dumps({
            "status": "ready", "index_id": "11111111-2222-3333-4444-555555555555",
            "source_revision": FULL_SHA, "durable": True, "reused": False,
        }))

    indexer = build_subprocess_indexer(BASE_ENV, runner=runner)
    outcome = indexer(tmp_path, FULL_SHA)

    assert outcome.registry_record_id == "11111111-2222-3333-4444-555555555555"
    assert outcome.indexed_revision == FULL_SHA
    # operation_id doubles as the lease owner so the run is traceable in the row.
    assert outcome.operation_id.startswith("refresh-")
    assert "--lease-owner" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--lease-owner") + 1] == outcome.operation_id
    assert seen["argv"][seen["argv"].index("--source-revision") + 1] == FULL_SHA

    # And it resolves to a SUCCEEDED reference pinned to the exact revision.
    ref = resolve_semantic_index(tmp_path, FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.SUCCEEDED


@pytest.mark.parametrize("payload", [
    {"status": "not_configured", "error": {"code": "missing_database"}},
    {"status": "failed", "error": {"code": "boom"}},
    {"status": "conflict"},
])
def test_non_ready_statuses_degrade_rather_than_raise(monkeypatch, tmp_path, payload):
    monkeypatch.setattr("semantic_adapter._index_command", lambda env: ["index_repo"])
    indexer = build_subprocess_indexer(
        BASE_ENV, runner=lambda argv, **kw: _completed(json.dumps(payload), returncode=1)
    )
    with pytest.raises(SemanticIndexUnavailable):
        indexer(tmp_path, FULL_SHA)
    # The orchestrator seam never propagates it.
    ref = resolve_semantic_index(tmp_path, FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.FAILED
    assert ref.fallback.kind is FallbackKind.EXACT_SEARCH


def test_unparseable_output_degrades(monkeypatch, tmp_path):
    monkeypatch.setattr("semantic_adapter._index_command", lambda env: ["index_repo"])
    indexer = build_subprocess_indexer(
        BASE_ENV, runner=lambda argv, **kw: _completed("Traceback: boom\n", returncode=1)
    )
    ref = resolve_semantic_index(tmp_path, FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.FAILED


def test_timeout_degrades(monkeypatch, tmp_path):
    monkeypatch.setattr("semantic_adapter._index_command", lambda env: ["index_repo"])

    def slow(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=1)

    indexer = build_subprocess_indexer({**BASE_ENV, "PROJECT_CONTEXT_INDEX_TIMEOUT": "1"}, runner=slow)
    ref = resolve_semantic_index(tmp_path, FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.FAILED


def test_missing_executable_degrades(monkeypatch, tmp_path):
    monkeypatch.setattr("semantic_adapter._index_command", lambda env: None)
    indexer = build_subprocess_indexer(BASE_ENV, runner=lambda argv, **kw: _completed("{}"))
    ref = resolve_semantic_index(tmp_path, FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.FAILED


def test_repo_slug_honors_shared_identity_override(monkeypatch, tmp_path):
    monkeypatch.setattr("semantic_adapter._index_command", lambda env: ["index_repo"])
    seen = {}

    def runner(argv, **kwargs):
        seen["argv"] = argv
        return _completed(json.dumps({
            "status": "ready", "index_id": "abc", "source_revision": FULL_SHA,
        }))

    indexer = build_subprocess_indexer(
        {**BASE_ENV, "PROJECT_CONTEXT_REPO_ID": "Agentic Coding_Tools"}, runner=runner
    )
    indexer(tmp_path, FULL_SHA)
    assert seen["argv"][seen["argv"].index("--repo-slug") + 1] == "agentic-coding-tools"
