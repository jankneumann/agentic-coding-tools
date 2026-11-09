"""Semantic evaluation via a calibrated Noul judgment (D4, D9).

Judges whether a step's actual output satisfies the semantic criteria
specified in a SemanticBlock by asking a single calibrated Noul question
through ``system_one_decisions.decide()`` (see design.md D1 of
``replace-the-gen-eval-semantic-judge-with-a-calibrated-noul``), rather than
parsing a self-reported confidence out of free-text LLM output. The existing
LLM backend infrastructure (CLIBackend, SDKBackend, AdaptiveBackend) is used
only to generate human-readable reasoning prose for items that fail the
noul threshold.

Verdicts are additive: they enhance but never override structural
verdicts. When the decision helper is unavailable, produces ``skip`` not
``failure``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from types import ModuleType
from typing import Any, Protocol

from .models import SemanticBlock, SemanticVerdict

system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None

logger = logging.getLogger(__name__)

_JUDGE_SYSTEM = """\
You are an evaluation judge. Given a step's actual output and evaluation criteria,
determine whether the output satisfies the criteria.

Respond with ONLY a JSON object (no markdown fences):
{
  "pass": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}
"""


class LLMBackend(Protocol):
    """Protocol for LLM backends compatible with semantic evaluation."""

    async def run(self, prompt: str, system: str | None = None) -> str: ...

    async def is_available(self) -> bool: ...


async def evaluate_semantic(
    backend: LLMBackend,
    semantic: SemanticBlock,
    actual_output: dict[str, Any],
    step_id: str,
) -> SemanticVerdict:
    """Judge a step's output against semantic criteria.

    Args:
        backend: LLM backend (CLIBackend, SDKBackend, or AdaptiveBackend),
            invoked only to produce reasoning prose when the noul judgment
            fails the confidence threshold.
        semantic: SemanticBlock with criteria and confidence threshold.
        actual_output: The step's actual response body/data.
        step_id: For logging context.

    Returns:
        SemanticVerdict with pass/fail/skip status.
    """
    if not semantic.judge:
        return SemanticVerdict(status="skip", reasoning="Semantic evaluation disabled")

    criteria_text = semantic.criteria or "Does the output look correct and complete?"

    if system_one_decisions is None:
        logger.warning(
            "system_one_decisions not installed; skipping semantic eval on step '%s'", step_id
        )
        return SemanticVerdict(status="skip", reasoning="LLM backend unavailable")

    state = {"criteria": criteria_text, "actual_output": actual_output}
    questions = {
        "satisfies": {"type": "noul", "instructions": "The actual output satisfies the criteria"}
    }
    # decide() makes a synchronous network call when the live extra is
    # configured; run it off the event loop so a live judgment doesn't block
    # every other scenario the orchestrator is evaluating concurrently.
    answers = await asyncio.to_thread(
        system_one_decisions.decide, state, questions, site="gen_eval.semantic_judge"
    )

    if answers is None:
        logger.warning("decide() unavailable for semantic eval on step '%s'", step_id)
        return SemanticVerdict(status="skip", reasoning="LLM backend unavailable")

    confidence = max(0.0, min(1.0, float(answers["satisfies"].noul)))

    if confidence >= semantic.min_confidence:
        return SemanticVerdict(status="pass", confidence=confidence)

    reasoning = await _generate_failure_reasoning(backend, criteria_text, actual_output, step_id)
    return SemanticVerdict(status="fail", confidence=confidence, reasoning=reasoning)


async def _generate_failure_reasoning(
    backend: LLMBackend,
    criteria_text: str,
    actual_output: dict[str, Any],
    step_id: str,
) -> str:
    """Produce human-readable reasoning prose for a step that already failed
    its noul threshold. The backend's own pass/confidence judgment is
    discarded -- only its ``reasoning`` text is used."""
    prompt = (
        f"## Step: {step_id}\n\n"
        f"## Criteria\n{criteria_text}\n\n"
        f"## Actual Output\n```json\n{json.dumps(actual_output, indent=2, default=str)}\n```\n\n"
        f"Judge whether the actual output satisfies the criteria."
    )

    try:
        raw = await backend.run(prompt, system=_JUDGE_SYSTEM)
    except Exception as exc:
        logger.warning("Reasoning generation failed for step '%s': %s", step_id, exc)
        return f"Below confidence threshold; reasoning generation failed: {exc}"

    return _parse_verdict(raw, min_confidence=0.0).reasoning


def _parse_verdict(raw: str, min_confidence: float) -> SemanticVerdict:
    """Parse LLM JSON response into a SemanticVerdict."""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return SemanticVerdict(
            status="skip",
            reasoning=f"Failed to parse LLM response as JSON: {raw[:200]}",
            error_message="JSON parse error",
        )

    passed = bool(data.get("pass", False))
    confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
    reasoning = str(data.get("reasoning", ""))

    # Apply confidence threshold
    if passed and confidence >= min_confidence:
        return SemanticVerdict(
            status="pass",
            confidence=confidence,
            reasoning=reasoning,
        )
    elif not passed:
        return SemanticVerdict(
            status="fail",
            confidence=confidence,
            reasoning=reasoning,
        )
    else:
        # Passed but below confidence threshold
        return SemanticVerdict(
            status="fail",
            confidence=confidence,
            reasoning=(
                f"Below confidence threshold "
                f"({confidence:.2f} < {min_confidence:.2f}): {reasoning}"
            ),
        )
