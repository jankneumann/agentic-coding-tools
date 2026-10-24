"""Drift guard: the expedite SKILL.md status table must agree with the code.

The code side is observed by *running* each check against fixtures and
collecting the statuses it returns, not by parsing expedite.py source.

Each table row claims "this check fails under this condition". SCENARIOS names
one fixture per condition, keyed the way the table row labels it, so the test
can compare the table's rows with the conditions under which the code fails.
A new failing branch in the code needs a new scenario here and a new row.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

THIS = Path(__file__).resolve()
SCRIPTS_DIR = THIS.parent.parent
SKILL_MD = SCRIPTS_DIR.parent / "SKILL.md"
sys.path.insert(0, str(SCRIPTS_DIR))
import expedite as ex  # noqa: E402

TABLE_HEADER = re.compile(r"^\|\s*Check fail\s*\|\s*Resolution\s*\|")
ROW_CHECK = re.compile(r"^\|\s*`([a-z_]+)`")
# "| `check` (condition) | ..." -> check, condition (absent for a bare check)
ROW_CONDITION = re.compile(r"^\|\s*`([a-z_]+)`\s*(?:\(([^)]*)\))?\s*\|")

# (check, condition) -> expedite() fixture for that condition. Conditions under
# which the check does not fail are included too, so a branch that starts
# failing without a table row is caught.
SCENARIOS: dict[tuple[str, str | None], dict] = {
    ("active_agents", None): dict(active=True),
    ("active_agents", "none active"): dict(smoke="pass"),
    ("validation_report", "no file"): {},
    ("validation_report", "no file, override"): dict(
        accept_missing_validation="docs-only change"),
    ("validation_report", "unreadable"): dict(unreadable_validation=True),
    ("validation_report", "hard gate fail"): dict(smoke="fail"),
    ("validation_report", "hard gates pass"): dict(smoke="pass"),
    ("rework_report", "no file"): dict(smoke="pass"),
    ("rework_report", "none"): dict(smoke="pass", rework="none"),
    ("rework_report", "defer"): dict(smoke="pass", rework="defer"),
    ("rework_report", "iterate"): dict(smoke="pass", rework="iterate"),
    ("rework_report", "revise-spec"): dict(smoke="pass", rework="revise-spec"),
    ("rework_report", "block-cleanup"): dict(smoke="pass", rework="block-cleanup"),
    ("rework_report", "load failure"): dict(smoke="pass", bad_rework=True),
    # rework_report.summary_action only derives known actions, so this branch
    # is defensive; reach it with a stubbed loader.
    ("rework_report", "unknown summary_action"): dict(
        smoke="pass", rework="none", unknown_action=True),
}


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
def runs(tmp_path_factory: pytest.TempPathFactory,
         ) -> dict[tuple[str, str | None], dict[str, str]]:
    """Run expedite() once per scenario; map each to its check statuses."""
    results: dict[tuple[str, str | None], dict[str, str]] = {}

    def run(**kwargs) -> dict[str, str]:
        repo = tmp_path_factory.mktemp("repo")
        _registry(repo, active=kwargs.pop("active", False))
        change = repo / "openspec" / "changes" / "abc"
        if "smoke" in kwargs:
            _validation(change / "validation-report.md", smoke=kwargs.pop("smoke"))
        if kwargs.pop("unreadable_validation", False):
            change.mkdir(parents=True, exist_ok=True)
            (change / "validation-report.md").write_bytes(b"\xff\xfe")
        if "rework" in kwargs:
            _rework(change / "rework-report.json", action=kwargs.pop("rework"))
        if kwargs.pop("bad_rework", False):
            change.mkdir(parents=True, exist_ok=True)
            (change / "rework-report.json").write_text("{not json")
        with pytest.MonkeyPatch.context() as mp:
            if kwargs.pop("unknown_action", False):
                mp.setattr(ex.rr, "load_rework_report", lambda _p: SimpleNamespace(
                    summary_action="bogus", total_failures=1, holdout_failures=0))
            checks = ex.expedite("abc", repo, **kwargs).checks
        return {c.name: c.status for c in checks}

    for key, kwargs in SCENARIOS.items():
        results[key] = run(**kwargs)
    return results


@pytest.fixture(scope="module")
def observed(runs: dict[tuple[str, str | None], dict[str, str]],
             ) -> dict[str, set[str]]:
    """Every status each check returned across all scenarios."""
    seen: dict[str, set[str]] = {}
    for statuses in runs.values():
        for name, status in statuses.items():
            seen.setdefault(name, set()).add(status)
    return seen


@pytest.fixture(scope="module")
def failing_conditions(runs: dict[tuple[str, str | None], dict[str, str]],
                       ) -> set[tuple[str, str | None]]:
    """(check, condition) pairs under which that check returned ``fail``."""
    return {(check, cond) for (check, cond), statuses in runs.items()
            if statuses[check] == "fail"}


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


def table_conditions() -> list[tuple[str, str | None]]:
    """(check, condition) per table row, backticks stripped from the condition."""
    pairs = []
    for row in table_rows():
        m = ROW_CONDITION.match(row)
        assert m, f"unparseable SKILL.md table row: {row}"
        cond = m.group(2)
        pairs.append((m.group(1), cond.replace("`", "").strip() if cond else None))
    return pairs


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


def test_table_rows_equal_failing_conditions(
    failing_conditions: set[tuple[str, str | None]],
) -> None:
    rows = table_conditions()
    assert len(rows) == len(set(rows)), f"duplicate SKILL.md table rows: {rows}"
    documented = set(rows)
    assert documented == failing_conditions, (
        "SKILL.md table and expedite() disagree on when a check fails; "
        f"rows that do not fail in code: {sorted(documented - failing_conditions, key=str)}; "
        f"failing conditions with no row: {sorted(failing_conditions - documented, key=str)}"
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
