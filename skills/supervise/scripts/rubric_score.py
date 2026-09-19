#!/usr/bin/env python3
"""Judged candidate-work rubric scoring (`ri-17` of
`roadmap-jev-system-one-integration-assessment`).

Replaces the host-dispatched analyst-archetype sub-agent
(`templates/rubric-prompt.md`) with one batched `decide()` call scoring every
requested stub on all 5 rubric factors -- up to 100 `Score` questions for 20
stubs. `digest.py` stays host-assisted (it never imports this module or
`system_one_decisions`); the host tries `score_batch()` here first and falls
back to the unchanged sub-agent dispatch only when it returns `None`. See
`openspec/changes/score-supervise-rubric-stubs-in-one-batched-call/design.md`
for the degradation contract (D3) and the Score-to-schema score mapping (D6).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# Per system_one_decisions.testing's documented stubbing rule: import the
# module, never a pre-bound name, so a monkeypatched `decide` attribute is
# what this code actually calls.
system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None

_FACTORS = ("relevance", "value", "readiness", "scope_fit", "risk")

# Verbatim from templates/rubric-prompt.md's factor descriptions.
_FACTOR_INSTRUCTIONS: dict[str, str] = {
    "relevance": "Is the finding still true on the current tree?",
    "value": "What changes for users/operators if this lands?",
    "readiness": "Could an implementer start today?",
    "scope_fit": "Is it one change, or several, or a fragment?",
    "risk": (
        "Blast radius if it goes wrong. Risk 5 means safest and 1 means "
        "highest risk."
    ),
}

# Ordered 5-level Score criteria, criteria[i] describing schema score i+1.
# `risk` is inverted so criteria[4] describes the safest/highest-scoring
# level, matching the schema's "risk 5 = safest" convention. Mirrors
# digest.py's `_FACTOR_LEVEL_LABELS` (duplicated rather than imported so
# digest.py never imports this module -- see design.md D1).
_FACTOR_CRITERIA: dict[str, list[str]] = {
    "relevance": [
        "No longer true on the current tree.",
        "Mostly stale, small part still true.",
        "Partially true on the current tree.",
        "Mostly true on the current tree.",
        "Still true on the current tree.",
    ],
    "value": [
        "Negligible change for users/operators.",
        "Minor change for users/operators.",
        "Moderate change for users/operators.",
        "Significant change for users/operators.",
        "Major change for users/operators.",
    ],
    "readiness": [
        "Far from ready to start.",
        "Needs substantial groundwork first.",
        "Needs minor groundwork first.",
        "Nearly ready to start today.",
        "An implementer could start today.",
    ],
    "scope_fit": [
        "A fragment, not a coherent change.",
        "Several change's worth, poorly bounded.",
        "Roughly one change, some spillover.",
        "Close to one focused change.",
        "Exactly one focused change.",
    ],
    "risk": [
        "Highest risk, largest blast radius.",
        "High risk if it goes wrong.",
        "Moderate risk if it goes wrong.",
        "Low risk, small blast radius.",
        "Safest, minimal blast radius.",
    ],
}


def _answer_field(answer: Any, name: str, default: Any = None) -> Any:
    """Read a field off a real SDK answer object or a plain dict/mapping."""
    if isinstance(answer, dict):
        return answer.get(name, default)
    return getattr(answer, name, default)


def _validate(repo_root: Path, name: str, value: Any) -> None:
    path = repo_root / "openspec" / "schemas" / name
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


def score_batch(
    repo_root: Path, manifest: dict[str, Any], *, dry_run: bool = False,
) -> dict[str, Any] | None:
    """Score every requested stub on all 5 rubric factors in one batched call.

    Returns a document matching `supervise-rubric-score.schema.json`
    (validated before being returned) only when every requested `stub_key`
    gets a usable, numeric answer for all 5 factors. Otherwise returns
    `None` -- module unavailable, `decide()` returns nothing usable, or any
    single stub/factor is missing or malformed -- for the whole call, not
    just the affected stub.

    This is deliberately all-or-nothing, unlike the per-item fallback used
    elsewhere in this roadmap (design.md D3): `rank_candidates`'s
    `_validate_score_join` already rejects a scores document that is
    missing even one requested stub_key, mirroring the sub-agent path's own
    pre-existing "missing, partial, invalid, or late output is rejected
    rather than repaired" policy. A partial batch from this function would
    be rejected there anyway, so returning `None` here -- triggering the
    unchanged sub-agent fallback -- is the correct behavior, not a
    weakening of it.
    """
    if system_one_decisions is None:
        return None
    requested = manifest.get("requested_keys")
    if not isinstance(requested, list) or not requested:
        return None
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list):
        return None
    by_key = {
        row["stub_key"]: row
        for row in candidates
        if isinstance(row, dict) and isinstance(row.get("stub_key"), str)
    }
    if set(by_key) != set(requested):
        return None

    state: dict[str, Any] = {"candidates": {}}
    questions: dict[str, Any] = {}
    for key in requested:
        candidate = by_key[key]
        stub = candidate.get("stub")
        if not isinstance(stub, dict):
            return None
        state["candidates"][key] = {
            "title": stub.get("title"),
            "signals": candidate.get("signals"),
            "evidence": candidate.get("evidence"),
        }
        for factor in _FACTORS:
            questions[f"{key}__{factor}"] = {
                "type": "score",
                "instructions": _FACTOR_INSTRUCTIONS[factor],
                "criteria": _FACTOR_CRITERIA[factor],
            }

    answers = system_one_decisions.decide(
        state, questions, site="supervise.rubric_score", dry_run=dry_run,
    )
    if not answers:
        return None

    scores: list[dict[str, Any]] = []
    for key in requested:
        row: dict[str, Any] = {"stub_key": key}
        for factor in _FACTORS:
            answer = answers.get(f"{key}__{factor}") if hasattr(answers, "get") else None
            if answer is None:
                return None
            raw_score = _answer_field(answer, "score")
            if not isinstance(raw_score, (int, float)):
                return None
            # `criteria[i]` describes schema score i+1; ScoreAnswer.score is a
            # 0-indexed, possibly-fractional position ("probability-weighted
            # average of the rubric levels"), so +1 then clamp into [1, 5].
            row[factor] = {"score": max(1, min(5, round(raw_score) + 1))}
        scores.append(row)

    document = {
        "schema_version": 1,
        "fingerprint": manifest["fingerprint"],
        "scored_at": manifest["as_of"],
        "scorer": {"archetype": "system_one_decisions.rubric_score"},
        "scores": scores,
    }
    try:
        _validate(repo_root, "supervise-rubric-score.schema.json", document)
    except (ValidationError, ValueError, OSError, KeyError):
        return None
    return document


def compute_agreement(
    a_scores: dict[str, Any], b_scores: dict[str, Any],
) -> dict[str, Any]:
    """Per-factor agreement between two rubric-score documents over the same
    stubs, mirroring `gatekeeper_shadow_report.py`'s disagreement-rate shape.

    NOTE (design.md D8): no recorded manifest + archived analyst output
    exists yet to compute a real production agreement rate from -- this is
    the report function only, exercised in tests against an explicitly
    synthetic fixture pair. It does not, by itself, establish or claim any
    real-world agreement rate; that requires a live shadow-mode period
    (mirroring `ri-06`'s `gatekeeper_shadow.py` pattern), which is out of
    scope for this item.
    """
    a_by_key = {row["stub_key"]: row for row in a_scores.get("scores", [])}
    b_by_key = {row["stub_key"]: row for row in b_scores.get("scores", [])}
    shared_keys = sorted(set(a_by_key) & set(b_by_key))
    total = 0
    agreements = 0
    per_factor: dict[str, dict[str, int]] = {
        factor: {"total": 0, "agreements": 0} for factor in _FACTORS
    }
    for key in shared_keys:
        for factor in _FACTORS:
            a_score = a_by_key[key].get(factor, {}).get("score")
            b_score = b_by_key[key].get(factor, {}).get("score")
            if a_score is None or b_score is None:
                continue
            total += 1
            per_factor[factor]["total"] += 1
            if a_score == b_score:
                agreements += 1
                per_factor[factor]["agreements"] += 1
    return {
        "shared_stub_count": len(shared_keys),
        "total_comparisons": total,
        "agreement_count": agreements,
        "agreement_rate": (agreements / total) if total else 0.0,
        "per_factor": {
            factor: {
                **counts,
                "agreement_rate": (
                    counts["agreements"] / counts["total"] if counts["total"] else 0.0
                ),
            }
            for factor, counts in per_factor.items()
        },
    }


def _cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Judged candidate-work rubric scoring.")
    parser.add_argument("--repo-root", default=".")
    commands = parser.add_subparsers(dest="command", required=True)

    score_cmd = commands.add_parser("score-batch")
    score_cmd.add_argument("--manifest", required=True)
    score_cmd.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()

    if args.command == "score-batch":
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        result = score_batch(root, manifest, dry_run=args.dry_run)
        if result is None:
            return 1
        print(json.dumps(result, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())
