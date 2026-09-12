"""Review-fix convergence loop engine.

Drives iterative review → synthesize → fix cycles until findings converge
to zero blocking issues, a stall is detected, or max rounds are reached.

Usage:
    from convergence_loop import converge, ConvergenceResult

    result = converge(
        change_id="my-feature",
        review_type="implementation",
        artifacts_dir=Path("openspec/changes/my-feature"),
        worktree_path=Path("/path/to/worktree"),
        agents_yaml_path=Path("agents.yaml"),
    )
    if result.converged:
        print("All clear!")
    else:
        print(f"Stopped: {result.reason}")
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Import review_dispatcher and consensus_synthesizer from parallel-infrastructure
# ---------------------------------------------------------------------------

_PARALLEL_INFRA_DIR = str(
    Path(__file__).resolve().parent.parent.parent
    / "parallel-infrastructure"
    / "scripts"
)
if _PARALLEL_INFRA_DIR not in sys.path:
    sys.path.insert(0, _PARALLEL_INFRA_DIR)

from consensus_synthesizer import (  # noqa: E402
    ConsensusSynthesizer,
    Finding,
    VendorResult,
)
from review_dispatcher import (  # noqa: E402
    ReviewOrchestrator,
    ReviewResult,
)
from review_ledger import (  # noqa: E402
    append_parked_disagreement,
    blocking_items as ledger_blocking_items,
    compact as compact_ledger,
    is_blocking_item,
    load_or_create as load_or_create_ledger,
    merge_findings,
    park_item,
    parked_items,
    reject_out_of_scope_fix,
    save as save_ledger,
    scoped_fix_payload,
    mark_addressed,
)

# Module-level aliases so tests can monkeypatch the checkpoint helpers via
# ``convergence_loop.cf_write_vendor_findings``. The bare imports also make
# the dependency direction explicit (autopilot → parallel-infrastructure).
from checkpoint_findings import (  # noqa: E402
    _safe_log_error as cf_safe_log_error,
    write_manifest as cf_write_manifest,
    write_raw_output as cf_write_raw_output,
    write_vendor_findings as cf_write_vendor_findings,
)

logger = logging.getLogger(__name__)

# Default criticality levels that count as blocking
_BLOCKING_CRITICALITIES = {"medium", "high", "critical"}

# Default stall detection window (post-compact blocking must strictly decrease)
_DEFAULT_STALL_WINDOW = 2


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ConvergenceResult:
    """Outcome of a convergence loop run.

    ``checkpoint_dir`` points at the most-recent round's checkpoint directory
    (e.g. ``<artifacts_dir>/.review-cache/round-2``). Recovery-aware callers
    read it to locate persisted vendor findings; existing callers ignore it
    (defaults to None for backward compatibility). Round subdivision under
    ``.review-cache/`` preserves cross-round audit history while staying
    inside the namespace specified by the spec.
    """

    converged: bool
    rounds: int
    reason: str | None = None
    consensus: dict[str, Any] | None = None
    escalate_findings: list[dict[str, Any]] | None = None
    validation_errors: list[str] | None = None
    checkpoint_dir: Path | None = None


# ---------------------------------------------------------------------------
# Review prompt builder
# ---------------------------------------------------------------------------

def build_review_prompt(
    artifacts_dir: Path,
    round_num: int,
    ledger: dict[str, Any] | None = None,
    last_fix_diff: str | None = None,
) -> str:
    """Build a review instruction from the artifacts directory.

    Round 1 is a full review plus "do not re-emit ledger items". Round N>1
    is compact+delta: open ledger items, last-fix diff, and a ban on
    re-opening retired or parked items (design D5).
    """
    parts: list[str] = [
        f"## Review Round {round_num}",
        "",
        "Review the following artifacts for correctness, completeness, "
        "and adherence to project standards.",
        "",
    ]

    # Include proposal if present
    proposal = artifacts_dir / "proposal.md"
    if proposal.exists():
        parts.append("### Proposal")
        parts.append(proposal.read_text()[:4000])
        parts.append("")

    # Include design if present
    design = artifacts_dir / "design.md"
    if design.exists():
        parts.append("### Design")
        parts.append(design.read_text()[:4000])
        parts.append("")

    from review_findings_schema import prompt_contract_block

    items = list((ledger or {}).get("items") or [])
    open_items = [i for i in items if i.get("status") == "open"]
    if open_items:
        parts.append("### Open ledger items")
        for item in open_items:
            parts.append(
                f"- [{item.get('id')}] {item.get('description', '')}"
            )
        parts.append("")
        parts.append(
            "Do not emit findings for issues already in the ledger "
            "except to re-verify the open items listed above."
        )
        parts.append("")

    if round_num > 1:
        diff_text = last_fix_diff if last_fix_diff else "(empty-diff)"
        parts.append("### Last-fix diff")
        parts.append(diff_text[:8000])
        parts.append("")
        parts.append(
            "Hunt only in the attached last-fix diff. Re-verify open "
            "ledger items. Do not re-open retired or parked items."
        )
        parts.append("")

    parts.extend([
        "### Instructions",
        "Return findings as JSON with a top-level `findings` array.",
        prompt_contract_block(),
        "",
        f"This is round {round_num}. Focus on remaining issues.",
    ])

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _review_results_to_vendor_results(
    results: list[ReviewResult],
) -> list[VendorResult]:
    """Convert ReviewResult list to VendorResult list for the synthesizer."""
    vendor_results: list[VendorResult] = []
    for r in results:
        findings: list[Finding] = []
        if r.success and r.findings:
            for f_data in r.findings.get("findings", []):
                try:
                    findings.append(Finding.from_dict(f_data, vendor=r.vendor))
                except (KeyError, TypeError):
                    logger.warning(
                        "Skipping malformed finding from %s: %s",
                        r.vendor, f_data,
                    )
        vendor_results.append(VendorResult(
            vendor=r.vendor,
            findings=findings,
            success=r.success,
            elapsed_seconds=r.elapsed_seconds,
            error=r.error,
        ))
    return vendor_results


def _is_blocking(
    cf: dict[str, Any],
    *,
    relax_unconfirmed: bool = False,
    blocking_criticalities: set[str] | None = None,
) -> bool:
    """Determine if a consensus finding or ledger item is blocking.

    Design D3: open + (deterministic OR confirmed high/critical).
    Unconfirmed medium judgment never blocks. ``relax_unconfirmed`` is
    retained for call-site compatibility and ignored.
    """
    del relax_unconfirmed  # D3 removed the last-round special case
    item = dict(cf)
    if "criticality" not in item and "agreed_criticality" in item:
        item["criticality"] = item["agreed_criticality"]
    if blocking_criticalities is None:
        # Preserve the historical default set for deterministic items so
        # low-severity deterministic nits still do not block unless the
        # caller opts in via blocking_criticalities.
        if (item.get("evidence_class") or "deterministic") == "deterministic":
            crit = item.get("criticality") or item.get("agreed_criticality") or "low"
            if crit not in _BLOCKING_CRITICALITIES:
                return False
    return is_blocking_item(item, blocking_criticalities=blocking_criticalities)


def _vendor_hits(cf: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    primary = cf.get("primary_vendor")
    if primary:
        hits.append(str(primary))
    for matched in cf.get("matched_findings") or []:
        vendor = matched.get("vendor") if isinstance(matched, dict) else None
        if vendor and vendor not in hits:
            hits.append(str(vendor))
    for extra in cf.get("vendor_hits") or []:
        if extra not in hits:
            hits.append(str(extra))
    return hits


def _file_path_from_vendors(
    cf: dict[str, Any],
    vendor_results: list[VendorResult],
) -> str | None:
    if cf.get("file_path"):
        return str(cf["file_path"])
    primary = cf.get("primary_vendor")
    fid = cf.get("primary_finding_id")
    for vr in vendor_results:
        if primary and vr.vendor != primary:
            continue
        for finding in vr.findings:
            if fid is not None and finding.id == fid and finding.file_path:
                return finding.file_path
    return None


def _enrich_consensus_findings(
    consensus_dict: dict[str, Any],
    report: Any,
    vendor_results: list[VendorResult],
) -> None:
    """Stamp evidence_class, axis, file_path, vendor_hits for the ledger."""
    objs = {}
    findings_attr = getattr(report, "consensus_findings", None)
    if findings_attr:
        for obj in findings_attr:
            objs[getattr(obj, "id", None)] = obj
    for cf in consensus_dict.get("consensus_findings", []):
        obj = objs.get(cf.get("id"))
        if obj is not None:
            cf.setdefault("evidence_class", getattr(obj, "evidence_class", None))
            cf.setdefault("agreed_axis", getattr(obj, "agreed_axis", None))
            cf.setdefault("axis", getattr(obj, "agreed_axis", None))
        cf["vendor_hits"] = _vendor_hits(cf)
        path = _file_path_from_vendors(cf, vendor_results)
        if path:
            cf["file_path"] = path


def _git(worktree_path: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout or ""


def _snapshot_rev(worktree_path: Path) -> str:
    """HEAD revision before a fix callback runs."""
    return _git(worktree_path, "rev-parse", "HEAD").strip()


def _last_fix_diff(
    worktree_path: Path,
    pre_fix_rev: str | None = None,
) -> str:
    """Diff of commits plus dirty tree since ``pre_fix_rev``.

    ``git diff HEAD`` is empty when the callback committed its edits, so
    round N+1 would hunt an empty-diff marker. ``git diff <pre_fix_rev>``
    compares the working tree to the snapshot, which includes both the
    new HEAD and leftover dirty files. Dirty-only is the fallback when
    no snapshot is available.
    """
    if pre_fix_rev:
        diff = _git(worktree_path, "diff", pre_fix_rev)
        if diff:
            return diff
    return _git(worktree_path, "diff", "HEAD")


def _untracked_paths(worktree_path: Path) -> set[str]:
    return {
        line.strip()
        for line in _git(
            worktree_path, "ls-files", "--others", "--exclude-standard",
        ).splitlines()
        if line.strip()
    }


def _changed_paths(
    worktree_path: Path,
    pre_fix_rev: str | None = None,
    pre_untracked: set[str] | None = None,
) -> list[str]:
    """Repo-relative paths changed by the fix callback (commits + dirty).

    Pre-existing untracked files (ledger, checkpoints) are subtracted so
    the scope check only sees the callback's edits.
    """
    names: set[str] = set()
    if pre_fix_rev:
        for line in _git(
            worktree_path, "diff", "--name-only", pre_fix_rev,
        ).splitlines():
            if line.strip():
                names.add(line.strip())
    else:
        for cmd in (
            ("diff", "--name-only", "HEAD"),
            ("diff", "--name-only", "--cached"),
        ):
            for line in _git(worktree_path, *cmd).splitlines():
                if line.strip():
                    names.add(line.strip())
    untracked = _untracked_paths(worktree_path)
    if pre_untracked is not None:
        untracked -= pre_untracked
    names |= untracked
    return sorted(names)


def _compute_vendor_agreement_rate(
    consensus_dict: dict[str, Any] | None,
) -> float:
    """Compute vendor agreement rate from consensus findings.

    Returns a float 0.0-1.0 representing the fraction of multi-vendor
    consensus findings where vendors agreed on disposition (confirmed).
    Single-vendor (unconfirmed) findings are excluded from the calculation.
    Returns 1.0 if there are no multi-vendor findings.
    """
    if not consensus_dict:
        return 1.0
    findings = consensus_dict.get("consensus_findings", [])
    multi_vendor = [
        f for f in findings if f.get("status") in ("confirmed", "disagreement")
    ]
    if not multi_vendor:
        return 1.0
    agreed = sum(1 for f in multi_vendor if f.get("status") == "confirmed")
    return agreed / len(multi_vendor)


def _build_escalation_summary(
    reason: str,
    rounds_completed: int,
    unresolved_findings: list[dict[str, Any]],
    trend: list[int],
    consensus_dict: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a structured escalation summary for human review.

    Args:
        reason: Why the loop stopped (max_rounds, disagreement, stalled).
        rounds_completed: Number of review rounds completed.
        unresolved_findings: Findings that remain unresolved.
        trend: Per-round blocking finding counts.
        consensus_dict: Latest consensus report dict.

    Returns:
        Structured dict suitable for the escalation_callback.
    """
    return {
        "reason": reason,
        "rounds_completed": rounds_completed,
        "unresolved_findings": unresolved_findings,
        "iteration_history": list(trend),
        "vendor_agreement_rate": _compute_vendor_agreement_rate(consensus_dict),
    }


def _build_convergence_metrics(
    *,
    rounds_completed: int,
    findings_per_round: list[int],
    convergence_status: str,
    total_time_seconds: float,
    consensus_dict: dict[str, Any] | None,
    escalation_count: int,
) -> dict[str, Any]:
    """Build structured convergence metrics for episodic memory.

    Args:
        rounds_completed: Number of review rounds completed.
        findings_per_round: Blocking finding counts per round.
        convergence_status: One of "converged", "escalated", "stalled",
            "max_rounds".
        total_time_seconds: Wall-clock time for the entire converge() call.
        consensus_dict: Latest consensus report dict (for agreement rate).
        escalation_count: Number of escalation events (0 if converged).

    Returns:
        Structured dict to be serialized as JSON for memory_callback.
        When convergence fails, includes capability-gap tag fields
        (failure_type, capability_gap, source) per the D4 schema.
    """
    metrics: dict[str, Any] = {
        "rounds_completed": rounds_completed,
        "findings_per_round": list(findings_per_round),
        "convergence_status": convergence_status,
        "total_time_seconds": round(total_time_seconds, 3),
        "vendor_agreement_rate": _compute_vendor_agreement_rate(consensus_dict),
        "escalation_count": escalation_count,
    }

    # Add capability-gap tag schema fields on failure
    if convergence_status != "converged":
        metrics["failure_type"] = "convergence_failed"
        metrics["capability_gap"] = (
            f"Review loop did not converge: {convergence_status} "
            f"after {rounds_completed} rounds"
        )
        metrics["source"] = "self-reported"

    return metrics


# ---------------------------------------------------------------------------
# Main convergence loop
# ---------------------------------------------------------------------------

def converge(
    change_id: str,
    review_type: str,
    artifacts_dir: Path,
    worktree_path: Path,
    agents_yaml_path: Path | None = None,
    max_rounds: int = 3,
    min_quorum: int = 2,
    fix_mode: str = "inline",
    fix_callback: Callable[[list[dict[str, Any]], Path], None] | None = None,
    memory_callback: Callable[[str], None] | None = None,
    orchestrator: ReviewOrchestrator | None = None,
    post_fix_validator: Callable[[Path], list[str]] | None = None,
    escalation_callback: Callable[[dict[str, Any]], None] | None = None,
    blocking_criticalities: set[str] | None = None,
    stall_window: int = _DEFAULT_STALL_WINDOW,
) -> ConvergenceResult:
    """Run the review-fix convergence loop.

    Args:
        change_id: OpenSpec change identifier.
        review_type: Type of review (plan, implementation).
        artifacts_dir: Path to artifacts being reviewed.
        worktree_path: Working directory for vendor CLI dispatch.
        agents_yaml_path: Path to agents.yaml (optional if orchestrator provided).
        max_rounds: Maximum review rounds before giving up.
        min_quorum: Minimum successful vendor reviews per round.
        fix_mode: "inline" (conductor fixes) or "targeted" (vendor dispatch).
        fix_callback: Called with (blocking_findings, worktree_path) to apply fixes.
        memory_callback: Called with a summary string each round for episodic memory.
        orchestrator: Pre-built ReviewOrchestrator (for testing/reuse).
        post_fix_validator: Called with ``(worktree_path)`` after fixes are applied.
            Returns a list of error strings (e.g. test failures, type errors).
            Errors are logged and attached to the result but do not alter
            convergence logic — the next review round will surface them.
        escalation_callback: Called with a structured escalation summary when
            the loop exits without converging (reason is "max_rounds" or
            "stalled"). Disagreement is parked, not a loop abort.
        blocking_criticalities: Set of criticality levels that count as
            blocking. Defaults to ``{"medium", "high", "critical"}``.
        stall_window: Number of data points for stall detection.
            Stall is detected when ``trend[-1] >= trend[-stall_window]``.
            Defaults to 2 (post-compact blocking must strictly decrease).

    Returns:
        ConvergenceResult with convergence status and details.
    """
    start_time = time.monotonic()

    # 1. Create orchestrator
    if orchestrator is None:
        if agents_yaml_path:
            orchestrator = ReviewOrchestrator.from_agents_yaml(agents_yaml_path)
        else:
            orchestrator = ReviewOrchestrator.from_coordinator()

    synthesizer = ConsensusSynthesizer(quorum=min_quorum)
    trend: list[int] = []
    consensus_dict: dict[str, Any] | None = None
    blocking: list[dict[str, Any]] = []
    all_validation_errors: list[str] = []
    latest_checkpoint_dir: Path | None = None
    last_fix_diff = ""
    ledger = load_or_create_ledger(artifacts_dir, change_id)

    # 2. Loop through rounds
    for round_num in range(1, max_rounds + 1):
        logger.info(
            "Convergence round %d/%d for %s", round_num, max_rounds, change_id,
        )

        if round_num > 1:
            compact_ledger(ledger, worktree_path)
            save_ledger(ledger, artifacts_dir)

        # 2a. Dispatch reviews
        prompt = build_review_prompt(
            artifacts_dir,
            round_num,
            ledger=ledger,
            last_fix_diff=last_fix_diff,
        )
        results = orchestrator.dispatch_and_wait(
            review_type=review_type,
            dispatch_mode="review",
            prompt=prompt,
            cwd=worktree_path,
            timeout_seconds=None,
        )

        # 2aa. Durably checkpoint vendor findings BEFORE synthesis. This is
        # the load-bearing write of the proposal: if synthesizer.synthesize()
        # below raises, the data is already on disk and recoverable. The
        # narrow try/except around the writes only logs and re-raises; it
        # does not swallow.
        checkpoint_dir = artifacts_dir / ".review-cache" / f"round-{round_num}"
        try:
            vendors_index: list[dict[str, Any]] = []
            dispatches: list[dict[str, Any]] = []
            for r in results:
                dispatches.append({
                    "vendor": r.vendor,
                    "success": r.success,
                    "model_used": r.model_used,
                    "models_attempted": r.models_attempted,
                    "elapsed_seconds": r.elapsed_seconds,
                    "error": r.error,
                    "error_class": r.error_class.value if r.error_class else None,
                })
                cf_write_raw_output(
                    checkpoint_dir,
                    vendor=r.vendor,
                    review_type=review_type,
                    stdout=r.raw_stdout,
                    stderr=r.raw_stderr,
                    coercions=list(r.coercions or []),
                )
                if r.success and r.findings:
                    findings_array = r.findings.get("findings", [])
                    cf_write_vendor_findings(
                        checkpoint_dir,
                        vendor=r.vendor,
                        review_type=review_type,
                        target=change_id,
                        findings=findings_array,
                        reviewer_vendor=r.vendor,
                    )
                    vendors_index.append({
                        "name": r.vendor,
                        "findings_path": f"findings-{r.vendor}-{review_type}.json",
                        "finding_count": len(findings_array),
                    })
            cf_write_manifest(
                checkpoint_dir,
                review_type=review_type,
                target=change_id,
                vendors=vendors_index,
                change_id=change_id,
                dispatches=dispatches,
                # quorum_requested = total vendors dispatched (incl. failures);
                # vendors_index only lists successful reviews, so passing it
                # implicitly via the default would understate intent.
                quorum_requested=len(results),
                quorum_received=sum(1 for r in results if r.success),
            )
        except (OSError, PermissionError) as exc:
            cf_safe_log_error(
                "convergence.checkpoint_write_failed",
                change_id=change_id,
                review_type=review_type,
                original_exception_class=type(exc).__name__,
                original_exception_message=str(exc),
                artifacts_dir=str(checkpoint_dir),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            raise
        latest_checkpoint_dir = checkpoint_dir.resolve()

        # 2b. Check quorum
        successful = [r for r in results if r.success]
        if len(successful) < min_quorum:
            logger.warning(
                "Quorum lost: %d/%d (need %d)",
                len(successful), len(results), min_quorum,
            )
            return ConvergenceResult(
                converged=False,
                rounds=round_num,
                reason="quorum_lost",
                validation_errors=all_validation_errors or None,
                checkpoint_dir=latest_checkpoint_dir,
            )

        # 2c-e. Compute consensus. Narrow try/except covers the three steps
        # between checkpoint persistence and consensus availability: parsing
        # vendor outputs into Finding objects, synthesize(), and to_dict(). On
        # any exception, log a structured event with the checkpoint location
        # so operators can locate the persisted findings, then re-raise the
        # ORIGINAL exception unmodified. NOT a fallback — the caller still
        # sees the failure.
        try:
            vendor_results = _review_results_to_vendor_results(results)
            report = synthesizer.synthesize(
                review_type=review_type,
                target=change_id,
                vendor_results=vendor_results,
            )
            consensus_dict = synthesizer.to_dict(report)
            _enrich_consensus_findings(consensus_dict, report, vendor_results)
        except Exception as exc:
            cf_safe_log_error(
                "convergence.synthesis_failed_with_checkpoint",
                change_id=change_id,
                review_type=review_type,
                original_exception_class=type(exc).__name__,
                original_exception_message=str(exc),
                checkpoint_dir=str(latest_checkpoint_dir),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            raise

        # 2f. Park disagreements; do not abort the loop (D4).
        all_findings = list(consensus_dict.get("consensus_findings", []))
        disagreement_findings = [
            cf for cf in all_findings if cf.get("status") == "disagreement"
        ]
        agreed_findings = [
            cf for cf in all_findings if cf.get("status") != "disagreement"
        ]
        if disagreement_findings:
            logger.info(
                "Parking %d disagreement findings in round %d",
                len(disagreement_findings), round_num,
            )
            parked = merge_findings(
                ledger, disagreement_findings, round_num,
                artifacts_dir=artifacts_dir,
            )
            for item in parked:
                park_item(ledger, item)
                dispositions: dict[str, str] = {}
                for cf in disagreement_findings:
                    if cf.get("description") == item.get("description"):
                        dispositions = dict(cf.get("vendor_dispositions") or {})
                        break
                if not dispositions and disagreement_findings:
                    dispositions = dict(
                        disagreement_findings[0].get("vendor_dispositions") or {}
                    )
                append_parked_disagreement(
                    artifacts_dir,
                    change_id,
                    ledger_id=int(item["id"]),
                    round_num=round_num,
                    vendor_dispositions=dispositions,
                    description=str(item.get("description") or ""),
                )
            if memory_callback:
                memory_callback(
                    f"Round {round_num}: parked {len(disagreement_findings)} "
                    "disagreements — continuing"
                )

        merge_findings(
            ledger, agreed_findings, round_num,
            artifacts_dir=artifacts_dir,
        )
        save_ledger(ledger, artifacts_dir)

        # 2g. Blocking set is the ledger after compact+merge (D3).
        blocking = ledger_blocking_items(
            ledger, blocking_criticalities=blocking_criticalities,
        )

        # Track post-compact blocking trend
        trend.append(len(blocking))

        leftovers = parked_items(ledger)

        # Write episodic memory
        if memory_callback:
            summary = consensus_dict.get("summary", {})
            memory_callback(
                f"Round {round_num}: {len(blocking)} blocking findings, "
                f"{summary.get('confirmed_count', 0)} confirmed, "
                f"{summary.get('unconfirmed_count', 0)} unconfirmed"
            )

        # 2i. If no blocking → converged (parked leftovers are advisory).
        if not blocking:
            logger.info("Converged in round %d", round_num)
            if memory_callback:
                memory_callback(json.dumps(_build_convergence_metrics(
                    rounds_completed=round_num,
                    findings_per_round=trend,
                    convergence_status="converged",
                    total_time_seconds=time.monotonic() - start_time,
                    consensus_dict=consensus_dict,
                    escalation_count=0,
                )))
            return ConvergenceResult(
                converged=True,
                rounds=round_num,
                reason=None,
                consensus=consensus_dict,
                escalate_findings=leftovers or None,
                validation_errors=all_validation_errors or None,
                checkpoint_dir=latest_checkpoint_dir,
            )

        # 2j. Stall when post-compact blocking is not strictly decreasing.
        if len(trend) >= stall_window and trend[-1] >= trend[-stall_window]:
            logger.warning(
                "Stall detected: trend %s (window=%d)",
                trend[-stall_window:], stall_window,
            )
            stall_result = ConvergenceResult(
                converged=False,
                rounds=round_num,
                reason="stalled",
                consensus=consensus_dict,
                escalate_findings=blocking,
                validation_errors=all_validation_errors or None,
                checkpoint_dir=latest_checkpoint_dir,
            )
            if escalation_callback is not None:
                escalation_callback(_build_escalation_summary(
                    reason="stalled",
                    rounds_completed=round_num,
                    unresolved_findings=blocking,
                    trend=trend,
                    consensus_dict=consensus_dict,
                ))
            if memory_callback:
                memory_callback(json.dumps(_build_convergence_metrics(
                    rounds_completed=round_num,
                    findings_per_round=trend,
                    convergence_status="stalled",
                    total_time_seconds=time.monotonic() - start_time,
                    consensus_dict=consensus_dict,
                    escalation_count=1,
                )))
            return stall_result

        # 2k. Dispatch scoped fixes for current blocking items only (D7).
        payloads = [
            scoped_fix_payload(item, artifacts_dir=artifacts_dir)
            for item in blocking
        ]
        by_id = {
            int(p["id"]): p for p in payloads if p.get("id") is not None
        }
        for item in ledger.get("items", []):
            payload = by_id.get(int(item.get("id") or 0))
            if payload and payload.get("spec_file"):
                item["spec_file"] = payload["spec_file"]
        save_ledger(ledger, artifacts_dir)
        if fix_callback is not None:
            logger.info(
                "Dispatching fixes for %d blocking findings", len(payloads),
            )
            pre_rev = _snapshot_rev(worktree_path)
            pre_untracked = _untracked_paths(worktree_path)
            fix_callback(payloads, worktree_path)
            changed = _changed_paths(worktree_path, pre_rev, pre_untracked)
            allowed: list[str] = []
            seen_allowed: set[str] = set()
            for payload in payloads:
                for path in payload.get("allowed_paths") or []:
                    if path not in seen_allowed:
                        seen_allowed.add(path)
                        allowed.append(path)
            if changed:
                reject_out_of_scope_fix(changed, allowed)
            last_fix_diff = _last_fix_diff(worktree_path, pre_rev)
            mark_addressed(ledger, [int(item["id"]) for item in blocking])
            save_ledger(ledger, artifacts_dir)

            # 2l. Post-fix validation (optional)
            if post_fix_validator is not None:
                try:
                    errors = post_fix_validator(worktree_path)
                except Exception as exc:
                    logger.warning("post_fix_validator raised: %s", exc)
                    errors = [f"Validator error: {exc}"]
                if errors:
                    logger.warning(
                        "Post-fix validation found %d issues in round %d",
                        len(errors), round_num,
                    )
                    all_validation_errors.extend(errors)

    # 3. Max rounds exhausted
    max_rounds_result = ConvergenceResult(
        converged=False,
        rounds=max_rounds,
        reason="max_rounds",
        consensus=consensus_dict,
        escalate_findings=blocking or None,
        validation_errors=all_validation_errors or None,
        checkpoint_dir=latest_checkpoint_dir,
    )
    if escalation_callback is not None:
        escalation_callback(_build_escalation_summary(
            reason="max_rounds",
            rounds_completed=max_rounds,
            unresolved_findings=blocking or [],
            trend=trend,
            consensus_dict=consensus_dict,
        ))
    if memory_callback:
        memory_callback(json.dumps(_build_convergence_metrics(
            rounds_completed=max_rounds,
            findings_per_round=trend,
            convergence_status="max_rounds",
            total_time_seconds=time.monotonic() - start_time,
            consensus_dict=consensus_dict,
            escalation_count=1,
        )))
    return max_rounds_result
