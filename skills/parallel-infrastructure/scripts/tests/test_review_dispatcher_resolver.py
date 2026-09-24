"""Ingest-time line resolution wired into CliVendorAdapter.dispatch().

Verifies resolution runs after schema validation, populates unanchored
counts, and never blocks a dispatch when no packet diff is available.
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

from review_dispatcher import CliConfig, CliVendorAdapter, ModeConfig  # noqa: E402
from review_dispatcher import _extract_diff_from_prompt  # noqa: E402

DIFF_BODY = (
    "diff --git a/src/foo.py b/src/foo.py\n"
    "index e69de29..a1b2c3d 100644\n"
    "--- a/src/foo.py\n"
    "+++ b/src/foo.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def foo():\n"
    "-    return 1\n"
    "+    return used_variable\n"
)

PACKET_PROMPT = (
    "## Review Round 1\n\n"
    "The packet is complete; do not explore the repo for missing artifacts.\n\n"
    "### Prompt contract\n(contract text)\n\n"
    "### Diff\n"
    "```diff\n" + DIFF_BODY.rstrip("\n") + "\n```\n\n"
    "### Instructions\nReturn findings as JSON.\n"
)

EMPTY_DIFF_PROMPT = (
    "## Review Round 1\n\n### Diff\n```diff\n(empty-diff)\n```\n"
)


def _adapter(**kwargs) -> CliVendorAdapter:
    cli_config = CliConfig(
        command="codex",
        dispatch_modes={"review": ModeConfig(args=["exec"])},
        model_flag="-m",
        **kwargs,
    )
    return CliVendorAdapter(agent_id="codex-local", vendor="codex", cli_config=cli_config)


def _findings_json(existing_code: str | None, file_path: str = "src/foo.py") -> str:
    finding = {
        "id": 1, "type": "correctness", "criticality": "high",
        "description": "test", "disposition": "fix", "axis": "correctness",
        "severity": "critical", "file_path": file_path,
    }
    if existing_code is not None:
        finding["existing_code"] = existing_code
    return json.dumps({"findings": [finding]})


class TestExtractDiffFromPrompt:
    def test_extracts_the_fenced_diff(self) -> None:
        extracted = _extract_diff_from_prompt(PACKET_PROMPT)
        assert extracted == DIFF_BODY.rstrip("\n")

    def test_empty_diff_marker_yields_empty_string(self) -> None:
        assert _extract_diff_from_prompt(EMPTY_DIFF_PROMPT) == ""

    def test_no_diff_fence_yields_empty_string(self) -> None:
        assert _extract_diff_from_prompt("no fence here") == ""


class TestDispatchResolvesLines:
    @patch("review_dispatcher._run_cli_process")
    def test_existing_code_resolves_to_a_line_range(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_findings_json("return used_variable"), stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", PACKET_PROMPT, cwd=tmp_path)
        assert result.success is True
        finding = result.findings["findings"][0]
        assert finding["line_range"] == {"start": 2, "end": 2}
        assert finding["line_resolution"] == "hunk_new"
        assert result.unanchored_findings == 0

    @patch("review_dispatcher._run_cli_process")
    def test_unmatched_snippet_counts_as_unanchored_but_is_kept(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_findings_json("this text is nowhere in the diff"), stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", PACKET_PROMPT, cwd=tmp_path)
        assert result.success is True
        finding = result.findings["findings"][0]
        assert "line_range" not in finding
        assert finding["line_resolution"] == "unresolved"
        assert result.unanchored_findings == 1

    @patch("review_dispatcher._run_cli_process")
    def test_no_diff_fence_in_prompt_skips_resolution_without_failing(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """A prompt that is not a review_packet-rendered packet (e.g. a
        hand-authored test prompt) must not break dispatch — resolution
        simply does not run."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_findings_json("return used_variable"), stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", "a bare prompt with no diff fence", cwd=tmp_path)
        assert result.success is True
        finding = result.findings["findings"][0]
        assert "line_resolution" not in finding
        assert result.unanchored_findings == 0

    @patch("review_dispatcher._run_cli_process")
    def test_finding_without_existing_code_is_unaffected(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_findings_json(None), stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", PACKET_PROMPT, cwd=tmp_path)
        finding = result.findings["findings"][0]
        assert "line_resolution" not in finding
        assert result.unanchored_findings == 0
