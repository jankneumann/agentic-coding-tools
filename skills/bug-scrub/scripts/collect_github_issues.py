"""Collect the open GitHub issue inventory for bug-scrub reports."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from models import SourceResult

_SOURCE = "github-issues"
_LIMIT = 1000


def collect(project_dir: str) -> SourceResult:
    """List all open issues without treating them as new bug findings."""
    if shutil.which("gh") is None:
        return SourceResult(source=_SOURCE, status="skipped", messages=["gh not found on PATH"])

    command = [
        "gh",
        "issue",
        "list",
        "--state",
        "open",
        "--limit",
        str(_LIMIT),
        "--json",
        "number,title,url,labels",
    ]
    start = time.monotonic()
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, cwd=project_dir, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return SourceResult(
            source=_SOURCE,
            status="error",
            duration_ms=int((time.monotonic() - start) * 1000),
            messages=[f"GitHub issue listing failed: {exc}"],
        )
    duration = int((time.monotonic() - start) * 1000)
    if result.returncode != 0:
        return SourceResult(
            source=_SOURCE,
            status="error",
            duration_ms=duration,
            messages=[result.stderr.strip() or "gh issue list failed"],
        )
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            raise ValueError("expected a list")
        if len(data) >= _LIMIT:
            raise ValueError(
                f"issue listing reached the {_LIMIT} issue limit; inventory may be incomplete"
            )
        inventory = []
        for issue in data:
            number = int(issue["number"])
            title = str(issue["title"])
            url = str(issue["url"])
            labels = [str(label["name"]) for label in issue["labels"]]
            inventory.append({"number": number, "title": title, "url": url, "labels": labels})
    except (KeyError, TypeError, ValueError) as exc:
        return SourceResult(
            source=_SOURCE,
            status="error",
            duration_ms=duration,
            messages=[f"Invalid GitHub issue listing: {exc}"],
        )
    return SourceResult(
        source=_SOURCE,
        status="ok",
        inventory=inventory,
        duration_ms=duration,
        messages=[f"Listed {len(inventory)} open GitHub issues"],
    )
