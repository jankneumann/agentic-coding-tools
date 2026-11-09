"""--check-freshness exit codes and output (design D6)."""
from __future__ import annotations

import io
import shutil
from datetime import datetime, timezone
from pathlib import Path

from archetype_roster import clear_archetypes_raw_cache
from report import sha256_file
from skill_audit import EvidenceInputs, audit_skill, check_freshness, main

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SKILLS = FIXTURES / "skills"
ROSTER = FIXTURES / "archetypes.yaml"
NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)


class Stub:
    def classify(self, skill, sections, model):
        return {s.section_id: "teaching" for s in sections}


class NoBridge:
    def try_recall(self, **kwargs):
        return {"status": "skipped", "reason": "coordinator_unreachable"}

    def try_resolve_archetype_for_phase(self, *a, **k):
        return None


def setup_module(module):
    clear_archetypes_raw_cache()


def _audit(tmp_path: Path, roster: Path, skill="all-shaped"):
    return audit_skill(
        skill, skills_root=SKILLS, output_dir=tmp_path / "out", archetypes_path=roster,
        backend=Stub(), bridge=NoBridge(), evidence_inputs=EvidenceInputs(entries=None, reason="stub"), now=NOW,
    )


def test_fresh_audit_passes_the_check(tmp_path):
    _audit(tmp_path, ROSTER)
    out = io.StringIO()
    assert check_freshness(["all-shaped"], output_dir=tmp_path / "out", archetypes_path=ROSTER, out=out) == 0
    assert "fresh" in out.getvalue() and sha256_file(ROSTER) in out.getvalue()


def test_roster_rotation_makes_the_audit_stale(tmp_path):
    roster = tmp_path / "archetypes.yaml"
    shutil.copy(ROSTER, roster)
    old_hash = sha256_file(roster)
    _audit(tmp_path, roster)
    # Rotate the roster: bump a reviewed date and change a model.
    roster.write_text(roster.read_text().replace('reviewed: "2026-09-13"', 'reviewed: "2026-09-16"').replace("economy: haiku", "economy: haiku-next"))
    clear_archetypes_raw_cache()
    new_hash = sha256_file(roster)
    assert new_hash != old_hash
    out = io.StringIO()
    assert check_freshness(["all-shaped"], output_dir=tmp_path / "out", archetypes_path=roster, out=out) == 1
    text = out.getvalue()
    assert old_hash in text and new_hash in text
    assert "2026-09-16" in text and "2026-09-13" in text
    assert "STALE" in text


def test_no_report_is_stale(tmp_path):
    out = io.StringIO()
    assert check_freshness(["all-shaped"], output_dir=tmp_path / "empty", archetypes_path=ROSTER, out=out) == 1
    assert "no report" in out.getvalue()


def test_cli_check_freshness_exit_codes(tmp_path, capsys):
    args = ["all-shaped", "--skills-root", str(SKILLS), "--archetypes", str(ROSTER), "--output-dir", str(tmp_path / "out")]
    assert main(args + ["--check-freshness"], bridge=NoBridge()) == 1
    _audit(tmp_path, ROSTER)
    assert main(args + ["--check-freshness"], bridge=NoBridge()) == 0
    assert main(["--all"] + args[1:] + ["--check-freshness"], bridge=NoBridge()) == 1  # other fixture skills have no report
    captured = capsys.readouterr().out
    assert "mixed: STALE" in captured and "all-shaped: fresh" in captured


def test_newest_report_wins(tmp_path):
    out = tmp_path / "out"
    _audit(tmp_path, ROSTER)
    stale = out / "all-shaped-2026-01-01.md"
    stale.write_text("- archetypes_sha256: " + "0" * 64 + "\n- reviewed_dates: (none)\n")
    assert check_freshness(["all-shaped"], output_dir=out, archetypes_path=ROSTER, out=io.StringIO()) == 0
