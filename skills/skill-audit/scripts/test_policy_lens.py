"""Test-policy lens for skill-audit (change ``pilot-test-quality-audit``, design D12).

Extracts the test-prescribing instructions from a SKILL.md and classifies each
on two axes:

* oracle source: ``spec_derived`` | ``impl_derived`` | ``unspecified``
* authorship:    ``separate_context`` | ``same_agent`` | ``unspecified``

``unclassified`` is the value of an axis nothing could decide; it is never a
guess. Classifier order: regex pre-pass, then one ``system_one_decisions.decide()``
call, then the existing ``ModelBackend``, else ``unclassified``. ``dry_run=True``
never reaches a backend.

Findings use the three kinds appended to the ledger schema:
``test_oracle_impl_derived``, ``test_same_context_authorship`` and
``test_coverage_target``. The lens is read-only over the audited skill and writes
``<skill>-test-policy-findings.json`` and ``<skill>-test-policy-<date>.md``, never
the rightsizing ledger or its dated report.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from audit_findings import Finding, build_ledger, write_ledger
from audit_paths import default_archetypes_path
from classifier import ModelBackend, Section, parse_sections, prepass
from report import sha256_file, reviewed_dates

# Import the module, never the name, so a stubbed ``decide`` attribute is what runs.
system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None

ORACLE_VALUES = ("spec_derived", "impl_derived", "unspecified")
AUTHORSHIP_VALUES = ("separate_context", "same_agent", "unspecified")
UNCLASSIFIED = "unclassified"

# --- extraction rules ----------------------------------------------------------

TEST_RE = re.compile(
    r"\b(?:tests?|testing|tested|pytest|assert\w*|coverage|tdd|mock\w*|characteriz\w*|red[/ -]green|fixtures?)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])(?<![eE]\.g\.)(?<!i\.e\.)\s+(?=[A-Z`\"'(\[*])")
_NEGATION_RE = re.compile(r"\b(?:never|not|no|don't|avoid|instead of|rather than|without)\b", re.IGNORECASE)

# --- classification rules ------------------------------------------------------

SPEC_DERIVED_RE = re.compile(
    r"\bspec[- ]derived\b|\bintent[- ]derived\b"
    r"|\bfrom (?:the |each |a )?(?:spec|specs|specification|scenarios?|requirements?|acceptance criteria|proposal)\b",
    re.IGNORECASE,
)
CHARACTERIZATION_RE = re.compile(r"\bcharacteriz\w*", re.IGNORECASE)
_ACTUAL_OUTPUT_RE = re.compile(
    r"\b(?:actual|current|observed|real) (?:output|results?|return values?|behaviou?r)\b", re.IGNORECASE
)
_EXPECTED_WORD_RE = re.compile(r"\b(?:expected|golden|baseline|snapshot|assert\w*)\b", re.IGNORECASE)
IMPL_DERIVED_RES = (
    re.compile(
        r"\bsnapshot (?:tests?|testing|files?)\b|\bgolden (?:files?|master|output|tests?)\b|\bapprov(?:al|ed) (?:tests?|files?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bexpected (?:values?|output|results?)\b[^.;]*\b(?:from|of|taken from|copied from|generated (?:by|from)) "
        r"(?:the )?(?:implementation|code|current|actual)\b",
        re.IGNORECASE,
    ),
)
SEPARATE_RE = re.compile(
    r"\bseparate (?:\w+ )?(?:agent|context|session|reviewer|author|worker)s?\b"
    r"|\bindependent (?:\w+ )?(?:agent|reviewer|author)s?\b"
    r"|\bdifferent (?:agent|context|session)s?\b|\bfresh context\b|\banother agent\b|\bsub-?agents? to write\b",
    re.IGNORECASE,
)
SAME_AGENT_RE = re.compile(
    r"\bsame (?:agent|context|session|conversation|worker)\b"
    r"|\bwrites?\b[^.;]*\btests?\b[^.;]*\b(?:then|before)\b[^.;]*\b(?:implement\w*|code|make (?:it|them|the tests?) pass)",
    re.IGNORECASE,
)
COVERAGE_RE = re.compile(r"\bcoverage\b", re.IGNORECASE)
COVERAGE_TARGET_RE = re.compile(
    r"\b(?:decrease|drop\w*|fall\w*|regress\w*|below|at least|threshold|minimum|gate|ratchet|target|goal|fail\w*)\b|\d+\s*%",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Instruction:
    text: str
    section_id: str


@dataclass
class Classification:
    instruction: Instruction
    oracle_source: str = UNCLASSIFIED
    authorship: str = UNCLASSIFIED


# --- extraction -------------------------------------------------------------------


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text).strip()
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(flat) if s.strip()]


def _prose_chunks(section: Section) -> list[str]:
    chunks: list[str] = []
    for block in section.blocks:
        if block.kind == "paragraph":
            chunks.append(block.text)
        elif block.kind in ("olist", "ulist"):
            chunks.extend(block.items)
    return chunks


def _search_unnegated(pattern: re.Pattern[str], text: str) -> bool:
    """True when ``pattern`` matches and no negation word sits just before the match."""
    for m in pattern.finditer(text):
        if not _NEGATION_RE.search(text[max(0, m.start() - 40) : m.start()]):
            return True
    return False


def _is_coverage_target(text: str) -> bool:
    return bool(COVERAGE_RE.search(text) and COVERAGE_TARGET_RE.search(text))


def _lens_pattern_hit(text: str) -> bool:
    return bool(
        SPEC_DERIVED_RE.search(text)
        or CHARACTERIZATION_RE.search(text)
        or SEPARATE_RE.search(text)
        or SAME_AGENT_RE.search(text)
        or _impl_derived(text)
        or _is_coverage_target(text)
    )


def extract_instructions(skill_md_text: str) -> list[Instruction]:
    """Test-prescribing sentences of a SKILL.md, in document order.

    A sentence qualifies when it mentions tests directly, or when it states an
    oracle-source / authorship / coverage rule inside a section that does.
    """
    found: list[Instruction] = []
    for section in parse_sections(skill_md_text, "SKILL.md"):
        if section.is_frontmatter:
            continue
        section_mentions_tests = bool(TEST_RE.search(section.heading) or TEST_RE.search(section.raw))
        if not section_mentions_tests:
            continue
        for chunk in _prose_chunks(section):
            for sentence in _sentences(chunk):
                if TEST_RE.search(sentence) or _lens_pattern_hit(sentence):
                    found.append(Instruction(text=sentence, section_id=section.section_id))
    return found


# --- classification ------------------------------------------------------------------


def _impl_derived(text: str) -> bool:
    if _ACTUAL_OUTPUT_RE.search(text) and _EXPECTED_WORD_RE.search(text):
        if _search_unnegated(_ACTUAL_OUTPUT_RE, text):
            return True
    return any(_search_unnegated(p, text) for p in IMPL_DERIVED_RES)


def _regex_axes(text: str) -> tuple[str, str] | None:
    """``(oracle_source, authorship)`` when any rule fires, else ``None`` (undecided)."""
    oracle = "unspecified"
    authorship = "unspecified"
    hit = False
    if _search_unnegated(SPEC_DERIVED_RE, text):
        oracle, hit = "spec_derived", True
    elif CHARACTERIZATION_RE.search(text) or _impl_derived(text):
        oracle, hit = "impl_derived", True
    if _search_unnegated(SEPARATE_RE, text):
        authorship, hit = "separate_context", True
    elif _search_unnegated(SAME_AGENT_RE, text):
        authorship, hit = "same_agent", True
    if _is_coverage_target(text):
        hit = True
    return (oracle, authorship) if hit else None


def _answer_field(answer: Any, name: str) -> Any:
    return answer.get(name) if isinstance(answer, dict) else getattr(answer, name, None)


def _judge(pending: dict[int, Instruction], *, dry_run: bool) -> dict[int, tuple[str, str]]:
    """One ``decide()`` call with two ``choice`` questions per pending instruction."""
    if system_one_decisions is None or not pending:
        return {}
    state = {
        "instructions": {f"i{n}": {"section_id": ins.section_id, "text": ins.text} for n, ins in pending.items()}
    }
    questions: dict[str, Any] = {}
    for n in pending:
        questions[f"oracle_{n}"] = {
            "type": "choice",
            "instructions": f"Where does the expected value of the test prescribed by instruction i{n} come from?",
            "criteria": {
                "spec_derived": "Expected values come from the spec, scenario or requirement.",
                "impl_derived": "Expected values come from running or reading the implementation.",
                "unspecified": "The instruction does not say.",
            },
        }
        questions[f"authorship_{n}"] = {
            "type": "choice",
            "instructions": f"Who writes the tests relative to the implementation in instruction i{n}?",
            "criteria": {
                "separate_context": "A different agent or context writes the tests.",
                "same_agent": "The same agent writes both tests and implementation in one context.",
                "unspecified": "The instruction does not say.",
            },
        }
    answers = system_one_decisions.decide(state, questions, site="skill-audit.test-policy", dry_run=dry_run)
    if not answers or not hasattr(answers, "get"):
        return {}
    out: dict[int, tuple[str, str]] = {}
    for n in pending:
        oracle = _answer_field(answers.get(f"oracle_{n}"), "choice")
        author = _answer_field(answers.get(f"authorship_{n}"), "choice")
        out[n] = (
            oracle if oracle in ORACLE_VALUES else UNCLASSIFIED,
            author if author in AUTHORSHIP_VALUES else UNCLASSIFIED,
        )
    return out


def _ask_backend(pending: dict[int, Instruction], backend: ModelBackend) -> dict[int, tuple[str, str]]:
    """Reuse the ``ModelBackend`` protocol; each value must be ``"<oracle>|<authorship>"``."""
    sections = [
        Section(
            section_id=f"i{n}",
            file="SKILL.md",
            heading="test-policy instruction",
            level=0,
            raw=(
                f"{ins.text}\n\nAnswer this entry with '<oracle_source>|<authorship>' where oracle_source is one of "
                f"{', '.join(ORACLE_VALUES)} and authorship is one of {', '.join(AUTHORSHIP_VALUES)}."
            ),
        )
        for n, ins in pending.items()
    ]
    raw = backend.classify("test-policy", sections, None)
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw.decode() if isinstance(raw, bytes) else raw).strip()))
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[int, tuple[str, str]] = {}
    for n in pending:
        value = raw.get(f"i{n}")
        parts = value.split("|") if isinstance(value, str) else []
        if len(parts) == 2 and parts[0].strip() in ORACLE_VALUES and parts[1].strip() in AUTHORSHIP_VALUES:
            out[n] = (parts[0].strip(), parts[1].strip())
    return out


def classify(
    instructions: list[Instruction], *, backend: ModelBackend | None = None, dry_run: bool = False
) -> list[Classification]:
    """One classification per instruction, in order. Never guesses."""
    results = [Classification(ins) for ins in instructions]
    pending: dict[int, Instruction] = {}
    for n, (ins, result) in enumerate(zip(instructions, results)):
        axes = _regex_axes(ins.text)
        if axes is None:
            pending[n] = ins
        else:
            result.oracle_source, result.authorship = axes

    judged = _judge(pending, dry_run=dry_run)
    for n, (oracle, author) in judged.items():
        results[n].oracle_source, results[n].authorship = oracle, author

    if backend is not None and not dry_run:
        still = {
            n: ins
            for n, ins in pending.items()
            if UNCLASSIFIED in (results[n].oracle_source, results[n].authorship)
        }
        if still:
            for n, (oracle, author) in _ask_backend(still, backend).items():
                results[n].oracle_source, results[n].authorship = oracle, author
    return results


# --- findings and outputs --------------------------------------------------------------

_KIND_ORDER = ("test_oracle_impl_derived", "test_same_context_authorship", "test_coverage_target")
_KIND_NOTE = {
    "test_oracle_impl_derived": "expected values come from the implementation and are not declared as characterization",
    "test_same_context_authorship": "one agent writes both the tests and the implementation in the same context",
    "test_coverage_target": "line coverage is used as a goal or gate",
}


def _kinds_for(c: Classification) -> list[str]:
    kinds = []
    if c.oracle_source == "impl_derived" and not CHARACTERIZATION_RE.search(c.instruction.text):
        kinds.append("test_oracle_impl_derived")
    if c.authorship == "same_agent":
        kinds.append("test_same_context_authorship")
    if _is_coverage_target(c.instruction.text):
        kinds.append("test_coverage_target")
    return kinds


def _snippet(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _build_findings(classifications: list[Classification], layer_by_section: dict[str, str]) -> list[Finding]:
    grouped: dict[tuple[str, str], list[Instruction]] = {}
    for c in classifications:
        for kind in _kinds_for(c):
            grouped.setdefault((kind, c.instruction.section_id), []).append(c.instruction)
    findings = []
    for kind, section_id in grouped:  # insertion order: document order, then kind order
        members = grouped[(kind, section_id)]
        findings.append(
            Finding(
                kind=kind,
                layer=layer_by_section.get(section_id, "unclassified"),
                section_id=section_id,
                remediation="add_reason",
                rationale=f"{_KIND_NOTE[kind]} ({len(members)} instruction(s)): \"{_snippet(members[0].text)}\"",
            )
        )
    return findings


def _render_report(skill: str, ledger: dict[str, Any], classifications: list[Classification]) -> str:
    lines = [
        f"# Skill audit, test-policy lens: {skill}",
        "",
        "- lens: test-policy",
        f"- generated_at: {ledger['generated_at']}",
        f"- instructions: {len(classifications)}",
        f"- findings: {len(ledger['findings'])}",
        "",
        "Findings are proposals; the lens never edits the audited skill. This report is not the "
        "rightsizing audit and does not count as the skill's freshness report.",
        "",
        "## Findings",
        "",
    ]
    if ledger["findings"]:
        lines += ["| id | kind | section | remediation | rationale |", "|---|---|---|---|---|"]
        for f in ledger["findings"]:
            rationale = f.get("rationale", "").replace("|", "\\|")
            lines.append(f"| {f['id']} | {f['kind']} | {f['section_id']} | {f['remediation']} | {rationale} |")
    else:
        lines.append("No test-policy findings.")
    lines += ["", "## Instructions", ""]
    if classifications:
        lines += ["| section | oracle_source | authorship | instruction |", "|---|---|---|---|"]
        for c in classifications:
            text = _snippet(c.instruction.text, 120).replace("|", "\\|")
            lines.append(f"| {c.instruction.section_id} | {c.oracle_source} | {c.authorship} | {text} |")
    else:
        lines.append("No test-prescribing instructions found.")
    lines.append("")
    return "\n".join(lines)


def audit_skill_test_policy(
    skill: str,
    *,
    skills_root: Path,
    output_dir: Path,
    backend: ModelBackend | None = None,
    dry_run: bool = True,
    archetypes_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run the lens over one skill; write and return the ledger."""
    skill_md = Path(skills_root) / skill / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"no SKILL.md for skill {skill!r} under {skills_root}")
    text = skill_md.read_text(encoding="utf-8")

    sections = parse_sections(text, "SKILL.md")
    layer_by_section: dict[str, str] = {}
    layers: list[dict[str, Any]] = []
    for s in sections:
        decided = prepass(s)
        layer_by_section[s.section_id] = decided[0] if decided else "unclassified"
        entry: dict[str, Any] = {
            "section_id": s.section_id,
            "file": s.file,
            "heading": s.heading,
            "layer": layer_by_section[s.section_id],
            "decided_by": "pre-pass" if decided else "none",
        }
        if decided:
            entry["rule"] = decided[1]
        layers.append(entry)

    classifications = classify(extract_instructions(text), backend=backend, dry_run=dry_run)
    findings = _build_findings(classifications, layer_by_section)

    # Midnight UTC keeps two runs on the same day byte-identical (NFR determinism).
    day = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%d")
    archetypes = archetypes_path or default_archetypes_path()
    freshness = {
        "archetypes_sha256": sha256_file(archetypes) if archetypes and Path(archetypes).is_file() else "0" * 64,
        "reviewed_dates": reviewed_dates(archetypes) if archetypes and Path(archetypes).is_file() else [],
        "evidence_window_days": 30,
    }
    ledger = build_ledger(
        skill=skill,
        convention="rightsizing",
        generated_at=f"{day}T00:00:00+00:00",
        freshness=freshness,
        layers=layers,
        dispatch_profile=[],
        evidence={"status": "unavailable", "reason": "not_applicable_test_policy_lens", "tier_rows": []},
        findings=findings,
    )
    output_dir = Path(output_dir)
    write_ledger(ledger, output_dir / f"{skill}-test-policy-findings.json")
    (output_dir / f"{skill}-test-policy-{day}.md").write_text(
        _render_report(skill, ledger, classifications), encoding="utf-8"
    )
    return ledger


__all__ = [
    "Classification",
    "Instruction",
    "audit_skill_test_policy",
    "classify",
    "extract_instructions",
]
