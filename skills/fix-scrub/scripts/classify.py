#!/usr/bin/env python3
"""Finding fixability classifier: assign each finding to auto/agent/manual tier."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

# Add fix-scrub scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_models import ClassifiedFinding, Finding, severity_rank  # noqa: E402

# Per system_one_decisions.testing's documented stubbing rule: import the
# module, never a pre-bound name, so a monkeypatched `decide` attribute is
# what this code actually calls.
system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None

# Ruff rules known to support --fix
_RUFF_FIXABLE_PREFIXES = {
    "F", "E", "W", "I", "UP", "B", "SIM", "RUF",
    "D", "C4", "PT", "RSE", "RET", "TCH", "TID",
}

# noul >= this maps to True ("an agent could act without asking a human" /
# "this finding includes a concrete fix"). No acceptance outcome calls for a
# tunable floor here (design D4), unlike ri-16's recall-oriented threshold.
DEFAULT_FIX_TIER_NOUL_THRESHOLD = 0.5


def _is_ruff_fixable(finding: Finding) -> bool:
    """Check if a ruff finding's rule likely supports --fix."""
    # Extract rule code from finding ID (e.g., "ruff-E501-file.py:10")
    parts = finding.id.split("-", 2)
    if len(parts) >= 2:
        code = parts[1]
        for prefix in _RUFF_FIXABLE_PREFIXES:
            if code.startswith(prefix):
                return True
    return False


def _marker_has_sufficient_context(finding: Finding) -> bool:
    """Check if a marker finding has >=10 chars after the keyword."""
    detail = finding.detail.strip()
    # The detail should be the text after the marker keyword (TODO:, FIXME:, etc.)
    # Strip leading colon/whitespace
    for prefix in (":", " "):
        if detail.startswith(prefix):
            detail = detail[len(prefix):]
    return len(detail.strip()) >= 10


def _deferred_has_proposed_fix(finding: Finding) -> bool:
    """Check if a deferred finding has a non-empty proposed fix."""
    detail_lower = finding.detail.lower()
    return "proposed fix" in detail_lower or "resolution" in detail_lower


def _answer_field(answer: Any, name: str, default: Any = None) -> Any:
    """Read a field off a real SDK answer object or a plain dict/mapping."""
    if isinstance(answer, dict):
        return answer.get(name, default)
    return getattr(answer, name, default)


def _judge_fix_tier_gates(
    findings: list[Finding], dry_run: bool = False,
) -> dict[int, bool]:
    """Judge every `markers`/`deferred:*` finding's content gate in one
    batched `decide()` call for the whole *findings* list.

    Returns `{finding_index: is_actionable}` covering only findings that got
    a usable answer -- a missing index means the answer was absent or
    malformed for that finding (or the whole batch was unavailable), and the
    caller falls back to the original heuristic for it, exactly as
    `classify_finding` behaved before this function existed. `ruff`, `mypy`,
    `architecture`, `security`, and unknown sources are never judged and
    never trigger a `decide()` call.
    """
    if system_one_decisions is None:
        return {}

    judgeable = {
        i: f
        for i, f in enumerate(findings)
        if f.source == "markers" or f.source.startswith("deferred:")
    }
    if not judgeable:
        return {}

    # Include `title` alongside `detail`: collect_deferred.py's open-tasks
    # collector puts the actual checkbox text in `title` and a generic
    # "Open task in change <id>" placeholder in `detail` (the two other
    # deferred collectors and the markers collector put real content in both
    # fields, or in `detail` alone). Sending `detail` only would make the
    # judge blind to open-tasks findings' actual content -- unable to give a
    # meaningful answer rather than degrading to the fallback.
    state = {
        "findings": {
            f"finding_{i}": {"source": f.source, "title": f.title, "detail": f.detail}
            for i, f in judgeable.items()
        },
    }
    questions: dict[str, Any] = {}
    for i, f in judgeable.items():
        if f.source == "markers":
            instructions = (
                f"In state.findings.finding_{i}, could an agent act on this "
                "marker without asking a human?"
            )
        else:
            instructions = (
                f"In state.findings.finding_{i}, does this finding include a "
                "concrete, applicable fix?"
            )
        questions[f"finding_{i}"] = {"type": "noul", "instructions": instructions}

    answers = system_one_decisions.decide(
        state, questions, site="fix-scrub.classify", dry_run=dry_run,
    )
    if not answers:
        return {}

    result: dict[int, bool] = {}
    for i in judgeable:
        answer = answers.get(f"finding_{i}") if hasattr(answers, "get") else None
        if answer is None:
            continue
        noul = _answer_field(answer, "noul")
        if not isinstance(noul, (int, float)):
            continue
        result[i] = noul >= DEFAULT_FIX_TIER_NOUL_THRESHOLD
    return result


def classify_finding(
    finding: Finding, judged_hint: bool | None = None,
) -> ClassifiedFinding:
    """Classify a single finding into a fixability tier.

    `judged_hint` overrides the marker/deferred content heuristic when not
    `None` (a judged answer for this finding was available). Every
    pre-existing call site passes no `judged_hint`, so the default `None`
    keeps this function's behavior identical to before judgment existed.
    """
    source = finding.source
    category = finding.category

    # Auto tier: ruff with fixable rules
    if source == "ruff" and _is_ruff_fixable(finding):
        return ClassifiedFinding(
            finding=finding,
            tier="auto",
            fix_strategy="ruff check --fix",
        )

    # Agent tier: mypy type errors
    if source == "mypy":
        return ClassifiedFinding(
            finding=finding,
            tier="agent",
            fix_strategy="Add or fix type annotations",
        )

    # Agent tier: markers with sufficient context
    has_context = (
        judged_hint if judged_hint is not None
        else _marker_has_sufficient_context(finding)
    )
    if source == "markers" and has_context:
        return ClassifiedFinding(
            finding=finding,
            tier="agent",
            fix_strategy="Resolve marker based on context",
        )

    # Agent tier: deferred with proposed fix
    has_fix = (
        judged_hint if judged_hint is not None
        else _deferred_has_proposed_fix(finding)
    )
    if source.startswith("deferred:") and has_fix:
        return ClassifiedFinding(
            finding=finding,
            tier="agent",
            fix_strategy="Apply proposed fix from deferred finding",
        )

    # Manual tier: markers with insufficient context
    if source == "markers":
        return ClassifiedFinding(
            finding=finding,
            tier="manual",
            fix_strategy="Insufficient context for automated fix",
        )

    # Manual tier: architecture, security, deferred without fix
    if source in ("architecture", "security") or category in (
        "architecture",
        "security",
    ):
        return ClassifiedFinding(
            finding=finding,
            tier="manual",
            fix_strategy="Requires design decision or manual review",
        )

    if source.startswith("deferred:"):
        return ClassifiedFinding(
            finding=finding,
            tier="manual",
            fix_strategy="No clear proposed fix — requires investigation",
        )

    # Default: manual for unknown sources
    return ClassifiedFinding(
        finding=finding,
        tier="manual",
        fix_strategy="Unknown source — manual review required",
    )


def classify(
    findings: list[Finding],
    severity_filter: str = "medium",
    dry_run: bool = False,
) -> list[ClassifiedFinding]:
    """Classify all findings into fixability tiers.

    Args:
        findings: List of findings from bug-scrub report.
        severity_filter: Minimum severity to include.
        dry_run: Forwarded to the judged classification's `decide()` call
            (see `_judge_fix_tier_gates`). Unrelated to fix-scrub's CLI
            `--dry-run` flag, which controls whether fixes are applied and
            is never wired here (design D6).

    Returns:
        List of classified findings.
    """
    min_rank = severity_rank(severity_filter)
    eligible = [f for f in findings if severity_rank(f.severity) >= min_rank]
    judged = _judge_fix_tier_gates(eligible, dry_run=dry_run)
    return [
        classify_finding(f, judged_hint=judged.get(i))
        for i, f in enumerate(eligible)
    ]
