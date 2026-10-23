"""Drift guard: the expedite SKILL.md status table must agree with the code.

The code side is observed by *running* each check against fixtures and
collecting the statuses it returns, not by parsing expedite.py source.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

THIS = Path(__file__).resolve()
SCRIPTS_DIR = THIS.parent.parent
SKILL_MD = SCRIPTS_DIR.parent / "SKILL.md"
sys.path.insert(0, str(SCRIPTS_DIR))
import expedite as ex  # noqa: E402

TABLE_HEADER = re.compile(r"^\|\s*Check fail\s*\|\s*Resolution\s*\|")
ROW_CHECK = re.compile(r"^\|\s*`([a-z_]+)`")


# ---------------------------------------------------------------------------
# Code side: observed check -> statuses
# ---------------------------------------------------------------------------


def _registry(repo: Path, *, active: bool) -> None:
    entries = []
    if active:
        now = datetime.now(timezone.utc).isoformat()
        entries.append({
            "change_id": "other", "agent_id": "wp-1",
            "branch": "openspec/other--wp-1", "worktree_path": "/x/other",
            "created_at": now, "last_heartbeat": now, "pinned": False,
        })
    (repo / ".git-worktrees").mkdir(exist_ok=True)
    (repo / ".git-worktrees" / ".registry.json").write_text(
        json.dumps({"version": 1, "entries": entries})
    )


def _validation(path: Path, *, smoke: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Validation Report\n\n## Spec Compliance\n**Status**: pass\n\n"
        f"## Smoke Tests\n**Status**: {smoke}\n\n## Security\n**Status**: pass\n\n"
        "## E2E Tests\n**Status**: pass\n"
    )


def _rework(path: Path, *, action: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    failures = [] if action == "none" else [{
        "scenario_id": "s1",
        "visibility": "holdout" if action == "block-cleanup" else "public",
        "recommended_action": action,
    }]
    path.write_text(json.dumps({
        "failures": failures,
        "summary": {
            "total_failures": len(failures),
            "public_failures": sum(1 for f in failures if f["visibility"] == "public"),
            "holdout_failures": sum(1 for f in failures if f["visibility"] == "holdout"),
            "has_blocking_holdout": action == "block-cleanup",
            "recommended_action": action,
        },
    }))


@pytest.fixture(scope="module")
def observed(tmp_path_factory: pytest.TempPathFactory) -> dict[str, set[str]]:
    """Run expedite() over fixtures covering every branch of every check."""
    seen: dict[str, set[str]] = {}

    def run(**kwargs) -> None:
        repo = tmp_path_factory.mktemp("repo")
        _registry(repo, active=kwargs.pop("active", False))
        change = repo / "openspec" / "changes" / "abc"
        if "smoke" in kwargs:
            _validation(change / "validation-report.md", smoke=kwargs.pop("smoke"))
        if "rework" in kwargs:
            _rework(change / "rework-report.json", action=kwargs.pop("rework"))
        if kwargs.pop("bad_rework", False):
            change.mkdir(parents=True, exist_ok=True)
            (change / "rework-report.json").write_text("{not json")
        for c in ex.expedite("abc", repo, **kwargs).checks:
            seen.setdefault(c.name, set()).add(c.status)

    run()
    run(active=True)
    run(accept_missing_validation="docs-only change")
    run(smoke="pass")
    run(smoke="fail")
    for action in ("none", "defer", "iterate", "revise-spec", "block-cleanup"):
        run(smoke="pass", rework=action)
    run(smoke="pass", bad_rework=True)
    return seen


# ---------------------------------------------------------------------------
# Doc side: SKILL.md table and prose
# ---------------------------------------------------------------------------


def _skill_lines() -> list[str]:
    return SKILL_MD.read_text().splitlines()


def table_rows() -> list[str]:
    lines = _skill_lines()
    start = next(i for i, ln in enumerate(lines) if TABLE_HEADER.match(ln))
    rows = []
    for ln in lines[start + 2:]:  # skip header and |---| separator
        if not ln.startswith("|"):
            break
        rows.append(ln)
    return rows


def table_checks() -> set[str]:
    return {m.group(1) for row in table_rows() if (m := ROW_CHECK.match(row))}


def prose_sentences() -> list[str]:
    """SKILL.md sentences outside fenced code blocks and tables."""
    prose: list[str] = []
    in_fence = False
    for ln in _skill_lines():
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or ln.startswith("|"):
            continue
        prose.append(ln if ln.strip() else "\n")
    text = " ".join(prose)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


# ---------------------------------------------------------------------------
# Drift assertions (design D4)
# ---------------------------------------------------------------------------


def test_table_checks_equal_emitted_checks(observed: dict[str, set[str]]) -> None:
    assert table_checks() == set(observed), (
        "SKILL.md status table and expedite() disagree on check names"
    )


def test_validation_report_no_file_row_present() -> None:
    assert any(
        ROW_CHECK.match(r) and "`validation_report` (no file)" in r
        for r in table_rows()
    )


def test_only_rework_report_can_skip(observed: dict[str, set[str]]) -> None:
    skippers = {name for name, statuses in observed.items() if "skip" in statuses}
    assert skippers == {"rework_report"}


def test_skip_documented_only_for_rework_report() -> None:
    offenders = [s for s in prose_sentences()
                 if "skip" in s and "`rework_report`" not in s]
    assert not offenders, f"skip documented without scoping to rework_report: {offenders}"


def test_missing_validation_report_not_described_as_non_blocking() -> None:
    offenders = [
        s for s in prose_sentences()
        if re.search(r"does not block|non-blocking", s, re.I)
        and re.search(r"validation", s, re.I)
    ]
    assert not offenders, offenders
