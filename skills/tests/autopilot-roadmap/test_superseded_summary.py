"""ri-17 follow-up: the orchestrator must treat ``superseded`` as terminal.

``_build_summary`` counted COMPLETED / FAILED / BLOCKED / SKIPPED toward
``terminal_count`` but not SUPERSEDED, and gated the "completed" verdict on
``completed_count == total``. A roadmap whose remaining items were all
superseded — exactly the shape this PR created in the symphony roadmap — could
therefore never report completion: there was nothing left to execute, but the
summary called it "partial" on every run.

Both tests fail on the pre-fix tree.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from models import (
    Effort,
    ItemStatus,
    Policy,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
)
from orchestrator import execute_roadmap


def _write_roadmap(workspace: Path, items: list[RoadmapItem]) -> None:
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="test-roadmap",
        source_proposal="test-proposal.md",
        items=items,
        status=RoadmapStatus.APPROVED,
        policy=Policy(),
    )
    (workspace / "roadmap.yaml").write_text(
        yaml.dump(roadmap.to_dict(), default_flow_style=False, sort_keys=False)
    )


def test_completed_plus_superseded_reports_completed(tmp_path: Path):
    """One item to run, one already superseded → the run finishes."""
    _write_roadmap(
        tmp_path,
        [
            RoadmapItem("ri-01", "Runs", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem(
                "ri-02",
                "Moved to another roadmap",
                ItemStatus.SUPERSEDED,
                2,
                Effort.M,
                superseded_by=["other-roadmap:ri-09"],
            ),
        ],
    )

    result = execute_roadmap(tmp_path, dispatch_fn=lambda *_: "success")

    assert result["completed_count"] == 1
    assert result["superseded_count"] == 1
    assert result["status"] == "completed"


def test_all_superseded_reports_completed_not_partial(tmp_path: Path):
    """Nothing left to execute is a finished roadmap, not a stalled one."""
    _write_roadmap(
        tmp_path,
        [
            RoadmapItem(
                "ri-01",
                "Moved",
                ItemStatus.SUPERSEDED,
                1,
                Effort.S,
                superseded_by=["other-roadmap:ri-01"],
            ),
        ],
    )

    result = execute_roadmap(tmp_path, dispatch_fn=lambda *_: "success")

    assert result["superseded_count"] == 1
    assert result["status"] == "completed"
