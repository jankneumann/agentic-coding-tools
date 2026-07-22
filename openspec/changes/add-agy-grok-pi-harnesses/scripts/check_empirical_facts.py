#!/usr/bin/env python3
"""Gate for wp-empirical: prove the CLI facts were actually established.

PLAN_REVIEW round 1 (finding C5, confirmed by both claude and codex) rejected the
original gate `! grep -q '| pending |' design.md`. That check passed vacuously —
deleting the table, or writing "unknown"/"n/a", satisfied it without any CLI ever
being invoked. Since the entire config surface is downstream of these facts, a
silently-degraded wp-empirical would propagate guessed flags into agents.yaml,
the eval backends, and the transcript adapters.

This script asserts the stronger property: every fact row exists, carries a
terminal status, and records evidence.

Exit 0 only when all of:
  * exactly the expected fact IDs are present (none deleted, none invented)
  * every row's status is `confirmed` or `refuted` (not pending/unknown/blank)
  * every row has a non-empty evidence cell

Usage:
    python3 check_empirical_facts.py [path/to/design.md]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

EXPECTED_IDS = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"]
TERMINAL = {"confirmed", "refuted"}

# | E1 | fact | consumed by | task | status | evidence |
ROW = re.compile(r"^\|\s*(E\d+)\s*(?:✚)?\s*\|(.*)$")


def parse_rows(text: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        fact_id = m.group(1)
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows[fact_id] = cells
    return rows


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path(
        "openspec/changes/add-agy-grok-pi-harnesses/design.md"
    )
    if not path.is_file():
        print(f"FAIL: {path} not found", file=sys.stderr)
        return 1

    rows = parse_rows(path.read_text())
    problems: list[str] = []

    missing = [i for i in EXPECTED_IDS if i not in rows]
    if missing:
        problems.append(f"fact rows deleted or renamed: {', '.join(missing)}")

    unexpected = [i for i in rows if i not in EXPECTED_IDS]
    if unexpected:
        problems.append(f"unrecognised fact rows: {', '.join(sorted(unexpected))}")

    for fact_id in EXPECTED_IDS:
        cells = rows.get(fact_id)
        if not cells:
            continue
        # cells: [id, fact, consumed_by, task, status, evidence]
        if len(cells) < 6:
            problems.append(f"{fact_id}: row has {len(cells)} columns, expected 6")
            continue
        status = cells[4].strip().strip("*").lower()
        evidence = cells[5].strip()
        if status not in TERMINAL:
            problems.append(
                f"{fact_id}: status is {status!r}; must be 'confirmed' or 'refuted'"
            )
        if not evidence:
            problems.append(
                f"{fact_id}: status {status!r} recorded with no evidence — "
                "record the command run and the relevant output"
            )

    if problems:
        print("FAIL: empirical CLI facts are not established:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(f"OK: all {len(EXPECTED_IDS)} empirical facts confirmed/refuted with evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
