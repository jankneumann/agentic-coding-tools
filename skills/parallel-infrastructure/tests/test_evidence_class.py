"""Judgment-class findings inform; they never gate.

An adversarial model reviewer is the most interesting reviewer in the set —
business-logic flaws and authorization confusion are exactly what a model
notices and a rule set cannot express. It is also non-deterministic: rerun it
and the findings move, and no seeded defect can prove it would have been caught.
A gate whose verdict is not reproducible cannot be trusted, bisected against, or
distinguished from a lazy run, which is the same failure this repo's other gates
kept hitting from the other direction.

So the distinction is structural rather than a naming convention: findings carry
an evidence class, only deterministic ones count toward `blocking_count`, and the
class is declared at ingest by the caller who chose the reviewer.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from consensus_synthesizer import (  # noqa: E402
    DETERMINISTIC,
    JUDGMENT,
    ConsensusSynthesizer,
    Finding,
    VendorResult,
)


def _finding(fid: int, desc: str, *, evidence: str = DETERMINISTIC, vendor: str = "v") -> Finding:
    return Finding(
        id=fid, type="security", criticality="high", description=desc,
        disposition="fix", vendor=vendor, axis="security", evidence_class=evidence,
    )


def _synth(*vendor_results: VendorResult):
    return ConsensusSynthesizer(quorum=1).synthesize(
        review_type="implementation", target="t", vendor_results=list(vendor_results)
    )


def test_a_deterministic_finding_still_blocks() -> None:
    """The control. Without this the next test could pass vacuously."""
    desc = "unauthenticated write endpoint accepts arbitrary tenant id"
    report = _synth(
        VendorResult(vendor="a", findings=[_finding(1, desc, vendor="a")]),
        VendorResult(vendor="b", findings=[_finding(1, desc, vendor="b")]),
    )
    assert report.blocking_count == 1
    assert report.advisory_count == 0


def test_a_judgment_finding_is_reported_but_never_blocks() -> None:
    desc = "unauthenticated write endpoint accepts arbitrary tenant id"
    report = _synth(
        VendorResult(vendor="a", findings=[_finding(1, desc, evidence=JUDGMENT, vendor="a")]),
        VendorResult(vendor="b", findings=[_finding(1, desc, evidence=JUDGMENT, vendor="b")]),
    )
    assert report.blocking_count == 0, "model judgment must not gate"
    assert report.advisory_count == 1, "but it must still be surfaced"
    assert report.total_unique == 1, "and ranked alongside everything else"


def test_one_deterministic_corroboration_keeps_a_finding_blocking() -> None:
    """Judgment must not be able to talk a reproducible finding out of blocking.

    If a single judgment voice could demote a consensus finding, adding an
    adversarial reviewer would *weaken* the gate — the opposite of the intent.
    """
    desc = "unauthenticated write endpoint accepts arbitrary tenant id"
    report = _synth(
        VendorResult(vendor="a", findings=[_finding(1, desc, evidence=JUDGMENT, vendor="a")]),
        VendorResult(vendor="b", findings=[_finding(1, desc, evidence=DETERMINISTIC, vendor="b")]),
    )
    assert report.blocking_count == 1
    assert report.advisory_count == 0


def test_a_payload_cannot_promote_itself_to_blocking(tmp_path: Path) -> None:
    """`--judgment-vendor` is the caller's declaration and wins over the payload.

    A model asked to label its own findings non-blocking has every incentive to
    do the opposite, so the class is applied at ingest by whoever chose the
    reviewer. The payload may still declare judgment for itself — that direction
    only ever makes a finding less blocking, so it is safe to honour.
    """
    findings_file = tmp_path / "findings-adversarial.json"
    findings_file.write_text(json.dumps({
        "review_type": "implementation",
        "target": "t",
        "reviewer_vendor": "adversarial",
        "findings": [{
            "id": 1, "type": "security", "criticality": "critical",
            "description": "the model is very sure about this one",
            "disposition": "fix", "axis": "security", "severity": "critical",
            "evidence_class": "deterministic",   # <- the payload's own claim
        }],
    }), encoding="utf-8")

    out = tmp_path / "consensus.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "consensus_synthesizer.py"),
         "--review-type", "implementation", "--target", "t",
         "--findings", str(findings_file), "--output", str(out),
         "--quorum", "1", "--judgment-vendor", "adversarial"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    summary = report.get("summary", report)
    assert summary["blocking_count"] == 0, (
        "the caller declared this reviewer judgment-class; the payload's own "
        "label must not override that"
    )
    assert summary["advisory_count"] == 1


def test_an_undeclared_vendor_keeps_its_deterministic_default(tmp_path: Path) -> None:
    """Existing emitters are unchanged: no flag, no behaviour change."""
    findings_file = tmp_path / "findings-codex.json"
    findings_file.write_text(json.dumps({
        "review_type": "implementation",
        "target": "t",
        "reviewer_vendor": "codex",
        "findings": [{
            "id": 1, "type": "correctness", "criticality": "high",
            "description": "off-by-one in the retry backoff",
            "disposition": "fix", "axis": "correctness", "severity": "critical",
        }],
    }), encoding="utf-8")

    out = tmp_path / "consensus.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "consensus_synthesizer.py"),
         "--review-type", "implementation", "--target", "t",
         "--findings", str(findings_file), "--output", str(out), "--quorum", "1"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(out.read_text(encoding="utf-8")).get("summary", {})
    assert summary["advisory_count"] == 0
