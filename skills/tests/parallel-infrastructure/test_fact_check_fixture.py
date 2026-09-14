"""Fact-check precision against the labeled review fixture set (D8).

Replays a recorded transcript instead of calling a live model, so this
stays deterministic in CI. See fixtures/review-fixtures/manifest.json for
the labeled cases and design.md D8 for the rationale. The live-model
figure is a separate validation-phase step recorded in validation-report.md.
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

import fact_check  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "review-fixtures"


def _load_manifest() -> dict:
    return json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))


def _load_transcript() -> dict:
    return json.loads(
        (FIXTURES_DIR / "fact-check-transcript.json").read_text(encoding="utf-8")
    )["responses"]


def _run_case(case: dict, transcript: dict) -> tuple[fact_check.FactCheckOutcome, list[dict]]:
    diff_text = (FIXTURES_DIR / case["diff_file"]).read_text(encoding="utf-8")
    findings = json.loads(
        (FIXTURES_DIR / case["findings_file"]).read_text(encoding="utf-8")
    )["findings"]
    recorded = transcript[case["id"]]

    def _stub_caller(_system_prompt: str, _user_prompt: str) -> str:
        return recorded

    outcome = fact_check.run(
        vendor="fixture", round_num=1, findings=findings, packet_diff=diff_text,
        caller=_stub_caller, model="fixture-recorded",
    )
    return outcome, findings


def test_no_labeled_true_finding_is_removed() -> None:
    manifest = _load_manifest()
    transcript = _load_transcript()
    removed_true: list[str] = []

    for case in manifest["cases"]:
        outcome, _findings = _run_case(case, transcript)
        removed_ids = {d.finding_id for d in outcome.decisions if d.verdict == "removed"}
        for label in case["labels"]:
            if label["label"] is True and str(label["finding_id"]) in removed_ids:
                removed_true.append(f"{case['id']}#{label['finding_id']}")

    assert removed_true == [], (
        f"Fact-check removed labeled-true finding(s): {removed_true} "
        "— a true finding must never be removed by the fact-check pass."
    )


def test_at_least_half_of_labeled_false_findings_are_removed() -> None:
    manifest = _load_manifest()
    transcript = _load_transcript()
    total_false = 0
    removed_false = 0

    for case in manifest["cases"]:
        outcome, _findings = _run_case(case, transcript)
        removed_ids = {d.finding_id for d in outcome.decisions if d.verdict == "removed"}
        for label in case["labels"]:
            if label["label"] is False:
                total_false += 1
                if str(label["finding_id"]) in removed_ids:
                    removed_false += 1

    assert total_false >= 5, "fixture set must carry at least ten findings (D8)"
    rate = removed_false / total_false
    assert rate >= 0.5, (
        f"Fact-check removed only {removed_false}/{total_false} "
        f"({rate:.0%}) labeled-false findings; the fixture floor is 50%."
    )


def test_protected_subject_veto_keeps_a_true_finding_despite_removal_attempt() -> None:
    """case-2 finding 3 is labeled true and its off-by-one wording is
    deliberately protected — the transcript still asks to remove it, and the
    veto must keep it regardless (verdict "vetoed", never "removed")."""
    manifest = _load_manifest()
    transcript = _load_transcript()
    case = next(c for c in manifest["cases"] if c["id"] == "case-2")
    outcome, _findings = _run_case(case, transcript)
    decision = next(d for d in outcome.decisions if d.finding_id == "3")
    assert decision.verdict == "vetoed"
    assert decision.vetoed == "protected_subject"


def test_fixture_manifest_has_at_least_ten_labeled_findings() -> None:
    manifest = _load_manifest()
    total = sum(len(case["labels"]) for case in manifest["cases"])
    assert total >= 10
