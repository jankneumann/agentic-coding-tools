"""decisions.timeline producer tests (tasks 3.3-3.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from _runtime import ProducerStatus
from contract import validate_producer_result
from producer_decisions import DecisionsTimelineProducer

FULL_SHA = "c" * 40


def _seed_capability(repo: Path, capability: str) -> None:
    (repo / "openspec/specs" / capability).mkdir(parents=True, exist_ok=True)
    (repo / "openspec/specs" / capability / "spec.md").write_text(
        f"# {capability} Specification\n", encoding="utf-8"
    )


def _seed_change_with_decision(repo: Path, change_id: str, capability: str, text: str) -> None:
    change = repo / "openspec/changes" / change_id
    change.mkdir(parents=True, exist_ok=True)
    (change / "session-log.md").write_text(
        "# Session Log\n\n"
        "## Phase: Build (2026-01-15)\n\n"
        "### Decisions\n\n"
        f"1. **Chose an approach** `architectural: {capability}` — {text}\n",
        encoding="utf-8",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _seed_capability(tmp_path, "widgets")
    _seed_change_with_decision(tmp_path, "add-widgets", "widgets", "chose a registry")
    return tmp_path


def _decisions_dir(repo: Path) -> Path:
    return repo / "docs/decisions"


def test_generate_creates_decision_index(repo: Path):
    result = DecisionsTimelineProducer().run("generate", repo, FULL_SHA)
    validate_producer_result(result)
    assert result.status is ProducerStatus.FRESH
    assert (_decisions_dir(repo) / "widgets.md").exists()
    assert (_decisions_dir(repo) / "README.md").exists()


def test_generate_then_check_is_fresh(repo: Path):
    DecisionsTimelineProducer().run("generate", repo, FULL_SHA)
    result = DecisionsTimelineProducer().run("check", repo, FULL_SHA)
    validate_producer_result(result)
    assert result.status is ProducerStatus.FRESH


def test_check_reports_drift_without_writing(repo: Path):
    # Never generated: check should report the would-be files as drift and write nothing.
    result = DecisionsTimelineProducer().run("check", repo, FULL_SHA)
    validate_producer_result(result)
    assert result.status is ProducerStatus.DEGRADED
    assert any(a.path.endswith("widgets.md") for a in result.artifacts)
    assert not _decisions_dir(repo).exists()


def test_new_decision_makes_index_stale(repo: Path):
    DecisionsTimelineProducer().run("generate", repo, FULL_SHA)
    _seed_capability(repo, "gadgets")
    _seed_change_with_decision(repo, "add-gadgets", "gadgets", "chose a factory")
    result = DecisionsTimelineProducer().run("check", repo, FULL_SHA)
    assert result.status is ProducerStatus.DEGRADED
    assert any(a.path.endswith("gadgets.md") for a in result.artifacts)


def test_repeat_generation_is_byte_identical(repo: Path):
    DecisionsTimelineProducer().run("generate", repo, FULL_SHA)
    first = (_decisions_dir(repo) / "widgets.md").read_bytes()
    DecisionsTimelineProducer().run("generate", repo, FULL_SHA)
    assert (_decisions_dir(repo) / "widgets.md").read_bytes() == first
