"""Semantic evaluation via LLM-as-judge (D4, D9).

Invokes an LLM backend to judge whether a step's actual output
satisfies the semantic criteria specified in a SemanticBlock.
Uses the framework's existing backend infrastructure (CLIBackend,
SDKBackend, AdaptiveBackend) rather than hardcoding a specific CLI.

Verdicts are additive: they enhance but never override structural
verdicts. When the LLM is unavailable, produces ``skip`` not ``failure``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from .models import SemanticBlock, SemanticVerdict

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
        backend: LLM backend (CLIBackend, SDKBackend, or AdaptiveBackend).
        semantic: SemanticBlock with criteria and confidence threshold.
        actual_output: The step's actual response body/data.
        step_id: For logging context.

    Returns:
        SemanticVerdict with pass/fail/skip status.
    """
    if not semantic.judge:
        return SemanticVerdict(status="skip", reasoning="Semantic evaluation disabled")

    # Check backend availability
    try:
        available = await backend.is_available()
    except Exception:
        available = False

    if not available:
        logger.warning("LLM backend unavailable for semantic eval on step '%s'", step_id)
        return SemanticVerdict(
            status="skip",
            reasoning="LLM backend unavailable",
        )

    # Build prompt
    criteria_text = semantic.criteria or "Does the output look correct and complete?"
    prompt = (
        f"## Step: {step_id}\n\n"
        f"## Criteria\n{criteria_text}\n\n"
        f"## Actual Output\n```json\n{json.dumps(actual_output, indent=2, default=str)}\n```\n\n"
        f"Judge whether the actual output satisfies the criteria."
    )

    try:
        raw = await backend.run(prompt, system=_JUDGE_SYSTEM)
        return _parse_verdict(raw, semantic.min_confidence)
    except Exception as exc:
        logger.warning(
            "Semantic evaluation failed for step '%s': %s", step_id, exc
        )
        return SemanticVerdict(
            status="skip",
            reasoning=f"LLM evaluation error: {exc}",
            error_message=str(exc),
        )


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
    confidence = float(data.get("confidence", 0.0))
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
