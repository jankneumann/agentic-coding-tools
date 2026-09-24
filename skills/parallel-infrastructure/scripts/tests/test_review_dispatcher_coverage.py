"""Per-vendor coverage scoring wired into CliVendorAdapter.dispatch().

Verifies the packet's selected-file list is recovered from the rendered
rule-groups section, a vendor's optional `coverage` block is coerced and
scored against it, and an absent or unscorable block never penalizes a
vendor — see the "Per-Vendor Coverage Contract" spec scenarios.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from review_dispatcher import (  # noqa: E402
    CliConfig,
    CliVendorAdapter,
    ModeConfig,
    _coerce_coverage_reasons,
    _extract_selected_files_from_prompt,
    _score_coverage,
)

RULE_GROUPS_PROMPT = (
    "## Review Round 1\n\n"
    "### Diff\n```diff\n(empty-diff)\n```\n\n"
    "### Rule groups\n\n"
    "#### Group 1 (default: `(default)`)\n"
    "Applies to:\n"
    "- src/foo.py\n"
    "- src/bar.py\n\n"
    "Review for correctness.\n\n"
    "#### Group 2 (project: `*.md`)\n"
    "Applies to:\n"
    "- docs/readme.md\n\n"
    "Markdown rule text.\n\n"
    "### Instructions\nReturn findings as JSON.\n"
)

NO_RULE_GROUPS_PROMPT = "## Review Round 1\n\n### Diff\n```diff\n(empty-diff)\n```\n"


def _adapter(**kwargs) -> CliVendorAdapter:
    cli_config = CliConfig(
        command="codex",
        dispatch_modes={"review": ModeConfig(args=["exec"])},
        model_flag="-m",
        **kwargs,
    )
    return CliVendorAdapter(agent_id="codex-local", vendor="codex", cli_config=cli_config)


def _findings_json(coverage: dict | None) -> str:
    finding = {
        "id": 1, "type": "correctness", "criticality": "high",
        "description": "test", "disposition": "fix", "axis": "correctness",
        "severity": "critical", "file_path": "src/foo.py",
    }
    payload: dict = {"findings": [finding]}
    if coverage is not None:
        payload["coverage"] = coverage
    return json.dumps(payload)


class TestExtractSelectedFilesFromPrompt:
    def test_recovers_every_file_across_groups(self) -> None:
        paths = _extract_selected_files_from_prompt(RULE_GROUPS_PROMPT)
        assert paths == ["src/foo.py", "src/bar.py", "docs/readme.md"]

    def test_no_rule_groups_section_yields_none(self) -> None:
        assert _extract_selected_files_from_prompt(NO_RULE_GROUPS_PROMPT) is None

    def test_no_diff_fence_prompt_yields_none(self) -> None:
        assert _extract_selected_files_from_prompt("a bare prompt") is None


class TestCoerceCoverageReasons:
    def test_fills_missing_reason_with_unspecified(self) -> None:
        findings = {
            "findings": [],
            "coverage": {"reviewed": [], "skipped": [{"path": "src/x.py"}]},
        }
        notes = _coerce_coverage_reasons(findings)
        assert findings["coverage"]["skipped"][0]["reason"] == "unspecified"
        assert notes == ["coverage.skipped[src/x.py].reason->unspecified"]

    def test_leaves_existing_reason_untouched(self) -> None:
        findings = {
            "findings": [],
            "coverage": {
                "reviewed": [], "skipped": [{"path": "src/x.py", "reason": "binary"}],
            },
        }
        notes = _coerce_coverage_reasons(findings)
        assert findings["coverage"]["skipped"][0]["reason"] == "binary"
        assert notes == []

    def test_no_coverage_block_is_a_noop(self) -> None:
        findings = {"findings": []}
        assert _coerce_coverage_reasons(findings) == []


class TestScoreCoverage:
    def test_partial_coverage_below_threshold(self) -> None:
        findings = {"coverage": {"reviewed": ["a.py", "b.py"], "skipped": []}}
        rate, eligibility, status = _score_coverage(
            findings, ["a.py", "b.py", "c.py", "d.py"], 0.8,
        )
        assert rate == 0.5
        assert eligibility == "partial"
        assert status == "reported"
        assert findings["coverage"]["rate"] == 0.5

    def test_full_coverage_at_or_above_threshold(self) -> None:
        findings = {"coverage": {"reviewed": ["a.py", "b.py"], "skipped": []}}
        rate, eligibility, status = _score_coverage(findings, ["a.py", "b.py"], 0.8)
        assert rate == 1.0
        assert eligibility == "full"
        assert status == "reported"

    def test_missing_coverage_block_is_unreported_and_full(self) -> None:
        rate, eligibility, status = _score_coverage({}, ["a.py"], 0.8)
        assert rate is None
        assert eligibility == "full"
        assert status == "unreported"

    def test_no_selected_files_is_unreported_and_full(self) -> None:
        findings = {"coverage": {"reviewed": ["a.py"], "skipped": []}}
        rate, eligibility, status = _score_coverage(findings, None, 0.8)
        assert rate is None
        assert eligibility == "full"
        assert status == "unreported"


class TestDispatchScoresCoverage:
    @patch("review_dispatcher.subprocess.run")
    def test_partial_coverage_reflected_on_result(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        coverage = {"reviewed": ["src/foo.py"], "skipped": []}
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_findings_json(coverage), stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", RULE_GROUPS_PROMPT, cwd=tmp_path)
        assert result.success is True
        assert result.coverage_status == "reported"
        assert result.coverage_eligibility == "partial"
        assert result.coverage_rate == 1 / 3

    @patch("review_dispatcher.subprocess.run")
    def test_missing_coverage_block_is_unreported(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_findings_json(None), stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", RULE_GROUPS_PROMPT, cwd=tmp_path)
        assert result.success is True
        assert result.coverage_status == "unreported"
        assert result.coverage_eligibility == "full"
        assert result.coverage_rate is None

    @patch("review_dispatcher.subprocess.run")
    def test_skipped_entry_without_reason_is_coerced_not_rejected(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        coverage = {
            "reviewed": ["src/foo.py", "src/bar.py"],
            "skipped": [{"path": "docs/readme.md"}],
        }
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_findings_json(coverage), stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", RULE_GROUPS_PROMPT, cwd=tmp_path)
        assert result.success is True
        assert result.findings["coverage"]["skipped"][0]["reason"] == "unspecified"
