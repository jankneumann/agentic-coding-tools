"""Read-only helper: next ready PR from a durable merge plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from merge_plan import validate_plan


def next_ready_pr(plan: dict[str, Any], *, after: int | None = None) -> int | None:
    """Return the first pending node whose dependencies are all merged.

    Node order in the plan is the tie-break. ``after`` (or ``last_merged_pr``)
    is recorded for resume after compact; it does not skip still-pending
    earlier nodes that became ready.
    """

    validate_plan(plan)
    merged = {
        node["pr"]
        for node in plan["nodes"]
        if node["state"]["outcome"] == "merged"
    }
    _ = after if after is not None else plan.get("last_merged_pr")
    for node in plan["nodes"]:
        if node["state"]["outcome"] != "pending":
            continue
        deps = node["definition"]["depends_on"]
        if all(dep in merged for dep in deps):
            return int(node["pr"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--after", type=int, default=None)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    ready = next_ready_pr(plan, after=args.after)
    print(json.dumps({"ready_pr": ready}))
    return 0 if ready is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
