"""`skills/autopilot/SKILL.md` documents its gates as commands, not as prose.

Spec: openspec/changes/encode-autopilot-gates-and-goal-gate-in-code/specs/
      skill-workflow/spec.md — Requirement "Prose-Free Gate Enforcement"
      Scenarios: *Grep finds no prose-only gate*, *VALIDATE vocabulary matches
      the transition table*, *Mirrors resynced*
Design decision: D9.

The acceptance criterion for this work package is "a grep of
`skills/autopilot/SKILL.md` finds no gate whose only enforcement is prose". A grep
cannot express that, so this file does. It enumerates `trust_posture.Gate` (never a
literal list of gate names), finds every place the document *names* a gate, and
requires each one to sit inside a fenced block that runs `runner.py gate-check` /
`gate-answer` — i.e. the document may only speak about a gate while showing the
command that enforces it.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from autopilot import TRANSITIONS

_SKILLS_DIR = Path(__file__).resolve().parents[2]
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))
from shared.trust_posture import Gate  # noqa: E402

_REPO_ROOT = _SKILLS_DIR.parent
_AUTOPILOT_MD = _SKILLS_DIR / "autopilot" / "SKILL.md"
_ROADMAP_MD = _SKILLS_DIR / "autopilot-roadmap" / "SKILL.md"
_PLAN_ROADMAP_MD = _SKILLS_DIR / "plan-roadmap" / "SKILL.md"
_ORCHESTRATOR_PY = _SKILLS_DIR / "autopilot-roadmap" / "scripts" / "orchestrator.py"
_DECOMPOSER_PY = _SKILLS_DIR / "plan-roadmap" / "scripts" / "decomposer.py"

#: The three SKILL.md files this package rewrites. install.sh mirrors all three.
_MIRRORED_SKILLS = ("autopilot", "autopilot-roadmap", "plan-roadmap")
_MIRROR_ROOTS = (".claude/skills", ".agents/skills")

#: Prose that *was* the gate: each of these sentences was the entire enforcement
#: of a human decision the loop now records as an ApprovalDecision.
_RETIRED_PHRASES = (
    "Wait for proposal approval",
    "STOP — Await human approval",
    "Ask if the issue has been resolved",
)

#: Gate -> a fragment of the heading of the section that must carry its protocol
#: block (D9: proposal approval, ESCALATE resume, PR creation, merge handoff).
#: Keyed by `Gate` so renaming a member breaks this map instead of silently
#: dropping a gate from the check.
_GATE_SECTIONS = {
    Gate.ESCALATE_RESUME: "Resume",
    Gate.PROPOSAL_APPROVAL: "PLAN Phase",
    Gate.PR_CREATION: "SUBMIT_PR",
    Gate.MERGE: "DONE",
}

#: Every line a gate protocol block must carry, so that a block cannot degrade
#: into a decorative `gate-check` with no way to answer it. `exit 0` / `exit 3`
#: are runner.py's contract: 0 means a gate is pending, 3 means none is.
_PROTOCOL_REQUIREMENTS = (
    "runner.py",
    "gate-check",
    "gate-answer",
    "--decision",
    "exit 0",
    "exit 3",
)


# --------------------------------------------------------------------------
# Markdown structure helpers
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Span:
    """A half-open char range over a document, plus its text."""

    start: int
    end: int
    text: str

    def contains(self, start: int, end: int) -> bool:
        return self.start <= start and end <= self.end


def _fenced_blocks(text: str) -> list[_Span]:
    """Fenced code blocks as char spans.

    Line-by-line rather than a regex because SKILL.md's `gh pr create` heredoc
    contains `## Summary` headings that must be seen as *fenced*, not as document
    structure.
    """
    blocks: list[_Span] = []
    open_at: int | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            if open_at is None:
                open_at = offset
            else:
                end = offset + len(line)
                blocks.append(_Span(open_at, end, text[open_at:end]))
                open_at = None
        offset += len(line)
    return blocks


def _protocol_blocks(text: str) -> list[_Span]:
    """Fenced blocks that actually run the gate protocol."""
    return [
        b
        for b in _fenced_blocks(text)
        if "gate-check" in b.text or "gate-answer" in b.text
    ]


_HEADING_RE = re.compile(r"^#{1,6} .*$", re.MULTILINE)


def _sections(text: str) -> list[tuple[str, _Span]]:
    """(heading line, span from that heading to the next) for real headings only."""
    fences = _fenced_blocks(text)
    heads = [
        m
        for m in _HEADING_RE.finditer(text)
        if not any(f.contains(m.start(), m.end()) for f in fences)
    ]
    out: list[tuple[str, _Span]] = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append((m.group(0).strip(), _Span(m.start(), end, text[m.start() : end])))
    return out


def _strip_fences(text: str) -> str:
    """The prose of *text*, with fenced blocks blanked out (offsets preserved)."""
    out = list(text)
    for block in _fenced_blocks(text):
        for i in range(block.start, block.end):
            if out[i] != "\n":
                out[i] = " "
    return "".join(out)


def _line_of(text: str, offset: int) -> str:
    line_no = text.count("\n", 0, offset) + 1
    line = text.splitlines()[line_no - 1]
    return f"line {line_no}: {line.strip()}"


def _mention_pattern(value: str) -> re.Pattern[str]:
    """Where an occurrence of *value* counts as naming the gate.

    Gate values are snake_case identifiers except the ones that are also ordinary
    English words — structurally, the ones with no underscore (`merge`). Counting
    every English "merge" would make the document unwritable, so for those only a
    machine-readable occurrence counts: a `--gate` argument, a JSON `"gate"` field,
    or a backticked token. Derived from the value's own shape, never from a list.
    """
    v = re.escape(value)
    if "_" in value:
        return re.compile(rf"(?P<gate>\b{v}\b)")
    return re.compile(rf"""(?:--gate[ =]+|`|"gate":\s*")(?P<gate>{v}\b)""")


def _module_constant(path: Path, name: str) -> str:
    """Read a module-level string constant without importing the module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                assert isinstance(node.value, ast.Constant)
                return str(node.value.value)
    raise AssertionError(f"{path} has no module-level constant {name}")


# --------------------------------------------------------------------------
# The gate prose is gone
# --------------------------------------------------------------------------


@pytest.mark.parametrize("phrase", _RETIRED_PHRASES)
def test_retired_gate_prose_is_gone(phrase: str) -> None:
    text = _AUTOPILOT_MD.read_text(encoding="utf-8")
    assert phrase not in text, (
        f"{_AUTOPILOT_MD} still contains the retired gate prose {phrase!r} "
        f"({_line_of(text, text.index(phrase))}). The gate is enforced by "
        f"runner.py gate-check / gate-answer now; the sentence must go."
    )


@pytest.mark.parametrize("gate", list(Gate), ids=lambda g: g.value)
def test_every_gate_name_sits_in_a_protocol_block(gate: Gate) -> None:
    """No gate may be *named* outside the block that shows how it is enforced."""
    text = _AUTOPILOT_MD.read_text(encoding="utf-8")
    blocks = _protocol_blocks(text)
    stray = [
        _line_of(text, m.start("gate"))
        for m in _mention_pattern(gate.value).finditer(text)
        if not any(b.contains(*m.span("gate")) for b in blocks)
    ]
    assert not stray, (
        f"{_AUTOPILOT_MD} names gate {gate.value!r} outside a "
        f"gate-check/gate-answer block:\n  " + "\n  ".join(stray)
    )


def test_gate_answer_examples_name_only_real_gates() -> None:
    """A documented `--gate X` must be a member of the enum runner.py accepts."""
    text = _AUTOPILOT_MD.read_text(encoding="utf-8")
    named = {m.group(1) for m in re.finditer(r"--gate[ =]+([^\s`]+)", text)}
    concrete = {n for n in named if not n.startswith("<")}
    unknown = concrete - {g.value for g in Gate}
    assert not unknown, (
        f"{_AUTOPILOT_MD} documents `--gate` values that are not "
        f"trust_posture.Gate members: {sorted(unknown)}"
    )


@pytest.mark.parametrize(
    "gate,heading_fragment",
    sorted(_GATE_SECTIONS.items(), key=lambda kv: kv[0].value),
    ids=lambda v: v.value if isinstance(v, Gate) else str(v),
)
def test_host_facing_gate_section_runs_the_protocol(
    gate: Gate, heading_fragment: str
) -> None:
    """Each section that used to hold a prose gate now runs the real protocol."""
    text = _AUTOPILOT_MD.read_text(encoding="utf-8")
    matched = [(h, s) for h, s in _sections(text) if heading_fragment in h]
    assert len(matched) == 1, (
        f"expected exactly one section whose heading contains "
        f"{heading_fragment!r}, found {[h for h, _ in matched]}"
    )
    heading, section = matched[0]
    blocks = [
        b for b in _protocol_blocks(section.text) if f"--gate {gate.value}" in b.text
    ]
    assert blocks, (
        f"section {heading!r} of {_AUTOPILOT_MD} must enforce the "
        f"{gate.value!r} gate with a `runner.py gate-answer --gate {gate.value}` "
        f"block, not with prose"
    )
    missing = [
        req for req in _PROTOCOL_REQUIREMENTS if req not in "\n".join(b.text for b in blocks)
    ]
    assert not missing, (
        f"the {gate.value!r} protocol block in section {heading!r} is missing "
        f"{missing} — a gate-check with no documented answer path or exit-code "
        f"semantics is prose with a command in it"
    )


# --------------------------------------------------------------------------
# The documented vocabulary matches the code
# --------------------------------------------------------------------------


def test_documented_validate_outcomes_match_the_transition_table() -> None:
    text = _AUTOPILOT_MD.read_text(encoding="utf-8")
    matched = [s for h, s in _sections(text) if "VALIDATE Phase" in h]
    assert len(matched) == 1, "expected exactly one 'VALIDATE Phase' section"
    prose = _strip_fences(matched[0].text)

    # Any outcome word from ANY phase's transition table is fair game to spot; the
    # ones the VALIDATE section quotes must be exactly VALIDATE's own.
    known = {outcome for table in TRANSITIONS.values() for outcome in table}
    documented = {
        token.strip().strip("\"'") for token in re.findall(r"`([^`\n]+)`", prose)
    } & known
    assert documented == set(TRANSITIONS["VALIDATE"]), (
        f"{_AUTOPILOT_MD} documents VALIDATE outcomes {sorted(documented)} but "
        f"TRANSITIONS['VALIDATE'] is {sorted(TRANSITIONS['VALIDATE'])}"
    )


# --------------------------------------------------------------------------
# The replan protocol is documented where the code put it
# --------------------------------------------------------------------------


def test_roadmap_skill_documents_the_replan_protocol() -> None:
    text = _ROADMAP_MD.read_text(encoding="utf-8")
    assert "Deferred: automated re-decomposition" not in text, (
        f"{_ROADMAP_MD} still defers replan handling; the gate, the request file "
        f"and the replan_requested status all exist now"
    )
    for token in (
        _module_constant(_ORCHESTRATOR_PY, "REPLAN_REQUEST_FILENAME"),
        _module_constant(_ORCHESTRATOR_PY, "REPLAN_REQUESTED_STATUS"),
    ):
        assert token in text, f"{_ROADMAP_MD} does not mention {token!r}"


def test_plan_roadmap_skill_documents_replan_mode() -> None:
    text = _PLAN_ROADMAP_MD.read_text(encoding="utf-8")
    for token in (
        "replan-scope",
        "replan-finish",
        _module_constant(_DECOMPOSER_PY, "REPLAN_REQUEST_FILENAME"),
    ):
        assert token in text, f"{_PLAN_ROADMAP_MD} does not document {token!r}"


# --------------------------------------------------------------------------
# Mirrors
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mirror_root", _MIRROR_ROOTS)
@pytest.mark.parametrize("skill", _MIRRORED_SKILLS)
def test_mirror_is_byte_identical(skill: str, mirror_root: str) -> None:
    source = _SKILLS_DIR / skill / "SKILL.md"
    mirror = _REPO_ROOT / mirror_root / skill / "SKILL.md"
    assert mirror.exists(), f"{mirror} is missing — run ./skills/install.sh"
    assert mirror.read_bytes() == source.read_bytes(), (
        f"{mirror} has drifted from {source} — run ./skills/install.sh to resync"
    )
