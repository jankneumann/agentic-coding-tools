"""Contract test: the readers ensure at the read boundary; the checkpoint never does.

D1 moves freshness responsibility to the party that needs the artifacts current —
the skill about to read them — and fixes the moment: immediately before the first
read, not at skill start. D8 keeps ``checkpoint.py`` out of that set, because
ri-09 D1/D10 make the operation ledger a reporter and a reporter that regenerates
its own evidence produces a non-reproducible report.

Both halves are pinned here because both are easy to lose in opposite directions.
The positive half decays into "someone reads a stale graph and never notices"; the
negative half decays into "the checkpoint quietly rewrites ~23 MB of *tracked*
artifacts on a stale branch" — this repository commits its committed-tier
artifacts, so an unwanted ``--ensure`` dirties the working tree rather than
scribbling in an ignored directory.

Scope note: this suite deliberately pins the call sites in each consumer's
``SKILL.md`` and not inside the analyzer scripts those steps run
(``validate_flows.py``, ``analyze_coupling.py``, ``validate_schema.py``). Those
scripts take an explicit artifact path, are run against fixtures with no
repository, and are pure readers. Making them regenerate would apply the exact
posture change D8 refuses for the checkpoint, to a script whose caller may have
handed it a path in a temporary directory.

Spec scenarios: project-context-refresh-orchestration *Consumer regenerates stale
artifacts before reading*, *Checkpoint reports rather than ensures*.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SKILLS_ROOT = _REPO_ROOT / "skills"

#: The six artifact readers D1 names. `checkpoint.py` is deliberately absent.
CONSUMER_SKILLS = (
    "explore-feature",
    "plan-feature",
    "validate-feature",
    "tech-debt-analysis",
    "validate-flows",
    "validate-packages",
)

#: Consumers whose SKILL.md names an artifact inside a runnable block, so the
#: "ensure comes first" assertion has something to be ordered against. Pinned as
#: a constant rather than derived, because a derived-only check goes green by
#: going vacuous the moment a code block stops naming an artifact.
SKILLS_WITH_CODE_BLOCK_READS = ("plan-feature", "validate-feature", "validate-flows")

ARTIFACT_NAMES = (
    "architecture.graph.json",
    "architecture.summary.json",
    "parallel_zones.json",
)

CHECKPOINT = _SKILLS_ROOT / "project-context-refresh" / "scripts" / "checkpoint.py"

#: The runner invocation, however the skill spells its skills-directory prefix.
_ENSURE_CALL = re.compile(r"run_architecture\.py\"?\s*\\?\s*--ensure")

#: The whole shared block, so the six can be compared for textual identity.
_ENSURE_BLOCK = re.compile(
    r"# Ensure architecture artifacts are current.*?\nfi\b", re.DOTALL
)

#: `make architecture` — the unconditional in-place producer the ensure call
#: replaces. `make architecture-diff` is a different target and stays.
_BARE_MAKE_ARCHITECTURE = re.compile(r"make architecture(?![-\w])")

_FENCE = re.compile(r"^```", re.MULTILINE)

#: Prefixes the skills use to reach a sibling skill's scripts. Normalised away
#: before comparing call sites, since the prefix is the one legitimate variation.
_PREFIXES = ("<skill-base-dir>/../", "<agent-skills-dir>/")


def _skill_md(skill: str) -> str:
    return (_SKILLS_ROOT / skill / "SKILL.md").read_text(encoding="utf-8")


def _code_spans(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` offsets of every fenced code block *body*.

    Fences are paired in document order. Prose that merely mentions an artifact
    path is not a read; a fenced command that names one is.
    """
    fences = [m.start() for m in _FENCE.finditer(text)]
    assert len(fences) % 2 == 0, "unbalanced ``` fences"
    spans = []
    for open_pos, close_pos in zip(fences[0::2], fences[1::2]):
        body_start = text.index("\n", open_pos) + 1
        spans.append((body_start, close_pos))
    return spans


def _in_code(offset: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in spans)


def _code_offsets(text: str, pattern: re.Pattern[str]) -> list[int]:
    spans = _code_spans(text)
    return [m.start() for m in pattern.finditer(text) if _in_code(m.start(), spans)]


def _first_artifact_read(text: str) -> int | None:
    offsets = [
        offset
        for name in ARTIFACT_NAMES
        for offset in _code_offsets(text, re.compile(re.escape(name)))
    ]
    return min(offsets) if offsets else None


class TestConsumersEnsureBeforeReading:
    """D1: one ensure call, in a fenced block, ahead of the first read."""

    @pytest.mark.parametrize("skill", CONSUMER_SKILLS)
    def test_skill_invokes_ensure_exactly_once(self, skill: str) -> None:
        offsets = _code_offsets(_skill_md(skill), _ENSURE_CALL)
        assert len(offsets) == 1, (
            f"{skill}/SKILL.md must invoke run_architecture.py --ensure exactly "
            f"once, in a runnable block, at the top of its artifact-reading step "
            f"(D1); found {len(offsets)}. Freshness is ensured at the read "
            f"boundary, not at skill start and not once per artifact."
        )

    @pytest.mark.parametrize("skill", SKILLS_WITH_CODE_BLOCK_READS)
    def test_ensure_precedes_the_first_artifact_read(self, skill: str) -> None:
        text = _skill_md(skill)
        ensure = _code_offsets(text, _ENSURE_CALL)[0]
        first_read = _first_artifact_read(text)
        assert first_read is not None, (
            f"{skill}/SKILL.md no longer names an architecture artifact in a "
            f"runnable block, so this ordering check has gone vacuous. Either "
            f"restore the read or drop {skill} from SKILLS_WITH_CODE_BLOCK_READS "
            f"with a reason."
        )
        assert ensure < first_read, (
            f"{skill}/SKILL.md reads an architecture artifact at offset "
            f"{first_read} before ensuring freshness at offset {ensure}. The "
            f"ensure call belongs at the top of the artifact-reading step (D1)."
        )

    def test_the_pinned_readers_really_do_read_in_code(self) -> None:
        """The ordering assertion above must not be able to pass by vacuity."""
        for skill in SKILLS_WITH_CODE_BLOCK_READS:
            assert _first_artifact_read(_skill_md(skill)) is not None, (
                f"{skill} is pinned as a code-block reader but its SKILL.md has "
                f"no artifact path inside a fenced block."
            )

    @pytest.mark.parametrize("skill", CONSUMER_SKILLS)
    def test_call_site_is_the_shared_block(self, skill: str) -> None:
        """One recognisable pattern across the six, modulo the path prefix."""
        text = _skill_md(skill)
        blocks = _ENSURE_BLOCK.findall(text)
        assert len(blocks) == 1, (
            f"{skill}/SKILL.md should carry exactly one copy of the shared "
            f"ensure block; found {len(blocks)}."
        )

    def test_the_six_call_sites_are_textually_identical(self) -> None:
        normalised = {}
        for skill in CONSUMER_SKILLS:
            block = _ENSURE_BLOCK.search(_skill_md(skill))
            assert block is not None, f"{skill}/SKILL.md has no ensure block"
            text = block.group(0)
            for prefix in _PREFIXES:
                text = text.replace(prefix, "<SKILLS>/")
            normalised.setdefault(text, []).append(skill)
        assert len(normalised) == 1, (
            "The six consumers must share one recognisable ensure block; they "
            "diverge into groups: "
            + "; ".join(str(v) for v in normalised.values())
        )

    @pytest.mark.parametrize("skill", CONSUMER_SKILLS)
    def test_no_unconditional_make_architecture_remains(self, skill: str) -> None:
        """`make architecture` writes on every run; `--ensure` writes only when stale."""
        offsets = _code_offsets(_skill_md(skill), _BARE_MAKE_ARCHITECTURE)
        assert offsets == [], (
            f"{skill}/SKILL.md still runs `make architecture` at offsets "
            f"{offsets}. It regenerates unconditionally — on this repository, "
            f"where the committed-tier artifacts are tracked, that dirties the "
            f"working tree even when nothing changed. Use the ensure block."
        )


def _checkpoint_literals() -> list[str]:
    """Every string literal in ``checkpoint.py`` that is not a docstring.

    Its prose legitimately mentions ``run_architecture.py --check`` — it explains
    that it reimplements that call *without* a subprocess. A grep over raw source
    would read that sentence as a call site, so only real literals are examined.
    """
    source = CHECKPOINT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and ast.get_docstring(node, clean=False) is not None
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    ]


class TestCheckpointNeverEnsures:
    """D8 / ri-09 D3: the checkpoint reports drift as data and stays read-only."""

    @pytest.mark.parametrize(
        "forbidden", ("--ensure", "run_architecture.py", "refresh_architecture.sh")
    )
    def test_no_literal_invokes_the_refresh_pipeline(self, forbidden: str) -> None:
        offenders = [lit for lit in _checkpoint_literals() if forbidden in lit]
        assert offenders == [], (
            f"checkpoint.py contains the literal {forbidden!r} in {offenders!r}. "
            f"The branch-local checkpoint reports architecture freshness as a "
            f"finding and never regenerates it (D8): a reporter that rewrites "
            f"its own evidence yields a non-reproducible report, and here it "
            f"would dirty tracked artifacts on any stale branch."
        )

    def test_checkpoint_still_reports_architecture_freshness(self) -> None:
        """The negative pin must not be satisfiable by dropping the reporting."""
        tree = ast.parse(CHECKPOINT.read_text(encoding="utf-8"))
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        for required in ("architecture_freshness", "ArchitectureFinding"):
            assert required in names, (
                f"checkpoint.py no longer defines {required}. D8 keeps the "
                f"checkpoint out of the ensure set precisely because it still "
                f"*reports* freshness; removing the report is not the pin."
            )
