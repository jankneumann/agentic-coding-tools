"""`skills/supervise/SKILL.md` documents its gates as commands, not as prose.

Spec: openspec/changes/route-supervise-gates-through-the-approval-gate-service/
      specs/skill-workflow/spec.md — Requirement "Roadmap Approval Gate"
      Scenario: *Grep finds no prose-only gate in the supervise skill*
Design decisions: D2, D5.

Mirrors `skills/tests/autopilot/test_prose_free_gates.py`'s structural approach
(enumerate `trust_posture.Gate`, never a literal name list; find every place the
document *names* a gate; require it to sit inside the block that enforces it) —
adapted for supervise's own protocol vocabulary. Autopilot names each gate at a
literal, per-phase call site, so its blocks always show `runner.py gate-check` /
`gate-answer`. Supervise raises only three gates: `roadmap_approval` (named,
`cycle_state.py gate-check` / `gate-answer` protocol blocks), `escalate_resume`
and a parked child's own gate (both resolved generically and dynamically through
`gate_router.resolve_parked` in the "Reconcile and resume" section, which never
names either literally) — so the other eight gates, `escalate_resume` included,
simply never appear as bare tokens in this document at all, and the per-gate
stray-occurrence check below passes for them vacuously rather than needing a
dedicated protocol-block requirement the way `roadmap_approval` does.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_SKILLS_DIR = Path(__file__).resolve().parents[2]
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))
from shared.trust_posture import Gate  # noqa: E402

_SUPERVISE_MD = _SKILLS_DIR / "supervise" / "SKILL.md"

#: The three sentences ri-04 retires: each was the entire enforcement of a
#: human decision the supervise skill now records as a gate-router decision.
_RETIRED_PHRASES = (
    "Then **stop**.",
    "If neither durable approval is present, report the missing approval and "
    "stop before `ExecutionAdapter.prepare`, before any implementation "
    "dispatch, and before any roadmap checkpoint or execution-state mutation.",
    "Only a parked `pending_gate` or `policy_pause` may resume with a durable "
    "`approval_ref`; the authorized CAS performs a generation increment while "
    "preserving the same dispatch ID, attempt, launch token, worktree, and "
    "branch, then repeats the normal child lifecycle.",
)

#: Only `roadmap_approval` is named literally in this document (D5); the other
#: two gates supervise raises (`escalate_resume`, a parked child's own gate)
#: are resolved generically through `resolve_parked` and never named.
_NAMED_GATE = Gate.ROADMAP_APPROVAL


# --------------------------------------------------------------------------
# Markdown structure helpers (subset of test_prose_free_gates.py's, autopilot)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Span:
    start: int
    end: int
    text: str

    def contains(self, start: int, end: int) -> bool:
        return self.start <= start and end <= self.end


def _fenced_blocks(text: str) -> list[_Span]:
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
    """Fenced blocks that enforce a gate: either the `gate-check` / `gate-answer`
    CLI (roadmap_approval, `cycle`/`execute`) or a `gate_router.resolve_parked`
    call (a parked child's gate or `escalate_resume`, "Reconcile and resume")."""
    markers = ("gate-check", "gate-answer", "resolve_parked")
    return [b for b in _fenced_blocks(text) if any(m in b.text for m in markers)]


def _line_of(text: str, offset: int) -> str:
    line_no = text.count("\n", 0, offset) + 1
    line = text.splitlines()[line_no - 1]
    return f"line {line_no}: {line.strip()}"


def _mention_pattern(value: str) -> re.Pattern[str]:
    """Where an occurrence of *value* counts as naming the gate.

    Gate values are snake_case identifiers except the ones that are also
    ordinary English words (no underscore) -- `merge`, here at SKILL.md:216
    ("PRs awaiting review or merge"). Counting every English "merge" would
    make the document unwritable, so for those only a machine-readable
    occurrence counts: a `--gate` argument, a JSON `"gate"` field, or a
    backticked token. Derived from the value's own shape, never a list.
    """
    v = re.escape(value)
    if "_" in value:
        return re.compile(rf"(?P<gate>\b{v}\b)")
    return re.compile(rf"""(?:--gate[ =]+|`|"gate":\s*")(?P<gate>{v}\b)""")


# --------------------------------------------------------------------------
# The gate prose is gone
# --------------------------------------------------------------------------


@pytest.mark.parametrize("phrase", _RETIRED_PHRASES)
def test_retired_gate_prose_is_gone(phrase: str) -> None:
    text = _SUPERVISE_MD.read_text(encoding="utf-8")
    assert phrase not in text, (
        f"{_SUPERVISE_MD} still contains the retired gate prose {phrase!r} "
        f"({_line_of(text, text.index(phrase))}). The gate is enforced by "
        f"cycle_state.py gate-check / gate-answer / resolve_parked now; the "
        f"sentence must go."
    )


@pytest.mark.parametrize("gate", list(Gate), ids=lambda g: g.value)
def test_every_gate_name_sits_in_a_protocol_block(gate: Gate) -> None:
    """No gate may be *named* outside the block that shows how it is enforced.

    Keyed by `trust_posture.Gate` (all nine members, not a literal list) so a
    renamed or newly-added gate fails this test instead of silently escaping
    it. For the eight gates this document never names -- including
    `escalate_resume`, resolved generically through `resolve_parked` rather
    than by name -- the assertion passes vacuously: zero stray occurrences.
    """
    text = _SUPERVISE_MD.read_text(encoding="utf-8")
    blocks = _protocol_blocks(text)
    stray = [
        _line_of(text, m.start("gate"))
        for m in _mention_pattern(gate.value).finditer(text)
        if not any(b.contains(*m.span("gate")) for b in blocks)
    ]
    assert not stray, (
        f"{_SUPERVISE_MD} names gate {gate.value!r} outside a "
        f"gate-check/gate-answer/resolve_parked block:\n  " + "\n  ".join(stray)
    )


def test_gate_answer_examples_name_only_real_gates() -> None:
    """A documented `--gate X` must be a member of the enum cycle_state.py accepts."""
    text = _SUPERVISE_MD.read_text(encoding="utf-8")
    named = {m.group(1) for m in re.finditer(r"--gate[ =]+([^\s`]+)", text)}
    concrete = {n for n in named if not n.startswith("<")}
    unknown = concrete - {g.value for g in Gate}
    assert not unknown, (
        f"{_SUPERVISE_MD} documents `--gate` values that are not "
        f"trust_posture.Gate members: {sorted(unknown)}"
    )


def test_roadmap_approval_is_named_at_least_once() -> None:
    """A sanity check on the test itself: if nobody ever names the one gate
    this document IS supposed to name, the stray-occurrence test above would
    pass vacuously for it too, silently stopping being a real check."""
    text = _SUPERVISE_MD.read_text(encoding="utf-8")
    assert list(_mention_pattern(_NAMED_GATE.value).finditer(text)), (
        f"{_SUPERVISE_MD} never names {_NAMED_GATE.value!r} — expected at "
        "least the `cycle` gate-check/gate-answer and `execute` Approval gate "
        "protocol blocks to name it"
    )


def test_cycle_and_execute_both_run_the_roadmap_approval_gate_check() -> None:
    """D5: `execute` always starts with `gate-check`, so a rehydrated `execute`
    session never has to find the approval in conversation history."""
    text = _SUPERVISE_MD.read_text(encoding="utf-8")
    cycle = text.split("## Verb: `cycle`", 1)[1].split("## Verb: `execute`", 1)[0]
    execute = text.split("## Verb: `execute`", 1)[1].split("## Idempotency", 1)[0]
    approval = execute.split("### Approval gate", 1)[1].split(
        "### Prepare and launch", 1
    )[0]

    for section, name in ((cycle, "cycle"), (approval, "execute's Approval gate")):
        blocks = _protocol_blocks(section)
        checks = [b for b in blocks if "gate-check" in b.text]
        assert checks, f"{name} section has no gate-check protocol block"
        evaluating = [b for b in checks if f"--gate {_NAMED_GATE.value}" in b.text or "gate-check --roadmap" in b.text]
        assert evaluating, f"{name}'s gate-check block does not evaluate roadmap_approval"


def test_dry_run_never_runs_gate_check() -> None:
    """D5: `cycle --dry-run` never runs `gate-check` -- a dry run stops at the
    digest, since evaluating would append to `checkpoint.json` and project
    into the mirror, and a dry run writes no supervisor state by contract."""
    text = _SUPERVISE_MD.read_text(encoding="utf-8")
    closing = text.split("### 5. Digest, then stop", 1)[1].split(
        "## Verb: `execute`", 1
    )[0]
    assert "gate-check never runs under `cycle --dry-run`" in " ".join(
        closing.split()
    ) or "never runs under `cycle --dry-run`" in " ".join(closing.split())


def test_notify_with_timeout_wait_is_documented() -> None:
    """D5: under notify_with_timeout, gate-check waits up to timeout_seconds."""
    text = _SUPERVISE_MD.read_text(encoding="utf-8")
    assert "timeout_seconds" in text
    assert "notify_with_timeout" in text


def test_exit_4_divergence_from_runner_is_stated() -> None:
    """D5's one documented divergence from runner.py: exit 4 keeps the
    pending_gates entry answerable via gate-answer, rather than clearing
    pending_gate and entering ESCALATE the way runner.py's EXIT_GATE_PARKED
    does -- the supervisor has no ESCALATE state to fall into."""
    text = _SUPERVISE_MD.read_text(encoding="utf-8")
    closing = text.split("### 5. Digest, then stop", 1)[1].split(
        "## Verb: `execute`", 1
    )[0]
    normalized = " ".join(closing.split())
    assert "EXIT_GATE_PARKED" in normalized
    assert "answerable via" in normalized or "gate-answer" in normalized
    assert "no ESCALATE state" in normalized
