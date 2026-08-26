#!/usr/bin/env python3
"""Build a durable merge plan from analysis-round JSON outputs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from merge_plan import validate_plan
from merge_pr import get_default_strategy


AUTO_EXECUTABLE_ORIGINS = frozenset({"dependabot", "renovate"})
CI_STATE_MAP = {
    "passing": "clean",
    "success": "clean",
    "pending": "unstable",
    "failed": "blocked",
    "failure": "blocked",
    "error": "dirty",
}


def _lookup(records: dict[int, dict[str, Any]], pr_number: int) -> dict[str, Any]:
    return records.get(pr_number, {})


def _ci_state(pr: dict[str, Any]) -> str:
    raw = str(pr.get("ci_state") or pr.get("check_summary") or "unknown").lower()
    if raw in {"clean", "unstable", "blocked", "dirty", "unknown"}:
        return raw
    return CI_STATE_MAP.get(raw, "unknown")


def _execution_policy(pr: dict[str, Any], origin: str) -> tuple[bool, list[str]]:
    """Derive a safe execution policy instead of trusting caller flags."""

    supplied = list(pr.get("gates") or [])
    if origin == "openspec":
        gates = ["proposal_acceptance"]
        gates.extend(gate for gate in supplied if gate != "proposal_acceptance")
        return False, gates

    requested_auto = pr.get("auto_executable")
    auto_executable = (
        origin in AUTO_EXECUTABLE_ORIGINS
        and requested_auto is not False
        and not supplied
    )
    if auto_executable:
        return True, []
    return False, supplied or ["required_review"]


def _has_dependency_path(
    dependencies: dict[int, set[int]],
    start: int,
    target: int,
) -> bool:
    pending = list(dependencies[start])
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(dependencies[current])
    return False


def _derive_dependencies(
    prs: list[dict[str, Any]],
    changed_files: dict[int, set[str]],
) -> dict[int, list[int]]:
    numbers = [int(pr["number"]) for pr in prs]
    dependencies: dict[int, set[int]] = {number: set() for number in numbers}
    branch_to_pr = {
        str(pr.get("branch", "")): int(pr["number"])
        for pr in prs
        if pr.get("branch")
    }

    for pr in prs:
        number = int(pr["number"])
        base_pr = branch_to_pr.get(str(pr.get("base_branch", "")))
        if base_pr is not None and base_pr != number:
            dependencies[number].add(base_pr)

    for index, earlier in enumerate(numbers):
        for later in numbers[index + 1 :]:
            if not changed_files[earlier].intersection(changed_files[later]):
                continue
            if _has_dependency_path(dependencies, earlier, later):
                continue
            dependencies[later].add(earlier)

    return {number: sorted(values) for number, values in dependencies.items()}


def build_plan(
    prs: Iterable[dict[str, Any]],
    staleness_by_pr: dict[int, dict[str, Any]],
    comments_by_pr: dict[int, dict[str, Any]],
    *,
    generated_at: str | None = None,
    storage_tier: str = "file",
) -> dict[str, Any]:
    """Join analysis outputs and derive a deterministic dependency DAG."""

    pr_list = list(prs)
    changed_files = {
        int(pr["number"]): set(
            _lookup(staleness_by_pr, int(pr["number"])).get("pr_files", [])
            or pr.get("changed_files", []),
        )
        for pr in pr_list
    }
    dependencies = _derive_dependencies(pr_list, changed_files)
    base_branch = next(
        (
            str(pr.get("default_branch"))
            for pr in pr_list
            if pr.get("default_branch")
        ),
        "main",
    )

    nodes = []
    for pr in pr_list:
        number = int(pr["number"])
        origin = str(pr.get("origin", "other"))
        staleness = _lookup(staleness_by_pr, number)
        comments = _lookup(comments_by_pr, number)
        auto_executable, gates = _execution_policy(pr, origin)
        nodes.append(
            {
                "pr": number,
                "title": str(pr.get("title", "")),
                "origin": origin,
                "strategy": str(
                    pr.get("strategy") or get_default_strategy(origin),
                ),
                "auto_executable": auto_executable,
                "definition": {
                    "depends_on": dependencies[number],
                    "gates": gates,
                    "changed_files": sorted(changed_files[number]),
                },
                "state": {
                    "outcome": "pending",
                    "needs_revalidation": False,
                    "claimed_by": None,
                    "staleness": str(staleness.get("staleness", "unknown")),
                    "ci_state": _ci_state(pr),
                    "unresolved_comments": int(
                        comments.get("unresolved_count", 0),
                    ),
                    "unresolved_comment_summary": None,
                    "vendor_verdict": None,
                    "blocking_reason": None,
                },
            },
        )

    plan = {
        "schema_version": "1.0",
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat(),
        "storage_tier": storage_tier,
        "base_branch": base_branch,
        "nodes": nodes,
    }
    validate_plan(plan)
    return plan


def write_plan(plan: dict[str, Any], destination: Path) -> None:
    """Validate and atomically persist a plan."""

    validate_plan(plan)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def _replace_bundle_member(source: Path, destination: Path) -> None:
    """Replace one prepared bundle member; split out for fault injection."""

    source.replace(destination)


def write_plan_bundle(plan: dict[str, Any], destination: Path) -> Path:
    """Persist JSON plus Markdown with JSON as the recoverable commit marker.

    Two filesystem paths cannot be renamed atomically as a pair.  Prepare both,
    publish the projection first, and publish the authoritative JSON last.  A
    crash between renames can leave only the projection ahead; ``FilePlanStore``
    repairs that projection from the authoritative JSON on its next load.
    """

    from render_plan import render_plan

    validate_plan(plan)
    destination.parent.mkdir(parents=True, exist_ok=True)
    projection = destination.with_suffix(".md")
    json_temporary = destination.with_suffix(destination.suffix + ".tmp")
    markdown_temporary = projection.with_suffix(projection.suffix + ".tmp")
    json_temporary.write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        markdown_temporary.write_text(render_plan(plan), encoding="utf-8")
        _replace_bundle_member(markdown_temporary, projection)
        _replace_bundle_member(json_temporary, destination)
    finally:
        json_temporary.unlink(missing_ok=True)
        markdown_temporary.unlink(missing_ok=True)
    return projection


def emit_plan(plan: dict[str, Any], destination: Path) -> Path:
    """Persist the authoritative JSON and its human-readable projection."""

    return write_plan_bundle(plan, destination)


def _load_records(path: Path, *, key: str) -> dict[int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return {int(number): value for number, value in payload.items()}
    return {int(item[key]): item for item in payload}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prs", required=True, type=Path)
    parser.add_argument("--staleness", required=True, type=Path)
    parser.add_argument("--comments", required=True, type=Path)
    parser.add_argument("--output", default=Path("merge-plan.json"), type=Path)
    args = parser.parse_args()

    prs = json.loads(args.prs.read_text(encoding="utf-8"))
    staleness = _load_records(args.staleness, key="pr_number")
    comments = _load_records(args.comments, key="pr_number")
    plan = build_plan(prs, staleness, comments)
    projection = emit_plan(plan, args.output)
    print(
        json.dumps(
            {
                "plan": str(args.output),
                "projection": str(projection),
                "nodes": len(plan["nodes"]),
            },
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
