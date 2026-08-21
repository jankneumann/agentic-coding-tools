"""ri-17 follow-up: the repo-wide validator must not fail open.

Two gaps in ``validate_cross_roadmap`` as shipped:

* it loaded siblings through the tolerant ``load_all_roadmaps``, so a roadmap
  that failed to parse — or one whose ``roadmap_id`` collided with another —
  vanished from the graph, and every check below (ref resolution, cycles,
  duplicate change_id) then reported clean for a repo it had not fully read;
* its duplicate-``change_id`` check deliberately deduplicated *within* a
  roadmap before comparing across roadmaps, so two items in one roadmap
  claiming the same ``change_id`` were reported by nothing at all —
  ``validate_roadmap`` does not check ``change_id`` either.

A ``change_id`` names exactly one OpenSpec change directory, so two items
claiming it means one change's completion silently satisfies both.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from decomposer import validate_cross_roadmap  # type: ignore[import-untyped]


def _item(item_id: str, **kwargs) -> dict:
    item = {
        "item_id": item_id,
        "title": f"Item {item_id}",
        "status": "approved",
        "priority": 1,
        "effort": "M",
        "depends_on": [],
        "acceptance_outcomes": ["measurable outcome"],
    }
    item.update(kwargs)
    return item


def _write(repo_root: Path, dirname: str, roadmap_id: str, items: list[dict]) -> None:
    path = repo_root / "openspec" / "roadmaps" / dirname / "roadmap.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            {
                "schema_version": 1,
                "roadmap_id": roadmap_id,
                "source_proposal": f"openspec/roadmaps/{dirname}/proposal.md",
                "status": "approved",
                "items": items,
            },
            sort_keys=False,
        )
    )


class TestDuplicateChangeId:
    def test_same_change_id_twice_in_one_roadmap_is_reported(self, tmp_path: Path):
        """The intra-roadmap case, which no validator caught before.

        Failure scenario: ri-03 and ri-09 both claim ``add-thing``. Autopilot
        completes ri-03 and archives the change; ri-09's archive cross-check
        then sees its change already archived and skips real work.
        """
        _write(
            tmp_path,
            "alpha",
            "alpha",
            [
                _item("ri-01", change_id="add-thing"),
                _item("ri-02", change_id="add-thing"),
            ],
        )
        errors = validate_cross_roadmap(tmp_path)
        assert any("add-thing" in e and "alpha" in e for e in errors), errors

    def test_cross_roadmap_duplicate_still_reported(self, tmp_path: Path):
        _write(tmp_path, "alpha", "alpha", [_item("ri-01", change_id="shared")])
        _write(tmp_path, "beta", "beta", [_item("ri-01", change_id="shared")])
        errors = validate_cross_roadmap(tmp_path)
        assert any("shared" in e and "multiple roadmaps" in e for e in errors), errors

    def test_distinct_change_ids_are_clean(self, tmp_path: Path):
        _write(
            tmp_path,
            "alpha",
            "alpha",
            [_item("ri-01", change_id="a"), _item("ri-02", change_id="b")],
        )
        assert validate_cross_roadmap(tmp_path) == []


class TestLoaderFailuresSurface:
    def test_unparseable_sibling_is_an_error_not_a_silent_skip(self, tmp_path: Path):
        """Pre-fix this returned [] — a clean bill of health for a repo whose
        second roadmap the validator never managed to read."""
        _write(tmp_path, "alpha", "alpha", [_item("ri-01")])
        bad = tmp_path / "openspec" / "roadmaps" / "bad" / "roadmap.yaml"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("items: [unclosed\n")

        errors = validate_cross_roadmap(tmp_path)
        assert any("bad" in e for e in errors), errors

    def test_duplicate_roadmap_id_is_an_error(self, tmp_path: Path):
        _write(tmp_path, "alpha", "alpha", [_item("ri-01")])
        _write(tmp_path, "alpha-fork", "alpha", [_item("ri-02")])
        errors = validate_cross_roadmap(tmp_path)
        assert any("roadmap_id" in e for e in errors), errors
