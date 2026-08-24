"""change_id uniqueness validation in validate_roadmap."""

from __future__ import annotations

from pathlib import Path

import yaml
from decomposer import validate_roadmap

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _roadmap(change_ids: list[str | None]) -> dict:
    return {
        "schema_version": 1,
        "roadmap_id": "rm-test",
        "source_proposal": "docs/proposals/test.md",
        "status": "planning",
        "policy": {"default_action": "wait_if_budget_exceeded"},
        "items": [
            {
                "item_id": f"ri-{n:02d}",
                "title": f"Item {n}",
                "status": "candidate",
                "priority": 1,
                "effort": "M",
                "depends_on": [],
                "acceptance_outcomes": [f"Outcome for item {n} is observable."],
                **({"change_id": cid} if cid else {}),
            }
            for n, cid in enumerate(change_ids, start=1)
        ],
    }


def test_duplicate_change_id_is_an_error():
    errors = validate_roadmap(_roadmap(["dupe", "dupe"]), _REPO_ROOT)
    assert any("change_id 'dupe'" in e for e in errors)


def test_distinct_change_ids_pass():
    assert validate_roadmap(_roadmap(["a", "b"]), _REPO_ROOT) == []


def test_absent_change_ids_still_valid():
    """Roadmaps predating the field must not fail retroactively."""
    assert validate_roadmap(_roadmap([None, None]), _REPO_ROOT) == []


def test_existing_repo_roadmaps_still_validate():
    """Three of the six committed roadmaps carry no change_id at all."""
    for path in sorted((_REPO_ROOT / "openspec" / "roadmaps").glob("*/roadmap.yaml")):
        data = yaml.safe_load(path.read_text())
        assert validate_roadmap(data, _REPO_ROOT) == [], f"{path} regressed"
