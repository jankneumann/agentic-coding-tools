"""Tests for fail-closed consensus blocker policy."""

from consensus_policy import evaluate_blocking


def test_unmatched_actionable_finding_remains_convergence_blocking() -> None:
    result = evaluate_blocking(
        policy_status="provisional",
        criticality="high",
        vendor_dispositions={"codex": "fix"},
        adjudication={"status": "unreviewed"},
    )
    assert result.convergence_blocking is True
    assert result.effective_blocking is True


def test_false_positive_with_evidence_is_not_blocking() -> None:
    result = evaluate_blocking(
        policy_status="provisional",
        criticality="high",
        vendor_dispositions={"codex": "fix"},
        adjudication={
            "status": "false_positive",
            "rationale": "target is outside the review scope",
            "evidence": ["scope-check.json"],
        },
    )
    assert result.effective_blocking is False


def test_deferred_actionable_finding_remains_convergence_blocking() -> None:
    result = evaluate_blocking(
        policy_status="confirmed",
        criticality="medium",
        vendor_dispositions={"codex": "fix", "grok": "fix"},
        adjudication={"status": "deferred", "rationale": "tracked", "tracking_reference": "#1"},
    )
    assert result.convergence_blocking is True


def test_disagreement_blocks_until_explicit_adjudication() -> None:
    result = evaluate_blocking(
        policy_status="disagreement",
        criticality="medium",
        vendor_dispositions={"codex": "fix", "grok": "accept"},
        adjudication={"status": "unreviewed"},
    )
    assert result.integration_blocking is True
    assert result.convergence_blocking is True
