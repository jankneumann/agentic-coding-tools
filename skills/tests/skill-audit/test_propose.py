"""--propose writes candidate-work stubs through the improve-harness projection helper (D8)."""
from __future__ import annotations

import json

import pytest

from audit_paths import ensure_sibling_paths

ensure_sibling_paths()

from candidate_work import find_schema_path, load_schema, validate_candidate_work_batch  # noqa: E402
from skill_audit import propose  # noqa: E402


def _ledger(findings):
    return {"skill": "validate-feature", "findings": findings}


def _finding(id_, kind, section, remediation="add_probe", layer="procedure"):
    return {"id": id_, "kind": kind, "layer": layer, "section_id": section, "remediation": remediation, "evidence": {}}


def test_stubs_are_schema_valid_and_deduplicated(tmp_path):
    ledger = _ledger([
        _finding("F001", "procedure_without_probe", "SKILL.md#03-steps"),
        _finding("F002", "procedure_without_probe", "SKILL.md#03-steps"),
        _finding("F003", "teaching_inferable", "SKILL.md#05-why", "move_to_reference", "teaching"),
        _finding("F004", "teaching_inferable", "SKILL.md#06-kept", "keep", "teaching"),
    ])
    report = tmp_path / "validate-feature-2026-09-16.md"
    report.write_text("# report\n")
    path = propose(ledger, report_path=report, output_dir=tmp_path, repo_root=tmp_path)
    assert path == tmp_path / "validate-feature-candidate-work.json"
    stubs = json.loads(path.read_text())
    assert len(stubs) == 2
    validate_candidate_work_batch(stubs, schema=load_schema(find_schema_path()))
    by_kind = {s["title"].split(": ")[1].split(" in ")[0]: s for s in stubs}
    merged = by_kind["procedure_without_probe"]
    assert sorted(merged["provenance"]["finding_ids"]) == ["F001", "F002"]
    assert merged["provenance"]["source_artifact"] == "validate-feature-2026-09-16.md"
    assert merged["provenance"]["generator"] == "improve-harness"
    assert merged["suggested_change_id"].startswith("update-rightsize-validate-feature-procedure-without-probe")
    teaching = by_kind["teaching_inferable"]
    assert teaching["provenance"]["finding_ids"] == ["F003"]
    assert teaching["suggested_change_id"].startswith("update-rightsize-validate-feature-teaching-inferable")
    assert teaching["priority"] > merged["priority"]


def test_no_non_keep_findings_writes_nothing(tmp_path):
    ledger = _ledger([_finding("F001", "teaching_inferable", "SKILL.md#05-why", "keep", "teaching")])
    report = tmp_path / "r.md"
    report.write_text("x")
    assert propose(ledger, report_path=report, output_dir=tmp_path, repo_root=tmp_path) is None
    assert not (tmp_path / "validate-feature-candidate-work.json").exists()


def test_suggested_change_ids_are_unique_per_section(tmp_path):
    ledger = _ledger([
        _finding("F001", "contract_unpinned", "SKILL.md#01-a", layer="contract"),
        _finding("F002", "contract_unpinned", "SKILL.md#02-b", layer="contract"),
    ])
    report = tmp_path / "r.md"
    report.write_text("x")
    stubs = json.loads(propose(ledger, report_path=report, output_dir=tmp_path, repo_root=tmp_path).read_text())
    ids = [s["suggested_change_id"] for s in stubs]
    assert len(set(ids)) == 2
    assert pytest  # keep the import used for future parametrisation
