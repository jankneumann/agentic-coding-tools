"""Report contents: histogram, dispatch profile, tier table, ranked findings, outlines, stamp."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from archetype_roster import clear_archetypes_raw_cache
from report import parse_stamp, rank_findings
from skill_audit import EvidenceInputs, audit_skill

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SKILLS = FIXTURES / "skills"
ROSTER = FIXTURES / "archetypes.yaml"
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
MEMORIES = json.loads((FIXTURES / "evidence" / "memory_response.json").read_text())["memories"]


class NoBridge:
    def try_resolve_archetype_for_phase(self, *a, **k):
        return None


class FixedStub:
    def __init__(self, label="teaching"):
        self.label = label
        self.calls = 0

    def classify(self, skill, sections, model):
        self.calls += 1
        return {s.section_id: self.label for s in sections}


def setup_module(module):
    clear_archetypes_raw_cache()


def _run(tmp_path, skill="mixed", **kw):
    kw.setdefault("evidence_inputs", EvidenceInputs(entries=MEMORIES, reason=None))
    kw.setdefault("bridge", NoBridge())
    return audit_skill(
        skill, skills_root=SKILLS, output_dir=tmp_path, archetypes_path=ROSTER,
        backend=kw.pop("backend", FixedStub()), now=NOW, **kw,
    )


def test_report_has_every_required_section(tmp_path):
    outcome = _run(tmp_path)
    text = outcome.report_path.read_text()
    for heading in (
        "## Layer histogram", "## Dispatch profile", "## Tier failure table", "## Ranked findings",
        "## Proposed lean SKILL.md outline", "## Proposed references/procedure.md outline", "## Freshness stamp",
    ):
        assert heading in text, heading
    stamp = parse_stamp(text)
    assert set(stamp) == {"archetypes_sha256", "reviewed_dates", "evidence_window_days", "generated_at"}
    assert stamp["archetypes_sha256"] == outcome.ledger["freshness"]["archetypes_sha256"]
    assert stamp["reviewed_dates"] == ["2026-08-16", "2026-09-13"]
    assert stamp["evidence_window_days"] == 30
    assert stamp["generated_at"] == "2026-09-16T12:00:00+00:00"
    assert outcome.report_path.name == "mixed-2026-09-16.md"
    assert outcome.ledger_path.name == "mixed-findings.json"


def test_report_header_states_convention_and_evidence(tmp_path):
    text = _run(tmp_path).report_path.read_text()
    assert "- convention: rightsizing" in text
    assert "- evidence: available" in text
    assert "**Cross-source agreement**: 0.0% of findings surfaced in 2+ sources (0/0)" in text
    assert "- evidence_window_days: 30" in text
    assert "- context_cost: n/a" in text


def test_histogram_and_layer_table_reflect_classification(tmp_path):
    outcome = _run(tmp_path)
    text = outcome.report_path.read_text()
    assert "| teaching | 4 |" in text
    assert "| contract | 2 |" in text
    assert "| procedure | 1 |" in text
    assert "`SKILL.md#02-why` | Why | teaching | model |" in text
    assert "`SKILL.md#00-frontmatter` | frontmatter | contract | pre-pass | frontmatter |" in text


def test_outlines_follow_the_layer_table(tmp_path):
    text = _run(tmp_path).report_path.read_text()
    lean = text.split("## Proposed lean SKILL.md outline")[1].split("## Proposed references/procedure.md outline")[0]
    assert "- frontmatter (`contract`)" in lean and "- Run (`contract`)" in lean
    assert "Teaching moved out: Why, Philosophy, Background, Notes" in lean
    assert "references/procedure.md" in lean
    procedure = text.split("## Proposed references/procedure.md outline")[1].split("## Layer table")[0]
    assert "- Steps (3 step(s), from `SKILL.md#06-steps`)" in procedure


def test_tier_table_present_with_zero_rows_when_unavailable(tmp_path):
    outcome = _run(tmp_path, evidence_inputs=EvidenceInputs(entries=None, reason="coordinator_unreachable"))
    text = outcome.report_path.read_text()
    assert "- evidence: unavailable (coordinator_unreachable)" in text
    table = text.split("## Tier failure table")[1].split("**Cross-source")[0]
    assert "| Archetype | Provider | Model |" in table
    assert table.count("\n|") == 2  # header + separator only
    assert outcome.ledger["evidence"] == {"status": "unavailable", "reason": "coordinator_unreachable", "tier_rows": []}


def test_dispatch_profile_rendered_or_explained(tmp_path):
    text = _run(tmp_path).report_path.read_text()
    assert "No dispatch archetypes discovered" in text
    # A lifecycle name resolves through the dispatch map even for a fixture skill body.
    (tmp_path / "skills" / "autopilot").mkdir(parents=True)
    (tmp_path / "skills" / "autopilot" / "SKILL.md").write_text((SKILLS / "all-shaped" / "SKILL.md").read_text())
    outcome = audit_skill(
        "autopilot", skills_root=tmp_path / "skills", output_dir=tmp_path / "out", archetypes_path=ROSTER,
        backend=FixedStub(), bridge=NoBridge(), evidence_inputs=EvidenceInputs(entries=[], reason=None), now=NOW,
    )
    text = outcome.report_path.read_text()
    assert "| architect | frontier | antigravity | gemini-3.8-flash-high | — | goal-directed | frontier |" in text
    assert "| runner | economy | claude_code | haiku | — | verbatim | — |" in text


def test_ranked_findings_put_keep_last_and_tier_first():
    findings = [
        {"id": "F001", "kind": "teaching_inferable", "remediation": "keep"},
        {"id": "F002", "kind": "teaching_inferable", "remediation": "move_to_reference"},
        {"id": "F003", "kind": "tier_concentrated_failure", "remediation": "add_probe"},
        {"id": "F004", "kind": "contract_unpinned", "remediation": "add_probe"},
    ]
    assert [f["id"] for f in rank_findings(findings)] == ["F003", "F004", "F002", "F001"]


def test_model_warning_is_surfaced_in_report(tmp_path):
    class Garbage:
        def classify(self, skill, sections, model):
            return "nope"

    text = _run(tmp_path, backend=Garbage()).report_path.read_text()
    assert "> skill-audit: mixed: model output invalid or unavailable; 4 section(s) labelled unclassified" in text
    assert "| unclassified | 4 |" in text
