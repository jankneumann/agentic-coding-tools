"""openspec.projection producer tests (tasks 4.1-4.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from _runtime import ChangeKind, ProducerStatus
from contract import validate_producer_result
import openspec_merge as M
from producer_openspec import OpenSpecProjectionProducer

FULL_SHA = "d" * 40


def _canonical(repo: Path, capability: str, requirements: str) -> None:
    d = repo / "openspec/specs" / capability
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(
        f"# {capability} Specification\n\n## Purpose\nTBD\n\n## Requirements\n{requirements}",
        encoding="utf-8",
    )


def _delta(repo: Path, change_id: str, capability: str, body: str) -> None:
    d = repo / "openspec/changes" / change_id / "specs" / capability
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(body, encoding="utf-8")


REQ_A = "### Requirement: Alpha\n\nThe system SHALL do alpha.\n\n"


# --------------------------------------------------------------------------- #
# Merge helper unit tests
# --------------------------------------------------------------------------- #
def test_added_requirement_projects_into_spec():
    canonical = f"## Requirements\n{REQ_A}"
    delta = M.parse_delta(
        "## ADDED Requirements\n\n### Requirement: Beta\n\nThe system SHALL do beta.\n"
    )
    out = M.project_capability(canonical, [delta])
    assert "Requirement: Alpha" in out and "Requirement: Beta" in out


def test_removed_requirement_drops_block():
    canonical = f"## Requirements\n{REQ_A}"
    delta = M.parse_delta("## REMOVED Requirements\n\n### Requirement: Alpha\n")
    out = M.project_capability(canonical, [delta])
    assert "Requirement: Alpha" not in out


def test_modified_requirement_replaces_block():
    canonical = f"## Requirements\n{REQ_A}"
    delta = M.parse_delta(
        "## MODIFIED Requirements\n\n### Requirement: Alpha\n\nThe system SHALL do alpha v2.\n"
    )
    out = M.project_capability(canonical, [delta])
    assert "alpha v2" in out
    assert out.count("Requirement: Alpha") == 1


def test_no_delta_untouched_capability_is_byte_identical():
    canonical = f"## Requirements\n{REQ_A}"
    # No deltas at all -> projection returns canonical unchanged.
    assert M.project_capability(canonical, []) == canonical


# --------------------------------------------------------------------------- #
# Producer behavior
# --------------------------------------------------------------------------- #
@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _canonical(tmp_path, "widgets", REQ_A)
    return tmp_path


def test_no_active_changes_is_fresh(repo: Path):
    result = OpenSpecProjectionProducer().run("check", repo, FULL_SHA)
    validate_producer_result(result)
    assert result.status is ProducerStatus.FRESH


def test_active_delta_reports_pending_merge(repo: Path):
    _delta(
        repo,
        "extend-widgets",
        "widgets",
        "## ADDED Requirements\n\n### Requirement: Gamma\n\nThe system SHALL do gamma.\n",
    )
    result = OpenSpecProjectionProducer().run("check", repo, FULL_SHA)
    validate_producer_result(result)
    assert result.status is ProducerStatus.DEGRADED
    assert result.artifacts[0].path == "openspec/specs/widgets/spec.md"
    assert result.artifacts[0].change is ChangeKind.MODIFIED
    assert result.fallback is not None  # custom projection-only fallback


def test_new_capability_delta_reports_added(repo: Path):
    _delta(
        repo,
        "add-gadgets",
        "gadgets",
        "## ADDED Requirements\n\n### Requirement: Gadget\n\nThe system SHALL gadget.\n",
    )
    result = OpenSpecProjectionProducer().run("check", repo, FULL_SHA)
    assert result.status is ProducerStatus.DEGRADED
    added = [a for a in result.artifacts if a.change is ChangeKind.ADDED]
    assert added and added[0].path == "openspec/specs/gadgets/spec.md"


def test_projection_never_mutates_canonical_specs(repo: Path):
    before = (repo / "openspec/specs/widgets/spec.md").read_bytes()
    _delta(
        repo,
        "extend-widgets",
        "widgets",
        "## ADDED Requirements\n\n### Requirement: Gamma\n\nThe system SHALL do gamma.\n",
    )
    # Both modes must leave canonical specs untouched.
    OpenSpecProjectionProducer().run("check", repo, FULL_SHA)
    OpenSpecProjectionProducer().run("generate", repo, FULL_SHA)
    assert (repo / "openspec/specs/widgets/spec.md").read_bytes() == before


def test_archive_subtree_is_ignored(repo: Path):
    # A delta under changes/archive/ must not be projected.
    d = repo / "openspec/changes/archive/2026-01-01-old/specs/widgets"
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(
        "## ADDED Requirements\n\n### Requirement: Old\n\nSHALL be old.\n", encoding="utf-8"
    )
    result = OpenSpecProjectionProducer().run("check", repo, FULL_SHA)
    assert result.status is ProducerStatus.FRESH
