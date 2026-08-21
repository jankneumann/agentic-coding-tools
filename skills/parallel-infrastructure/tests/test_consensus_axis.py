"""Tests for axis handling in consensus_synthesizer.py.

Covers the review-findings axis contract (see
``openspec/changes/introduce-fitness-function-gates/contracts/review-findings-axis.md``):

  * ``axis`` round-trips from a vendor finding through synthesis into the
    consensus finding's ``agreed_axis`` (and into the serialized report),
  * cross-vendor matching keys on ``(axis, file_path, line_range-overlap)``,
    so two vendors reporting the same lines under *different* axes do not
    merge into a single consensus finding,
  * legacy payloads without an ``axis`` key keep the documented migration
    default ``correctness``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from consensus_synthesizer import (  # noqa: E402
    ConsensusSynthesizer,
    Finding,
    VendorResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finding_dict(
    finding_id: int,
    *,
    axis: str | None = "correctness",
    description: str = "Retry loop drops the last error without logging it",
    file_path: str = "src/worker.py",
    start: int = 10,
    end: int = 20,
    criticality: str = "high",
    disposition: str = "fix",
    type_: str = "correctness",
) -> dict:
    data = {
        "id": finding_id,
        "type": type_,
        "criticality": criticality,
        "description": description,
        "disposition": disposition,
        "file_path": file_path,
        "line_range": {"start": start, "end": end},
    }
    if axis is not None:
        data["axis"] = axis
    return data


def _synthesize(vendor_findings: dict[str, list[dict]]):
    synth = ConsensusSynthesizer()
    results = [
        VendorResult(
            vendor=vendor,
            findings=[Finding.from_dict(d, vendor) for d in dicts],
        )
        for vendor, dicts in vendor_findings.items()
    ]
    return synth, synth.synthesize("implementation", "wp-demo", results)


# ---------------------------------------------------------------------------
# (a) axis round-trips through synthesis
# ---------------------------------------------------------------------------

def test_finding_from_dict_reads_axis():
    f = Finding.from_dict(_finding_dict(1, axis="observability"), "codex")
    assert f.axis == "observability"


def test_finding_from_dict_defaults_axis_for_legacy_payloads():
    """Rule 2: legacy findings without `axis` default to `correctness`."""
    f = Finding.from_dict(_finding_dict(1, axis=None), "codex")
    assert f.axis == "correctness"


def test_axis_round_trips_through_synthesis_single_vendor():
    _, report = _synthesize({"codex": [_finding_dict(1, axis="observability")]})

    assert len(report.consensus_findings) == 1
    assert report.consensus_findings[0].agreed_axis == "observability"


def test_axis_round_trips_through_synthesis_multi_vendor():
    _, report = _synthesize(
        {
            "codex": [_finding_dict(1, axis="observability")],
            "grok": [_finding_dict(1, axis="observability")],
        }
    )

    assert len(report.consensus_findings) == 1
    cf = report.consensus_findings[0]
    assert cf.status == "confirmed"
    assert cf.agreed_axis == "observability"


def test_agreed_axis_serialized_in_report_dict():
    synth, report = _synthesize({"codex": [_finding_dict(1, axis="resilience")]})
    payload = synth.to_dict(report)

    assert payload["consensus_findings"][0]["agreed_axis"] == "resilience"


# ---------------------------------------------------------------------------
# (b) different axes at the same location must not merge
# ---------------------------------------------------------------------------

def test_same_location_different_axis_does_not_merge():
    """Rule 3: same-line findings with different axes stay separate."""
    _, report = _synthesize(
        {
            "codex": [
                _finding_dict(
                    1,
                    axis="observability",
                    description="No structured log emitted when the retry budget runs out",
                )
            ],
            "grok": [
                _finding_dict(
                    1,
                    axis="correctness",
                    description="Retry budget off-by-one lets an extra attempt through",
                )
            ],
        }
    )

    assert len(report.consensus_findings) == 2
    assert {cf.status for cf in report.consensus_findings} == {"unconfirmed"}
    assert {cf.agreed_axis for cf in report.consensus_findings} == {
        "observability",
        "correctness",
    }


def test_same_location_same_axis_still_merges():
    """Guard: the axis key must not break legitimate cross-vendor merging."""
    _, report = _synthesize(
        {
            "codex": [
                _finding_dict(
                    1,
                    axis="observability",
                    description="No structured log emitted when the retry budget runs out",
                )
            ],
            "grok": [
                _finding_dict(
                    1,
                    axis="observability",
                    description="Retry exhaustion is silent — nothing is logged",
                )
            ],
        }
    )

    assert len(report.consensus_findings) == 1
    assert report.consensus_findings[0].status == "confirmed"


def test_agreed_axis_majority_vote():
    """Three vendors, two axes: the majority axis wins."""
    _, report = _synthesize(
        {
            "codex": [_finding_dict(1, axis="resilience")],
            "grok": [_finding_dict(1, axis="resilience")],
            "gemini": [_finding_dict(1, axis="resilience")],
        }
    )

    assert len(report.consensus_findings) == 1
    assert report.consensus_findings[0].agreed_axis == "resilience"


def test_legacy_payloads_without_axis_still_merge():
    """Rule 4 (safe defaults): axis-less legacy findings behave as before."""
    _, report = _synthesize(
        {
            "codex": [_finding_dict(1, axis=None)],
            "grok": [_finding_dict(1, axis=None)],
        }
    )

    assert len(report.consensus_findings) == 1
    cf = report.consensus_findings[0]
    assert cf.status == "confirmed"
    assert cf.agreed_axis == "correctness"
