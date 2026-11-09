"""Tests for the phase-outcome shadow reporting CLI (design D5)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from phase_outcome_shadow_report import (  # noqa: E402
    collect_shadow_entries,
    disagreement_report,
)


def _write_loop_state(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps({"phase_history": entries}))


class TestPhaseOutcomeShadowReport:
    def test_disagreement_rate_over_multiple_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        _write_loop_state(
            f1,
            [
                {"phase": "PHASE_OUTCOME_SHADOW", "acting_outcome": "complete", "judged_outcome": "complete"},
                {"phase": "PHASE_OUTCOME_SHADOW", "acting_outcome": "complete", "judged_outcome": "failed"},
                {"phase": "IMPLEMENT", "outcome": "complete"},  # not a shadow entry
            ],
        )
        _write_loop_state(
            f2,
            [
                {"phase": "PHASE_OUTCOME_SHADOW", "acting_outcome": "failed", "judged_outcome": "failed"},
            ],
        )

        entries = collect_shadow_entries([f1, f2])
        report = disagreement_report(entries)

        assert report["total_transitions"] == 3
        assert report["disagreement_count"] == 1
        assert report["disagreement_rate"] == 1 / 3
        assert report["disagreement_pairs"] == {"complete -> failed": 1}

    def test_no_entries_yields_zero_rate(self, tmp_path: Path) -> None:
        f1 = tmp_path / "empty.json"
        _write_loop_state(f1, [])

        report = disagreement_report(collect_shadow_entries([f1]))

        assert report["total_transitions"] == 0
        assert report["disagreement_rate"] == 0.0

    def test_missing_file_is_skipped_not_raised(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.json"

        assert collect_shadow_entries([missing]) == []
