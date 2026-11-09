#!/usr/bin/env python3
"""Render bounded, delimited GitHub issue metadata for supervisor triage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

_MAX_RECORD_BYTES = 2048
_MAX_PAGE_SIZE = 20


def _fit_record(number: int, title: str, labels: list[str]) -> str:
    """Keep each serialized issue below the untrusted-evidence size limit."""
    title = title[:1024]
    labels = [label[:128] for label in labels[:10]]
    while True:
        line = json.dumps(
            {"number": number, "title": title, "labels": labels},
            ensure_ascii=False,
        )
        if len(line.encode("utf-8")) <= _MAX_RECORD_BYTES:
            return line
        if title:
            title = title[: len(title) // 2]
        elif labels:
            labels.pop()
        else:
            raise ValueError("issue metadata cannot fit the evidence limit")


def render_inventory(
    report: dict[str, Any], *, offset: int = 0, limit: int = _MAX_PAGE_SIZE
) -> str:
    """Return a page of issue metadata without the issue-supplied URL field."""
    if offset < 0 or not 1 <= limit <= _MAX_PAGE_SIZE:
        raise ValueError("offset must be nonnegative and limit must be 1..20")
    sources = report.get("source_results")
    if not isinstance(sources, list):
        raise ValueError("bug-scrub report has no source results")
    source = next(
        (
            item
            for item in sources
            if isinstance(item, dict) and item.get("source") == "github-issues"
        ),
        None,
    )
    if source is None:
        raise ValueError("bug-scrub report has no github-issues source")
    if source.get("status") != "ok":
        raise ValueError(f"github-issues source is {source.get('status', 'unavailable')}")
    inventory = source.get("inventory")
    if not isinstance(inventory, list):
        raise ValueError("github-issues inventory is invalid")

    records: list[str] = []
    for item in inventory:
        if not isinstance(item, dict):
            continue
        number = item.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            continue
        title = item.get("title")
        labels = item.get("labels")
        if not isinstance(title, str) or not isinstance(labels, list):
            continue
        records.append(
            _fit_record(number, title, [label for label in labels if isinstance(label, str)])
        )

    lines = ["BEGIN UNTRUSTED GITHUB ISSUE INVENTORY"]
    lines.append(json.dumps({"offset": offset, "total": len(records), "page_size": limit}))
    lines.extend(records[offset : offset + limit])
    lines.append("END UNTRUSTED GITHUB ISSUE INVENTORY")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=_MAX_PAGE_SIZE)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("bug-scrub report must be a JSON object")
        print(render_inventory(report, offset=args.offset, limit=args.limit), end="")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
