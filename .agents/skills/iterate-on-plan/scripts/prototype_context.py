"""Prototype context loader for /iterate-on-plan --prototype-context.

Per D1, /iterate-on-plan gains a --prototype-context <change-id> flag.
When present, this loader reads the prototype-findings.md the
/prototype-feature skill produced, parses the embedded JSON blocks
into VariantDescriptor objects, and computes a synthesis_plan via the
parallel-infrastructure synthesizer. The SKILL workflow then feeds
that context into its iteration loop and emits convergence.* findings
to refine design.md and tasks.md.

Spec scenarios:
  - ConvergenceViaIterateOnPlan.convergence-mode-activated
  - ConvergenceViaIterateOnPlan.convergence-without-context (no auto-load)
  - ConvergenceViaIterateOnPlan.missing-prototype-artifacts (fail fast)

The loader has NO auto-discovery — convergence mode must always be
explicit. The SKILL workflow only calls this function when --prototype-
context is in argv.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The variant-descriptor module lives under parallel-infrastructure;
# add it to sys.path defensively so this loader works whether iterate-
# on-plan is invoked from the canonical skills/ tree or from a runtime
# mirror that doesn't co-locate the modules.
_HERE = Path(__file__).resolve()
for candidate in (
    _HERE.parents[2] / "parallel-infrastructure" / "scripts",
    _HERE.parents[3] / "parallel-infrastructure" / "scripts",
):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from variant_descriptor import VariantDescriptor, synthesize_variants  # noqa: E402

FINDINGS_FILENAME = "prototype-findings.md"


class PrototypeContextMissing(FileNotFoundError):
    """Raised when --prototype-context was passed but the artifacts
    needed to load convergence context are absent or unreadable.

    The SKILL workflow MUST surface this as a fail-fast error rather
    than silently downgrading to non-convergence iteration — the user
    explicitly asked for prototype-aware refinement, and a missing
    findings file means we can't honor that request.
    """


@dataclass
class PrototypeContext:
    """Bundle of artifacts iterate-on-plan needs for convergence-aware refinement."""

    change_id: str
    descriptors: list[VariantDescriptor] = field(default_factory=list)
    synthesis_plan: dict[str, Any] = field(default_factory=dict)


def _extract_json_blocks(markdown_text: str) -> list[dict[str, Any]]:
    """Pull every ```json ... ``` block out of the findings markdown.

    The companion writer (collect_outcomes.write_findings_file) emits
    one JSON block per variant; reversing that here is straightforward
    line-based parsing rather than reaching for a markdown library.
    """
    blocks: list[dict[str, Any]] = []
    in_block = False
    buffer: list[str] = []
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped == "```json":
            in_block = True
            buffer = []
            continue
        if stripped == "```" and in_block:
            try:
                blocks.append(json.loads("\n".join(buffer)))
            except json.JSONDecodeError:
                # Malformed block — skip silently; the descriptor count
                # check below will trigger PrototypeContextMissing if
                # we end up with zero usable descriptors.
                pass
            in_block = False
            continue
        if in_block:
            buffer.append(line)
    return blocks


def load_prototype_context(*, change_dir: Path) -> PrototypeContext:
    """Load and parse prototype-findings.md from a change directory.

    Returns a PrototypeContext with parsed descriptors and a synthesis
    plan ready for the iterate-on-plan SKILL workflow to consume.

    Raises PrototypeContextMissing when the findings file is absent or
    contains no parseable VariantDescriptor blocks.
    """
    findings_path = change_dir / FINDINGS_FILENAME
    if not findings_path.is_file():
        raise PrototypeContextMissing(
            f"prototype-findings.md not found at {findings_path}. "
            "Run /prototype-feature first."
        )

    blocks = _extract_json_blocks(findings_path.read_text())
    descriptors: list[VariantDescriptor] = []
    for block in blocks:
        try:
            descriptors.append(VariantDescriptor.from_dict(block))
        except (KeyError, TypeError, ValueError):
            # Skip malformed blocks — they may be sample/comment blocks
            # rather than real descriptors. The total-count guard below
            # ensures we still fail fast when nothing usable is left.
            continue

    if not descriptors:
        raise PrototypeContextMissing(
            f"prototype-findings.md at {findings_path} contained no usable "
            "VariantDescriptor blocks. The file may be empty, malformed, "
            "or written by an incompatible tool. Re-run /prototype-feature."
        )

    change_id = change_dir.name
    plan = synthesize_variants(descriptors, change_id=change_id)
    return PrototypeContext(
        change_id=change_id, descriptors=descriptors, synthesis_plan=plan
    )


__all__ = [
    "FINDINGS_FILENAME",
    "PrototypeContext",
    "PrototypeContextMissing",
    "load_prototype_context",
]
