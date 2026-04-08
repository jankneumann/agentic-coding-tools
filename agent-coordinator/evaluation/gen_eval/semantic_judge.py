"""LLM-as-judge semantic evaluation via CLI pathway.

Invokes the existing ``claude --print`` CLI for semantic evaluation.
Returns a structured judgment dict with verdict, confidence, and reasoning.

Design decision D4: Semantic verdicts are additive — they enhance but
never override structural verdicts. When the LLM is unavailable, this
module raises an exception so the caller can produce a ``skip`` verdict.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are an evaluation judge. Assess whether the following response meets the criteria.

## Criteria
{criteria}

## Response Fields
{fields_text}

## Instructions
Return ONLY valid JSON with this exact structure:
{{"verdict": "pass" or "fail", "confidence": 0.0-1.0, "reasoning": "explanation"}}

- verdict: "pass" if the response meets the criteria, "fail" otherwise
- confidence: your confidence in the verdict (0.0 to 1.0)
- reasoning: brief explanation of your judgment
"""


async def semantic_judge_evaluate(
    criteria: str,
    field_values: dict[str, Any],
    *,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Invoke LLM judgment via CLI and return structured result.

    Args:
        criteria: Natural-language description of correct behavior.
        field_values: Extracted response fields to evaluate.
        timeout_seconds: CLI invocation timeout.

    Returns:
        Dict with keys: verdict ("pass"/"fail"), confidence (float),
        reasoning (str).

    Raises:
        RuntimeError: If the LLM backend is unreachable or returns
            unparseable output.
    """
    fields_text = json.dumps(field_values, indent=2, default=str)
    prompt = _PROMPT_TEMPLATE.format(criteria=criteria, fields_text=fields_text)

    try:
        result = subprocess.run(
            ["claude", "--print", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        msg = "LLM backend unavailable: 'claude' CLI not found"
        raise RuntimeError(msg)
    except subprocess.TimeoutExpired:
        msg = f"LLM backend unavailable: CLI timed out after {timeout_seconds}s"
        raise RuntimeError(msg)

    if result.returncode != 0:
        msg = f"LLM backend unavailable: CLI exit code {result.returncode}"
        raise RuntimeError(msg)

    output = result.stdout.strip()

    # Extract JSON from potential markdown code blocks
    if "```" in output:
        lines = output.split("\n")
        json_lines: list[str] = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                json_lines.append(line)
        output = "\n".join(json_lines)

    try:
        judgment = json.loads(output)
    except json.JSONDecodeError:
        msg = f"LLM returned unparseable output: {output[:200]}"
        raise RuntimeError(msg)

    # Validate structure
    if "verdict" not in judgment or "confidence" not in judgment:
        msg = f"LLM response missing required fields: {judgment}"
        raise RuntimeError(msg)

    return {
        "verdict": judgment["verdict"],
        "confidence": float(judgment["confidence"]),
        "reasoning": judgment.get("reasoning", ""),
    }
