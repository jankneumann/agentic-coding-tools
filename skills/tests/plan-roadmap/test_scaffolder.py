"""Tests for the plan-roadmap scaffolder module."""

from __future__ import annotations

from pathlib import Path

import pytest
from models import Effort, ItemStatus, Roadmap, RoadmapItem, RoadmapStatus
from scaffolder import scaffold_changes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_item(
    item_id: str = "ri-01",
    title: str = "Test Feature",
    status: ItemStatus = ItemStatus.CANDIDATE,
    **kwargs,
) -> RoadmapItem:
    defaults = {
        "priority": 1,
        "effort": Effort.M,
        "depends_on": [],
        "description": "A test feature description.",
        "acceptance_outcomes": ["Tests pass", "Feature works"],
    }
    defaults.update(kwargs)
    return RoadmapItem(item_id=item_id, title=title, status=status, **defaults)

def _make_roadmap(items: list[RoadmapItem] | None = None) -> Roadmap:
    if items is None:
        items = [_make_item()]
    return Roadmap(
        schema_version=1,
        roadmap_id="roadmap-test-proposal",
        source_proposal="proposals/test.md",
        items=items,
        status=RoadmapStatus.PLANNING,
    )

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestScaffoldChanges:
    def test_creates_change_directory(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_changes(roadmap, tmp_path)
        assert len(created) == 1
        assert created[0].is_dir()

    def test_creates_proposal_md(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_changes(roadmap, tmp_path)
        proposal_path = created[0] / "proposal.md"
        assert proposal_path.exists()
        content = proposal_path.read_text()
        assert "Test Feature" in content

    def test_proposal_contains_parent_roadmap(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_changes(roadmap, tmp_path)
        proposal_path = created[0] / "proposal.md"
        content = proposal_path.read_text()
        assert "roadmap-test-proposal" in content
        assert "Parent roadmap" in content

    def test_proposal_contains_effort_and_priority(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_changes(roadmap, tmp_path)
        content = (created[0] / "proposal.md").read_text()
        assert "Effort: M" in content
        assert "Priority: 1" in content

    def test_proposal_contains_acceptance_outcomes(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_changes(roadmap, tmp_path)
        content = (created[0] / "proposal.md").read_text()
        assert "Tests pass" in content
        assert "Feature works" in content

    def test_proposal_contains_dependencies(self, tmp_path: Path):
        item = _make_item(depends_on=["ri-00-infra"])
        roadmap = _make_roadmap([item])
        created = scaffold_changes(roadmap, tmp_path)
        content = (created[0] / "proposal.md").read_text()
        assert "ri-00-infra" in content

    def test_creates_tasks_md(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_changes(roadmap, tmp_path)
        tasks_path = created[0] / "tasks.md"
        assert tasks_path.exists()
        content = tasks_path.read_text()
        assert "Test Feature" in content
        assert "- [ ]" in content  # Has checkbox items

    def test_creates_specs_directory(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_changes(roadmap, tmp_path)
        specs_dir = created[0] / "specs"
        assert specs_dir.is_dir()

    def test_multiple_items_create_multiple_dirs(self, tmp_path: Path):
        items = [
            _make_item("ri-01", "Feature Alpha", priority=1),
            _make_item("ri-02", "Feature Beta", priority=2),
        ]
        roadmap = _make_roadmap(items)
        created = scaffold_changes(roadmap, tmp_path)
        assert len(created) == 2
        # Each should have its own directory
        dir_names = {p.name for p in created}
        assert len(dir_names) == 2

    def test_skips_completed_items(self, tmp_path: Path):
        items = [
            _make_item("ri-01", "Active Feature", status=ItemStatus.CANDIDATE),
            _make_item("ri-02", "Done Feature", status=ItemStatus.COMPLETED),
        ]
        roadmap = _make_roadmap(items)
        created = scaffold_changes(roadmap, tmp_path)
        assert len(created) == 1

    def test_updates_item_change_id(self, tmp_path: Path):
        item = _make_item()
        assert item.change_id is None
        roadmap = _make_roadmap([item])
        scaffold_changes(roadmap, tmp_path)
        assert item.change_id is not None
        assert len(item.change_id) > 0

    def test_uses_existing_change_id(self, tmp_path: Path):
        item = _make_item()
        item.change_id = "custom-change-id"
        roadmap = _make_roadmap([item])
        created = scaffold_changes(roadmap, tmp_path)
        assert created[0].name == "custom-change-id"

    def test_directory_under_openspec_changes(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_changes(roadmap, tmp_path)
        # Should be under repo_root/openspec/changes/
        assert "openspec" in str(created[0])
        assert "changes" in str(created[0])

    def test_idempotent_scaffold(self, tmp_path: Path):
        """Running scaffold twice should not fail or corrupt files."""
        roadmap = _make_roadmap()
        created1 = scaffold_changes(roadmap, tmp_path)
        created2 = scaffold_changes(roadmap, tmp_path)
        assert len(created1) == len(created2)
        # Files should still be valid
        assert (created2[0] / "proposal.md").exists()
        assert (created2[0] / "tasks.md").exists()
