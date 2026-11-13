"""Spec-only tests for the skill-audit test-policy lens (task 7.2, wp-skill-audit-lens).

Change ``pilot-test-quality-audit``, capability ``test-oracle-audit``, requirement
"Skill-Audit Test-Policy Lens" (scenarios .49 coverage gate found, .50 same-agent
authorship found, .51 existing ledgers still validate, .52 no backend yields
unclassified). Design D12; contract
``contracts/schemas/skill-audit-kinds.delta.json``.

API under test (``skills/skill-audit/scripts/test_policy_lens.py``, which does not
exist yet; these tests define it):

* ``extract_instructions(skill_md_text) -> list[Instruction]``; each Instruction has
  ``.text`` (the sentence) and ``.section_id`` (``SKILL.md#NN-<slug>``, the same id
  scheme as ``classifier.parse_sections``).
* ``classify(instructions, *, backend=None, dry_run=False) -> list[Classification]``,
  one per instruction, in order; each has ``.instruction``, ``.oracle_source`` in
  {spec_derived, impl_derived, unspecified, unclassified} and ``.authorship`` in
  {separate_context, same_agent, unspecified, unclassified}. ``unclassified`` is the
  value of an axis nothing could decide (never a guess).
* ``audit_skill_test_policy(skill, *, skills_root, output_dir, backend=None,
  dry_run=True) -> dict`` returning the ledger it wrote.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import re
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
SKILLS_ROOT = TESTS_DIR.parents[1]
REPO_ROOT = SKILLS_ROOT.parent
SCHEMA_PATH = (
    SKILLS_ROOT / "skill-audit" / "install_assets" / "openspec" / "schemas"
    / "skill-audit-findings.schema.json"
)
SYNCED_SCHEMA_PATH = REPO_ROOT / "openspec" / "schemas" / "skill-audit-findings.schema.json"
COMMITTED_LEDGERS = sorted((REPO_ROOT / "docs" / "reports" / "skill-audit").glob("*-findings.json"))

NEW_KINDS = ["test_oracle_impl_derived", "test_same_context_authorship", "test_coverage_target"]
OLD_KINDS = [
    "teaching_inferable",
    "procedure_without_probe",
    "constraint_without_reason",
    "contract_unpinned",
    "missing_deviation_protocol",
    "tier_concentrated_failure",
    "convention_drift",
]

COVERAGE_SKILL = """\
---
name: cov-skill
description: Fixture skill with a coverage gate.
---

# Cov Skill

## Overview

This skill ships a small feature.

## Coverage gate

Line coverage must not decrease; fail the build if coverage drops below 80%.
"""

SAME_AGENT_SKILL = """\
---
name: tdd-skill
description: Fixture skill with same-context test and implementation authorship.
---

# TDD Skill

## Red green loop

Write a failing test first, then write the implementation yourself in the same
context so the test passes.
"""

IMPL_DERIVED_SKILL = """\
---
name: snap-skill
description: Fixture skill whose tests take expected values from the implementation.
---

# Snap Skill

## Expected values

Run the implementation and paste its actual output into the test as the expected
value.
"""

SPEC_DERIVED_SKILL = """\
---
name: spec-skill
description: Fixture skill with disciplined test policy.
---

# Spec Skill

## Independent tests

Derive each expected value from the spec scenario, not from the implementation.
A separate reviewer agent writes the tests in a separate context.
"""

VAGUE_SKILL = """\
---
name: vague-skill
description: Fixture skill with a test instruction no regex rule decides.
---

# Vague Skill

## Fixtures

Keep the fixtures tidy where reasonable.
"""

NO_TEST_SKILL = """\
---
name: plain-skill
description: Fixture skill that says nothing about tests.
---

# Plain Skill

## Deploy

Push the branch and open a pull request for the maintainers.
"""


# --- helpers -----------------------------------------------------------------


@pytest.fixture(scope="module")
def lens():
    """Import the lens lazily so every test, not collection, fails while it is absent."""
    return importlib.import_module("test_policy_lens")


class RaisingBackend:
    """A model backend that fails the test if it is ever consulted."""

    def __init__(self) -> None:
        self.calls = 0

    def classify(self, skill, sections, model):
        self.calls += 1
        raise AssertionError("model backend must not be called")


def _make_skill(root: Path, name: str, text: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return skill_dir


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _only_instruction(lens, text: str):
    found = lens.extract_instructions(text)
    assert len(found) == 1, [i.text for i in found]
    return found[0]


def _classify_one(lens, skill_text: str, **kwargs):
    instrs = lens.extract_instructions(skill_text)
    assert instrs, "fixture must contain a test-prescribing instruction"
    result = lens.classify(instrs, **kwargs)
    assert len(result) == len(instrs)
    return result[0]


def _audit(lens, tmp_path: Path, name: str, text: str, **kwargs):
    skills_root = tmp_path / "skills"
    out = tmp_path / "out"
    _make_skill(skills_root, name, text)
    result = lens.audit_skill_test_policy(name, skills_root=skills_root, output_dir=out, **kwargs)
    ledger = json.loads((out / f"{name}-test-policy-findings.json").read_text(encoding="utf-8"))
    return result, ledger, skills_root, out


def _kinds(ledger: dict) -> list[str]:
    return [f["kind"] for f in ledger["findings"]]


# --- extraction ---------------------------------------------------------------


def test_extract_returns_test_prescribing_sentences_with_section_ids(lens):
    """Scenario .49 (extraction half): the instruction is found and tied to its section."""
    instrs = lens.extract_instructions(COVERAGE_SKILL)
    assert instrs
    hit = [i for i in instrs if "coverage" in i.text.lower()]
    assert hit, [i.text for i in instrs]
    assert hit[0].section_id.startswith("SKILL.md#")
    assert "coverage-gate" in hit[0].section_id


def test_extract_ignores_prose_that_does_not_prescribe_tests(lens):
    """Scenario .49 / D12: only sections and sentences about tests are extracted."""
    assert lens.extract_instructions(NO_TEST_SKILL) == []


def test_extract_empty_text_yields_no_instructions(lens):
    """Scenario .52 (degenerate input): nothing to extract is not an error."""
    assert lens.extract_instructions("") == []


def test_extract_is_deterministic(lens):
    """Spec NFR determinism, carried into D12: same text, same instructions, same order."""
    first = [(i.section_id, i.text) for i in lens.extract_instructions(SAME_AGENT_SKILL)]
    second = [(i.section_id, i.text) for i in lens.extract_instructions(SAME_AGENT_SKILL)]
    assert first == second


# --- classification (regex pre-pass) --------------------------------------------


def test_regex_marks_write_test_then_implementation_as_same_agent(lens):
    """Scenario .50: failing test then implementation in the same context -> same_agent."""
    c = _classify_one(lens, SAME_AGENT_SKILL, backend=RaisingBackend())
    assert c.authorship == "same_agent"


def test_regex_marks_impl_output_as_expected_value_as_impl_derived(lens):
    """Scenario .50/.52 and D12: expected values taken from the implementation -> impl_derived."""
    c = _classify_one(lens, IMPL_DERIVED_SKILL, backend=RaisingBackend())
    assert c.oracle_source == "impl_derived"


def test_regex_marks_spec_derived_and_separate_context(lens):
    """Scenario .52 (regex still classifies obvious ones): spec-derived oracle, separate author."""
    instrs = lens.extract_instructions(SPEC_DERIVED_SKILL)
    result = lens.classify(instrs, backend=RaisingBackend())
    assert any(c.oracle_source == "spec_derived" for c in result)
    assert any(c.authorship == "separate_context" for c in result)


def test_classification_axes_use_only_declared_values(lens):
    """Spec requirement: axes are drawn from the declared sets (plus unclassified)."""
    oracle = {"spec_derived", "impl_derived", "unspecified", "unclassified"}
    author = {"separate_context", "same_agent", "unspecified", "unclassified"}
    for text in (COVERAGE_SKILL, SAME_AGENT_SKILL, IMPL_DERIVED_SKILL, SPEC_DERIVED_SKILL, VAGUE_SKILL):
        for c in lens.classify(lens.extract_instructions(text)):
            assert c.oracle_source in oracle
            assert c.authorship in author


def test_classify_returns_one_classification_per_instruction_in_order(lens):
    """Scenario .52: classification is total and order-preserving."""
    instrs = lens.extract_instructions(SPEC_DERIVED_SKILL)
    result = lens.classify(instrs)
    assert len(result) == len(instrs)
    assert [c.instruction.text for c in result] == [i.text for i in instrs]


# --- no judge, no backend ---------------------------------------------------------


def test_unmatched_instruction_without_backend_is_unclassified(lens):
    """Scenario .52: regex-unmatched, no judge, no model backend -> unclassified, not guessed."""
    c = _classify_one(lens, VAGUE_SKILL, backend=None)
    assert c.oracle_source == "unclassified"
    assert c.authorship == "unclassified"


def test_null_backend_leaves_unmatched_instruction_unclassified(lens):
    """Scenario .52: the existing NullBackend behaves like no backend."""
    from classifier import NullBackend

    c = _classify_one(lens, VAGUE_SKILL, backend=NullBackend())
    assert c.oracle_source == "unclassified"
    assert c.authorship == "unclassified"


def test_dry_run_never_consults_the_backend(lens):
    """Scenario .52 and D12: dry-run degrades to unclassified instead of calling a model."""
    backend = RaisingBackend()
    c = _classify_one(lens, VAGUE_SKILL, backend=backend, dry_run=True)
    assert backend.calls == 0
    assert c.oracle_source == "unclassified"
    assert c.authorship == "unclassified"


def test_backend_is_not_consulted_when_regex_decides_everything(lens):
    """D12 classifier order: regex pre-pass first; the model only sees the undecided."""
    backend = RaisingBackend()
    lens.classify(lens.extract_instructions(SAME_AGENT_SKILL), backend=backend)
    assert backend.calls == 0


# --- audit: findings --------------------------------------------------------------


def test_coverage_gate_instruction_yields_coverage_target_finding_citing_section(lens, tmp_path):
    """Scenario .49: a coverage-must-not-decrease instruction -> test_coverage_target on that section."""
    _, ledger, _, _ = _audit(lens, tmp_path, "cov-skill", COVERAGE_SKILL)
    hits = [f for f in ledger["findings"] if f["kind"] == "test_coverage_target"]
    assert hits, ledger["findings"]
    assert "coverage-gate" in hits[0]["section_id"]
    assert hits[0]["section_id"].startswith("SKILL.md#")


def test_same_agent_instruction_yields_same_context_authorship_finding(lens, tmp_path):
    """Scenario .50: failing test then implementation in one context -> test_same_context_authorship."""
    _, ledger, _, _ = _audit(lens, tmp_path, "tdd-skill", SAME_AGENT_SKILL)
    hits = [f for f in ledger["findings"] if f["kind"] == "test_same_context_authorship"]
    assert hits, ledger["findings"]
    assert "red-green-loop" in hits[0]["section_id"]


def test_impl_derived_oracle_yields_test_oracle_impl_derived_finding(lens, tmp_path):
    """Scenario .50 family / D12: impl-derived expected values -> test_oracle_impl_derived."""
    _, ledger, _, _ = _audit(lens, tmp_path, "snap-skill", IMPL_DERIVED_SKILL)
    assert "test_oracle_impl_derived" in _kinds(ledger)


def test_disciplined_skill_yields_no_test_policy_findings(lens, tmp_path):
    """D12: spec-derived, separate-context instructions are the policy, not a finding."""
    _, ledger, _, _ = _audit(lens, tmp_path, "spec-skill", SPEC_DERIVED_SKILL)
    assert not set(_kinds(ledger)) & set(NEW_KINDS)


def test_unclassified_instruction_emits_no_finding(lens, tmp_path):
    """Scenario .52: unclassified instructions produce no finding (and the files still exist)."""
    _, ledger, _, out = _audit(lens, tmp_path, "vague-skill", VAGUE_SKILL, backend=None)
    assert ledger["findings"] == []
    assert (out / "vague-skill-test-policy-findings.json").is_file()


def test_findings_only_use_the_three_lens_kinds(lens, tmp_path):
    """Spec: the mode emits findings of exactly the three new kinds."""
    for name, text in (
        ("cov-skill", COVERAGE_SKILL),
        ("tdd-skill", SAME_AGENT_SKILL),
        ("snap-skill", IMPL_DERIVED_SKILL),
    ):
        _, ledger, _, _ = _audit(lens, tmp_path / name, name, text)
        assert set(_kinds(ledger)) <= set(NEW_KINDS)


def test_returned_dict_matches_the_written_ledger(lens, tmp_path):
    """API: audit_skill_test_policy returns a dict carrying the same findings it wrote."""
    result, ledger, _, _ = _audit(lens, tmp_path, "cov-skill", COVERAGE_SKILL)
    assert isinstance(result, dict)
    assert result["findings"] == ledger["findings"]


def test_lens_findings_have_unique_ids_and_valid_remediation(lens, tmp_path):
    """Scenario .51 adjunct: lens findings obey the ledger's id and remediation vocabulary."""
    from audit_findings import REMEDIATIONS

    _, ledger, _, _ = _audit(lens, tmp_path, "tdd-skill", SAME_AGENT_SKILL)
    ids = [f["id"] for f in ledger["findings"]]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"F[0-9]{3,}", i) for i in ids)
    assert all(f["remediation"] in REMEDIATIONS for f in ledger["findings"])


def test_lens_ledger_validates_against_extended_schema(lens, tmp_path):
    """Scenario .51: a lens-produced ledger is schema-valid (RED until the enum is extended)."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for name, text in (("cov-skill", COVERAGE_SKILL), ("tdd-skill", SAME_AGENT_SKILL)):
        _, ledger, _, _ = _audit(lens, tmp_path / name, name, text)
        assert [e.message for e in validator.iter_errors(ledger)] == []


# --- audit: outputs and read-only -----------------------------------------------------


def test_outputs_are_named_per_d12_and_in_output_dir(lens, tmp_path):
    """D12 Outputs: <skill>-test-policy-findings.json and <skill>-test-policy-<date>.md."""
    _, _, _, out = _audit(lens, tmp_path, "cov-skill", COVERAGE_SKILL)
    names = sorted(p.name for p in out.iterdir())
    assert "cov-skill-test-policy-findings.json" in names
    reports = [n for n in names if re.fullmatch(r"cov-skill-test-policy-\d{4}-\d{2}-\d{2}\.md", n)]
    assert len(reports) == 1, names


def test_never_writes_the_rightsizing_ledger_or_report(lens, tmp_path):
    """D12: the lens never creates <skill>-findings.json nor a <skill>-<date>.md report."""
    _, _, _, out = _audit(lens, tmp_path, "cov-skill", COVERAGE_SKILL)
    names = [p.name for p in out.iterdir()]
    assert "cov-skill-findings.json" not in names
    assert not [n for n in names if re.fullmatch(r"cov-skill-\d{4}-\d{2}-\d{2}\.md", n)]


def test_existing_rightsizing_outputs_are_left_byte_identical(lens, tmp_path):
    """D12: it never overwrites the rightsizing audit's ledger or dated report."""
    skills_root = tmp_path / "skills"
    out = tmp_path / "out"
    out.mkdir()
    _make_skill(skills_root, "cov-skill", COVERAGE_SKILL)
    ledger = out / "cov-skill-findings.json"
    report = out / "cov-skill-2026-01-01.md"
    ledger.write_text('{"sentinel": "rightsizing"}\n', encoding="utf-8")
    report.write_text("# rightsizing report\n", encoding="utf-8")
    before = (ledger.read_bytes(), report.read_bytes())

    lens.audit_skill_test_policy("cov-skill", skills_root=skills_root, output_dir=out)

    assert (ledger.read_bytes(), report.read_bytes()) == before


def test_audited_skill_is_not_modified(lens, tmp_path):
    """Spec: the lens is read-only over the audited skill."""
    skills_root = tmp_path / "skills"
    _make_skill(skills_root, "tdd-skill", SAME_AGENT_SKILL)
    before = _tree_digest(skills_root)

    lens.audit_skill_test_policy("tdd-skill", skills_root=skills_root, output_dir=tmp_path / "out")

    assert _tree_digest(skills_root) == before


def test_findings_file_is_deterministic(lens, tmp_path):
    """Spec NFR determinism: two runs over the same skill write byte-identical findings."""
    skills_root = tmp_path / "skills"
    _make_skill(skills_root, "tdd-skill", SAME_AGENT_SKILL)
    a, b = tmp_path / "a", tmp_path / "b"
    lens.audit_skill_test_policy("tdd-skill", skills_root=skills_root, output_dir=a)
    lens.audit_skill_test_policy("tdd-skill", skills_root=skills_root, output_dir=b)
    name = "tdd-skill-test-policy-findings.json"
    assert (a / name).read_bytes() == (b / name).read_bytes()


def test_report_names_the_skill_and_cites_findings(lens, tmp_path):
    """D12 Outputs: the dated markdown report is a readable rendering of the ledger."""
    _, ledger, _, out = _audit(lens, tmp_path, "cov-skill", COVERAGE_SKILL)
    (report,) = [p for p in out.iterdir() if p.suffix == ".md"]
    text = report.read_text(encoding="utf-8")
    assert "cov-skill" in text
    assert ledger["findings"][0]["section_id"] in text


def test_missing_skill_fails_loudly_without_writing(lens, tmp_path):
    """Scenario .52 adjunct: auditing a skill that does not exist is an error, not an empty ledger."""
    out = tmp_path / "out"
    (tmp_path / "skills").mkdir()
    with pytest.raises((FileNotFoundError, ValueError, SystemExit)):
        lens.audit_skill_test_policy("nope", skills_root=tmp_path / "skills", output_dir=out)
    assert not out.exists() or not list(out.glob("*"))


# --- CLI ----------------------------------------------------------------------------------


def test_cli_lens_flag_runs_the_test_policy_lens(lens, tmp_path):
    """D12: invoked as `skill_audit.py --lens test-policy <skill>`; no rightsizing outputs."""
    from skill_audit import main

    skills_root = tmp_path / "skills"
    out = tmp_path / "out"
    _make_skill(skills_root, "cov-skill", COVERAGE_SKILL)

    rc = main(["--lens", "test-policy", "cov-skill", "--skills-root", str(skills_root),
               "--output-dir", str(out)])

    assert rc == 0
    names = [p.name for p in out.iterdir()]
    assert "cov-skill-test-policy-findings.json" in names
    assert "cov-skill-findings.json" not in names


# --- schema extension and existing-ledger compatibility ------------------------------------


def _kind_enum(path: Path) -> list[str]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    return schema["$defs"]["finding"]["properties"]["kind"]["enum"]


def test_schema_kind_enum_is_extended_append_only():
    """Scenario .51 / delta contract: the three kinds are appended after the original seven."""
    assert _kind_enum(SCHEMA_PATH) == OLD_KINDS + NEW_KINDS


def test_synced_schema_copy_has_the_same_extended_enum():
    """Design D12 Schema: openspec/schemas copy carries the identical enum."""
    assert _kind_enum(SYNCED_SCHEMA_PATH) == OLD_KINDS + NEW_KINDS


def test_audit_findings_kinds_include_the_lens_kinds():
    """Contract: the Finding dataclass accepts the three new kinds (KINDS extended)."""
    from audit_findings import KINDS, Finding

    assert list(KINDS[: len(OLD_KINDS)]) == OLD_KINDS
    for kind in NEW_KINDS:
        assert kind in KINDS
        Finding(kind=kind, layer="procedure", section_id="SKILL.md#01-x", remediation="add_probe")


def test_committed_ledgers_are_discovered():
    """Scenario .51 guard: the glob really finds the committed ledgers (no vacuous pass)."""
    assert COMMITTED_LEDGERS


@pytest.mark.parametrize("ledger_path", COMMITTED_LEDGERS, ids=lambda p: p.name)
def test_every_committed_ledger_validates_against_the_schema(ledger_path):
    """Scenario .51: every *-findings.json under docs/reports/skill-audit/ still validates."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert [e.message for e in validator.iter_errors(ledger)] == []
