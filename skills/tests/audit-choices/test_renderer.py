"""Tests for the choices.md renderer (skills/audit-choices/scripts/choices_ledger.py).

Design D2 (renderer is pure Python, renders from choices.json only).
Spec: skill-workflow.4 (Least-confident-first ranking).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "skills" / "audit-choices" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import choices_ledger  # noqa: E402


def _header():
    return choices_ledger.make_header(
        now=datetime(2026, 8, 21, tzinfo=timezone.utc), git_sha="a" * 40, run_id="run-001"
    )


def _entry(confidence, verdict, choice="A choice", self_reported=True, session_log_ref=None):
    return choices_ledger.Entry(
        choice=choice,
        scenario="WHEN X THEN Y instead of Z.",
        gap="The spec left this unspecified.",
        reach="Constrains future callers.",
        verdict=verdict,
        verdict_rationale="Because reasons.",
        confidence=confidence,
        provenance=choices_ledger.Provenance(commits=["abc1234"], files=["f.py"]),
        self_reported=self_reported,
        session_log_ref=session_log_ref if self_reported else None,
    ).to_dict()


def _doc(entries):
    return choices_ledger.build_document(
        header=_header(),
        change_id="my-change",
        audited_range={"base_sha": "b" * 40, "head_sha": "c" * 40},
        entries=entries,
    )


class TestRanking:
    def test_ranking_ascending_confidence(self):
        entries = [
            _entry("high", "sound", choice="High sound"),
            _entry("low", "sound", choice="Low sound"),
            _entry("medium", "sound", choice="Medium sound"),
        ]
        ranked = choices_ledger.rank_entries(entries)
        confidences = [e["confidence"] for e in ranked]
        assert confidences == ["low", "medium", "high"]

    def test_no_entry_precedes_one_of_strictly_lower_confidence(self):
        entries = [
            _entry("high", "sound", choice="A"),
            _entry("low", "needs-user", choice="B"),
            _entry("medium", "unsound", choice="C"),
            _entry("low", "sound", choice="D"),
            _entry("high", "needs-user", choice="E"),
        ]
        ranked = choices_ledger.rank_entries(entries)
        rank_order = {"low": 0, "medium": 1, "high": 2}
        for i in range(len(ranked)):
            for j in range(i + 1, len(ranked)):
                assert rank_order[ranked[i]["confidence"]] <= rank_order[ranked[j]["confidence"]], (
                    f"entry at {i} ({ranked[i]['confidence']}) precedes a strictly "
                    f"lower-confidence entry at {j} ({ranked[j]['confidence']})"
                )

    def test_equal_confidence_orders_needs_user_before_unsound_before_sound(self):
        entries = [
            _entry("medium", "sound", choice="Sound"),
            _entry("medium", "unsound", choice="Unsound"),
            _entry("medium", "needs-user", choice="NeedsUser"),
        ]
        ranked = choices_ledger.rank_entries(entries)
        verdicts = [e["verdict"] for e in ranked]
        assert verdicts == ["needs-user", "unsound", "sound"]


class TestRenderMarkdown:
    def test_includes_every_required_entry_field(self):
        entry = _entry("low", "needs-user", choice="Retry budget choice", self_reported=True,
                        session_log_ref="my-change#D1")
        md = choices_ledger.render_markdown(_doc([entry]))
        assert "Retry budget choice" in md
        assert "WHEN X THEN Y instead of Z." in md
        assert "The spec left this unspecified." in md
        assert "Constrains future callers." in md
        assert "needs-user" in md
        assert "Because reasons." in md
        assert "low" in md
        assert "abc1234" in md
        assert "f.py" in md
        assert "my-change#D1" in md

    def test_not_self_reported_marker_present_when_false(self):
        entry = _entry("high", "sound", choice="Unreported choice", self_reported=False)
        md = choices_ledger.render_markdown(_doc([entry]))
        assert "Not self-reported" in md
        assert "session-log.md" in md

    def test_render_is_pure_and_deterministic(self):
        entries = [_entry("low", "needs-user", choice="X")]
        doc = _doc(entries)
        md1 = choices_ledger.render_markdown(doc)
        md2 = choices_ledger.render_markdown(doc)
        assert md1 == md2

    def test_empty_entries_renders_without_error(self):
        md = choices_ledger.render_markdown(_doc([]))
        assert "my-change" in md
