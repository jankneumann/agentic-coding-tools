"""Tests for the plan-roadmap scaffolder module."""

from __future__ import annotations

from pathlib import Path

from models import Effort, ItemStatus, Roadmap, RoadmapItem, RoadmapStatus
from scaffolder import populate_change_ids, scaffold_change


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
class TestScaffoldChange:
    def test_creates_change_directory(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        assert created.is_dir()

    def test_creates_proposal_md(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        proposal_path = created / "proposal.md"
        assert proposal_path.exists()
        assert "Test Feature" in proposal_path.read_text()

    def test_proposal_contains_parent_roadmap(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        content = (created / "proposal.md").read_text()
        assert "roadmap-test-proposal" in content
        assert "Parent roadmap" in content

    def test_proposal_contains_effort_and_priority(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        content = (created / "proposal.md").read_text()
        assert "Effort: M" in content
        assert "Priority: 1" in content

    def test_proposal_contains_acceptance_outcomes(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        content = (created / "proposal.md").read_text()
        assert "Tests pass" in content
        assert "Feature works" in content

    def test_proposal_contains_dependencies(self, tmp_path: Path):
        item = _make_item(depends_on=["ri-00-infra"])
        roadmap = _make_roadmap([item])
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        assert "ri-00-infra" in (created / "proposal.md").read_text()

    def test_creates_tasks_md(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        tasks_path = created / "tasks.md"
        assert tasks_path.exists()
        content = tasks_path.read_text()
        assert "Test Feature" in content
        assert "- [ ]" in content  # Has checkbox items

    def test_creates_specs_directory(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        assert (created / "specs").is_dir()

    def test_updates_item_change_id(self, tmp_path: Path):
        item = _make_item()
        assert item.change_id is None
        roadmap = _make_roadmap([item])
        scaffold_change(roadmap, tmp_path, "ri-01")
        assert item.change_id
        assert len(item.change_id) > 0

    def test_uses_existing_change_id(self, tmp_path: Path):
        item = _make_item()
        item.change_id = "custom-change-id"
        roadmap = _make_roadmap([item])
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        assert created.name == "custom-change-id"

    def test_directory_under_openspec_changes(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        assert created.parent.name == "changes"
        assert created.parent.parent.name == "openspec"

    def test_idempotent_scaffold(self, tmp_path: Path):
        """Running scaffold twice should not fail or corrupt files."""
        roadmap = _make_roadmap()
        first = scaffold_change(roadmap, tmp_path, "ri-01")
        second = scaffold_change(roadmap, tmp_path, "ri-01")
        assert first == second
        assert (second / "proposal.md").exists()
        assert (second / "tasks.md").exists()


class TestSingleItemOnly:
    """Scaffolding is per-item at pickup time — never the whole roadmap up front.

    Bulk scaffolding produced one `openspec validate --strict` failure per item,
    because a change with an empty `specs/` directory has no delta. CI runs
    `openspec validate --strict --all`, so an N-item roadmap turned CI red for
    the whole life of the roadmap.
    """

    def test_scaffolds_only_the_requested_item(self, tmp_path: Path):
        items = [
            _make_item("ri-01", "Feature Alpha", priority=1),
            _make_item("ri-02", "Feature Beta", priority=2),
        ]
        roadmap = _make_roadmap(items)
        scaffold_change(roadmap, tmp_path, "ri-01")
        changes = sorted(p.name for p in (tmp_path / "openspec" / "changes").iterdir())
        assert changes == ["feature-alpha"]

    def test_unknown_item_id_raises(self, tmp_path: Path):
        roadmap = _make_roadmap()
        with pytest.raises(KeyError):
            scaffold_change(roadmap, tmp_path, "ri-99")

    def test_completed_item_raises(self, tmp_path: Path):
        item = _make_item("ri-01", "Done Feature", status=ItemStatus.COMPLETED)
        roadmap = _make_roadmap([item])
        with pytest.raises(ValueError, match="only candidate or approved"):
            scaffold_change(roadmap, tmp_path, "ri-01")

    def test_no_bulk_entry_point_exists(self):
        """A bulk API is the footgun; it must not come back."""
        import scaffolder

        assert not hasattr(scaffolder, "scaffold_changes")


class TestPopulateChangeIds:
    """change_id must be persisted at decomposition time.

    The generation contract never asks the model for change_id and the schema
    leaves it optional, so a generated roadmap carries none. Every consumer
    that must locate openspec/changes/<change-id>/ then re-derives it and hopes
    the answers agree. populate_change_ids fixes the value once, before save.
    """

    def test_populates_missing_ids(self):
        items = [_make_item("ri-01", "Feature Alpha"), _make_item("ri-02", "Feature Beta")]
        roadmap = _make_roadmap(items)
        assert all(i.change_id is None for i in items)
        assigned = populate_change_ids(roadmap)
        assert assigned == {"ri-01": "feature-alpha", "ri-02": "feature-beta"}
        assert [i.change_id for i in items] == ["feature-alpha", "feature-beta"]

    def test_preserves_operator_set_ids(self):
        item = _make_item("ri-01", "Feature Alpha")
        item.change_id = "hand-picked-id"
        roadmap = _make_roadmap([item])
        populate_change_ids(roadmap)
        assert item.change_id == "hand-picked-id"

    def test_is_idempotent(self):
        roadmap = _make_roadmap([_make_item("ri-01", "Feature Alpha")])
        first = populate_change_ids(roadmap)
        second = populate_change_ids(roadmap)
        assert first == second

    def test_disambiguates_colliding_slugs(self):
        """Two titles reducing to the same slug must not claim one directory."""
        items = [
            _make_item("ri-01", "Ship the thing"),
            _make_item("ri-02", "Ship the thing"),
            _make_item("ri-03", "Ship the thing"),
        ]
        roadmap = _make_roadmap(items)
        populate_change_ids(roadmap)
        ids = [i.change_id for i in items]
        assert ids == ["ship-the-thing", "ship-the-thing-2", "ship-the-thing-3"]
        assert len(set(ids)) == 3

    def test_agrees_with_scaffold_change(self, tmp_path: Path):
        """The persisted id must be the directory scaffold_change creates."""
        roadmap = _make_roadmap([_make_item("ri-01", "Feature Alpha")])
        assigned = populate_change_ids(roadmap)
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        assert created.name == assigned["ri-01"]


class TestStubIsNotCommittable:
    def test_specs_dir_has_no_deltas(self, tmp_path: Path):
        """The stub is deliberately incomplete.

        `openspec validate --strict` requires at least one delta file carrying a
        `#### Scenario:` block. The scaffolder writes none, so the caller must
        author spec deltas (normally via /plan-feature) before committing.
        """
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        assert list((created / "specs").iterdir()) == []
