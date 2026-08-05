"""Tests for the evidence locator resolver (R2, design D3).

A locator is ``verified`` when the normalized digest of its source span still
matches, ``drifted`` when the symbol resolves but content changed, and
``unresolvable`` when the file or span is gone. Only ``unresolvable`` is fatal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from verify_locators import (
    DRIFTED,
    UNRESOLVABLE,
    VERIFIED,
    normalized_span_digest,
    resolve_locator,
    verify_handbook,
)

SOURCE = """def claim_task(agent_id):
    row = db.fetch_one()
    return row
"""


def _write_source(tmp_path: Path, text: str = SOURCE) -> Path:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    target = src / "api.py"
    target.write_text(text, encoding="utf-8")
    return target


def _locator(digest: str, *, start: int = 1, end: int = 3) -> dict[str, Any]:
    return {
        "node_id": "py:api.claim_task",
        "file": "src/api.py",
        "span": {"start": start, "end": end},
        "content_digest": digest,
        "role": "execution_path",
    }


def _handbook(locator: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot": {"generated_at": "2026-08-05T00:00:00+00:00", "git_sha": "abc",
                     "handbook_version": "1.0.0"},
        "system_flows": [],
        "behavior_units": [
            {"id": "bh:task-claiming", "title": "Task claiming",
             "responsibility": "claim", "inputs": [], "outputs": [],
             "depends_on": [], "member_nodes": ["py:api.claim_task"]}
        ],
        "unit_details": {
            "bh:task-claiming": {
                "triggers": [], "state_changes": [], "execution_paths": [],
                "exception_paths": [], "evidence": [locator],
            }
        },
        "uncovered": [],
    }


# --------------------------------------------------------------------------- #
# R2 success path
# --------------------------------------------------------------------------- #
def test_all_locators_verify_against_unchanged_tree(tmp_path: Path) -> None:
    _write_source(tmp_path)
    digest = normalized_span_digest(tmp_path / "src/api.py", 1, 3)

    report = verify_handbook(_handbook(_locator(digest)), tmp_path)

    assert report.counts[VERIFIED] == 1
    assert report.counts[DRIFTED] == 0
    assert report.counts[UNRESOLVABLE] == 0
    assert report.exit_code == 0
    assert report.diagnostics.errors == []


def test_verified_locator_produces_no_findings(tmp_path: Path) -> None:
    _write_source(tmp_path)
    digest = normalized_span_digest(tmp_path / "src/api.py", 1, 3)

    report = verify_handbook(_handbook(_locator(digest)), tmp_path)

    locator_findings = [
        d for d in report.diagnostics.items if d.code.startswith("HANDBOOK_LOCATOR")
    ]
    assert locator_findings == []


# --------------------------------------------------------------------------- #
# D3 — normalization: formatting-only churn must not drift
# --------------------------------------------------------------------------- #
def test_trailing_whitespace_change_stays_verified(tmp_path: Path) -> None:
    target = _write_source(tmp_path)
    digest = normalized_span_digest(target, 1, 3)
    target.write_text(SOURCE.replace("    row = db.fetch_one()",
                                     "    row = db.fetch_one()   "), encoding="utf-8")

    status, _ = resolve_locator(_locator(digest), tmp_path)

    assert status == VERIFIED


def test_crlf_line_endings_stay_verified(tmp_path: Path) -> None:
    target = _write_source(tmp_path)
    digest = normalized_span_digest(target, 1, 3)
    target.write_bytes(SOURCE.replace("\n", "\r\n").encode("utf-8"))

    status, _ = resolve_locator(_locator(digest), tmp_path)

    assert status == VERIFIED


# --------------------------------------------------------------------------- #
# R2 failure paths
# --------------------------------------------------------------------------- #
def test_edited_span_is_drifted(tmp_path: Path) -> None:
    target = _write_source(tmp_path)
    digest = normalized_span_digest(target, 1, 3)
    target.write_text(SOURCE.replace("return row", "return row.id"), encoding="utf-8")

    report = verify_handbook(_handbook(_locator(digest)), tmp_path)

    assert report.counts[DRIFTED] == 1
    assert report.exit_code == 0, "drift is a warning, not a failure"
    warn = [d for d in report.diagnostics.warnings if d.code == "HANDBOOK_LOCATOR_DRIFT"]
    assert warn
    assert warn[0].details["behavior_unit"] == "bh:task-claiming"
    assert warn[0].file == "src/api.py"


def test_deleted_file_is_unresolvable(tmp_path: Path) -> None:
    target = _write_source(tmp_path)
    digest = normalized_span_digest(target, 1, 3)
    target.unlink()

    report = verify_handbook(_handbook(_locator(digest)), tmp_path)

    assert report.counts[UNRESOLVABLE] == 1
    assert report.exit_code == 1
    errs = [d for d in report.diagnostics.errors
            if d.code == "HANDBOOK_LOCATOR_UNRESOLVABLE"]
    assert errs
    assert errs[0].details["behavior_unit"] == "bh:task-claiming"


def test_span_beyond_end_of_file_is_unresolvable(tmp_path: Path) -> None:
    _write_source(tmp_path)

    status, _ = resolve_locator(_locator("sha256:whatever", start=90, end=99), tmp_path)

    assert status == UNRESOLVABLE


def test_stale_reason_code_reported_for_drift(tmp_path: Path) -> None:
    target = _write_source(tmp_path)
    digest = normalized_span_digest(target, 1, 3)
    target.write_text(SOURCE.replace("return row", "return None"), encoding="utf-8")

    report = verify_handbook(_handbook(_locator(digest)), tmp_path)

    assert "handbook_locator_drift" in report.stale_reasons


def test_no_stale_reason_when_all_verified(tmp_path: Path) -> None:
    _write_source(tmp_path)
    digest = normalized_span_digest(tmp_path / "src/api.py", 1, 3)

    report = verify_handbook(_handbook(_locator(digest)), tmp_path)

    assert report.stale_reasons == []


# --------------------------------------------------------------------------- #
# CLI wiring
# --------------------------------------------------------------------------- #
def test_cli_writes_diagnostics_and_exits_nonzero_on_unresolvable(tmp_path: Path) -> None:
    from verify_locators import main

    _write_source(tmp_path)
    digest = normalized_span_digest(tmp_path / "src/api.py", 1, 3)
    (tmp_path / "src/api.py").unlink()

    hb_path = tmp_path / "architecture.behaviors.json"
    hb_path.write_text(json.dumps(_handbook(_locator(digest))), encoding="utf-8")
    diag_path = tmp_path / "architecture.diagnostics.json"

    rc = main([
        "--handbook", str(hb_path),
        "--repo-root", str(tmp_path),
        "--diagnostics", str(diag_path),
    ])

    assert rc == 1
    written = json.loads(diag_path.read_text())
    codes = {f["code"] for f in written["findings"]}
    assert "HANDBOOK_LOCATOR_UNRESOLVABLE" in codes


def test_cli_is_a_noop_when_handbook_absent(tmp_path: Path) -> None:
    from verify_locators import main

    rc = main([
        "--handbook", str(tmp_path / "missing.json"),
        "--repo-root", str(tmp_path),
    ])

    assert rc == 0, "absence of a handbook is fresh-by-absence, not an error"
