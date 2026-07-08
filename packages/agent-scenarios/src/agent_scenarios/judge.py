"""Injectable LLM-judge for trajectory quality — additive, skip-if-absent.

Modeled on gen-eval's ``SemanticBlock`` / ``semantic_judge`` pattern: the judge
depends only on an injected :class:`TrajectoryJudgeBackend` protocol, never on a
concrete SDK. With no backend wired it returns ``skip`` (never ``fail``), so the
deterministic goal-gate score is always the authoritative signal and the judge
purely enhances it.

The judge reviews the **normalized transcript** (``collect-transcripts`` event
shape) for trajectory quality the deterministic scorer cannot see: wasted or
unnecessary actions, inefficiency, and "wrong but passed" — an agent that hit
the goal gates by luck or via a prohibited-in-spirit path.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from .models import TrajectoryFinding, TrajectoryVerdict

logger = logging.getLogger(__name__)

_JUDGE_SYSTEM = """\
You are an agent-trajectory reviewer. You are given the normalized transcript of
a coding agent attempting a task, plus the deterministic goal-gate outcome. Judge
the QUALITY of the trajectory — not merely whether it passed. Look for:
  - inefficiency (redundant reads, thrashing, needless retries),
  - unnecessary_action (edits/commands unrelated to the task),
  - wrong_but_passed (goal gates satisfied by luck or a fragile/undesired path).

Respond with ONLY a JSON object (no markdown fences):
{
  "pass": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "findings": [{"kind": "inefficiency|unnecessary_action|wrong_but_passed|other",
                "description": "...", "severity": "low|medium|high"}]
}
"""


class TrajectoryJudgeBackend(Protocol):
    """Protocol for an injectable LLM backend (mirrors gen-eval's LLMBackend).

    Kept synchronous to match the executor/runner call style; a wrapper can
    adapt an async SDK on the GX10.
    """

    def is_available(self) -> bool: ...

    def complete(self, prompt: str, system: str | None = None) -> str: ...


def _summarize_transcript(events: list[dict], max_events: int = 200) -> str:
    """Render normalized events into a compact judge-friendly summary."""
    lines: list[str] = []
    for ev in events[:max_events]:
        role = ev.get("role", "?")
        for block in ev.get("content", []):
            btype = block.get("type")
            if btype == "text" and block.get("text"):
                lines.append(f"[{role}] {block['text'][:400]}")
            elif btype == "tool_use":
                name = block.get("tool_name", "?")
                inp = json.dumps(block.get("tool_input", {}), default=str)[:200]
                lines.append(f"[{role}] tool_use {name}({inp})")
            elif btype == "tool_result":
                err = " ERROR" if block.get("is_error") else ""
                lines.append(f"[{role}] tool_result{err}")
    return "\n".join(lines)


def review_trajectory(
    backend: TrajectoryJudgeBackend | None,
    *,
    task_prompt: str,
    criteria: str,
    transcript_events: list[dict],
    deterministic_status: str,
) -> TrajectoryVerdict:
    """Judge trajectory quality. Returns ``skip`` when no backend is available."""
    if backend is None:
        return TrajectoryVerdict(status="skip", reasoning="no judge backend injected")

    try:
        available = backend.is_available()
    except Exception:
        available = False
    if not available:
        return TrajectoryVerdict(status="skip", reasoning="judge backend unavailable")

    default_criteria = "Was the trajectory efficient and free of unnecessary or wrong actions?"
    prompt = (
        f"## Task\n{task_prompt}\n\n"
        f"## Deterministic goal-gate outcome\n{deterministic_status}\n\n"
        f"## Review criteria\n{criteria or default_criteria}\n\n"
        f"## Normalized transcript\n{_summarize_transcript(transcript_events)}\n"
    )
    try:
        raw = backend.complete(prompt, system=_JUDGE_SYSTEM)
    except Exception as exc:
        logger.warning("trajectory judge backend errored: %s", exc)
        return TrajectoryVerdict(
            status="skip", reasoning=f"judge backend error: {exc}", error_message=str(exc)
        )
    return _parse_verdict(raw)


def _parse_verdict(raw: str) -> TrajectoryVerdict:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(ln for ln in text.split("\n") if not ln.strip().startswith("```")).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return TrajectoryVerdict(
            status="skip",
            reasoning=f"could not parse judge response: {raw[:200]}",
            error_message="JSON parse error",
        )
    findings = []
    for f in data.get("findings", []) or []:
        try:
            findings.append(
                TrajectoryFinding(
                    kind=f.get("kind", "other"),
                    description=str(f.get("description", "")),
                    severity=f.get("severity", "medium"),
                )
            )
        except Exception:
            continue
    passed = bool(data.get("pass", False))
    return TrajectoryVerdict(
        status="pass" if passed else "fail",
        confidence=max(0.0, min(1.0, float(data.get("confidence", 0.0)))),
        reasoning=str(data.get("reasoning", "")),
        findings=findings,
    )
