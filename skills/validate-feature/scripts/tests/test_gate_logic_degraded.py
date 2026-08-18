"""Tests for the DEGRADED gate status in gate_logic.py.

TDD tests written before implementation (task 2.3, OpenSpec change
introduce-fitness-function-gates). Covers design decision D6 and the status
vocabulary in contracts/architecture-gates-config.md:

| Status     | soft_gate   | hard_gate                                        |
|------------|-------------|--------------------------------------------------|
| DEGRADED   | warn loudly | block if required, unless --accept-degraded <phase> |

DEGRADED means "could not be checked" — distinct from both pass and fail — so
the block message must say NOT CHECKED, and any override must be echoed into
the gate summary.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Ensure scripts dir is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from gate_logic import (  # noqa: E402
    check_phase_status,
    check_smoke_status,
    hard_gate,
    pre_merge_gate,
    soft_gate,
)

_GATE_LOGIC = _SCRIPTS_DIR / "gate_logic.py"


def _validate_feature_skill() -> str:
    return (_SCRIPTS_DIR.parent / "SKILL.md").read_text()


def test_unavailable_e2e_checker_records_degraded() -> None:
    skill = _validate_feature_skill()
    branch = skill.split(
        "elif [ \"$PLAYWRIGHT_AVAILABLE\" = false ]; then", 1
    )[1]
    branch = branch.split("else", 1)[0]
    assert "E2E_RESULT=\"DEGRADED\"" in branch


def test_unavailable_architecture_checker_records_degraded() -> None:
    skill = _validate_feature_skill()
    branch = skill.split(
        "Architecture flow validation was NOT CHECKED", 1
    )[1]
    branch = branch.split("fi", 1)[0]
    assert "FLOW_RESULT=\"DEGRADED\"" in branch


def _report(tmp_path: Path, smoke: str = "pass", security: str = "pass",
            e2e: str = "pass") -> Path:
    report = tmp_path / "validation-report.md"
    report.write_text(
        f"## Smoke Tests\n\n- **Status**: {smoke}\n\n"
        f"## Security\n\n- **Status**: {security}\n\n"
        f"## E2E Tests\n\n- **Status**: {e2e}\n"
    )
    return report


class TestDegradedParsing:
    """DEGRADED must parse out of validation-report.md."""

    def test_uppercase_degraded_parses(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text(
            "## Security\n\n"
            "- **Status**: DEGRADED\n"
            "- **Not checked**: OWASP Dependency-Check — Java runtime absent\n"
        )
        assert check_phase_status(str(report), "Security") == "degraded"

    def test_lowercase_degraded_parses(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text("## Smoke Tests\n\n- **Status**: degraded\n")
        assert check_smoke_status(str(report)) == "degraded"

    def test_degraded_is_distinct_from_pass_and_fail(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text("## E2E Tests\n\n- **Status**: DEGRADED\n")
        status = check_phase_status(str(report), "E2E Tests")
        assert status not in ("pass", "fail", "skipped", "missing")

    def test_legacy_statuses_are_unchanged(self, tmp_path: Path) -> None:
        """Regression guard: existing vocabulary must parse exactly as before."""
        for written, expected in (
            ("pass", "pass"),
            ("fail", "fail"),
            ("skipped", "skipped"),
        ):
            report = tmp_path / f"report-{written}.md"
            report.write_text(f"## Smoke Tests\n\n- **Status**: {written}\n")
            assert check_smoke_status(str(report)) == expected


class TestSoftGateDegraded:
    """Soft gate warns loudly and continues (it never blocks)."""

    def test_degraded_continues(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text("## Smoke Tests\n\n- **Status**: DEGRADED\n")

        action, reason = soft_gate(str(report))
        assert action == "continue"

    def test_degraded_warns_loudly(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text("## Smoke Tests\n\n- **Status**: DEGRADED\n")

        _action, reason = soft_gate(str(report))
        assert "DEGRADED" in reason
        assert "NOT CHECKED" in reason


class TestHardGateDegraded:
    """Hard gate blocks a DEGRADED phase and says it was not checked."""

    def test_degraded_halts(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text("## Smoke Tests\n\n- **Status**: DEGRADED\n")

        action, reason = hard_gate(str(report))
        assert action == "halt"

    def test_message_says_not_checked_not_failed(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text("## Smoke Tests\n\n- **Status**: DEGRADED\n")

        _action, reason = hard_gate(str(report))
        assert "NOT CHECKED" in reason
        assert "failed" not in reason.lower()

    def test_accept_degraded_allows_continue(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text("## Smoke Tests\n\n- **Status**: DEGRADED\n")

        action, reason = hard_gate(str(report), accept_degraded=["Smoke Tests"])
        assert action == "continue"
        assert "OVERRIDE" in reason.upper()


class TestPreMergeGateDegraded:
    """Pre-merge gate: DEGRADED required phase blocks unless overridden."""

    def test_degraded_required_phase_blocks(self, tmp_path: Path) -> None:
        report = _report(tmp_path, security="DEGRADED")

        action, reason, statuses = pre_merge_gate(str(report))
        assert action == "halt"
        assert statuses["Security"] == "degraded"
        assert "NOT CHECKED" in reason

    def test_block_message_distinguishes_degraded_from_failure(
        self, tmp_path: Path
    ) -> None:
        report = _report(tmp_path, security="DEGRADED", e2e="fail")

        _action, reason, _statuses = pre_merge_gate(str(report))
        # The failed phase reads as a failure; the degraded one as unchecked.
        assert "E2E tests: fail" in reason
        assert "NOT CHECKED" in reason
        assert "Security scan" in reason

    def test_accept_degraded_lets_it_pass(self, tmp_path: Path) -> None:
        report = _report(tmp_path, security="DEGRADED")

        action, _reason, _statuses = pre_merge_gate(
            str(report), accept_degraded=["Security"],
        )
        assert action == "continue"

    def test_override_is_recorded_in_the_summary(self, tmp_path: Path) -> None:
        report = _report(tmp_path, security="DEGRADED")

        _action, reason, _statuses = pre_merge_gate(
            str(report), accept_degraded=["Security"],
        )
        assert "DEGRADED OVERRIDE" in reason.upper()
        assert "Security" in reason

    def test_override_accepts_the_human_readable_label(self, tmp_path: Path) -> None:
        report = _report(tmp_path, security="DEGRADED")

        action, _reason, _statuses = pre_merge_gate(
            str(report), accept_degraded=["Security scan"],
        )
        assert action == "continue"

    def test_override_for_another_phase_does_not_unblock(self, tmp_path: Path) -> None:
        report = _report(tmp_path, security="DEGRADED")

        action, _reason, _statuses = pre_merge_gate(
            str(report), accept_degraded=["E2E Tests"],
        )
        assert action == "halt"

    def test_override_does_not_excuse_a_real_failure(self, tmp_path: Path) -> None:
        report = _report(tmp_path, security="DEGRADED", e2e="fail")

        action, reason, _statuses = pre_merge_gate(
            str(report), accept_degraded=["Security"],
        )
        assert action == "halt"
        assert "E2E tests: fail" in reason

    def test_all_pass_summary_has_no_override_noise(self, tmp_path: Path) -> None:
        report = _report(tmp_path)

        _action, reason, _statuses = pre_merge_gate(
            str(report), accept_degraded=["Security"],
        )
        assert "OVERRIDE" not in reason.upper()


class TestCliAcceptDegraded:
    """The override must be reachable and auditable from the CLI."""

    def _run(self, report: Path, *args: str) -> tuple[int, dict]:
        proc = subprocess.run(
            [sys.executable, str(_GATE_LOGIC), str(report), *args],
            capture_output=True,
            text=True,
        )
        return proc.returncode, json.loads(proc.stdout)

    def test_degraded_blocks_without_flag(self, tmp_path: Path) -> None:
        code, payload = self._run(_report(tmp_path, security="DEGRADED"))
        assert code == 1
        assert payload["action"] == "halt"
        assert "NOT CHECKED" in payload["reason"]

    def test_accept_degraded_flag_allows_merge(self, tmp_path: Path) -> None:
        code, payload = self._run(
            _report(tmp_path, security="DEGRADED"), "--accept-degraded", "Security",
        )
        assert code == 0
        assert payload["action"] == "continue"
        assert payload["accept_degraded"] == ["Security"]
        assert "DEGRADED OVERRIDE" in payload["reason"].upper()
