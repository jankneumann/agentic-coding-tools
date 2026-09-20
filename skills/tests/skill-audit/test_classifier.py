"""Classifier tests: deterministic pre-pass, one batched model call, no guessing.

Spec: skill-workflow "Shaped sections are classified without a model call",
"Undecidable prose is batched into one model call", "Invalid model output
never becomes a label", "Teaching that cites repo specifics is kept",
"Classification is deterministic". Design D1, D2, D10.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from classifier import (
    Classification,
    NullBackend,
    classify_sections,
    generate_findings,
    parse_sections,
    parse_skill,
    prepass,
    repo_specific_tokens,
    resolve_analyst,
    validate_model_output,
)
from audit_findings import build_ledger, write_ledger

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SKILLS = FIXTURES / "skills"
ROSTER = FIXTURES / "archetypes.yaml"
FRESHNESS = {"archetypes_sha256": "0" * 64, "reviewed_dates": [], "evidence_window_days": 30}


class FixedStub:
    """Labels every section in the batch with one fixed layer; records calls."""

    def __init__(self, label: str = "teaching") -> None:
        self.label = label
        self.calls: list[tuple[str, list[str], str | None]] = []

    def classify(self, skill, sections, model):
        self.calls.append((skill, [s.section_id for s in sections], model))
        return {s.section_id: self.label for s in sections}


class FailingStub:
    """Raises if called, or returns garbage when ``garbage`` is set."""

    def __init__(self, garbage=None) -> None:
        self.garbage = garbage
        self.calls = 0

    def classify(self, skill, sections, model):
        self.calls += 1
        if self.garbage is None:
            raise AssertionError("model backend must not be called")
        return self.garbage


def _audit(skill: str, backend, model=None):
    sections = parse_skill(SKILLS / skill)
    classification = classify_sections(skill, sections, backend, model=model)
    findings = generate_findings(sections, classification, test_texts=[])
    return sections, classification, findings


# --- pre-pass ---------------------------------------------------------------


def test_all_shaped_needs_zero_model_calls():
    stub = FailingStub()
    sections, classification, _ = _audit("all-shaped", stub)
    assert stub.calls == 0
    assert classification.model_calls == 0
    layers = {label.section_id.split("-", 1)[1]: (label.layer, label.rule) for label in classification.labels}
    assert layers["frontmatter"] == ("contract", "frontmatter")
    assert layers["all-shaped"] == ("contract", "skill_base_dir")
    assert layers["arguments"] == ("contract", "contract_table")
    assert layers["run"] == ("contract", "fenced_command")
    assert layers["never-edit-the-target"] == ("constraint", "constraint")
    assert layers["steps"] == ("procedure", "procedure")
    assert layers["exit-codes"] == ("contract", "contract_table")
    assert all(label.layer != "unclassified" for label in classification.labels)
    assert all(label.decided_by == "pre-pass" for label in classification.labels)


def test_prohibition_without_reason_is_constraint_and_flagged():
    text = "---\nname: x\n---\n\n## Rule\n\nNever push to main.\n"
    sections = parse_sections(text, "SKILL.md")
    assert prepass(sections[1]) == ("constraint", "prohibition_without_reason")
    classification = classify_sections("x", sections, FailingStub())
    findings = generate_findings(sections, classification, test_texts=[])
    kinds = {f.kind: f for f in findings}
    assert kinds["constraint_without_reason"].remediation == "add_reason"


def test_fenced_prose_blocks_do_not_make_a_contract():
    text = "## Example\n\nSome prose.\n\n```markdown\n# a heading\n```\n"
    sections = parse_sections(text, "SKILL.md")
    assert prepass(sections[0]) is None


# --- batching ---------------------------------------------------------------


def test_mixed_batches_every_undecided_section_into_one_call():
    stub = FixedStub("teaching")
    sections, classification, _ = _audit("mixed", stub, model="sonnet")
    assert len(stub.calls) == 1
    skill, batch, model = stub.calls[0]
    assert skill == "mixed"
    assert model == "sonnet"
    expected = sorted(s.section_id for s in sections if prepass(s) is None)
    assert sorted(batch) == expected
    assert len(batch) == 4
    assert classification.batch_size == 4
    model_labelled = [label for label in classification.labels if label.decided_by == "model"]
    assert len(model_labelled) == 4
    assert all(label.layer == "teaching" for label in model_labelled)
    assert not any(label.layer == "unclassified" for label in classification.labels)


@pytest.mark.parametrize(
    "garbage",
    [
        None,
        "not json",
        {"SKILL.md#02-why": "teaching"},  # missing ids
        {"SKILL.md#02-why": "vibes", "SKILL.md#03-philosophy": "teaching", "SKILL.md#04-background": "teaching", "SKILL.md#05-notes": "teaching"},
        ["teaching"] * 4,
    ],
)
def test_invalid_model_output_labels_batch_unclassified(garbage, caplog):
    stub = FailingStub(garbage=garbage if garbage is not None else "")
    with caplog.at_level(logging.WARNING, logger="skill_audit"):
        sections, classification, findings = _audit("mixed", stub)
    assert stub.calls == 1
    undecided = [label for label in classification.labels if label.decided_by == "none"]
    assert len(undecided) == 4
    assert all(label.layer == "unclassified" for label in undecided)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "skill-audit" in r.getMessage()]
    assert len(warnings) == 1
    assert "mixed" in warnings[0].getMessage() and "4" in warnings[0].getMessage()
    assert not any(f.kind == "teaching_inferable" for f in findings)
    unclassified_ids = {label.section_id for label in undecided}
    assert not any(f.section_id in unclassified_ids for f in findings)


def test_null_backend_never_guesses():
    _, classification, _ = _audit("mixed", NullBackend())
    assert classification.model_calls == 1
    assert sum(1 for label in classification.labels if label.layer == "unclassified") == 4


def test_validate_model_output_accepts_fenced_json():
    raw = '```json\n{"a": "teaching", "b": "procedure"}\n```'
    assert validate_model_output(raw, ["a", "b"]) == {"a": "teaching", "b": "procedure"}
    assert validate_model_output('{"a": "teaching", "b": "procedure", "c": "x"}', ["a", "b"]) is None
    assert validate_model_output('{"a": "unclassified", "b": "procedure"}', ["a", "b"]) is None


# --- teaching with repo tokens ---------------------------------------------


def test_teaching_that_cites_repo_specifics_is_kept():
    stub = FixedStub("teaching")
    sections, classification, findings = _audit("teaching-with-repo-token", stub)
    by_section = {f.section_id: f for f in findings if f.kind == "teaching_inferable"}
    tdd = next(f for sid, f in by_section.items() if "red-green" in sid)
    generic = next(f for sid, f in by_section.items() if "generic" in sid)
    assert tdd.remediation == "keep"
    assert "docs/decisions/" in tdd.evidence["repo_specific_tokens"]
    assert generic.remediation == "move_to_reference"
    assert generic.evidence["repo_specific_tokens"] == []


def test_repo_specific_tokens_recognise_paths_commands_and_decisions():
    tokens = repo_specific_tokens(
        "See docs/decisions/ and run tool.py; /prioritize-proposals reads it per D8. "
        "Visit https://example.com/path for more."
    )
    assert "docs/decisions/" in tokens
    assert "tool.py" in tokens
    assert "/prioritize-proposals" in tokens
    assert "D8" in tokens
    assert not any("example.com" in t for t in tokens)


# --- determinism ------------------------------------------------------------


def _ledger(skill: str, tmp_path: Path, name: str) -> bytes:
    sections, classification, findings = _audit(skill, FixedStub("teaching"))
    ledger = build_ledger(
        skill=skill,
        convention="rightsizing",
        generated_at="2026-09-16T00:00:00+00:00",
        freshness=FRESHNESS,
        layers=[label.to_dict() for label in classification.labels],
        dispatch_profile=[],
        evidence={"status": "unavailable", "reason": "stubbed", "tier_rows": []},
        findings=findings,
    )
    return write_ledger(ledger, tmp_path / name).read_bytes()


def test_ledger_is_byte_identical(tmp_path):
    first = _ledger("mixed", tmp_path, "run1.json")
    second = _ledger("mixed", tmp_path, "run2.json")
    assert first == second
    assert first  # non-empty


# --- analyst resolution ------------------------------------------------------


class _Bridge:
    def __init__(self, data):
        self.data = data
        self.phases: list[str] = []

    def try_resolve_archetype_for_phase(self, phase, signals=None, **kwargs):
        self.phases.append(phase)
        return self.data


def test_resolve_analyst_uses_the_analyst_phase():
    bridge = _Bridge({"model": "sonnet", "archetype": "analyst", "system_prompt": "", "reasons": []})
    assert resolve_analyst(bridge=bridge, roster_path=ROSTER) == "sonnet"
    assert bridge.phases == ["EXPLORE"]


def test_resolve_analyst_omits_model_on_failure():
    assert resolve_analyst(bridge=_Bridge(None), roster_path=ROSTER) is None

    class Boom:
        def try_resolve_archetype_for_phase(self, *a, **k):
            raise RuntimeError("down")

    assert resolve_analyst(bridge=Boom(), roster_path=ROSTER) is None


def test_findings_cover_procedure_without_probe_and_deviation_protocol():
    stub = FixedStub("teaching")
    _, _, findings = _audit("mixed", stub)
    kinds = [f.kind for f in findings]
    assert "missing_deviation_protocol" in kinds
    assert "procedure_without_probe" not in kinds  # "Confirm the exit code" is a probe
    assert Classification  # imported symbol is part of the public API
