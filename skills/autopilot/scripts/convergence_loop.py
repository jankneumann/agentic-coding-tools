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

import logging
import sys
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

# Module-level aliases so tests can monkeypatch the checkpoint helpers via
# ``convergence_loop.cf_write_vendor_findings``. The bare imports also make
# the dependency direction explicit (autopilot → parallel-infrastructure).
from checkpoint_findings import (  # noqa: E402
    _safe_log_error as cf_safe_log_error,
    write_manifest as cf_write_manifest,
    write_vendor_findings as cf_write_vendor_findings,
)

logger = logging.getLogger(__name__)

# Criticality levels that count as blocking
_BLOCKING_CRITICALITIES = {"medium", "high", "critical"}


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

def build_review_prompt(artifacts_dir: Path, round_num: int) -> str:
    """Build a review instruction from the artifacts directory.

    Reads key artifacts (proposal, design docs, code) and produces a
    prompt instructing the reviewer what to focus on.
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

    parts.extend([
        "### Instructions",
        "Return findings as JSON with a top-level `findings` array.",
        "Each finding must have: id, type, criticality, description, "
        "disposition (fix/accept/escalate/regenerate), and optionally file_path and line_range.",
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
) -> bool:
    """Determine if a consensus finding is blocking.

    Blocking = medium+ criticality AND (confirmed or unconfirmed).
    In the final round, unconfirmed findings are relaxed (not blocking).
    """
    criticality = cf.get("agreed_criticality", "low")
    status = cf.get("status", "unconfirmed")

    if criticality not in _BLOCKING_CRITICALITIES:
        return False

    if status == "confirmed":
        return True

    if status == "unconfirmed" and not relax_unconfirmed:
        return True

    return False


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

    Returns:
        ConvergenceResult with convergence status and details.
    """
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

    # 2. Loop through rounds
    for round_num in range(1, max_rounds + 1):
        logger.info(
            "Convergence round %d/%d for %s", round_num, max_rounds, change_id,
        )

        # 2a. Dispatch reviews
        prompt = build_review_prompt(artifacts_dir, round_num)
        results = orchestrator.dispatch_and_wait(
            review_type=review_type,
            dispatch_mode="review",
            prompt=prompt,
            cwd=worktree_path,
        )

        # 2aa. Durably checkpoint vendor findings BEFORE synthesis. This is
        # the load-bearing write of the proposal: if synthesizer.synthesize()
        # below raises (e.g. the line_range parser bug), the data is already
        # on disk and recoverable. The narrow try/except around the writes
        # only logs and re-raises; it does not swallow.
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
        # vendor outputs into Finding objects (where the line_range parser
        # bug fires), synthesize(), and to_dict(). On any exception, log a
        # structured event with the checkpoint location so operators can
        # locate the persisted findings, then re-raise the ORIGINAL exception
        # unmodified. NOT a fallback — the caller still sees the failure.
        try:
            vendor_results = _review_results_to_vendor_results(results)
            report = synthesizer.synthesize(
                review_type=review_type,
                target=change_id,
                vendor_results=vendor_results,
            )
            consensus_dict = synthesizer.to_dict(report)
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

        # 2f. Check for disagreement findings → escalate
        disagreement_findings = [
            cf for cf in consensus_dict.get("consensus_findings", [])
            if cf.get("status") == "disagreement"
        ]
        if disagreement_findings:
            logger.info(
                "Disagreement found in round %d, escalating %d findings",
                round_num, len(disagreement_findings),
            )
            if memory_callback:
                memory_callback(
                    f"Round {round_num}: disagreement on "
                    f"{len(disagreement_findings)} findings — escalating"
                )
            return ConvergenceResult(
                converged=False,
                rounds=round_num,
                reason="disagreement",
                consensus=consensus_dict,
                escalate_findings=disagreement_findings,
                validation_errors=all_validation_errors or None,
                checkpoint_dir=latest_checkpoint_dir,
            )

        # 2g. Filter blocking findings (medium+ confirmed/unconfirmed)
        is_final_round = round_num == max_rounds

        # 2h. Relax unconfirmed in final round
        blocking = [
            cf for cf in consensus_dict.get("consensus_findings", [])
            if _is_blocking(cf, relax_unconfirmed=is_final_round)
        ]

        # Track trend
        trend.append(len(blocking))

        # Write episodic memory
        if memory_callback:
            summary = consensus_dict.get("summary", {})
            memory_callback(
                f"Round {round_num}: {len(blocking)} blocking findings, "
                f"{summary.get('confirmed_count', 0)} confirmed, "
                f"{summary.get('unconfirmed_count', 0)} unconfirmed"
            )

        # 2i. If no blocking → converged!
        if not blocking:
            logger.info("Converged in round %d", round_num)
            return ConvergenceResult(
                converged=True,
                rounds=round_num,
                reason=None,
                consensus=consensus_dict,
                validation_errors=all_validation_errors or None,
                checkpoint_dir=latest_checkpoint_dir,
            )

        # 2j. 3-point stall detection
        if len(trend) >= 3 and trend[-1] >= trend[-3]:
            logger.warning(
                "Stall detected: trend %s", trend[-3:],
            )
            return ConvergenceResult(
                converged=False,
                rounds=round_num,
                reason="stalled",
                consensus=consensus_dict,
                escalate_findings=blocking,
                validation_errors=all_validation_errors or None,
                checkpoint_dir=latest_checkpoint_dir,
            )

        # 2k. Dispatch fixes
        if fix_callback is not None:
            logger.info(
                "Dispatching fixes for %d blocking findings", len(blocking),
            )
            fix_callback(blocking, worktree_path)

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
    return ConvergenceResult(
        converged=False,
        rounds=max_rounds,
        reason="max_rounds",
        consensus=consensus_dict,
        escalate_findings=blocking or None,
        validation_errors=all_validation_errors or None,
        checkpoint_dir=latest_checkpoint_dir,
    )
