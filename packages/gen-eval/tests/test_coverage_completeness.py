"""Every contracted unit is exercised or excluded with a reason (task 5.4a).

Spec scenarios:
  - gen-eval-framework.dogfood
      · an unexercised, unexcluded tool coverage unit fails the gate
      · an excluded coverage unit states why

Design decisions: D11 (the tool floor is completeness with declared
exclusions, not a percentage).

An 80% floor on gen-eval's own CLI is arithmetically unreachable — 14 of 17
flags would have to be exercised and only 5 are. Shipping it would be a gate
that can never pass, the exact mirror of the gate that could never fail, and
equally useless.

The percentage also answers the wrong question. "84% covered" does not say
whether the missing 16% is ``--verbose`` (fine) or ``--fail-threshold`` (not
fine). Completeness forces that judgement to be written down where a reviewer
sees it, which is the point: an unexplained exclusion is how a coverage gap
gets laundered into "intentional".

Exclusions live beside the scenario suite rather than in the CLI contract.
The contract declares what the surface *is*, and that answer does not change
because one suite happens not to exercise part of it — a second consumer
reading the same contract would otherwise inherit gen-eval's gaps as though
they were properties of the interface.

Three ways the gate must fail, all proven here rather than assumed:
a unit that is neither exercised nor excluded, an exclusion with a blank
reason, and an exclusion naming a unit the contract does not declare (a stale
exclusion silently re-opens the gap it once explained).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
CHECKER = PACKAGE_ROOT / "scripts" / "check_coverage_completeness.py"
EXCLUSIONS = PACKAGE_ROOT / "evaluation" / "coverage-exclusions.yaml"
REPORT = PACKAGE_ROOT / "evaluation" / ".reports" / "gen-eval-report.json"


def write_report(
    tmp_path: Path,
    *,
    declared: int,
    covered: list[str],
    unevaluated: list[str],
    coverage_pct: float | None = None,
) -> Path:
    """The subset of the report shape the checker reads."""
    path = tmp_path / "gen-eval-report.json"
    total = declared or 1
    payload: dict[str, Any] = {
        "declared_interface_count": declared,
        "coverage_pct": (
            coverage_pct if coverage_pct is not None else len(covered) / total * 100
        ),
        "per_interface": {unit: {"pass": 1} for unit in covered},
        "unevaluated_interfaces": unevaluated,
    }
    path.write_text(json.dumps(payload))
    return path


def write_exclusions(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "coverage-exclusions.yaml"
    path.write_text(yaml.safe_dump({"exclusions": entries}, sort_keys=False))
    return path


def run_checker(report: Path, exclusions: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--report",
            str(report),
            "--exclusions",
            str(exclusions),
        ],
        capture_output=True,
        text=True,
    )


class TestTheGateFails:
    """Proven to fail, not merely observed to pass."""

    def test_an_unexercised_unexcluded_unit_fails(self, tmp_path: Path) -> None:
        result = run_checker(
            write_report(
                tmp_path, declared=2, covered=["cli:--a"], unevaluated=["cli:--b"]
            ),
            write_exclusions(tmp_path, []),
        )
        assert result.returncode == 1
        assert "cli:--b" in result.stderr

    def test_the_failure_names_every_such_unit(self, tmp_path: Path) -> None:
        """One run must list all of them; fixing them one build at a time is toil."""
        result = run_checker(
            write_report(
                tmp_path,
                declared=3,
                covered=["cli:--a"],
                unevaluated=["cli:--b", "cli:--c"],
            ),
            write_exclusions(tmp_path, []),
        )
        assert "cli:--b" in result.stderr and "cli:--c" in result.stderr

    def test_a_blank_reason_fails(self, tmp_path: Path) -> None:
        result = run_checker(
            write_report(
                tmp_path, declared=2, covered=["cli:--a"], unevaluated=["cli:--b"]
            ),
            write_exclusions(tmp_path, [{"unit": "cli:--b", "reason": "   "}]),
        )
        assert result.returncode == 1
        assert "reason" in result.stderr

    def test_a_missing_reason_key_fails(self, tmp_path: Path) -> None:
        result = run_checker(
            write_report(
                tmp_path, declared=2, covered=["cli:--a"], unevaluated=["cli:--b"]
            ),
            write_exclusions(tmp_path, [{"unit": "cli:--b"}]),
        )
        assert result.returncode == 1

    def test_zero_coverage_fails_even_when_everything_is_excluded(
        self, tmp_path: Path
    ) -> None:
        """Excluding the entire surface is not a covered suite (D3)."""
        result = run_checker(
            write_report(
                tmp_path, declared=2, covered=[], unevaluated=["cli:--a", "cli:--b"]
            ),
            write_exclusions(
                tmp_path,
                [
                    {"unit": "cli:--a", "reason": "no"},
                    {"unit": "cli:--b", "reason": "no"},
                ],
            ),
        )
        assert result.returncode == 1
        assert "0" in result.stderr

    def test_an_empty_declared_surface_fails(self, tmp_path: Path) -> None:
        result = run_checker(
            write_report(tmp_path, declared=0, covered=[], unevaluated=[]),
            write_exclusions(tmp_path, []),
        )
        assert result.returncode == 1

    def test_a_stale_exclusion_fails(self, tmp_path: Path) -> None:
        """An exclusion for a unit the contract dropped explains nothing.

        Left unchecked it accumulates, and the next flag that happens to reuse
        the name inherits an approval nobody granted it.
        """
        result = run_checker(
            write_report(
                tmp_path, declared=2, covered=["cli:--a", "cli:--b"], unevaluated=[]
            ),
            write_exclusions(tmp_path, [{"unit": "cli:--gone", "reason": "obsolete"}]),
        )
        assert result.returncode == 1
        assert "cli:--gone" in result.stderr


class TestTheGatePasses:
    """The shape a satisfied suite actually has."""

    def test_a_fully_exercised_surface_passes(self, tmp_path: Path) -> None:
        result = run_checker(
            write_report(
                tmp_path, declared=2, covered=["cli:--a", "cli:--b"], unevaluated=[]
            ),
            write_exclusions(tmp_path, []),
        )
        assert result.returncode == 0, result.stderr

    def test_a_partly_excluded_surface_passes(self, tmp_path: Path) -> None:
        """29% coverage passes when the other 71% is explained (D11)."""
        result = run_checker(
            write_report(
                tmp_path, declared=2, covered=["cli:--a"], unevaluated=["cli:--b"]
            ),
            write_exclusions(
                tmp_path,
                [{"unit": "cli:--b", "reason": "Diagnostic output only."}],
            ),
        )
        assert result.returncode == 0, result.stderr

    def test_a_percentage_is_reported_but_is_not_the_gate(
        self, tmp_path: Path
    ) -> None:
        result = run_checker(
            write_report(
                tmp_path, declared=2, covered=["cli:--a"], unevaluated=["cli:--b"]
            ),
            write_exclusions(tmp_path, [{"unit": "cli:--b", "reason": "documented"}]),
        )
        assert result.returncode == 0
        assert "50.0" in result.stdout


class TestGenEvalsOwnSuiteSatisfiesIt:
    """The gate is only real if it runs against the artifact it guards."""

    def test_the_exclusions_file_exists(self) -> None:
        assert EXCLUSIONS.is_file(), (
            f"{EXCLUSIONS} is missing — every unit the dogfood suite does not "
            f"exercise needs a written reason (task 5.4c)"
        )

    def test_every_exclusion_has_a_non_blank_reason(self) -> None:
        entries = yaml.safe_load(EXCLUSIONS.read_text())["exclusions"]
        for entry in entries:
            assert entry.get("reason", "").strip(), entry

    def test_the_real_report_passes_the_gate(self) -> None:
        if not REPORT.is_file():
            pytest.skip("no dogfood report on disk — run `make dogfood` first")
        result = run_checker(REPORT, EXCLUSIONS)
        assert result.returncode == 0, result.stderr
