#!/usr/bin/env python3
"""Conditional multi-vendor review for pull requests.

Dispatches vendor-diverse reviews for PRs that warrant deeper analysis
(large changes, no existing reviews) and synthesizes a consensus report.
Skips review for small changes, bot PRs, and PRs with existing reviews.

Usage:
  python vendor_review.py <pr_number> --origin <origin> [--reviews-json <path>]
                          [--dry-run] [--timeout <seconds>]

Output: JSON result to stdout with review findings or skip reason.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from _helpers import (
    capture_head,
    capture_untracked,
    check_gh,
    quarantine_new_untracked,
    run_gh,
    verify_and_restore_head,
)

# Per system_one_decisions.testing's documented stubbing rule: import the
# module, never a pre-bound name, so a monkeypatched `decide` attribute is
# what this code actually calls.
system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None

_SCRIPTS_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Thresholds — PRs at or below these are "small" and skip vendor review.
# Defaults for load_vendor_review_thresholds(); the deterministic fallback
# path when the judged eligibility check (below) is unavailable.
# ---------------------------------------------------------------------------

SMALL_PR_MAX_CHANGED_LINES = 50
SMALL_PR_MAX_FILES = 3
DEFAULT_TIMEOUT = 300

DEFAULT_VENDOR_REVIEW_CONFIDENCE_FLOOR = 0.5
_VENDOR_REVIEW_JUDGMENT_CONFIG_PATH = _SCRIPTS_DIR / "vendor-review-judgment.json"

# Ordered lowest-to-highest risk, matching docs/proposals/
# jev-system-one-integration-assessment.md A4's Score(risk, [...]).
_RISK_LEVELS = (
    "docs/config only",
    "internal refactor",
    "behaviour change",
    "security or data path",
)

# Origins that always skip vendor review (scoped automated fixes / dep bumps)
SKIP_ORIGINS = frozenset({
    "sentinel", "bolt", "palette", "jules",
    "dependabot", "renovate",
})

# Origins that are candidates for vendor review
REVIEW_ORIGINS = frozenset({"openspec", "codex", "other"})


# ---------------------------------------------------------------------------
# PR size computation
# ---------------------------------------------------------------------------

def compute_pr_size(pr_number: int) -> dict:
    """Compute changed lines and file count from PR diff.

    Also fetches title/body — cheap metadata, not the diff itself — used by
    the judged eligibility check below as its state.

    Returns:
        {"additions": int, "deletions": int, "changed_lines": int,
         "changed_files": int, "files": [str], "title": str, "body": str}
    """
    try:
        raw = run_gh([
            "pr", "diff", str(pr_number), "--name-only",
        ])
    except RuntimeError as e:
        print(f"Warning: Could not fetch diff file list for PR #{pr_number}: {e}",
              file=sys.stderr)
        return {"additions": 0, "deletions": 0, "changed_lines": 0,
                "changed_files": 0, "files": [], "title": "", "body": ""}

    files = [f for f in raw.strip().splitlines() if f.strip()]
    changed_files = len(files)

    # Get line-level stats and title/body via the --json flag
    additions = 0
    deletions = 0
    title = ""
    body = ""
    try:
        stat_raw = run_gh([
            "pr", "view", str(pr_number), "--json", "additions,deletions,title,body",
        ])
        stat_data = json.loads(stat_raw)
        additions = stat_data.get("additions", 0)
        deletions = stat_data.get("deletions", 0)
        title = stat_data.get("title") or ""
        body = stat_data.get("body") or ""
    except (RuntimeError, json.JSONDecodeError) as e:
        print(f"Warning: Could not fetch PR stats for #{pr_number}: {e}",
              file=sys.stderr)

    return {
        "additions": additions,
        "deletions": deletions,
        "changed_lines": additions + deletions,
        "changed_files": changed_files,
        "files": files,
        "title": title,
        "body": body,
    }


# ---------------------------------------------------------------------------
# Review eligibility
# ---------------------------------------------------------------------------

def load_vendor_review_thresholds(config_path: Path | None = None) -> dict[str, Any]:
    """Read the optional sidecar JSON, falling back to module defaults.

    Mirrors gatekeeper_shadow.load_shadow_thresholds and
    triage.load_deep_analysis_floor: a malformed or missing sidecar
    degrades to the defaults rather than raising. Covers both the
    deterministic fallback thresholds (max_changed_lines/max_files) and the
    judged path's act-floor (confidence_floor) in one file, since both
    govern the same decision point.
    """
    path = config_path or _VENDOR_REVIEW_JUDGMENT_CONFIG_PATH
    defaults: dict[str, Any] = {
        "max_changed_lines": SMALL_PR_MAX_CHANGED_LINES,
        "max_files": SMALL_PR_MAX_FILES,
        "confidence_floor": DEFAULT_VENDOR_REVIEW_CONFIDENCE_FLOOR,
    }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(raw, dict):
        return defaults
    try:
        result = dict(defaults)
        if "max_changed_lines" in raw:
            result["max_changed_lines"] = int(raw["max_changed_lines"])
        if "max_files" in raw:
            result["max_files"] = int(raw["max_files"])
        if "confidence_floor" in raw:
            result["confidence_floor"] = float(raw["confidence_floor"])
        return result
    except (TypeError, ValueError):
        return defaults


def _answer_field(answer: Any, name: str, default: Any = None) -> Any:
    """Read a field off a real SDK answer object or a plain dict/mapping."""
    if isinstance(answer, dict):
        return answer.get(name, default)
    return getattr(answer, name, default)


def _classify_pr_risk(pr_number: int, origin: str, pr_size: dict) -> dict[str, Any] | None:
    """Ask one calibrated judgment for whether this PR warrants review.

    State is title, body, file list and diff stat — never the diff itself
    (docs/proposals/jev-system-one-integration-assessment.md A4). Returns
    `None` on any unavailability (module missing, `decide()` returns no
    usable answer) — never raises. Callers fall back to the existing
    size-threshold rule. The deterministic draft/origin skips already ran
    before this is ever called, so a call-count test can assert this
    function is never reached for those PRs.
    """
    if system_one_decisions is None:
        return None

    state: dict[str, Any] = {
        "title": pr_size.get("title") or "",
        "body": (pr_size.get("body") or "")[:2000],
        "files": pr_size.get("files", []),
        "additions": pr_size.get("additions", 0),
        "deletions": pr_size.get("deletions", 0),
        "origin": origin,
    }
    questions = {
        "warrants_review": {
            "type": "noul",
            "instructions": "This PR warrants independent multi-vendor review.",
            "criteria": {
                "true": (
                    "The change touches security, auth, data paths, "
                    "guardrails, or policy -- worth a second opinion "
                    "regardless of size."
                ),
                "false": (
                    "The change is low-risk -- docs, config, or a narrow "
                    "refactor that one reviewer's judgment already covers."
                ),
            },
        },
        "risk": {
            "type": "score",
            "instructions": "How risky is this change, from lowest to highest?",
            "criteria": list(_RISK_LEVELS),
        },
    }

    answers = system_one_decisions.decide(
        state, questions, site="merge-pull-requests.vendor_review",
    )
    if not answers:
        return None

    warrants_answer = answers.get("warrants_review") if hasattr(answers, "get") else None
    if warrants_answer is None:
        return None
    noul = _answer_field(warrants_answer, "noul")
    if not isinstance(noul, (int, float)):
        return None

    risk_answer = answers.get("risk") if hasattr(answers, "get") else None
    risk_score = _answer_field(risk_answer, "score") if risk_answer is not None else None
    risk_probability = _answer_field(risk_answer, "confidence") if risk_answer is not None else None

    floor = load_vendor_review_thresholds()["confidence_floor"]
    return {
        "eligible": noul >= floor,
        "risk_score": risk_score,
        "risk_probability": risk_probability,
    }


def check_review_eligibility(
    pr_number: int,
    origin: str,
    pr_size: dict,
    existing_reviews: list[dict] | None = None,
    is_draft: bool = False,
) -> dict:
    """Determine whether a PR warrants multi-vendor review.

    Returns:
        {"eligible": bool, "reason": str, "details": dict}
    """
    # Draft PRs never get reviewed
    if is_draft:
        return {
            "eligible": False,
            "reason": "draft_pr",
            "details": {"message": "Draft PRs are not reviewed"},
        }

    # Bot/automation origins always skip -- deterministic facts about
    # provenance, never routed through the judged call below.
    if origin in SKIP_ORIGINS:
        return {
            "eligible": False,
            "reason": "skip_origin",
            "details": {"origin": origin,
                         "message": f"Origin '{origin}' is auto-skip (scoped automation or dependency update)"},
        }

    changed_lines = pr_size.get("changed_lines", 0)
    changed_files = pr_size.get("changed_files", 0)

    judged = _classify_pr_risk(pr_number, origin, pr_size)
    if judged is not None:
        evidence = {
            "evidence_class": "judgment",
            "risk_score": judged["risk_score"],
            "risk_probability": judged["risk_probability"],
        }
        if not judged["eligible"]:
            return {
                "eligible": False,
                "reason": "low_risk_judged",
                "details": {
                    **evidence,
                    "message": "Judged low-risk -- skipping vendor review",
                },
            }
    else:
        evidence = {}
        thresholds = load_vendor_review_thresholds()
        if (
            changed_lines <= thresholds["max_changed_lines"]
            and changed_files <= thresholds["max_files"]
        ):
            return {
                "eligible": False,
                "reason": "small_pr",
                "details": {
                    "changed_lines": changed_lines,
                    "changed_files": changed_files,
                    "threshold_lines": thresholds["max_changed_lines"],
                    "threshold_files": thresholds["max_files"],
                    "message": f"PR is small ({changed_lines} lines, {changed_files} files) — skipping review",
                },
            }

    # Check existing reviews — skip if there's a fresh approval
    if existing_reviews:
        approvals = [
            r for r in existing_reviews
            if r.get("state") == "APPROVED"
        ]
        if approvals:
            return {
                "eligible": False,
                "reason": "has_approval",
                "details": {
                    "approvals": len(approvals),
                    "reviewers": [r.get("reviewer", "unknown") for r in approvals],
                    "message": f"PR already has {len(approvals)} approval(s) — skipping review",
                },
            }
        changes_requested = [
            r for r in existing_reviews
            if r.get("state") == "CHANGES_REQUESTED"
        ]
        if changes_requested:
            return {
                "eligible": False,
                "reason": "changes_requested",
                "details": {
                    "message": "PR has unresolved change requests — vendor review deferred until addressed",
                },
            }

    # Eligible for review
    return {
        "eligible": True,
        "reason": "needs_review",
        "details": {
            "origin": origin,
            "changed_lines": changed_lines,
            "changed_files": changed_files,
            "message": f"PR qualifies for vendor review ({changed_lines} lines, {changed_files} files, origin={origin})",
            **evidence,
        },
    }


# ---------------------------------------------------------------------------
# Review prompt construction
# ---------------------------------------------------------------------------

#: Fallback finding shape, used only when the canonical schema cannot be read.
#: Kept in sync by ``tests/merge-pull-requests/test_vendor_review_prompt.py``,
#: which fails when these drift from ``review-findings.schema.json``.
_FALLBACK_REQUIRED = (
    "id", "type", "criticality", "description", "disposition", "axis", "severity",
)
_FALLBACK_ENUMS = {
    "type": (
        "spec_gap", "contract_mismatch", "architecture", "security", "performance",
        "style", "correctness", "observability", "compatibility", "resilience",
        "behavioral_failure",
    ),
    "criticality": ("low", "medium", "high", "critical"),
    "disposition": ("fix", "regenerate", "accept", "escalate"),
    "axis": (
        "correctness", "readability", "architecture", "security", "performance",
        "observability", "resilience", "compatibility",
    ),
    "severity": ("critical", "nit", "optional", "fyi", "none"),
    "evidence_class": ("deterministic", "judgment"),
}


def _finding_contract() -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Return ``(required_fields, enums)`` for one finding, from the canonical schema.

    The prompt is the ONLY contract most vendors ever see. Only ``grok-local``
    passes ``--json-schema @review-findings-schema``; codex, antigravity and pi
    are dispatched with the prompt alone, so a field the prompt omits is a field
    those vendors cannot know about — and their output is then rejected by a
    validator enforcing a contract they were never shown.

    Deriving both lists from ``openspec/schemas/review-findings.schema.json``
    keeps this prompt from becoming yet another hand-maintained copy of a schema
    that already has three.
    """
    try:
        dispatcher_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "parallel-infrastructure" / "scripts"
        )
        if str(dispatcher_dir) not in sys.path:
            sys.path.insert(0, str(dispatcher_dir))
        from review_findings_schema import prompt_contract

        required, enums = prompt_contract()
        if required and enums:
            return required, enums
    except Exception:  # noqa: BLE001 - prompt must build even if the schema moves
        pass
    return _FALLBACK_REQUIRED, dict(_FALLBACK_ENUMS)


def _enum_hint(enums: dict[str, tuple[str, ...]], field: str) -> str:
    """Render one field's allowed values for the example block."""
    values = enums.get(field)
    return "|".join(values) if values else f"<{field}>"


def build_review_prompt(pr_number: int, pr_size: dict) -> str:
    """Build a review prompt for vendor dispatch."""
    files_list = "\n".join(f"  - {f}" for f in pr_size.get("files", []))
    required, enums = _finding_contract()
    required_list = ", ".join(required)

    # criticality and severity are separate vocabularies with an overlapping
    # member ("critical"). Naming them side by side is what stops a vendor from
    # reusing one value for both fields and failing validation on a technicality.
    vocab_lines = []
    if "criticality" in enums:
        vocab_lines.append(
            f"  criticality: {_enum_hint(enums, 'criticality')}"
            "   — how much the finding matters"
        )
    if "severity" in enums:
        vocab_lines.append(
            f"  severity:    {_enum_hint(enums, 'severity')}"
            "   — review-gate grading (NOT the same scale as criticality)"
        )
    if "axis" in enums:
        vocab_lines.append(
            f"  axis:        {_enum_hint(enums, 'axis')}"
            "   — which review dimension the finding belongs to"
        )
    if "evidence_class" in enums:
        vocab_lines.append(
            f"  evidence_class: {_enum_hint(enums, 'evidence_class')}"
            "   — 'judgment' when the finding rests on your reasoning rather than"
            " on a reproducible observation you actually made. Optional; omitted"
            " means deterministic. Marking a finding 'judgment' means it is"
            " reported and ranked but never blocks a merge, so prefer it when you"
            " are not certain — an honest 60%-confidence finding is more useful"
            " than a suppressed one or an overstated one."
        )
    vocab_block = "\n".join(vocab_lines)

    return f"""Review pull request #{pr_number}.

This PR modifies {pr_size['changed_files']} files with {pr_size['additions']} additions and {pr_size['deletions']} deletions.

Changed files:
{files_list}

Review checklist:
1. **Correctness**: Logic errors, edge cases, off-by-one errors
2. **Security**: Input validation, injection risks, auth/authz gaps, secrets exposure
3. **Architecture**: Follows codebase patterns, appropriate abstractions, no unnecessary coupling
4. **Performance**: Inefficient algorithms, N+1 queries, missing indexes, resource leaks
5. **Style**: Naming conventions, code organization, dead code

For each finding, output JSON conforming to this structure:
{{
  "review_type": "pr",
  "target": "PR #{pr_number}",
  "reviewer_vendor": "<your-vendor-name>",
  "findings": [
    {{
      "id": 1,
      "type": "{_enum_hint(enums, 'type')}",
      "criticality": "{_enum_hint(enums, 'criticality')}",
      "axis": "{_enum_hint(enums, 'axis')}",
      "severity": "{_enum_hint(enums, 'severity')}",
      "description": "What the issue is",
      "resolution": "How to fix it",
      "disposition": "{_enum_hint(enums, 'disposition')}",
      "file_path": "path/to/file",
      "line_range": {{"start": 10, "end": 20}}
    }}
  ]
}}

REQUIRED on every finding — output is REJECTED if any is missing:
  {required_list}

These fields use DIFFERENT vocabularies. Do not reuse one value for another:
{vocab_block}

Use exactly one value from the listed set for each enum field; do not invent
values and do not emit the "a|b|c" alternation itself.

If you find no issues, return {{"findings": []}} rather than prose.
Output ONLY the JSON object, no additional text.
Use `gh pr diff {pr_number}` to read the actual diff before reviewing.
"""


# ---------------------------------------------------------------------------
# Dispatch reviews
# ---------------------------------------------------------------------------

def vendor_artifact_dir(pr_number: int) -> Path:
    """Where files a vendor wrote into the checkout are quarantined.

    ``MERGE_VENDOR_ARTIFACT_DIR`` overrides the system temp directory. A fresh
    timestamped subdirectory per dispatch keeps repeated reviews apart. An
    override that resolves inside the checkout is refused by
    ``quarantine_new_untracked`` and fails the review rather than relocating
    the files to another committable path.
    """
    base = os.environ.get("MERGE_VENDOR_ARTIFACT_DIR") or (
        Path(tempfile.gettempdir()) / "vendor-review-artifacts"
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(base) / f"pr{pr_number}-{stamp}"


def dispatch_vendor_reviews(
    pr_number: int,
    pr_size: dict,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    dry_run: bool = False,
) -> dict:
    """Dispatch reviews to available vendors and synthesize consensus.

    Returns:
        {"dispatched": bool, "vendors": [...], "consensus": {...} | None,
         "error": str | None}
    """
    if dry_run:
        return {
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": None,
            "dry_run": True,
            "message": "Dry-run: would dispatch vendor reviews",
        }

    # Import review infrastructure — lives in parallel-infrastructure
    dispatcher_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "parallel-infrastructure" / "scripts"
    )
    if not dispatcher_dir.exists():
        return {
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": f"Review dispatcher not found at {dispatcher_dir}",
        }

    sys.path.insert(0, str(dispatcher_dir))
    try:
        from review_dispatcher import ReviewOrchestrator, ReviewResult
        from consensus_synthesizer import (
            ConsensusSynthesizer,
            Finding,
            VendorResult,
        )
    except ImportError as e:
        return {
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": f"Could not import review infrastructure: {e}",
        }

    # Build orchestrator — try coordinator first, fall back to agents.yaml
    orch = ReviewOrchestrator.from_coordinator()
    if not orch.adapters:
        orch = ReviewOrchestrator.from_agents_yaml()

    if not orch.adapters:
        return {
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": "No vendor CLIs configured in coordinator or agents.yaml",
        }

    # Discover available reviewers (exclude claude since we're running as claude)
    reviewers = orch.discover_reviewers(exclude_vendor="claude_code")
    available = [r for r in reviewers if r.available]

    if not available:
        return {
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": "No vendor CLIs available for review dispatch",
        }

    # Build prompt and dispatch
    prompt = build_review_prompt(pr_number, pr_size)
    cwd = Path.cwd()

    # Vendor CLIs run against the shared working tree with full ambient
    # authority and have been observed checking out FETCH_HEAD, silently
    # detaching the operator's HEAD (issue #349). Snapshot HEAD before
    # dispatch and verify/restore after.
    head_before = capture_head()
    untracked_before = capture_untracked()

    # Both guards run in `finally`: an interrupted or failing dispatch (vendor
    # timeouts run to minutes) can leave exactly the state they exist to undo.
    try:
        results: list[ReviewResult] = orch.dispatch_and_wait(
            review_type="pr",
            dispatch_mode="review",
            prompt=prompt,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            exclude_vendor="claude_code",
        )
    finally:
        head_guard = verify_and_restore_head(head_before)
        if head_guard["drift_detected"]:
            print(
                f"WARNING: vendor review dispatch moved HEAD "
                f"({head_before['branch'] or 'detached'}@{head_before['sha'][:8]} -> "
                f"{head_guard['after']['branch'] or 'detached'}@{head_guard['after']['sha'][:8]}); "
                f"restore {'succeeded' if head_guard['restored'] else 'FAILED: ' + str(head_guard['error'])}",
                file=sys.stderr,
            )

        # The same authority lets a vendor write files into the checkout, where
        # a later `git add -A` sync-point commit would publish them. Move them out.
        workspace_guard = quarantine_new_untracked(
            untracked_before, vendor_artifact_dir(pr_number),
        )
        if workspace_guard["moved"]:
            print(
                f"WARNING: vendor review dispatch wrote untracked file(s) into the "
                f"checkout; moved to {workspace_guard['quarantined_to']}: "
                + ", ".join(workspace_guard["moved"]),
                file=sys.stderr,
            )
        if workspace_guard["errors"]:
            print(
                "ERROR: vendor review file(s) could not be moved out of the checkout: "
                + "; ".join(workspace_guard["errors"]),
                file=sys.stderr,
            )

    # A vendor file left in the checkout fails the review: the caller is a sync
    # point whose next commit could publish it.
    stranded = sorted(set(workspace_guard["new_untracked"]) - set(workspace_guard["moved"]))
    guard_error = (
        f"workspace guard left {len(stranded)} vendor file(s) in the checkout "
        f"({', '.join(stranded)}): " + "; ".join(workspace_guard["errors"])
        if stranded else None
    )

    # Collect successful vendor results for consensus
    vendor_results: list[VendorResult] = []
    vendor_summaries = []
    for r in results:
        summary = {
            "vendor": r.vendor,
            "success": r.success,
            "model_used": r.model_used,
            "elapsed_seconds": r.elapsed_seconds,
            "error": r.error,
            "findings_count": len(r.findings.get("findings", [])) if r.findings else 0,
        }
        vendor_summaries.append(summary)

        if r.success and r.findings:
            findings = [
                Finding.from_dict(f, vendor=r.vendor)
                for f in r.findings.get("findings", [])
            ]
            vendor_results.append(VendorResult(
                vendor=r.vendor,
                findings=findings,
                elapsed_seconds=r.elapsed_seconds,
            ))

    # Synthesize consensus if we have results
    consensus_dict = None
    if vendor_results:
        synth = ConsensusSynthesizer(quorum=1)  # quorum=1 since single vendor is acceptable for PR review
        report = synth.synthesize(
            review_type="pr",
            target=f"PR #{pr_number}",
            vendor_results=vendor_results,
        )
        consensus_dict = synth.to_dict(report)

    return {
        "dispatched": True,
        "vendors": vendor_summaries,
        "consensus": consensus_dict,
        "head_guard": head_guard,
        "workspace_guard": workspace_guard,
        "error": guard_error,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Conditional multi-vendor review for pull requests.",
    )
    parser.add_argument("pr_number", type=int, help="PR number to review")
    parser.add_argument("--origin", required=True,
                        help="PR origin classification (openspec, codex, other, etc.)")
    parser.add_argument("--reviews-json",
                        help="Path to JSON file with existing review data from analyze_comments.py")
    parser.add_argument("--is-draft", action="store_true",
                        help="Whether the PR is a draft")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report eligibility without dispatching reviews")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Per-vendor timeout in seconds (default: {DEFAULT_TIMEOUT})")
    args = parser.parse_args()

    check_gh()

    # Compute PR size
    pr_size = compute_pr_size(args.pr_number)

    # Load existing reviews if provided
    existing_reviews = None
    if args.reviews_json:
        try:
            data = json.loads(Path(args.reviews_json).read_text())
            existing_reviews = data.get("reviews", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load reviews from {args.reviews_json}: {e}",
                  file=sys.stderr)

    # Check eligibility
    eligibility = check_review_eligibility(
        pr_number=args.pr_number,
        origin=args.origin,
        pr_size=pr_size,
        existing_reviews=existing_reviews,
        is_draft=args.is_draft,
    )

    result = {
        "pr_number": args.pr_number,
        "origin": args.origin,
        "pr_size": {
            "additions": pr_size["additions"],
            "deletions": pr_size["deletions"],
            "changed_lines": pr_size["changed_lines"],
            "changed_files": pr_size["changed_files"],
        },
        "eligibility": eligibility,
    }

    if not eligibility["eligible"]:
        # Not eligible — output result and exit
        print(json.dumps(result, indent=2))
        if args.dry_run:
            print(
                f"# Dry-run: PR #{args.pr_number} skipped for vendor review — "
                f"{eligibility['reason']}: {eligibility['details']['message']}",
                file=sys.stderr,
            )
        return 0

    # Eligible — dispatch vendor reviews
    review_result = dispatch_vendor_reviews(
        pr_number=args.pr_number,
        pr_size=pr_size,
        timeout_seconds=args.timeout,
        dry_run=args.dry_run,
    )
    result["review"] = review_result

    print(json.dumps(result, indent=2))

    if args.dry_run:
        print(
            f"# Dry-run: PR #{args.pr_number} eligible for vendor review — "
            f"{eligibility['details']['message']}",
            file=sys.stderr,
        )
        return 0

    # Summary to stderr
    if review_result.get("dispatched"):
        succeeded = sum(1 for v in review_result.get("vendors", []) if v["success"])
        total = len(review_result.get("vendors", []))
        consensus = review_result.get("consensus")
        if consensus:
            summary = consensus.get("summary", {})
            print(
                f"# Vendor review: {succeeded}/{total} vendors, "
                f"{summary.get('total_unique_findings', 0)} findings "
                f"({summary.get('confirmed_count', 0)} confirmed, "
                f"{summary.get('blocking_count', 0)} blocking)",
                file=sys.stderr,
            )
        else:
            print(
                f"# Vendor review: {succeeded}/{total} vendors — no findings produced",
                file=sys.stderr,
            )
    elif review_result.get("error"):
        print(
            f"# Vendor review failed: {review_result['error']}",
            file=sys.stderr,
        )

    # Fail loudly when a vendor CLI mutated the checkout, even if HEAD was
    # restored — the operator must know the shared tree was touched.
    head_guard = review_result.get("head_guard")
    if head_guard and head_guard.get("drift_detected"):
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
