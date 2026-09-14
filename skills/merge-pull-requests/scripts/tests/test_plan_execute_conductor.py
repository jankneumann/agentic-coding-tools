"""Integration: classify → next_node → delegation → cheap-path merge stub."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_plan import build_plan  # noqa: E402
from execute_plan import _delegation_commands, execute_node  # noqa: E402
from merge_plan import validate_plan  # noqa: E402
from next_node import next_ready_pr  # noqa: E402
from plan_storage import FilePlanStore  # noqa: E402
from test_execute_plan import dependencies, passing_status  # noqa: E402


def test_three_node_kinds_through_classify_next_delegate_cheap_merge(tmp_path: Path) -> None:
    prs = [
        {
            "number": 1,
            "title": "Plan only",
            "branch": "openspec/add-docs",
            "origin": "openspec",
            "ci_state": "clean",
        },
        {
            "number": 2,
            "title": "Implementation",
            "branch": "openspec/add-code",
            "origin": "openspec",
            "ci_state": "clean",
        },
        {
            "number": 3,
            "title": "Bump",
            "branch": "dependabot/pip/x",
            "origin": "dependabot",
            "ci_state": "clean",
        },
    ]
    staleness = {
        1: {
            "staleness": "fresh",
            "pr_files": ["openspec/changes/add-docs/proposal.md"],
        },
        2: {
            "staleness": "fresh",
            "pr_files": ["skills/foo/SKILL.md"],
        },
        3: {"staleness": "fresh", "pr_files": ["requirements.txt"]},
    }
    comments = {1: {"unresolved_count": 0}, 2: {"unresolved_count": 0}, 3: {"unresolved_count": 0}}
    plan = build_plan(prs, staleness, comments, generated_at="2026-09-10T00:00:00+00:00")
    validate_plan(plan)
    nodes = {node["pr"]: node for node in plan["nodes"]}
    assert nodes[1]["definition"]["kind"] == "plan"
    assert nodes[1]["definition"]["remediation_skill"] == "iterate-on-plan"
    assert nodes[2]["definition"]["kind"] == "implementation"
    assert nodes[2]["definition"]["remediation_skill"] == "iterate-on-implementation"
    assert nodes[3]["definition"]["kind"] == "automation"
    assert nodes[3]["definition"]["remediation_skill"] == "none"

    assert next_ready_pr(plan) == 1
    assert _delegation_commands(nodes[1], "openspec/add-docs") == [
        "/iterate-on-plan add-docs --vendor-review"
    ]
    assert _delegation_commands(nodes[2], "openspec/add-code") == [
        "/iterate-on-implementation add-code --vendor-review"
    ]

    path = tmp_path / "merge-plan.json"
    store = FilePlanStore(path)
    store.save(plan)
    loaded = store.load()
    loaded["nodes"][0]["state"]["outcome"] = "merged"
    loaded["nodes"][1]["state"]["outcome"] = "merged"
    store.save(loaded)
    assert next_ready_pr(store.load()) == 3

    result = execute_node(
        path,
        3,
        dependencies=dependencies(
            get_live_status=lambda _pr: passing_status(),
            review_vendor=lambda *_a: (_ for _ in ()).throw(
                AssertionError("cheap path must not review")
            ) if False else {"eligibility": {"eligible": False, "reason": "skip"}, "consensus": None},
        ),
    )
    assert result["outcome"] == "merged"
    assert FilePlanStore(path).load()["compact_requested"] is True
