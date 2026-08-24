"""Regression tests for the ``superseded`` status introduced by ri-17.

ri-17 added a new terminal item status but only taught the *readiness* path
about it. Four other consumers enumerate terminal statuses or coerce the new
edge fields, and each was left with the pre-ri-17 view:

* ``archive-roadmap`` treated only COMPLETED/SKIPPED as terminal, so a roadmap
  with superseded items could no longer be archived without ``--force``;
* the autopilot-roadmap summary omitted superseded from ``terminal_count``, so
  such a roadmap reported "partial" forever;
* readiness keyed on ``status`` alone, so a ``superseded_by`` edge added
  without the paired status flip still scheduled the item;
* ``from_dict`` used ``list(data.get(k, []))``, which raises on a YAML key with
  an empty value.

Every test here fails on the pre-fix tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from models import (
    Effort,
    ItemStatus,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
    load_all_roadmaps_strict,
)

_ARCHIVE_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "archive-roadmap" / "scripts"
)
if str(_ARCHIVE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_ARCHIVE_SCRIPTS))


def _item(item_id: str, **kwargs) -> RoadmapItem:
    defaults: dict = {
        "title": "Item",
        "status": ItemStatus.APPROVED,
        "priority": 1,
        "effort": Effort.M,
    }
    defaults.update(kwargs)
    return RoadmapItem(item_id=item_id, **defaults)


def _write_roadmap(
    repo_root: Path, roadmap_id: str, items: list[RoadmapItem]
) -> Path:
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id=roadmap_id,
        source_proposal=f"openspec/roadmaps/{roadmap_id}/proposal.md",
        items=items,
        status=RoadmapStatus.APPROVED,
    )
    path = repo_root / "openspec" / "roadmaps" / roadmap_id / "roadmap.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(roadmap.to_dict(), default_flow_style=False, sort_keys=False)
    )
    return path


# ---------------------------------------------------------------------------
# archive-roadmap terminality
# ---------------------------------------------------------------------------
class TestArchiveTerminality:
    def test_superseded_is_terminal(self):
        """A superseded item must not block archiving.

        Pre-fix this raised IncompleteRoadmapError, which is how this PR's own
        data change (six symphony items flipped to ``superseded``) made the
        symphony roadmap un-archivable without ``--force``.
        """
        from archive import _TERMINAL_STATUSES  # type: ignore[import-untyped]

        assert ItemStatus.SUPERSEDED in _TERMINAL_STATUSES

    def test_unfinished_statuses_still_block(self):
        """The widening must not make everything terminal."""
        from archive import _TERMINAL_STATUSES  # type: ignore[import-untyped]

        for status in (
            ItemStatus.APPROVED,
            ItemStatus.IN_PROGRESS,
            ItemStatus.BLOCKED,
            ItemStatus.FAILED,
        ):
            assert status not in _TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# readiness must respect the edge, not only the status
# ---------------------------------------------------------------------------
class TestSupersededByBlocksReadiness:
    def test_edge_without_status_flip_is_not_ready(self):
        """``superseded_by`` set but status left ``approved`` — still not ready.

        Concrete scenario: an operator adds the typed edge migrating an item to
        another roadmap and forgets the paired ``status: superseded``. Pre-fix,
        ready_items still scheduled it and the run duplicated work the
        successor item owns.
        """
        roadmap = Roadmap(
            schema_version=1,
            roadmap_id="alpha",
            source_proposal="p.md",
            items=[
                _item(
                    "ri-01",
                    status=ItemStatus.APPROVED,
                    superseded_by=["beta:ri-09"],
                ),
                _item("ri-02", status=ItemStatus.APPROVED),
            ],
            status=RoadmapStatus.APPROVED,
        )
        ready = {i.item_id for i in roadmap.ready_items()}
        assert ready == {"ri-02"}

    def test_plain_approved_item_still_ready(self):
        """The new guard must not withhold ordinary items."""
        roadmap = Roadmap(
            schema_version=1,
            roadmap_id="alpha",
            source_proposal="p.md",
            items=[_item("ri-01", status=ItemStatus.APPROVED)],
            status=RoadmapStatus.APPROVED,
        )
        assert [i.item_id for i in roadmap.ready_items()] == ["ri-01"]


# ---------------------------------------------------------------------------
# null-valued YAML keys must not drop a whole roadmap
# ---------------------------------------------------------------------------
class TestNullEdgeCoercion:
    @pytest.mark.parametrize("field", ["external_depends_on", "superseded_by"])
    def test_explicit_null_coerces_to_empty_list(self, field: str):
        """``external_depends_on:`` with no value parses as None in YAML.

        Pre-fix ``list(None)`` raised TypeError inside ``from_dict``; the
        tolerant sibling loader swallowed it, so a single blank value silently
        removed the entire workspace from cross-roadmap resolution.
        """
        data = {
            "item_id": "ri-01",
            "title": "Item",
            "status": "approved",
            "priority": 1,
            "effort": "M",
            "depends_on": [],
            field: None,
        }
        item = RoadmapItem.from_dict(data)
        assert getattr(item, field) == []


# ---------------------------------------------------------------------------
# strict loader surfaces what the tolerant one hides
# ---------------------------------------------------------------------------
class TestStrictLoader:
    def test_unparseable_roadmap_is_reported(self, tmp_path: Path):
        _write_roadmap(tmp_path, "good", [_item("ri-01")])
        bad = tmp_path / "openspec" / "roadmaps" / "bad" / "roadmap.yaml"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("this: [is not: a roadmap\n")

        roadmaps, errors = load_all_roadmaps_strict(tmp_path)
        assert "good" in roadmaps
        assert any("bad" in e for e in errors), errors

    def test_duplicate_roadmap_id_is_reported(self, tmp_path: Path):
        """Two directories declaring the same roadmap_id must not silently
        collapse — last-writer-wins discards one workspace's items entirely."""
        for dirname in ("alpha", "alpha-copy"):
            roadmap = Roadmap(
                schema_version=1,
                roadmap_id="alpha",  # same declared id, different directory
                source_proposal="p.md",
                items=[_item("ri-01")],
                status=RoadmapStatus.APPROVED,
            )
            path = tmp_path / "openspec" / "roadmaps" / dirname / "roadmap.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.dump(roadmap.to_dict(), sort_keys=False))

        _roadmaps, errors = load_all_roadmaps_strict(tmp_path)
        assert any("roadmap_id" in e and "alpha" in e for e in errors), errors

    def test_clean_repo_reports_no_errors(self, tmp_path: Path):
        _write_roadmap(tmp_path, "alpha", [_item("ri-01")])
        roadmaps, errors = load_all_roadmaps_strict(tmp_path)
        assert set(roadmaps) == {"alpha"}
        assert errors == []
