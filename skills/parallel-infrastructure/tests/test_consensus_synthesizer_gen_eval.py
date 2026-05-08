"""Tests for consensus_synthesizer.py gen-eval / behavioral source integration.

Verifies WP5 of the factory-missions-architecture-alignment change:

  * synthesizer accepts ``findings-gen-eval.json`` as a vendor source
    alongside scrutiny findings,
  * missing ``findings-gen-eval.json`` is not an error (graceful skip
    with a log line),
  * findings are ranked uniformly by severity (critical → low) with no
    different ranking logic for behavioral vs scrutiny findings.

These tests scope themselves to ``test_consensus_synthesizer_gen_eval.py``
so they don't entangle with future scrutiny-side test additions.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from consensus_synthesizer import (  # noqa: E402
    ConsensusInputError,
    Finding,
    format_vendor_counts,
    load_behavioral_findings,
    rank_findings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "openspec"
    / "schemas"
    / "review-findings.schema.json"
)


def _scrutiny_finding(
    *, fid: int, criticality: str, vendor: str, file_path: str
) -> dict:
    """Build a scrutiny-style finding dict (correctness type)."""
    return {
        "id": fid,
        "type": "correctness",
        "criticality": criticality,
        "description": f"{vendor} finding {fid} in {file_path}",
        "disposition": "fix",
        "file_path": file_path,
    }


def _behavioral_finding(
    *, fid: int, criticality: str, file_path: str, line_start: int = 10
) -> dict:
    """Build a behavioral_failure finding dict."""
    return {
        "id": fid,
        "type": "behavioral_failure",
        "criticality": criticality,
        "description": f"behavioral failure {fid}",
        "disposition": "fix",
        "file_path": file_path,
        "line_range": {"start": line_start, "end": line_start + 5},
    }


def _write_findings_file(
    path: Path, *, vendor: str, findings: list[dict], target: str = "demo"
) -> None:
    path.write_text(
        json.dumps(
            {
                "review_type": "implementation",
                "target": target,
                "reviewer_vendor": vendor,
                "findings": findings,
            },
            indent=2,
        )
    )


def _run_synthesizer_cli(
    *, input_dir: Path, output: Path, extra_args: list[str] | None = None
) -> subprocess.CompletedProcess:
    """Invoke the CLI directly so the stdout-merged-line assertion is real."""
    script = (
        Path(__file__).resolve().parent.parent / "scripts" / "consensus_synthesizer.py"
    )
    args = [
        sys.executable,
        str(script),
        "--review-type",
        "implementation",
        "--target",
        "demo",
        "--input-dir",
        str(input_dir),
        "--output",
        str(output),
        "--quorum",
        "2",
    ]
    if SCHEMA_PATH.exists():
        args += ["--schema", str(SCHEMA_PATH)]
    if extra_args:
        args += extra_args
    return subprocess.run(args, capture_output=True, text=True, check=False)


# ---------------------------------------------------------------------------
# 5.1 — synthesizer merges gen-eval and reviewer findings
# ---------------------------------------------------------------------------


def test_synthesizer_merges_gen_eval_with_reviewer_findings(tmp_path: Path) -> None:
    """3 claude + 2 codex + 4 gen-eval (all high) → 9 entries, vendor-count log."""
    _write_findings_file(
        tmp_path / "findings-claude.json",
        vendor="claude",
        findings=[
            _scrutiny_finding(fid=i + 1, criticality="medium", vendor="claude", file_path=f"src/c{i}.py")
            for i in range(3)
        ],
    )
    _write_findings_file(
        tmp_path / "findings-codex.json",
        vendor="codex",
        findings=[
            _scrutiny_finding(fid=i + 1, criticality="low", vendor="codex", file_path=f"src/x{i}.py")
            for i in range(2)
        ],
    )
    _write_findings_file(
        tmp_path / "findings-gen-eval.json",
        vendor="gen-eval",
        findings=[
            _behavioral_finding(fid=i + 1, criticality="high", file_path=f"specs/spec{i}.md")
            for i in range(4)
        ],
    )

    output = tmp_path / "consensus.json"
    result = _run_synthesizer_cli(input_dir=tmp_path, output=output)

    assert result.returncode == 0, result.stderr

    # Per-vendor count regex: `merged: .*claude=3.*codex=2.*gen-eval=4`
    assert re.search(
        r"merged: .*claude=3.*codex=2.*gen-eval=4", result.stdout
    ), f"vendor-count log not found in stdout:\n{result.stdout}"

    consensus = json.loads(output.read_text())
    findings = consensus["consensus_findings"]

    # 9 distinct findings (no cross-vendor matches expected — different
    # types and file paths)
    assert len(findings) == 9, f"expected 9 entries, got {len(findings)}: {findings}"

    # All 4 behavioral_failure entries present
    behavioral = [f for f in findings if f["agreed_type"] == "behavioral_failure"]
    assert len(behavioral) == 4

    # Findings ordered by severity ascending (critical < high < medium < low).
    # Map to numeric rank.
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ranks = [rank[f["agreed_criticality"]] for f in findings]
    assert ranks == sorted(ranks), f"not sorted by severity: {ranks}"


def test_synthesizer_merge_log_uses_format_helper() -> None:
    """The vendor-count helper must produce a string matching the contract regex."""
    line = format_vendor_counts({"claude": 3, "codex": 2, "gen-eval": 4})
    assert re.match(r"merged: .*claude=3.*codex=2.*gen-eval=4", line)


# ---------------------------------------------------------------------------
# 5.2 — missing findings file graceful handling
# ---------------------------------------------------------------------------


def test_synthesizer_handles_missing_gen_eval_file(tmp_path: Path) -> None:
    """No findings-gen-eval.json → log skip line, exit zero, scrutiny only."""
    _write_findings_file(
        tmp_path / "findings-claude.json",
        vendor="claude",
        findings=[
            _scrutiny_finding(fid=i + 1, criticality="medium", vendor="claude", file_path=f"src/c{i}.py")
            for i in range(3)
        ],
    )
    _write_findings_file(
        tmp_path / "findings-codex.json",
        vendor="codex",
        findings=[
            _scrutiny_finding(fid=i + 1, criticality="high", vendor="codex", file_path=f"src/x{i}.py")
            for i in range(2)
        ],
    )
    # Intentionally no findings-gen-eval.json

    output = tmp_path / "consensus.json"
    result = _run_synthesizer_cli(input_dir=tmp_path, output=output)

    assert result.returncode == 0, result.stderr
    assert "no gen-eval findings (skipping behavioral source)" in result.stdout, (
        f"missing skip log line:\n{result.stdout}"
    )

    consensus = json.loads(output.read_text())
    findings = consensus["consensus_findings"]
    assert len(findings) == 5, f"expected 5 scrutiny entries, got {len(findings)}"
    # No behavioral_failure entries when file absent
    assert all(f["agreed_type"] != "behavioral_failure" for f in findings)


def test_load_behavioral_findings_missing_file_is_empty(tmp_path: Path) -> None:
    """Library-level: missing file returns [] and logs to provided stream."""
    log = io.StringIO()
    out = load_behavioral_findings(tmp_path, log_stream=log)
    assert out == []
    assert "no gen-eval findings (skipping behavioral source)" in log.getvalue()


# ---------------------------------------------------------------------------
# 5.x — uniform severity ranking across scrutiny + behavioral
# ---------------------------------------------------------------------------


def test_synthesizer_orders_by_severity_ascending(tmp_path: Path) -> None:
    """1 critical scrutiny + 1 high behavioral + 1 medium scrutiny → critical, high, medium."""
    _write_findings_file(
        tmp_path / "findings-claude.json",
        vendor="claude",
        findings=[
            _scrutiny_finding(fid=1, criticality="critical", vendor="claude", file_path="src/a.py"),
        ],
    )
    _write_findings_file(
        tmp_path / "findings-codex.json",
        vendor="codex",
        findings=[
            _scrutiny_finding(fid=1, criticality="medium", vendor="codex", file_path="src/b.py"),
        ],
    )
    _write_findings_file(
        tmp_path / "findings-gen-eval.json",
        vendor="gen-eval",
        findings=[
            _behavioral_finding(fid=1, criticality="high", file_path="specs/foo.md"),
        ],
    )

    output = tmp_path / "consensus.json"
    result = _run_synthesizer_cli(input_dir=tmp_path, output=output)
    assert result.returncode == 0, result.stderr

    consensus = json.loads(output.read_text())
    crits = [f["agreed_criticality"] for f in consensus["consensus_findings"]]
    assert crits == ["critical", "high", "medium"], crits


def test_rank_findings_orders_critical_first() -> None:
    """Library-level rank helper: critical < high < medium < low."""
    items = [
        Finding(
            id=1,
            type="correctness",
            criticality="medium",
            description="m",
            disposition="fix",
            vendor="a",
        ),
        Finding(
            id=2,
            type="behavioral_failure",
            criticality="critical",
            description="c",
            disposition="fix",
            vendor="b",
        ),
        Finding(
            id=3,
            type="correctness",
            criticality="low",
            description="l",
            disposition="fix",
            vendor="c",
        ),
        Finding(
            id=4,
            type="behavioral_failure",
            criticality="high",
            description="h",
            disposition="fix",
            vendor="d",
        ),
    ]
    ranked = rank_findings(items)
    assert [f.criticality for f in ranked] == ["critical", "high", "medium", "low"]


# ---------------------------------------------------------------------------
# Schema validation — ensure load_behavioral_findings catches malformed files
# ---------------------------------------------------------------------------


def test_load_behavioral_findings_rejects_schema_violation(tmp_path: Path) -> None:
    """A findings file missing required `disposition` MUST raise ConsensusInputError.

    Skipped if jsonschema isn't installed in the test venv (we still pass when
    validation is unavailable since the synthesizer's contract is best-effort
    in that case).
    """
    pytest.importorskip("jsonschema")

    # Missing required `disposition` field
    bad = tmp_path / "findings-gen-eval.json"
    bad.write_text(
        json.dumps(
            {
                "review_type": "implementation",
                "target": "demo",
                "reviewer_vendor": "gen-eval",
                "findings": [
                    {
                        "id": 1,
                        "type": "behavioral_failure",
                        "criticality": "high",
                        "description": "missing disposition",
                        # disposition omitted on purpose
                    }
                ],
            }
        )
    )

    with pytest.raises(ConsensusInputError):
        load_behavioral_findings(tmp_path, schema_path=SCHEMA_PATH)
