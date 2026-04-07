#!/usr/bin/env python3
"""Migrate beads issues from .beads/issues.jsonl to coordinator work_queue.

One-time migration script. Reads beads JSONL format and creates coordinator
issues via the IssueService.

Usage:
    python3 scripts/migrate_beads_to_coordinator.py [--dry-run]
"""

import asyncio
import json
import sys
from pathlib import Path


# Beads priority (0-4) → coordinator priority (1-10)
# 0→1, 1→3, 2→5, 3→7, 4→9
def map_priority(beads_priority: int) -> int:
    return beads_priority * 2 + 1


# Beads status → coordinator status
STATUS_MAP = {
    "open": "pending",
    "in_progress": "running",
    "closed": "completed",
    "blocked": "pending",  # blocked is computed, not stored
}


async def migrate(jsonl_path: Path, *, dry_run: bool = False) -> None:
    issues = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                issues.append(json.loads(line))

    print(f"Found {len(issues)} beads issues to migrate")

    if not dry_run:
        # Import here so dry-run works without coordinator deps
        sys.path.insert(0, str(Path(__file__).parent.parent / "agent-coordinator"))
        from src.db import get_db
        from src.issue_service import IssueService

        service = IssueService(db=get_db())

    for issue in issues:
        priority = map_priority(issue.get("priority", 2))
        status = STATUS_MAP.get(issue.get("status", "open"), "pending")
        labels = issue.get("labels", [])
        issue_type = issue.get("issue_type", "task")

        print(f"  [{issue['id']}] {issue['title']}")
        print(f"    type={issue_type} priority={priority} status={status} labels={labels}")

        if dry_run:
            print("    → (dry run, skipped)")
            continue

        created = await service.create(
            title=issue["title"],
            description=issue.get("description"),
            issue_type=issue_type,
            priority=priority,
            labels=labels,
            assignee=issue.get("owner"),
        )

        # If the issue was closed, close it in coordinator too
        if issue.get("status") == "closed":
            await service.close(
                issue_id=created.id,
                reason=issue.get("close_reason"),
            )

        print(f"    → Created as {created.id}")

    print(f"\nMigration {'preview' if dry_run else 'complete'}: {len(issues)} issues")


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    # Find .beads/issues.jsonl
    repo_root = Path(__file__).parent.parent
    jsonl_path = repo_root / ".beads" / "issues.jsonl"

    if not jsonl_path.exists():
        print(f"No beads issues found at {jsonl_path}")
        sys.exit(0)

    asyncio.run(migrate(jsonl_path, dry_run=dry_run))


if __name__ == "__main__":
    main()
