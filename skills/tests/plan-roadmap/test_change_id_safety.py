"""change_id must be safe as a single path component.

change_id is optional in roadmap.yaml, so its value can come from a hand edit
or a model. It flows unmodified into repo_root/openspec/changes/<id>, so an
explicit '../../../escaped' wrote outside the repository entirely.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from models import Effort, ItemStatus, Roadmap, RoadmapItem, RoadmapStatus
from scaffolder import scaffold_change, validate_change_id


def _roadmap_with_change_id(change_id: str) -> Roadmap:
    item = RoadmapItem(
        item_id="ri-01", title="X", status=ItemStatus.CANDIDATE,
        priority=1, effort=Effort.M, depends_on=[], acceptance_outcomes=["o"],
    )
    item.change_id = change_id
    return Roadmap(
        schema_version=1, roadmap_id="r", source_proposal="p.md",
        items=[item], status=RoadmapStatus.PLANNING,
    )


@pytest.mark.parametrize(
    "bad",
    [
        "../../../escaped",
        "..",
        "a/b",
        "/absolute",
        ".hidden",
        "",
        "UPPER",
        "has space",
        "trailing/",
    ],
)
def test_unsafe_ids_rejected(bad: str):
    assert validate_change_id(bad) is not None


@pytest.mark.parametrize(
    "good",
    [
        "gate-drift-with-mirrors-hooks-and-blocking-ci",
        "adopt-opsx-1.0-workflow",  # a real archived change-id uses a dot
        "ri-01",
        "a",
    ],
)
def test_safe_ids_accepted(good: str):
    assert validate_change_id(good) is None


def test_scaffold_refuses_to_escape_repo_root(tmp_path: Path):
    roadmap = _roadmap_with_change_id("../../../escaped")
    with pytest.raises(ValueError, match="traverse directories"):
        scaffold_change(roadmap, tmp_path, "ri-01")
    # Nothing was written anywhere under the repo root either.
    assert not (tmp_path / "openspec").exists()


def test_scaffold_stays_inside_repo_root_for_valid_id(tmp_path: Path):
    roadmap = _roadmap_with_change_id("legit-change")
    created = scaffold_change(roadmap, tmp_path, "ri-01")
    assert created.resolve().is_relative_to(tmp_path.resolve())
