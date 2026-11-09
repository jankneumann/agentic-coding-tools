"""CLI surface: exit codes, conventions, output files, degradation, wall time."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from archetype_roster import clear_archetypes_raw_cache
from audit_paths import SKILLS_ROOT
from skill_audit import main

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SKILLS = FIXTURES / "skills"
ROSTER = FIXTURES / "archetypes.yaml"
REAL_ROSTER = SKILLS_ROOT.parent / "agent-coordinator" / "archetypes.yaml"


class DownBridge:
    def try_recall(self, **kwargs):
        return {"status": "skipped", "operation": "try_recall", "reason": "coordinator_unreachable", "COORDINATOR_AVAILABLE": False}

    def try_resolve_archetype_for_phase(self, *a, **k):
        return None


class Stub:
    def __init__(self):
        self.calls = 0

    def classify(self, skill, sections, model):
        self.calls += 1
        return {s.section_id: "teaching" for s in sections}


def setup_module(module):
    clear_archetypes_raw_cache()


def _args(skill, tmp_path, *extra):
    return [skill, "--skills-root", str(SKILLS), "--archetypes", str(ROSTER), "--output-dir", str(tmp_path), *extra]


def _drift_rules(tmp_path, skill):
    ledger = json.loads((tmp_path / f"{skill}-findings.json").read_text())
    return {f["evidence"].get("rule") for f in ledger["findings"] if f["kind"] == "convention_drift"}


def test_unknown_skill_and_bad_args_exit_1(tmp_path, capsys):
    assert main(_args("does-not-exist", tmp_path), bridge=DownBridge()) == 1
    assert "unknown skill" in capsys.readouterr().err
    assert main(["--skills-root", str(SKILLS)], bridge=DownBridge()) == 1
    assert main(["mixed", "--all", "--skills-root", str(SKILLS)], bridge=DownBridge()) == 1
    assert main(_args("mixed", tmp_path, "--evidence-window", "0"), bridge=DownBridge()) == 1
    assert main(_args("mixed", tmp_path, "--archetypes", str(tmp_path / "missing.yaml")), bridge=DownBridge()) == 1


def test_single_skill_writes_report_and_ledger(tmp_path, capsys):
    stub = Stub()
    assert main(_args("mixed", tmp_path), backend=stub, bridge=DownBridge()) == 0
    out = capsys.readouterr().out
    assert "mixed:" in out and "report" in out
    assert (tmp_path / "mixed-findings.json").exists()
    assert list(tmp_path.glob("mixed-????-??-??.md"))
    assert stub.calls == 1
    text = next(tmp_path.glob("mixed-????-??-??.md")).read_text()
    assert "- convention: rightsizing" in text


def test_default_convention_is_rightsizing_and_tolerates_missing_triggers(tmp_path):
    # `mixed` has no triggers: key.
    assert main(_args("mixed", tmp_path), backend=Stub(), bridge=DownBridge()) == 0
    ledger = json.loads((tmp_path / "mixed-findings.json").read_text())
    assert ledger["convention"] == "rightsizing"
    assert not any(
        f["kind"] == "convention_drift" and "triggers" in (f.get("rationale") or "")
        for f in ledger["findings"]
    )


def test_current_convention_flags_missing_tail_block(tmp_path):
    assert main(_args("no-tail-block", tmp_path, "--convention", "current"), backend=Stub(), bridge=DownBridge()) == 0
    assert "assert_tail_block_present" in _drift_rules(tmp_path, "no-tail-block")
    text = next(tmp_path.glob("no-tail-block-????-??-??.md")).read_text()
    assert "- convention: current" in text
    # rightsizing treats the tail block as optional.
    assert main(_args("no-tail-block", tmp_path / "rs"), backend=Stub(), bridge=DownBridge()) == 0
    assert "assert_tail_block_present" not in _drift_rules(tmp_path / "rs", "no-tail-block")


def test_current_convention_flags_missing_triggers_key(tmp_path):
    assert main(_args("mixed", tmp_path, "--convention", "current"), backend=Stub(), bridge=DownBridge()) == 0
    assert "assert_required_keys_present" in _drift_rules(tmp_path, "mixed")


def test_rightsizing_flags_oversized_and_nested_references(tmp_path):
    assert main(_args("oversized", tmp_path), backend=Stub(), bridge=DownBridge()) == 0
    assert "max_lines" in _drift_rules(tmp_path, "oversized")
    assert main(_args("nested-references", tmp_path), backend=Stub(), bridge=DownBridge()) == 0
    rules = _drift_rules(tmp_path, "nested-references")
    assert "reference_depth" in rules
    assert "max_lines" not in rules


def test_propose_flag_writes_candidate_work(tmp_path):
    assert main(_args("mixed", tmp_path, "--propose"), backend=Stub(), bridge=DownBridge()) == 0
    stubs = json.loads((tmp_path / "mixed-candidate-work.json").read_text())
    assert stubs and all(s["provenance"]["generator"] == "improve-harness" for s in stubs)


def test_coordinator_down_exits_zero_with_unavailable_evidence(tmp_path):
    assert main(_args("mixed", tmp_path), backend=Stub(), bridge=DownBridge()) == 0
    ledger = json.loads((tmp_path / "mixed-findings.json").read_text())
    assert ledger["evidence"]["status"] == "unavailable"
    text = next(tmp_path.glob("mixed-????-??-??.md")).read_text()
    assert "- evidence: unavailable (coordinator_unreachable)" in text


def test_real_bridge_against_closed_port_exits_zero(tmp_path, monkeypatch):
    for key in ("COORDINATION_API_URL", "COORDINATOR_HTTP_URL", "AGENT_COORDINATOR_API_URL", "AGENT_COORDINATOR_HTTP_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("COORDINATION_API_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("COORDINATION_HTTP_TIMEOUT", "0.5")
    assert main(_args("all-shaped", tmp_path), backend=Stub()) == 0
    ledger = json.loads((tmp_path / "all-shaped-findings.json").read_text())
    assert ledger["evidence"]["status"] == "unavailable"


def test_audit_never_writes_under_the_audited_skill(tmp_path):
    before = sorted(p for p in (SKILLS / "mixed").rglob("*"))
    mtimes = {p: p.stat().st_mtime_ns for p in before}
    assert main(_args("mixed", tmp_path), backend=Stub(), bridge=DownBridge()) == 0
    after = sorted(p for p in (SKILLS / "mixed").rglob("*"))
    assert before == after
    assert all(p.stat().st_mtime_ns == mtimes[p] for p in before)


@pytest.mark.skipif(
    not (SKILLS_ROOT / "quick-task" / "SKILL.md").is_file() or not REAL_ROSTER.is_file() or os.environ.get("SKILL_AUDIT_SKIP_TIMING"),
    reason="committed skill corpus not present",
)
def test_all_wall_time(tmp_path):
    stub = Stub()
    start = time.monotonic()
    rc = main(["--all", "--skills-root", str(SKILLS_ROOT), "--archetypes", str(REAL_ROSTER), "--output-dir", str(tmp_path)], backend=stub, bridge=DownBridge())
    elapsed = time.monotonic() - start
    assert rc == 0
    assert elapsed <= 60, f"--all took {elapsed:.1f}s"
    ledgers = list(tmp_path.glob("*-findings.json"))
    assert len(ledgers) == len(list(SKILLS_ROOT.glob("*/SKILL.md")))
    assert stub.calls <= len(ledgers)
