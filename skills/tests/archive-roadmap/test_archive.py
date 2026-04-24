"""Tests for archive_roadmap helper."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

# Make roadmap-runtime importable for fixture construction
_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from models import Effort, ItemStatus, Roadmap, RoadmapItem, save_roadmap  # type: ignore[import-untyped]

from archive import archive_roadmap, IncompleteRoadmapError


def _make_workspace(tmp_path: Path, *, items: list[RoadmapItem]) -> Path:
    workspace = tmp_path / "openspec" / "roadmaps" / "test-epic"
    workspace.mkdir(parents=True)
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="test-epic",
        source_proposal="proposals/test.md",
        items=items,
    )
    save_roadmap(roadmap, workspace / "roadmap.yaml")
    (workspace / "proposal.md").write_text("# Test\n")
    (workspace / "learnings").mkdir()
    (workspace / "learnings" / "ri-01.md").write_text("learned\n")
    return workspace


def _item(item_id: str, status: ItemStatus) -> RoadmapItem:
    return RoadmapItem(
        item_id=item_id,
        title=f"Item {item_id}",
        status=status,
        priority=1,
        effort=Effort.M,
        depends_on=[],
    )


class TestHappyPath:
    def test_archives_completed_roadmap(self, tmp_path):
        workspace = _make_workspace(tmp_path, items=[
            _item("ri-01", ItemStatus.COMPLETED),
            _item("ri-02", ItemStatus.COMPLETED),
        ])

        result = archive_roadmap(workspace, today=date(2026, 4, 24))

        assert not workspace.exists()
        assert result.destination.exists()
        assert result.destination.name == "2026-04-24-test-epic"
        assert result.destination.parent.name == "archive"
        assert result.item_counts == {"completed": 2}
        assert result.forced is False

    def test_preserves_workspace_contents(self, tmp_path):
        workspace = _make_workspace(tmp_path, items=[
            _item("ri-01", ItemStatus.COMPLETED),
        ])

        result = archive_roadmap(workspace, today=date(2026, 4, 24))

        assert (result.destination / "roadmap.yaml").exists()
        assert (result.destination / "proposal.md").exists()
        assert (result.destination / "learnings" / "ri-01.md").exists()

    def test_skipped_items_count_as_terminal(self, tmp_path):
        workspace = _make_workspace(tmp_path, items=[
            _item("ri-01", ItemStatus.COMPLETED),
            _item("ri-02", ItemStatus.SKIPPED),
        ])

        result = archive_roadmap(workspace, today=date(2026, 4, 24))

        assert result.destination.exists()
        assert result.forced is False


class TestIncompleteRefusal:
    def test_refuses_with_in_progress_item(self, tmp_path):
        workspace = _make_workspace(tmp_path, items=[
            _item("ri-01", ItemStatus.COMPLETED),
            _item("ri-02", ItemStatus.IN_PROGRESS),
        ])

        with pytest.raises(IncompleteRoadmapError) as exc:
            archive_roadmap(workspace)

        assert workspace.exists(), "Workspace must remain in place when refusing"
        assert "in_progress" in exc.value.counts

    def test_refuses_with_blocked_item(self, tmp_path):
        workspace = _make_workspace(tmp_path, items=[
            _item("ri-01", ItemStatus.BLOCKED),
        ])

        with pytest.raises(IncompleteRoadmapError):
            archive_roadmap(workspace)

    def test_force_archives_incomplete(self, tmp_path):
        workspace = _make_workspace(tmp_path, items=[
            _item("ri-01", ItemStatus.COMPLETED),
            _item("ri-02", ItemStatus.FAILED),
        ])

        result = archive_roadmap(workspace, force=True, today=date(2026, 4, 24))

        assert result.destination.exists()
        assert result.forced is True
        assert result.item_counts == {"completed": 1, "failed": 1}


class TestCollisionAndMissing:
    def test_collision_aborts(self, tmp_path):
        workspace = _make_workspace(tmp_path, items=[_item("ri-01", ItemStatus.COMPLETED)])

        archive_roadmap(workspace, today=date(2026, 4, 24))

        # Recreate workspace and try to archive on the same date
        workspace_again = _make_workspace(tmp_path, items=[_item("ri-01", ItemStatus.COMPLETED)])
        with pytest.raises(FileExistsError, match="already exists"):
            archive_roadmap(workspace_again, today=date(2026, 4, 24))
        assert workspace_again.exists(), "Source must remain on collision"

    def test_missing_workspace(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Workspace directory"):
            archive_roadmap(tmp_path / "nonexistent")

    def test_missing_roadmap_yaml(self, tmp_path):
        workspace = tmp_path / "openspec" / "roadmaps" / "empty-epic"
        workspace.mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="No roadmap.yaml"):
            archive_roadmap(workspace)


class TestArchiveRootOverride:
    def test_explicit_archive_root(self, tmp_path):
        workspace = _make_workspace(tmp_path, items=[_item("ri-01", ItemStatus.COMPLETED)])
        custom_archive = tmp_path / "custom-archive"

        result = archive_roadmap(
            workspace,
            archive_root=custom_archive,
            today=date(2026, 4, 24),
        )

        assert result.destination.parent == custom_archive
        assert result.destination.name == "2026-04-24-test-epic"
