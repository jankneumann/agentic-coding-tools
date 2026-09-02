"""Tests for the plan-roadmap scaffolder module."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from models import Effort, ItemStatus, Roadmap, RoadmapItem, RoadmapStatus
from scaffolder import populate_change_ids, scaffold_change, scaffold_changes


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


class TestBulkScaffolding:
    """Roadmap creation scaffolds every approved item, and each one validates.

    The earlier bug was not that bulk scaffolding existed — it is the intended
    model — but that the scaffolder created `specs/` and never wrote a delta
    into it. Git drops empty directories, so the change reached CI with no
    specs at all and failed `openspec validate --strict` with "no deltas found".
    """

    def test_scaffolds_every_candidate_item(self, tmp_path: Path):
        items = [
            _make_item("ri-01", "Feature Alpha", priority=1),
            _make_item("ri-02", "Feature Beta", priority=2),
        ]
        roadmap = _make_roadmap(items)
        created = scaffold_changes(roadmap, tmp_path)
        assert len(created) == 2
        assert sorted(p.name for p in created) == ["feature-alpha", "feature-beta"]

    def test_skips_completed_items(self, tmp_path: Path):
        items = [
            _make_item("ri-01", "Active Feature", status=ItemStatus.CANDIDATE),
            _make_item("ri-02", "Done Feature", status=ItemStatus.COMPLETED),
        ]
        roadmap = _make_roadmap(items)
        assert len(scaffold_changes(roadmap, tmp_path)) == 1

    def test_populates_change_ids_as_a_side_effect(self, tmp_path: Path):
        item = _make_item()
        roadmap = _make_roadmap([item])
        scaffold_changes(roadmap, tmp_path)
        assert item.change_id == "test-feature"

    def test_unknown_item_id_raises(self, tmp_path: Path):
        roadmap = _make_roadmap()
        with pytest.raises(KeyError):
            scaffold_change(roadmap, tmp_path, "ri-99")

    def test_completed_item_raises_for_single_scaffold(self, tmp_path: Path):
        item = _make_item("ri-01", "Done Feature", status=ItemStatus.COMPLETED)
        roadmap = _make_roadmap([item])
        with pytest.raises(ValueError, match="only candidate or approved"):
            scaffold_change(roadmap, tmp_path, "ri-01")



def _delta_text(change_dir):
    """Read the single scaffolded spec delta, wherever its capability dir landed."""
    (delta,) = list((change_dir / "specs").rglob("spec.md"))
    return delta.read_text()


class TestScaffoldWritesSpecDeltas:
    """The delta is what makes a scaffold valid — this is the missing function."""

    def test_writes_a_spec_delta_file(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        deltas = list((created / "specs").rglob("spec.md"))
        assert len(deltas) == 1

    def test_specs_dir_is_never_empty(self, tmp_path: Path):
        """Git does not track empty directories — an empty specs/ vanishes."""
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        assert list((created / "specs").rglob("*.md"))

    def test_delta_declares_a_requirement_and_scenarios(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        text = _delta_text(created)
        assert "## ADDED Requirements" in text
        # One requirement per acceptance outcome, each with its own scenario.
        assert text.count("### Requirement:") == 2
        assert text.count("#### Scenario:") == 2

    def test_every_acceptance_outcome_appears(self, tmp_path: Path):
        roadmap = _make_roadmap()
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        text = _delta_text(created)
        for outcome in ["Tests pass", "Feature works"]:
            assert outcome in text

    def test_item_without_outcomes_still_produces_a_scenario(self, tmp_path: Path):
        item = _make_item(acceptance_outcomes=[])
        roadmap = _make_roadmap([item])
        created = scaffold_change(roadmap, tmp_path, "ri-01")
        text = _delta_text(created)
        assert "#### Scenario:" in text


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


class TestScaffoldPassesTheRealValidator:
    """The invariant that matters, checked with the real tool rather than a proxy.

    Every prior test here asserted the *shape* of the output — that files exist
    and contain certain strings — and all of them passed while the scaffolder
    emitted changes `openspec validate --strict` rejected. Only running the
    actual validator catches that, which is the whole argument for ri-19.
    """

    @staticmethod
    def _openspec_project(tmp_path: Path) -> Path:
        """A minimal OpenSpec project the CLI will accept."""
        (tmp_path / "openspec" / "specs").mkdir(parents=True)
        (tmp_path / "openspec" / "project.md").write_text("# Project\n")
        (tmp_path / "openspec" / "AGENTS.md").write_text("# Agents\n")
        return tmp_path

    def test_scaffolded_roadmap_validates(self, tmp_path: Path):
        openspec = shutil.which("openspec")
        if openspec is None:
            pytest.skip("openspec CLI not available")

        root = self._openspec_project(tmp_path)
        items = [
            _make_item("ri-01", "Feature Alpha", priority=1),
            _make_item("ri-02", "Feature Beta", priority=2),
        ]
        scaffold_changes(_make_roadmap(items), root)

        result = subprocess.run(
            [openspec, "validate", "--strict", "--all"],
            cwd=root, capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
