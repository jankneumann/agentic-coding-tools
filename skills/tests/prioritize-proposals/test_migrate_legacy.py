"""Tests for migrate_legacy.py — one-shot migration of the stale 2026-05-04 file."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills" / "prioritize-proposals" / "scripts"))

from migrate_legacy import LEGACY_RUN_NAME, migrate_legacy  # noqa: E402


def _make_legacy_file(repo: Path, name: str, content: str) -> Path:
    src = repo / "openspec" / "changes" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(content)
    return src


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return tmp_path


class TestMigrateLegacy:
    def test_moves_md_to_legacy_entry(self, repo: Path):
        src_md = _make_legacy_file(repo, "prioritized-proposals.md", "stale report")
        result = migrate_legacy(repo)
        legacy_dir = repo / "openspec" / "priorities" / LEGACY_RUN_NAME
        assert (legacy_dir / "report.md").read_text() == "stale report"
        assert not src_md.exists()
        assert result.moved == [("openspec/changes/prioritized-proposals.md", f"openspec/priorities/{LEGACY_RUN_NAME}/report.md")]

    def test_moves_json_when_present(self, repo: Path):
        _make_legacy_file(repo, "prioritized-proposals.md", "stale report")
        _make_legacy_file(repo, "prioritized-proposals.json", '{"old": "report"}')
        result = migrate_legacy(repo)
        legacy_dir = repo / "openspec" / "priorities" / LEGACY_RUN_NAME
        assert (legacy_dir / "report.json").read_text() == '{"old": "report"}'
        moved_dsts = [dst for _, dst in result.moved]
        assert f"openspec/priorities/{LEGACY_RUN_NAME}/report.json" in moved_dsts

    def test_idempotent_no_source(self, repo: Path):
        # No source file at all → no-op
        result = migrate_legacy(repo)
        assert result.moved == []
        assert result.skipped_reason == "no_source"

    def test_idempotent_already_migrated(self, repo: Path):
        # Source exists AND destination exists → refuse to overwrite
        _make_legacy_file(repo, "prioritized-proposals.md", "stale report")
        legacy_dir = repo / "openspec" / "priorities" / LEGACY_RUN_NAME
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "report.md").write_text("already-migrated content")

        result = migrate_legacy(repo)
        assert result.moved == []
        assert result.skipped_reason == "already_migrated"
        # The pre-existing migrated entry is preserved, not clobbered
        assert (legacy_dir / "report.md").read_text() == "already-migrated content"
        # The source file is still there — the operator must resolve manually
        src_md = repo / "openspec" / "changes" / "prioritized-proposals.md"
        assert src_md.exists()

    def test_creates_priorities_tree_if_absent(self, repo: Path):
        _make_legacy_file(repo, "prioritized-proposals.md", "stale")
        migrate_legacy(repo)
        # priorities/ and legacy subdir both created
        assert (repo / "openspec" / "priorities").is_dir()
        assert (repo / "openspec" / "priorities" / LEGACY_RUN_NAME).is_dir()


class TestLegacyRunName:
    def test_constant_value(self):
        # Per D6 — the directory name is the literal "2026-05-04-legacy" and is
        # whitelisted in any future header-presence check.
        assert LEGACY_RUN_NAME == "2026-05-04-legacy"
