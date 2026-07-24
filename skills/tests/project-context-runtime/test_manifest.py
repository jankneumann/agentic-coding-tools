"""Deterministic manifest projection and writer tests.

Spec scenarios: project-context-refresh-records.8, .9, .10, .11, .12, .13, .14, .15, .17
Contracts: context-refresh-types / -manifest schemas
Design decisions: D4, D5, D6
"""

from __future__ import annotations

from pathlib import Path

import atomic
import manifest as mf
import models as m
import pytest

REV = "f" * 40
REPO = "github.com/acme/repo"


def _terminal_record(state: m.OperationState = m.OperationState.DEGRADED) -> m.OperationRecord:
    # Deliberately out-of-order producers and artifacts to prove sorting.
    docs = m.ProducerResult(
        producer_id="documentation",
        producer_version="2.0.0",
        status=m.ProducerStatus.FRESH,
        artifacts=(
            m.RepositoryArtifact("docs/z.md", m.ChangeKind.MODIFIED, "2" * 64),
            m.RepositoryArtifact("docs/a.md", m.ChangeKind.ADDED, "1" * 64),
        ),
        validations=(m.ValidationResult("docs.lint", m.ValidationStatus.PASSED, "ok"),),
    )
    arch = m.ProducerResult(
        producer_id="architecture",
        producer_version="1.0.0",
        status=m.ProducerStatus.DEGRADED,
        artifacts=(m.RepositoryArtifact("docs/arch.md", m.ChangeKind.MODIFIED, "3" * 64),),
        validations=(m.ValidationResult("arch.build", m.ValidationStatus.PASSED, "ok"),),
        remediation=(m.Remediation("configure embedder"),),
        fallback=m.Fallback(m.FallbackKind.EXACT_SEARCH, "embedder offline"),
    )
    return m.OperationRecord(
        operation_id=m.derive_operation_id(REPO, REV),
        repository_id=REPO,
        source_revision=REV,
        state=state,
        record_revision=6,
        attempt=1,
        created_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T09:00:00+00:00",  # volatile: must be excluded
        producer_results=(docs, arch),  # unsorted on purpose
        semantic_index=m.initial_semantic_index(REV),
        manifest=m.ManifestPointer(status=m.ManifestPointerStatus.ABSENT),
    )


def test_projection_is_byte_identical_across_runs() -> None:
    record = _terminal_record()
    a = atomic.canonical_json_bytes(mf.project_manifest(record).to_dict())
    b = atomic.canonical_json_bytes(mf.project_manifest(record).to_dict())
    assert a == b


def test_projection_sorts_producers_and_artifacts() -> None:
    manifest = mf.project_manifest(_terminal_record())
    assert [p.producer_id for p in manifest.producer_results] == [
        "architecture",
        "documentation",
    ]
    # Top-level aggregated artifacts are sorted by path.
    assert [a.path for a in manifest.repository_artifacts] == [
        "docs/a.md",
        "docs/arch.md",
        "docs/z.md",
    ]
    # Per-producer artifacts are sorted too.
    docs = next(p for p in manifest.producer_results if p.producer_id == "documentation")
    assert [a.path for a in docs.artifacts] == ["docs/a.md", "docs/z.md"]


def test_projection_aggregates_validations() -> None:
    manifest = mf.project_manifest(_terminal_record())
    assert [v.validation_id for v in manifest.validations] == ["arch.build", "docs.lint"]


def test_projection_reports_degraded_fallbacks() -> None:
    manifest = mf.project_manifest(_terminal_record())
    assert [df.producer_id for df in manifest.degraded_fallbacks] == ["architecture"]
    assert manifest.degraded_fallbacks[0].fallback.kind is m.FallbackKind.EXACT_SEARCH


def test_semantic_index_excluded_from_repository_artifacts() -> None:
    manifest = mf.project_manifest(_terminal_record())
    assert manifest.semantic_index.status is m.SemanticIndexStatus.PENDING
    assert manifest.semantic_index.fallback is not None
    for artifact in manifest.repository_artifacts:
        assert "semantic" not in artifact.path
    # The manifest schema has no field that lists the index as an artifact.
    assert "semantic_index" not in {a.path for a in manifest.repository_artifacts}


def test_non_terminal_projection_rejected() -> None:
    for state in (m.OperationState.PENDING, m.OperationState.RUNNING):
        with pytest.raises(m.ContextRefreshError):
            mf.project_manifest(_terminal_record(state=state))


def test_write_manifest_then_rerun_is_byte_noop(tmp_path: Path) -> None:
    record = _terminal_record()
    first = mf.write_manifest(record, "openspec/context/refresh.json", repo_root=tmp_path)
    assert first.changed is True
    target = tmp_path / "openspec" / "context" / "refresh.json"
    assert target.exists()
    # A second projection of the same logical record replaces nothing.
    second = mf.write_manifest(record, "openspec/context/refresh.json", repo_root=tmp_path)
    assert second.changed is False
    assert second.sha256 == first.sha256


def test_written_manifest_matches_canonical_bytes(tmp_path: Path) -> None:
    record = _terminal_record()
    result = mf.write_manifest(record, "ctx/refresh.json", repo_root=tmp_path)
    target = tmp_path / "ctx" / "refresh.json"
    expected = atomic.canonical_json_bytes(mf.project_manifest(record).to_dict())
    assert target.read_bytes() == expected
    assert result.sha256 == atomic.sha256_hex(expected)


def test_write_manifest_rejects_unsafe_target(tmp_path: Path) -> None:
    record = _terminal_record()
    for bad in ("/etc/passwd", "../escape.json", "a\\b.json"):
        with pytest.raises(m.UnsafePathError):
            mf.write_manifest(record, bad, repo_root=tmp_path)


def test_manifest_excludes_volatile_operation_fields(tmp_path: Path) -> None:
    record = _terminal_record()
    data = mf.project_manifest(record).to_dict()
    for volatile in ("updated_at", "attempt", "record_revision", "state"):
        assert volatile not in data
    assert data["operation_created_at"] == "2026-07-24T00:00:00+00:00"
