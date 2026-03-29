from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from render_report import _render_markdown  # noqa: E402


def test_markdown_includes_commit_sha_metadata() -> None:
    report = {
        "profile": {
            "primary_profile": "python",
            "profiles": ["python"],
            "confidence": "high",
            "signals": ["pyproject.toml"],
        },
        "scanner_results": [],
        "summary": {
            "total_findings": 0,
            "by_severity": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "info": 0,
            },
        },
        "gate": {
            "decision": "PASS",
            "fail_on": "high",
            "triggered_count": 0,
            "reasons": [],
        },
        "findings": [],
    }

    markdown = _render_markdown(
        report,
        run_context={
            "change_id": "add-security-review-skill",
            "commit_sha": "abc123",
            "timestamp": "2026-02-20T00:00:00+00:00",
        },
    )

    assert "- Commit SHA: abc123" in markdown
