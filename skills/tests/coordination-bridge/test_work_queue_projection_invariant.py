"""Guard test: the work queue is a projection, never a source of phase truth.

Contract (see docs/guides/work-queue-truth-projection.md and
skills/coordination-bridge/SKILL.md -> "Work-Queue Truth / Projection
Contract"): ``openspec/changes/<id>/loop-state.json`` (``LoopState`` in
``skills/autopilot/scripts/autopilot.py``) is the authoritative execution
state. The coordinator work queue (``/work/claim`` / ``get_work``) is a derived
distribution/claim mechanism. Truth flows loop-state -> queue, never the
reverse.

This test FAILS if any skill source treats a ``work/claim`` / ``get_work``
result as the source of the current phase — i.e. couples the authoritative
``current_phase`` / loop-state symbol to a work-queue claim within the same
statement / adjacent statements. That coupling is exactly the direction-of-truth
inversion the contract forbids.

If a legitimate future need arises (there is none today — autopilot does not use
the queue for dispatch), do not weaken this guard: implement the projection per
the three enforcement rules in the guide, which keep ``current_phase`` sourced
from loop-state, not from the claim result.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# The grep invariant
# ---------------------------------------------------------------------------
# A "claim token" is any reference to claiming/reading work off the coordinator
# queue. An "authoritative-phase symbol" is the loop-state field that records
# what phase a run is in. The invariant is: these two must never appear coupled
# in skill source — no skill may set/derive the current phase from a claim.

_CLAIM_TOKEN = r"(?:try_get_work|get_work|/work/claim|work/claim)"
_PHASE_AUTHORITY = r"(?:current_phase|loop[_-]state|LoopState)"

# Proximity window (characters) over comment-stripped source. A claim token and
# an authoritative-phase symbol appearing within this distance of one another is
# treated as a coupling — this catches both the single-line form
# (``current_phase = try_get_work(...)["phase"]``) and the two-line form
# (``r = get_work(...)`` / ``current_phase = r["phase"]``).
_WINDOW = 200

_VIOLATION = re.compile(
    rf"{_CLAIM_TOKEN}.{{0,{_WINDOW}}}{_PHASE_AUTHORITY}"
    rf"|{_PHASE_AUTHORITY}.{{0,{_WINDOW}}}{_CLAIM_TOKEN}",
    re.DOTALL,
)


def _skills_root() -> Path:
    # tests/coordination-bridge/<this file> -> skills/
    return Path(__file__).resolve().parents[2]


def _strip_comments(src: str) -> str:
    """Drop ``#`` line/inline comments so prose that names both tokens (e.g. a
    comment stating the invariant) does not read as a violation. Naive but
    sufficient: executable coupling — the thing we guard against — never lives
    inside a comment."""
    out_lines: list[str] = []
    for line in src.splitlines():
        hash_idx = line.find("#")
        out_lines.append(line if hash_idx == -1 else line[:hash_idx])
    return "\n".join(out_lines)


def _collect_skill_sources() -> list[Path]:
    """All skill ``.py`` sources, excluding test trees (tests legitimately
    construct synthetic violation strings)."""
    root = _skills_root()
    files: list[Path] = []
    for path in root.rglob("*.py"):
        parts = set(path.parts)
        if "tests" in parts or "test" in parts:
            continue
        if path.name.startswith("test_"):
            continue
        if ".venv" in parts:
            continue
        files.append(path)
    return files


def test_no_skill_sources_current_phase_from_work_queue():
    """No skill source may couple ``current_phase`` / loop-state to a
    ``work/claim`` / ``get_work`` result. See module docstring for the contract."""
    offenders: list[tuple[Path, str]] = []
    for path in _collect_skill_sources():
        try:
            src = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        stripped = _strip_comments(src)
        match = _VIOLATION.search(stripped)
        if match:
            snippet = " ".join(match.group(0).split())[:160]
            offenders.append((path, snippet))

    if offenders:
        root = _skills_root()
        msg = [
            "Work-queue truth/projection contract violated: a skill source "
            "couples the authoritative phase (current_phase / loop-state) to a "
            "work-queue claim (get_work / /work/claim).",
            "loop-state.json is the source of truth; the queue is a derived "
            "projection. See docs/guides/work-queue-truth-projection.md.",
            "Offenders:",
        ]
        for path, snippet in offenders:
            msg.append(f"  {path.relative_to(root)}: ...{snippet}...")
        pytest.fail("\n".join(msg))


def test_invariant_regex_catches_synthetic_violation():
    """The detector must flag a real coupling — proves the guard is not a no-op
    that would pass no matter what."""
    single_line = 'current_phase = try_get_work(agent_id="x")["phase"]'
    two_line = (
        "result = get_work(task_types=[\"plan\"])\n"
        "    state.current_phase = result[\"phase\"]"
    )
    endpoint_form = 'phase = http_post("/work/claim")["current_phase"]'

    assert _VIOLATION.search(single_line), "single-line coupling not detected"
    assert _VIOLATION.search(two_line), "two-line coupling not detected"
    assert _VIOLATION.search(endpoint_form), "endpoint-form coupling not detected"


def test_invariant_regex_allows_decoupled_usage():
    """Legitimate, decoupled usage must NOT trip the guard: a claim call with no
    nearby phase-authority symbol, and a loop-state read with no nearby claim."""
    claim_only = "task = try_get_work(agent_id=aid, agent_type=at)"
    loopstate_only = "state.current_phase = transition(state, outcome)"
    assert not _VIOLATION.search(claim_only)
    assert not _VIOLATION.search(loopstate_only)


def test_guard_actually_runs():
    """Sanity: the scan examines a non-empty set of skill sources."""
    files = _collect_skill_sources()
    assert files, "No skill .py sources found — guard is a no-op"
