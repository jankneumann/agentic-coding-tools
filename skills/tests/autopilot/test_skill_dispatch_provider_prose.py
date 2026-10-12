"""`skills/autopilot/SKILL.md` names `provider` at every phase dispatch site.

Spec: openspec/changes/add-infeasible-incumbent-fallback design D1
      (agent-archetypes.11 — "A harness without a provider adapter escalates").
      `build_phase_dispatch_kwargs` (phase_agent.py) always emits `provider` in
      its JSON payload now; this test guards that SKILL.md's prose actually
      tells the dispatching agent to pass it through. Modelled on
      `test_prose_free_gates.py`'s "a grep cannot express that, so this file
      does" approach.

Rule under test: a harness whose only adapter is `Agent(...)` MUST route a
non-`claude_code` `provider` through the provider-neutral adapter or escalate
— it never calls `Agent(...)` with another vendor's model. SKILL.md documents
this once, in the shared 8-phase protocol intro, and names `provider` in every
individual phase's adapter-call sentence (the sentence that follows its
`runner.py build-dispatch` invocation).
"""

from __future__ import annotations

import re
from pathlib import Path

_SKILL_MD = Path(__file__).resolve().parents[2] / "autopilot" / "SKILL.md"

# A `runner.py ... build-dispatch \` invocation line, immediately followed
# (next line) by its `--phase <PHASE>` continuation. Every per-phase dispatch
# block in SKILL.md shells out this way (see the "Build dispatch kwargs" /
# "Build kwargs" steps throughout).
_BUILD_DISPATCH_RE = re.compile(
    r'runner\.py"\s+build-dispatch\s*\\\s*\n\s*--phase\s+(\w+)',
)

_EXPECTED_DISPATCH_COUNT = 8


def _skill_text() -> str:
    return _SKILL_MD.read_text(encoding="utf-8")


def _build_dispatch_occurrences(text: str) -> list["re.Match[str]"]:
    return list(_BUILD_DISPATCH_RE.finditer(text))


def test_exactly_eight_build_dispatch_invocations() -> None:
    """The 8-phase protocol (GATEKEEPER + 7 write-capable/review phases)."""
    text = _skill_text()
    matches = _build_dispatch_occurrences(text)
    phases = [m.group(1) for m in matches]
    assert len(matches) == _EXPECTED_DISPATCH_COUNT, (
        f"expected {_EXPECTED_DISPATCH_COUNT} `runner.py build-dispatch` "
        f"invocations in {_SKILL_MD}, found {len(matches)}: {phases}"
    )
    # Phase names must be distinct — a duplicate would mean one phase's block
    # was pasted twice rather than another phase's block going missing.
    assert len(set(phases)) == len(phases), (
        f"{_SKILL_MD} has duplicate `--phase` dispatch blocks: {phases}"
    )


def test_every_build_dispatch_adapter_call_names_provider() -> None:
    """The adapter-call sentence that follows each `build-dispatch` must name
    `provider` — the text between one invocation and the next (or EOF for the
    last one)."""
    text = _skill_text()
    matches = _build_dispatch_occurrences(text)
    assert matches, f"no `runner.py build-dispatch` invocations found in {_SKILL_MD}"

    missing = []
    for i, match in enumerate(matches):
        window_start = match.end()
        window_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        window = text[window_start:window_end]
        if "provider" not in window:
            missing.append(match.group(1))

    assert not missing, (
        f"{_SKILL_MD}: the adapter-call sentence following "
        f"`build-dispatch --phase X` does not name `provider` for phases: "
        f"{missing}"
    )


def test_protocol_intro_states_the_harness_routing_rule() -> None:
    """The shared 8-phase protocol intro documents: a harness whose only
    adapter is `Agent(...)` must route a non-`claude_code` provider through
    the provider-neutral adapter or escalate — it never calls `Agent(...)`
    with another vendor's model."""
    text = _skill_text()
    route_match = re.search(
        r"route\w*\s+a\s+non-`?claude_code`?\s+`?provider`?\s+through\s+the\s+"
        r"provider-neutral\s+adapter\b",
        text,
    )
    assert route_match, (
        f"{_SKILL_MD} is missing the 'route a non-claude_code provider through "
        "the provider-neutral adapter' rule sentence (agent-archetypes.11)"
    )
    # "...or escalate" closes the same sentence, within a short window after
    # the matched phrase (not merely somewhere later in the document).
    tail = text[route_match.end() : route_match.end() + 200]
    assert re.search(r"\bor\s+escalate\b", tail), (
        f"{_SKILL_MD}'s provider-routing rule sentence does not close with "
        "'or escalate' (agent-archetypes.11)"
    )
    assert re.search(
        r"never\s+calls\s+`?Agent\(\.\.\.\)`?\s+with\s+another\s+vendor's\s+model",
        text,
    ), (
        f"{_SKILL_MD} is missing the 'never calls Agent(...) with another "
        "vendor's model' rule sentence"
    )


def test_json_dispatch_contract_names_provider() -> None:
    """The `runner.py build-dispatch` JSON output contract (documented once in
    the protocol intro) must list `provider` as a field."""
    text = _skill_text()
    assert re.search(r"\{prompt,[^}]*\bprovider\b[^}]*\}", text), (
        f"{_SKILL_MD}'s documented build-dispatch JSON contract does not list "
        "`provider`"
    )
