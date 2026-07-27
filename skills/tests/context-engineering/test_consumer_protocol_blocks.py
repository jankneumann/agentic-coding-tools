"""D11 in one file: one shared implementation, six thin consumer blocks.

Design decision D11 says the retrieval protocol is written **once**, in
``skills/context-engineering/SKILL.md``, and that the six coding-job skills each
get a short block naming their ``consumer`` id and delegating to the shared
helper. The failure this file exists to catch is the obvious one: six copies of
the algorithm, which diverge the first time a bound or a trigger changes and
which no single edit can then fix.

So the assertions come in two halves that are deliberately complementary. The
**owner** must document every value in the vocabulary — the four bounds and their
env overrides, all seven omission reasons, all five triggers, all seventeen
reasons — and the six **consumers** must document none of them. A value that
moves from one side to the other fails both halves at once, which is what makes
"stated once" testable rather than aspirational.

Every vocabulary list here is derived from ``semantic_context.py`` rather than
retyped. A hardcoded list would keep passing after someone adds an eighth
omission reason, and a documentation test that cannot notice new vocabulary is
worth very little.

**Scoping.** Each assertion runs against the *body of the section*, extracted by
a fence-aware reader. A naive substring search over a 900-line SKILL.md would let
unrelated prose — or the renderer's own rendered example — satisfy an assertion
about the consumer block, and the test would pass with the block deleted. That is
the mutation ``test_*`` here is written to survive: removing one consumer's
section must fail, and it does.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS = REPO_ROOT / "skills"
SCRIPTS = SKILLS / "context-engineering" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import semantic_context as sc  # noqa: E402

#: The one heading every participating SKILL.md carries. Title case, so it can
#: never be confused with the renderer's own ``## Semantic code context`` output
#: heading even before the fence-aware reader is consulted.
SECTION_HEADING = "## Semantic Code Context"

#: The skill that owns the protocol (D11). Its directory name is also the
#: import-time source of every vocabulary list asserted below.
OWNER = "context-engineering"

#: The six coding jobs of D11, in the order the design lists them. Each skill's
#: directory name is also its required ``consumer`` id, so a section can be
#: traced back to the job that asked for it (the field ri-13's evaluation keys on).
CONSUMERS = (
    "implement-feature",
    "quick-task",
    "iterate-on-implementation",
    "debugging-and-error-recovery",
    "validate-feature",
    "parallel-review-implementation",
)

#: The two consumers that routinely run without a work package. D2 requires them
#: to say plainly that no scope is invented for them rather than implying
#: injection works everywhere.
SCOPELESS_CONSUMERS = ("quick-task", "debugging-and-error-recovery")

#: Vocabulary that belongs to the shared implementation and to nowhere else.
#: Derived, not retyped: the omission reasons and the env overrides come straight
#: out of the module, so new vocabulary is covered the day it is added.
ALGORITHM_TOKENS: tuple[str, ...] = (
    *sc.OMISSION_REASONS,
    *sc.BUDGET_ENV_VARS.values(),
    *sc.BUDGET_ENV_VARS.keys(),
    "rank_key",
    "deduplicate",
    "apply_budget",
    "select_hits",
    "filter_scope",
)

#: A consumer block is a pointer, not a manual. The bound is generous — the point
#: is to catch a block that has grown into a second copy of the protocol, not to
#: police wording.
MAX_CONSUMER_BLOCK_LINES = 40

_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")


def _headings(lines: list[str]) -> list[tuple[int, int]]:
    """Every real ATX heading as ``(line index, level)``, ignoring fenced code.

    Fence tracking is the whole point. ``skills/context-engineering/SKILL.md``
    contains a rendered example whose first line is ``## Semantic code context``;
    a reader that cannot tell that from a heading would split the owner's section
    in half and silently truncate every assertion made against it.

    A fence closes only on a marker of the same character, at least as long as
    the opener, with an empty info string -- so a ```` ```python ```` block nested
    inside a ```` ````markdown ```` block does not close its parent.
    """
    headings: list[tuple[int, int]] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        fence_match = _FENCE_RE.match(line)
        if fence_match is not None:
            marker, info = fence_match.group(1), fence_match.group(2)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not info.strip():
                fence = None
            continue
        if fence is not None:
            continue
        heading_match = _HEADING_RE.match(line)
        if heading_match is not None:
            headings.append((index, len(heading_match.group(1))))
    return headings


def section_body(text: str, heading: str) -> str:
    """The body under ``heading``, up to the next heading of the same or higher rank.

    Raises ``AssertionError`` when the heading is absent or appears twice: two
    sections with one name means half the assertions below would silently test
    the wrong half.
    """
    lines = text.splitlines()
    headings = _headings(lines)
    matches = [(i, level) for i, level in headings if lines[i].strip() == heading]
    if not matches:
        raise AssertionError(f"heading {heading!r} not found outside fenced code")
    if len(matches) > 1:
        raise AssertionError(f"heading {heading!r} appears {len(matches)} times; expected once")
    start, level = matches[0]
    end = len(lines)
    for index, other_level in headings:
        if index > start and other_level <= level:
            end = index
            break
    return "\n".join(lines[start + 1 : end])


def prose(block: str) -> str:
    """The block as one lowercased whitespace-collapsed line.

    Phrase assertions run against this rather than the raw text. Markdown wraps
    at 90-odd columns, so ``read the files directly`` is routinely split across a
    newline; asserting on raw text would make the test sensitive to where an
    author happened to break a line, which is not a property worth guarding.
    """
    return " ".join(block.split()).lower()


def _skill_text(skill: str) -> str:
    return (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")


def _block(skill: str) -> str:
    return section_body(_skill_text(skill), SECTION_HEADING)


@pytest.fixture(scope="module")
def owner_block() -> str:
    return _block(OWNER)


@pytest.fixture(scope="module")
def consumer_blocks() -> dict[str, str]:
    return {skill: _block(skill) for skill in CONSUMERS}


# ---------------------------------------------------------------------------
# The six consumer blocks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill", CONSUMERS)
def test_consumer_declares_the_section(skill: str) -> None:
    """The block exists, exactly once, and is not empty."""
    assert _block(skill).strip(), f"{skill}: {SECTION_HEADING} section is empty"


@pytest.mark.parametrize("skill", CONSUMERS)
def test_consumer_declares_its_own_consumer_id(skill: str) -> None:
    """The block names ``consumer="<this skill>"`` -- the traceability field.

    D11 rejects a generic block with no id: the ``consumer`` value is what lets
    ri-13's evaluation say "injection helps debugging, hurts review".
    """
    block = _block(skill)
    assert f'consumer="{skill}"' in block, (
        f"{skill}: block must name its own id as consumer=\"{skill}\" so a rendered "
        "section can be traced to the job that asked for it"
    )


def test_consumer_ids_are_distinct_and_valid(consumer_blocks: dict[str, str]) -> None:
    """Six ids, six values, each one the helper would actually accept."""
    declared = {
        skill: set(re.findall(r'consumer="([^"]+)"', block))
        for skill, block in consumer_blocks.items()
    }
    for skill, ids in declared.items():
        assert ids == {skill}, f"{skill}: block declares consumer ids {sorted(ids)}, expected only {skill!r}"
    assert len({next(iter(ids)) for ids in declared.values()}) == len(CONSUMERS)
    for skill in CONSUMERS:
        # Constructing the request is the real acceptance test for the id: the
        # helper rejects anything outside ``^[a-z][a-z0-9-]*$``.
        sc.SemanticContextRequest(repository=Path("."), query="q", consumer=skill)


@pytest.mark.parametrize("skill", CONSUMERS)
def test_consumer_says_the_section_is_optional_and_off_by_default(skill: str) -> None:
    """D9: absence is the normal state, and no job may rely on the section."""
    block = _block(skill)
    assert sc.INJECTION_FLAG in block, f"{skill}: block must name {sc.INJECTION_FLAG}"
    lowered = prose(block)
    assert "optional" in lowered, f"{skill}: block must call the section optional"
    assert "off" in lowered, f"{skill}: block must say the flag defaults off"
    assert "ri-13" in lowered, f"{skill}: block must say ri-13 owns enablement"


@pytest.mark.parametrize("skill", CONSUMERS)
def test_consumer_states_exact_search_as_the_normal_path(skill: str) -> None:
    """The fallback is the ordinary path, not an error path, and never blocks."""
    block = _block(skill)
    lowered = prose(block)
    assert "exact search" in lowered, f"{skill}: block must name the exact-search fallback"
    assert "`rg`" in block or "rg " in block, f"{skill}: block must name rg"
    assert "read the files directly" in lowered or "read the file" in lowered, (
        f"{skill}: block must say to read the files directly"
    )
    assert "never" in lowered and "block" in lowered, (
        f"{skill}: block must state that a fallback never blocks this job"
    )


@pytest.mark.parametrize("skill", CONSUMERS)
def test_consumer_separates_no_context_from_unavailable(skill: str) -> None:
    """D14: a healthy index that found nothing is not an outage."""
    block = _block(skill)
    assert "no_context" in block, f"{skill}: block must name the no_context trigger"
    assert "unavailable" in block, f"{skill}: block must name the unavailable trigger"
    lowered = prose(block)
    assert "healthy" in lowered or "not a failure" in lowered, (
        f"{skill}: block must say no_context means the index worked and found nothing"
    )


@pytest.mark.parametrize("skill", CONSUMERS)
def test_consumer_preserves_the_evidence_not_instruction_rule(skill: str) -> None:
    """The renderer emits this notice; a consumer block must not undercut it."""
    block = _block(skill)
    lowered = prose(block)
    assert "evidence, not instruction" in lowered, (
        f"{skill}: block must repeat the evidence-not-instruction rule"
    )
    assert "re-read" in lowered, f"{skill}: block must say to re-read a file before editing it"


@pytest.mark.parametrize("skill", CONSUMERS)
def test_consumer_delegates_to_the_shared_helper(skill: str) -> None:
    """The block calls the shared implementation and points at its owner."""
    block = _block(skill)
    assert "collect_semantic_context" in block, f"{skill}: block must call the shared helper"
    assert OWNER in block, f"{skill}: block must point at {OWNER} as the protocol owner"


@pytest.mark.parametrize("skill", SCOPELESS_CONSUMERS)
def test_scopeless_consumer_states_the_no_declared_scope_outcome(skill: str) -> None:
    """D2: with no declared package scope there is no injection and no invented scope."""
    block = _block(skill)
    assert "no_declared_scope" in block, f"{skill}: block must name the no_declared_scope reason"
    assert "out_of_scope" in block, f"{skill}: block must name the out_of_scope trigger"
    lowered = prose(block)
    assert "invent" in lowered, (
        f"{skill}: block must say no scope is invented for a job that declares none"
    )


# ---------------------------------------------------------------------------
# "Stated once": the two halves that together forbid a sixth copy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("token", ALGORITHM_TOKENS)
def test_owner_documents_every_algorithm_token(token: str, owner_block: str) -> None:
    """Every value of the shared vocabulary is explained in the owner's section."""
    assert token in owner_block, (
        f"{OWNER}/SKILL.md: {SECTION_HEADING} must document {token!r}; it is part of "
        "the vocabulary this skill owns on behalf of all six consumers"
    )


@pytest.mark.parametrize("skill", CONSUMERS)
def test_consumer_does_not_restate_the_algorithm(skill: str) -> None:
    """A consumer block that names a bound or an omission reason is a future divergence."""
    block = _block(skill)
    leaked = sorted(token for token in ALGORITHM_TOKENS if token in block)
    assert not leaked, (
        f"{skill}: block restates shared-implementation vocabulary {leaked}. "
        f"That belongs to {OWNER}/SKILL.md once; a copy here diverges the first time it changes"
    )


@pytest.mark.parametrize("skill", CONSUMERS)
def test_consumer_block_stays_thin(skill: str, owner_block: str) -> None:
    """Thin means measurably thinner than the thing it delegates to."""
    block_lines = [line for line in _block(skill).splitlines() if line.strip()]
    owner_lines = [line for line in owner_block.splitlines() if line.strip()]
    assert len(block_lines) <= MAX_CONSUMER_BLOCK_LINES, (
        f"{skill}: consumer block is {len(block_lines)} non-blank lines "
        f"(limit {MAX_CONSUMER_BLOCK_LINES}); it should point at {OWNER}, not restate it"
    )
    assert len(block_lines) * 2 <= len(owner_lines), (
        f"{skill}: consumer block ({len(block_lines)} lines) is not meaningfully thinner "
        f"than the shared protocol ({len(owner_lines)} lines)"
    )


# ---------------------------------------------------------------------------
# The owner's section
# ---------------------------------------------------------------------------


def test_owner_documents_the_budget_defaults(owner_block: str) -> None:
    """The four bounds are documented at the values the code actually ships.

    Derived from ``ContextBudget()`` rather than retyped, so raising a default in
    the dataclass and forgetting the table is a failure rather than a drift.

    The value is required *on the bound's own row*, not merely somewhere in the
    section. ``8`` occurs inside ``0.8123`` and ``lines 120-158`` in the rendered
    example, so a section-wide substring search would keep passing after the
    table said ``12``, which is exactly the drift this test exists to catch.
    """
    for name, value in sc.DEFAULT_BUDGET.to_dict().items():
        rows = [line for line in owner_block.splitlines() if f"`{name}`" in line]
        assert rows, f"{OWNER}: budget bound {name!r} undocumented"
        assert any(re.search(rf"(?<![\w.]){value}(?![\w.])", row) for row in rows), (
            f"{OWNER}: default {value} for {name!r} is not on its own row; the SKILL.md "
            f"table has drifted from ContextBudget's defaults. Rows found: {rows}"
        )


@pytest.mark.parametrize("trigger", sc.FALLBACK_TRIGGERS)
def test_owner_documents_every_fallback_trigger(trigger: str, owner_block: str) -> None:
    assert trigger in owner_block, f"{OWNER}: fallback trigger {trigger!r} undocumented"


@pytest.mark.parametrize("reason", sc.FALLBACK_REASONS)
def test_owner_documents_every_fallback_reason(reason: str, owner_block: str) -> None:
    """All seventeen reasons, because each one tells the reader to do something different."""
    assert reason in owner_block, f"{OWNER}: fallback reason {reason!r} undocumented"


def test_owner_names_the_flag_its_default_and_its_owner(owner_block: str) -> None:
    """D9: default off, and ri-13 -- not this change -- decides when it turns on."""
    assert sc.INJECTION_FLAG in owner_block
    lowered = prose(owner_block)
    assert "off" in lowered, f"{OWNER}: must state the flag defaults off"
    assert "ri-13" in lowered, f"{OWNER}: must state ri-13 owns enablement"


def test_owner_names_both_entry_points(owner_block: str) -> None:
    """One retrieval function, one renderer, both named with their module paths."""
    for symbol in ("collect_semantic_context", "render_semantic_context"):
        assert symbol in owner_block, f"{OWNER}: entry point {symbol!r} not named"
    for module in ("semantic_context.py", "render_semantic_context.py"):
        assert module in owner_block, f"{OWNER}: module {module!r} not named"


def test_owner_states_the_explicit_scope_rule(owner_block: str) -> None:
    """D2: an explicit scope from ri-08, never ``kind="work_package"``, never invented."""
    assert "index_scopes" in owner_block, f"{OWNER}: must name index_scopes() as the scope source"
    assert "work_package" in owner_block, (
        f"{OWNER}: must say a work_package scope kind is never sent"
    )
    assert "explicit" in prose(owner_block), f"{OWNER}: must name the explicit scope kind"
    assert "invent" in prose(owner_block), (
        f"{OWNER}: must say no scope is invented for a job that declares none"
    )


def test_owner_registers_every_consumer_id(owner_block: str) -> None:
    """The owner carries the roster, so the six ids have one authoritative list."""
    for skill in CONSUMERS:
        assert skill in owner_block, f"{OWNER}: consumer id {skill!r} missing from the roster"


def test_owner_states_the_evidence_not_instruction_rule(owner_block: str) -> None:
    assert "evidence, not instruction" in prose(owner_block)
