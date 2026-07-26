"""Deferred semantic indexing on the mutating refresh path (ri-11 D7).

At a sync point the semantic index must not be attempted inline: the revision
being refreshed is never main's final state, so an inline index would be staled
by the convergence commit that follows it and a correct system would then index a
second time. Deferred mode therefore skips the attempt and records the honest
claim — ``pending`` with the canonical ``exact-search`` fallback — leaving the
enqueue for the final pushed revision to the convergence driver.

Two properties are pinned here, and they are the ones that make deferral safe:

* it never fails open — a deferred index is a *weaker* recorded claim than an
  attempted one, and it degrades the operation through the existing
  ``decide_outcome`` rule rather than reporting a clean success;
* it changes nothing deterministic — the producer results of a deferred run are
  byte-identical to those of an inline run at the same revision.

``SemanticIndexStatus.PENDING`` and the "non-succeeded reference requires a
fallback" rule both already exist in ri-06, so none of this needs a schema change.
"""

from __future__ import annotations

import json
import subprocess

import pytest

import cli
import orchestrator
from _runtime import (
    ProducerResult,
    ProducerStatus,
    ValidationResult,
    ValidationStatus,
)
from models import FallbackKind, OperationState, SemanticIndexStatus
from registry import Producer, ProducerSpec, register
from semantic_adapter import SemanticIndexOutcome

FULL_SHA = "c" * 40
PRODUCER_ID = "documentation.inventory"


class _FreshProducer(Producer):
    def __init__(self, pid: str = PRODUCER_ID) -> None:
        self.spec = ProducerSpec(
            producer_id=pid,
            producer_version="1",
            owner="owner",
            inputs=("x",),
            outputs=(),
        )

    def run(self, mode, repository, source_revision):  # noqa: ANN001
        return ProducerResult(
            producer_id=self.spec.producer_id,
            producer_version="1",
            status=ProducerStatus.FRESH,
            validations=(
                ValidationResult(
                    validation_id=f"{self.spec.producer_id}-check",
                    status=ValidationStatus.PASSED,
                    summary="ok",
                ),
            ),
        )


def _fresh_architecture(repository, revision, mode):  # noqa: ANN001
    """A deterministic architecture seam, so results are comparable across runs."""
    return ProducerResult(
        producer_id=orchestrator.ARCHITECTURE_PRODUCER_ID,
        producer_version="1",
        status=ProducerStatus.FRESH,
        validations=(
            ValidationResult(
                validation_id="architecture-provenance",
                status=ValidationStatus.PASSED,
                summary="ok",
            ),
        ),
    )


class _RecordingIndexer:
    """An indexer that must not be called in deferred mode."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, repository, requested_revision):  # noqa: ANN001
        self.calls.append((str(repository), requested_revision))
        return SemanticIndexOutcome(
            operation_id="op-1",
            registry_record_id="rec-1",
            indexed_revision=requested_revision,
        )


@pytest.fixture
def repository(tmp_path, monkeypatch):
    """A real git checkout with one trivially fresh producer registered.

    A full (unscoped) refresh drives the durable store, which resolves its base
    directory from ``--git-common-dir``, so the fixture must be a real repository.
    """
    monkeypatch.setenv("PROJECT_CONTEXT_REPO_ID", "deferred-index-fixture")
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    register(_FreshProducer())
    return tmp_path


def _generate(repository, indexer, **kwargs):
    return orchestrator.generate(
        repository,
        revision=FULL_SHA,
        architecture=_fresh_architecture,
        semantic_indexer=indexer,
        **kwargs,
    )


def test_deferred_refresh_records_pending_with_an_exact_search_fallback(repository):
    indexer = _RecordingIndexer()

    result = _generate(repository, indexer, defer_semantic_index=True)

    assert indexer.calls == []  # the inline attempt is skipped, not merely ignored
    reference = result.semantic_index
    assert reference is not None
    assert reference.status is SemanticIndexStatus.PENDING
    assert reference.requested_revision == FULL_SHA
    assert reference.fallback is not None
    assert reference.fallback.kind is FallbackKind.EXACT_SEARCH
    assert reference.fallback.reason.strip()


def test_a_deferred_index_degrades_rather_than_reporting_success(repository):
    """Never fail open: a pending index is not a currency claim (D7)."""
    result = _generate(repository, _RecordingIndexer(), defer_semantic_index=True)

    assert result.outcome is OperationState.DEGRADED
    assert result.exit_code() == 2


def test_deferring_is_off_by_default(repository):
    """Safe default: without the keyword the inline attempt still happens."""
    indexer = _RecordingIndexer()

    result = _generate(repository, indexer)

    assert indexer.calls == [(str(repository), FULL_SHA)]
    assert result.semantic_index is not None
    assert result.semantic_index.status is SemanticIndexStatus.SUCCEEDED
    assert result.outcome is OperationState.SUCCEEDED


def test_deferred_and_inline_runs_agree_on_every_deterministic_result(
    tmp_path, monkeypatch
):
    """The deferral changes the index claim and nothing else."""
    monkeypatch.setenv("PROJECT_CONTEXT_REPO_ID", "deferred-index-comparison")
    register(_FreshProducer())
    inline_repo = tmp_path / "inline"
    deferred_repo = tmp_path / "deferred"
    for repo in (inline_repo, deferred_repo):
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)

    inline = _generate(inline_repo, _RecordingIndexer())
    deferred = _generate(deferred_repo, _RecordingIndexer(), defer_semantic_index=True)

    def canonical(result):
        return json.dumps(
            [r.to_dict() for r in result.producer_results], sort_keys=True, indent=2
        )

    assert canonical(deferred) == canonical(inline)
    # Same operation identity, and both still emit the durable manifest.
    assert deferred.operation_id == inline.operation_id
    assert deferred.manifest_path == inline.manifest_path
    # Only the index claim differs.
    assert inline.semantic_index.status is SemanticIndexStatus.SUCCEEDED
    assert deferred.semantic_index.status is SemanticIndexStatus.PENDING


def test_cli_defer_flag_reaches_the_orchestrator(repository, monkeypatch, capsys):
    seen: dict[str, object] = {}

    def fake_generate(repo, **kwargs):  # noqa: ANN001
        seen.update(kwargs)
        return orchestrator.RefreshResult(
            operation_id="op-1",
            outcome=OperationState.SUCCEEDED,
            producer_results=(),
        )

    monkeypatch.setattr(orchestrator, "generate", fake_generate)
    monkeypatch.setattr(cli, "_require_mutation", lambda repo: None)

    cli.main(["--repo", str(repository), "--revision", FULL_SHA, "refresh"])
    capsys.readouterr()
    assert seen["defer_semantic_index"] is False

    cli.main(
        [
            "--repo",
            str(repository),
            "--revision",
            FULL_SHA,
            "refresh",
            "--defer-semantic-index",
        ]
    )
    capsys.readouterr()
    assert seen["defer_semantic_index"] is True


def test_refresh_check_has_no_defer_flag(repository):
    """The read-only path never attempts the index, so there is nothing to defer."""
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--repo",
                str(repository),
                "--revision",
                FULL_SHA,
                "refresh-check",
                "--defer-semantic-index",
            ]
        )
