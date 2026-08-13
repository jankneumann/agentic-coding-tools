"""Golden regression coverage for fail-closed review hardening."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "parallel-infrastructure" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from consensus_synthesizer import ConsensusSynthesizer, Finding, VendorResult
from review_attempts import run_vendor_recovery
from review_result_policy import is_quorum_eligible


def _eligible_chain(vendor: str) -> dict[str, object]:
    return run_vendor_recovery(
        logical_request_id=f"integration:{vendor}",
        vendor=vendor,
        primary_model="test-model",
        fallback_models=[],
        timeout_seconds=30,
        invoke=lambda *_args: {"validation_status": "schema_valid"},
    )


def test_unmatched_actionable_finding_cannot_create_a_false_zero() -> None:
    fixture = Path(__file__).parent / "fixtures" / "review-hardening" / "false-zero.json"
    data = json.loads(fixture.read_text())
    finding = Finding.from_dict(data["finding"], vendor=data["vendor"])

    report = ConsensusSynthesizer(quorum=2).synthesize(
        review_type="implementation",
        target="review-hardening",
        vendor_results=[
            VendorResult(
                vendor="codex",
                findings=[finding],
                logical_result=_eligible_chain("codex"),
            ),
            VendorResult(
                vendor="grok",
                findings=[],
                logical_result=_eligible_chain("grok"),
            ),
        ],
    )

    summary = ConsensusSynthesizer(quorum=2).to_dict(report)["summary"]
    assert summary["integration_blocking_count"] == 0
    assert summary["convergence_blocking_count"] == 1
    assert summary["effective_blocking_count"] == summary["blocking_count"] == 1


def test_schema_valid_empty_completion_is_a_quorum_vote() -> None:
    chain = run_vendor_recovery(
        logical_request_id="integration:empty",
        vendor="codex",
        primary_model="gpt-test",
        fallback_models=[],
        timeout_seconds=30,
        invoke=lambda _vendor, _model, _remaining, _reason: {
            "transport": "cli",
            "validation_status": "schema_valid",
        },
    )

    assert chain["terminal_outcome"] == "success"
    assert is_quorum_eligible(chain) is True
