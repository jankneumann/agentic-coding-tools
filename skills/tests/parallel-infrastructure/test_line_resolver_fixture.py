"""Line-resolution floor against the labeled review fixture set (D8).

Asserts at least ninety percent of fixture findings carrying an
existing_code snippet resolve to a line_range — see the "Resolution floor
is enforced" scenario in specs/skill-workflow/spec.md. Findings without
existing_code are excluded from the denominator; they were never anchored
to begin with.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from openspec_paths import repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
SCRIPTS = REPO_ROOT / "skills" / "parallel-infrastructure" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import line_resolver  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "review-fixtures"
RESOLUTION_FLOOR = 0.9


def _load_manifest() -> dict:
    return json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))


def test_resolution_rate_meets_the_floor() -> None:
    manifest = _load_manifest()
    total_anchored = 0
    total_resolved = 0
    unresolved: list[str] = []

    for case in manifest["cases"]:
        diff_text = (FIXTURES_DIR / case["diff_file"]).read_text(encoding="utf-8")
        findings = json.loads(
            (FIXTURES_DIR / case["findings_file"]).read_text(encoding="utf-8")
        )["findings"]
        anchored = [f for f in findings if f.get("existing_code")]
        total_anchored += len(anchored)

        resolved, _unanchored_count = line_resolver.resolve_all(findings, diff_text)
        by_id = {f["id"]: f for f in resolved}
        for original in anchored:
            resolved_finding = by_id[original["id"]]
            if resolved_finding.get("line_resolution") != line_resolver.RESOLUTION_UNRESOLVED:
                total_resolved += 1
            else:
                unresolved.append(f"{case['id']}#{original['id']}")

    assert total_anchored >= 8, "fixture set must carry enough anchored findings to measure a floor"
    rate = total_resolved / total_anchored
    assert rate >= RESOLUTION_FLOOR, (
        f"Line resolution rate {rate:.0%} ({total_resolved}/{total_anchored}) "
        f"is below the {RESOLUTION_FLOOR:.0%} floor; unresolved: {unresolved}"
    )


def test_old_side_and_new_side_anchors_both_resolve() -> None:
    """case-3 finding 2 anchors to a removed (old-side) line; case-1 finding 1
    anchors to an added (new-side) line — both resolution paths must work."""
    diff_text = (FIXTURES_DIR / "case-3.diff").read_text(encoding="utf-8")
    findings = json.loads(
        (FIXTURES_DIR / "case-3.findings.json").read_text(encoding="utf-8")
    )["findings"]
    resolved, _ = line_resolver.resolve_all(findings, diff_text)
    old_side = next(f for f in resolved if f["id"] == 2)
    assert old_side["line_resolution"] == line_resolver.RESOLUTION_HUNK_OLD

    diff_text_1 = (FIXTURES_DIR / "case-1.diff").read_text(encoding="utf-8")
    findings_1 = json.loads(
        (FIXTURES_DIR / "case-1.findings.json").read_text(encoding="utf-8")
    )["findings"]
    resolved_1, _ = line_resolver.resolve_all(findings_1, diff_text_1)
    new_side = next(f for f in resolved_1 if f["id"] == 1)
    assert new_side["line_resolution"] == line_resolver.RESOLUTION_HUNK_NEW
