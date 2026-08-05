"""Tests for the CI signal collectors (pytest, ruff, mypy, openspec).

Each collector is tested for:
- Parsing realistic sample output into the correct Finding objects.
- Handling tool-not-available scenarios (FileNotFoundError / missing binary).
- Handling clean/no-issue output (zero findings, status "ok").
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# sys.path insertion so we can import collector modules from scripts/
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import collect_mypy
import collect_openspec
import collect_pytest
import collect_ruff


# ========================================================================
# pytest collector
# ========================================================================
class TestCollectPytest:
    """Tests for collect_pytest.collect()."""

    SAMPLE_FAILURE_OUTPUT = (
        "/abs/path/tests/test_models.py:17: AssertionError\n"
        "/abs/path/tests/test_api.py:42: TypeError\n"
        "\n"
        "FAILED tests/test_models.py::TestModels::test_create - "
        "AssertionError: expected 1 got 2\n"
        "FAILED tests/test_api.py::test_health_endpoint - "
        "TypeError: 'NoneType' object is not subscriptable\n"
        "2 failed, 10 passed in 4.21s\n"
    )

    @patch("collect_pytest.shutil.which", return_value="/usr/bin/pytest")
    @patch("collect_pytest.subprocess.run")
    def test_parse_failures(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Realistic failure output is parsed into Finding objects."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest"],
            returncode=1,
            stdout=self.SAMPLE_FAILURE_OUTPUT,
            stderr="",
        )

        result = collect_pytest.collect("/fake/project")

        assert result.source == "pytest"
        assert result.status == "ok"
        assert len(result.findings) == 2

        # First finding: class-scoped test
        f0 = result.findings[0]
        assert f0.id == "pytest-TestModels::test_create"
        assert f0.severity == "high"
        assert f0.category == "test-failure"
        assert f0.source == "pytest"
        assert "test_create" in f0.title
        assert f0.detail == "AssertionError: expected 1 got 2"

        # Second finding: module-scoped test
        f1 = result.findings[1]
        assert f1.id == "pytest-test_health_endpoint"
        assert "test_health_endpoint" in f1.title
        assert "NoneType" in f1.detail

    @patch("collect_pytest.shutil.which", return_value="/usr/bin/pytest")
    @patch(
        "collect_pytest.subprocess.run",
        side_effect=FileNotFoundError("No such file or directory: 'pytest'"),
    )
    def test_tool_not_available_file_not_found(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """FileNotFoundError during subprocess.run returns skipped status."""
        result = collect_pytest.collect("/fake/project")

        assert result.source == "pytest"
        assert result.status == "skipped"
        assert any("not found" in m for m in result.messages)
        assert result.findings == []

    @patch("collect_pytest.shutil.which", return_value=None)
    def test_tool_not_on_path(self, mock_which: MagicMock) -> None:
        """When pytest is not on PATH, returns skipped status."""
        result = collect_pytest.collect("/fake/project")

        assert result.status == "skipped"
        assert any("not found" in m for m in result.messages)

    @patch("collect_pytest.shutil.which", return_value="/usr/bin/pytest")
    @patch("collect_pytest.subprocess.run")
    def test_no_failures(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Exit code 0 (all tests pass) yields status ok with no findings."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest"],
            returncode=0,
            stdout="10 passed in 1.23s\n",
            stderr="",
        )

        result = collect_pytest.collect("/fake/project")

        assert result.status == "ok"
        assert result.findings == []
        assert result.duration_ms >= 0

    @patch("collect_pytest.shutil.which", return_value="/usr/bin/pytest")
    @patch("collect_pytest.subprocess.run")
    def test_no_tests_collected(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Exit code 5 (no tests collected) yields ok with a message."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest"],
            returncode=5,
            stdout="no tests ran in 0.01s\n",
            stderr="",
        )

        result = collect_pytest.collect("/fake/project")

        assert result.status == "ok"
        assert result.findings == []
        assert any("no tests" in m for m in result.messages)

    @patch("collect_pytest.shutil.which", return_value="/usr/bin/pytest")
    @patch(
        "collect_pytest.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=300),
    )
    def test_timeout(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """TimeoutExpired returns error status."""
        result = collect_pytest.collect("/fake/project")

        assert result.status == "error"
        assert any("timed out" in m for m in result.messages)

    @patch("collect_pytest.shutil.which", return_value="/usr/bin/pytest")
    @patch("collect_pytest.subprocess.run")
    def test_nonzero_exit_no_failed_lines(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Non-zero exit with no FAILED lines yields error status."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest"],
            returncode=2,
            stdout="ERROR: invalid argument\n",
            stderr="",
        )

        result = collect_pytest.collect("/fake/project")

        assert result.status == "error"
        assert any("exited with code 2" in m for m in result.messages)


# ========================================================================
# ruff collector
# ========================================================================
class TestCollectRuff:
    """Tests for collect_ruff.collect()."""

    SAMPLE_JSON_OUTPUT = json.dumps(
        [
            {
                "code": "E501",
                "message": "Line too long (120 > 88)",
                "filename": "/fake/project/src/api.py",
                "location": {"row": 15, "column": 1},
                "end_location": {"row": 15, "column": 121},
                "fix": None,
                "noqa_row": 15,
                "url": "https://docs.astral.sh/ruff/rules/line-too-long",
            },
            {
                "code": "W291",
                "message": "Trailing whitespace",
                "filename": "/fake/project/src/utils.py",
                "location": {"row": 8, "column": 30},
                "end_location": {"row": 8, "column": 33},
                "fix": None,
                "noqa_row": 8,
                "url": "https://docs.astral.sh/ruff/rules/trailing-whitespace",
            },
            {
                "code": "F841",
                "message": "Local variable `x` is assigned to but never used",
                "filename": "/fake/project/tests/test_core.py",
                "location": {"row": 22, "column": 5},
                "end_location": {"row": 22, "column": 6},
                "fix": None,
                "noqa_row": 22,
                "url": "https://docs.astral.sh/ruff/rules/unused-variable",
            },
        ]
    )

    @patch("collect_ruff.subprocess.run")
    def test_parse_json_output(self, mock_run: MagicMock) -> None:
        """Realistic ruff JSON output is parsed into Finding objects."""
        # First call: ruff --version (guard)
        # Second call: ruff check --output-format=json .
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["ruff", "--version"],
                returncode=0,
                stdout="ruff 0.3.0\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["ruff", "check"],
                returncode=1,
                stdout=self.SAMPLE_JSON_OUTPUT,
                stderr="",
            ),
        ]

        result = collect_ruff.collect("/fake/project")

        assert result.source == "ruff"
        assert result.status == "ok"
        assert len(result.findings) == 3

        # E501 -> high severity
        f0 = result.findings[0]
        assert f0.severity == "high"
        assert f0.category == "lint"
        assert "E501" in f0.title
        assert "Line too long" in f0.title
        assert f0.line == 15

        # W291 -> medium severity
        f1 = result.findings[1]
        assert f1.severity == "medium"
        assert "W291" in f1.title

        # F841 -> medium severity (not E or W prefix)
        f2 = result.findings[2]
        assert f2.severity == "medium"
        assert "F841" in f2.title

    @patch(
        "collect_ruff.subprocess.run",
        side_effect=FileNotFoundError("No such file or directory: 'ruff'"),
    )
    def test_tool_not_available(self, mock_run: MagicMock) -> None:
        """FileNotFoundError on the version check returns skipped status."""
        result = collect_ruff.collect("/fake/project")

        assert result.source == "ruff"
        assert result.status == "skipped"
        assert any("not installed" in m or "not on PATH" in m for m in result.messages)
        assert result.findings == []

    @patch("collect_ruff.subprocess.run")
    def test_no_issues(self, mock_run: MagicMock) -> None:
        """Clean ruff run (exit code 0, empty JSON array) yields ok."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["ruff", "--version"],
                returncode=0,
                stdout="ruff 0.3.0\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["ruff", "check"],
                returncode=0,
                stdout="[]",
                stderr="",
            ),
        ]

        result = collect_ruff.collect("/fake/project")

        assert result.status == "ok"
        assert result.findings == []

    @patch("collect_ruff.subprocess.run")
    def test_no_issues_empty_stdout(self, mock_run: MagicMock) -> None:
        """Clean ruff run with empty stdout (no JSON) yields ok."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["ruff", "--version"],
                returncode=0,
                stdout="ruff 0.3.0\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["ruff", "check"],
                returncode=0,
                stdout="",
                stderr="",
            ),
        ]

        result = collect_ruff.collect("/fake/project")

        assert result.status == "ok"
        assert result.findings == []

    def test_severity_mapping_e_codes(self) -> None:
        """E-prefixed codes map to 'high' severity."""
        assert collect_ruff._map_severity("E501") == "high"
        assert collect_ruff._map_severity("E101") == "high"
        assert collect_ruff._map_severity("e999") == "high"

    def test_severity_mapping_w_codes(self) -> None:
        """W-prefixed codes map to 'medium' severity."""
        assert collect_ruff._map_severity("W291") == "medium"
        assert collect_ruff._map_severity("W605") == "medium"
        assert collect_ruff._map_severity("w100") == "medium"

    def test_severity_mapping_other_codes(self) -> None:
        """Non-E/W codes (F, I, etc.) map to 'medium' severity."""
        assert collect_ruff._map_severity("F841") == "medium"
        assert collect_ruff._map_severity("I001") == "medium"
        assert collect_ruff._map_severity("N802") == "medium"

    @patch("collect_ruff.subprocess.run")
    def test_unexpected_exit_code(self, mock_run: MagicMock) -> None:
        """Unexpected exit code (not 0 or 1) returns error status."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["ruff", "--version"],
                returncode=0,
                stdout="ruff 0.3.0\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["ruff", "check"],
                returncode=2,
                stdout="",
                stderr="internal error\n",
            ),
        ]

        result = collect_ruff.collect("/fake/project")

        assert result.status == "error"
        assert any("exited with code 2" in m for m in result.messages)

    @patch("collect_ruff.subprocess.run")
    def test_invalid_json(self, mock_run: MagicMock) -> None:
        """Malformed JSON output returns error status."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["ruff", "--version"],
                returncode=0,
                stdout="ruff 0.3.0\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["ruff", "check"],
                returncode=1,
                stdout="not valid json {{{",
                stderr="",
            ),
        ]

        result = collect_ruff.collect("/fake/project")

        assert result.status == "error"
        assert any("parse" in m.lower() for m in result.messages)


# ========================================================================
# mypy collector
# ========================================================================
class TestCollectMypy:
    """Tests for collect_mypy.collect()."""

    SAMPLE_OUTPUT = (
        'src/api/routes.py:42: error: Incompatible types in assignment '
        '(expression has type "str", variable has type "int") [assignment]\n'
        'src/models/user.py:17: error: Missing return statement [return]\n'
        'src/utils/helpers.py:88: error: Argument 1 to "process" has '
        'incompatible type "None"; expected "dict[str, Any]" [arg-type]\n'
        "Found 3 errors in 3 files (checked 12 source files)\n"
    )

    @patch("collect_mypy.shutil.which", return_value="/usr/bin/mypy")
    @patch("collect_mypy.subprocess.run")
    def test_parse_errors(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Realistic mypy output is parsed into Finding objects."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mypy"],
            returncode=1,
            stdout=self.SAMPLE_OUTPUT,
            stderr="",
        )

        result = collect_mypy.collect("/fake/project")

        assert result.source == "mypy"
        assert result.status == "ok"
        assert len(result.findings) == 3

        # First finding: assignment error
        f0 = result.findings[0]
        assert f0.id == "mypy-assignment-routes.py:42"
        assert f0.severity == "medium"
        assert f0.category == "type-error"
        assert f0.file_path == "src/api/routes.py"
        assert f0.line == 42
        assert "Incompatible types" in f0.title

        # Second finding: missing return
        f1 = result.findings[1]
        assert f1.id == "mypy-return-user.py:17"
        assert f1.line == 17
        assert "Missing return" in f1.title

        # Third finding: arg-type
        f2 = result.findings[2]
        assert f2.id == "mypy-arg-type-helpers.py:88"
        assert f2.line == 88

    @patch("collect_mypy.shutil.which", return_value=None)
    def test_tool_not_on_path(self, mock_which: MagicMock) -> None:
        """When mypy is not on PATH, returns skipped status."""
        result = collect_mypy.collect("/fake/project")

        assert result.source == "mypy"
        assert result.status == "skipped"
        assert any("not found" in m for m in result.messages)
        assert result.findings == []

    @patch("collect_mypy.shutil.which", return_value="/usr/bin/mypy")
    @patch(
        "collect_mypy.subprocess.run",
        side_effect=FileNotFoundError("No such file or directory: 'mypy'"),
    )
    def test_tool_not_available_file_not_found(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """FileNotFoundError during subprocess.run returns skipped status."""
        result = collect_mypy.collect("/fake/project")

        assert result.source == "mypy"
        assert result.status == "skipped"
        assert any("Failed to run mypy" in m for m in result.messages)

    @patch("collect_mypy.shutil.which", return_value="/usr/bin/mypy")
    @patch("collect_mypy.subprocess.run")
    def test_no_errors(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Clean mypy run yields ok with no findings."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mypy"],
            returncode=0,
            stdout="",
            stderr="",
        )

        result = collect_mypy.collect("/fake/project")

        assert result.status == "ok"
        assert result.findings == []
        assert result.duration_ms >= 0

    @patch("collect_mypy.shutil.which", return_value="/usr/bin/mypy")
    @patch("collect_mypy.subprocess.run")
    def test_detail_is_raw_line(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """The detail field stores the raw mypy output line."""
        single_error = (
            'src/foo.py:10: error: Name "bar" is not defined [name-defined]\n'
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mypy"],
            returncode=1,
            stdout=single_error,
            stderr="",
        )

        result = collect_mypy.collect("/fake/project")

        assert len(result.findings) == 1
        assert result.findings[0].detail == single_error.strip()

    @patch("collect_mypy.shutil.which", return_value="/usr/bin/mypy")
    @patch("collect_mypy.subprocess.run")
    def test_error_without_code(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Mypy lines without a [code] bracket get code='unknown'."""
        no_code_output = (
            "src/foo.py:5: error: Some generic error message\n"
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mypy"],
            returncode=1,
            stdout=no_code_output,
            stderr="",
        )

        result = collect_mypy.collect("/fake/project")

        assert len(result.findings) == 1
        assert result.findings[0].id == "mypy-unknown-foo.py:5"


# ========================================================================
# openspec collector
# ========================================================================
class TestCollectOpenspec:
    """Tests for collect_openspec.collect()."""

    # Captured verbatim from `openspec validate --strict --all --json` (CLI
    # 1.7.0).  The previous fixture here was invented -- it used a
    # `error: msg (spec: file:12)` shape that no release of the CLI has ever
    # emitted, so the collector parsed real output into zero findings while
    # this test stayed green.  Keep these fixtures byte-faithful to the CLI.
    SAMPLE_VALIDATION_JSON = json.dumps(
        {
            "items": [
                {
                    "id": "broken-probe",
                    "type": "change",
                    "valid": False,
                    "issues": [
                        {
                            "level": "ERROR",
                            "path": "probe-cap/spec.md",
                            "message": (
                                'ADDED "Probe Requirement" must contain '
                                "SHALL or MUST"
                            ),
                        }
                    ],
                    "durationMs": 1,
                },
                {
                    "id": "agent-archetypes",
                    "type": "spec",
                    "valid": True,
                    "issues": [
                        {
                            "level": "INFO",
                            "path": "requirements[0]",
                            "message": (
                                "Requirement text is very long (>500 "
                                "characters). Consider breaking it down."
                            ),
                        }
                    ],
                    "durationMs": 3,
                },
            ],
            "summary": {
                "totals": {"items": 2, "passed": 1, "failed": 1},
                "byType": {
                    "change": {"items": 1, "passed": 0, "failed": 1},
                    "spec": {"items": 1, "passed": 1, "failed": 0},
                },
            },
            "version": "1.0",
            "root": {"path": "/fake/project", "source": "nearest"},
        }
    )

    # Real human-readable output of the same command.  Note it carries no
    # per-issue detail at all -- only a per-item tick and a totals line.  That
    # is why the collector asks for --json instead of scraping this.
    SAMPLE_VALIDATION_TEXT = (
        "- Validating...\n"
        "✗ change/broken-probe\n"
        "Totals: 0 passed, 1 failed (1 items)\n"
        "Details: openspec validate broken-probe --type change\n"
    )

    @patch("collect_openspec.shutil.which", return_value="/usr/bin/openspec")
    @patch("collect_openspec.subprocess.run")
    def test_parse_validation_output(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Real openspec --json output is parsed into findings."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["openspec", "validate"],
            returncode=1,
            stdout=self.SAMPLE_VALIDATION_JSON,
            stderr="",
        )

        result = collect_openspec.collect("/fake/project")

        assert result.source == "openspec"
        assert result.status == "ok"
        assert len(result.findings) == 2

        # ERROR issue on a change, with a file-shaped path.
        f0 = result.findings[0]
        assert f0.source == "openspec"
        assert f0.severity == "high"
        assert f0.category == "spec-violation"
        assert "Probe Requirement" in f0.title
        assert "SHALL or MUST" in f0.title
        assert f0.file_path == "probe-cap/spec.md"
        assert "broken-probe" in f0.id
        assert "broken-probe" in f0.detail

        # INFO issue on a spec, whose path is a structural pointer rather than
        # a file.  It must not be reported as a file path.
        f1 = result.findings[1]
        assert f1.severity == "info"
        assert "very long" in f1.title
        assert f1.file_path == ""
        assert "requirements[0]" in f1.detail

    @patch("collect_openspec.shutil.which", return_value="/usr/bin/openspec")
    @patch("collect_openspec.subprocess.run")
    def test_severity_maps_from_issue_level(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """ERROR/WARNING/INFO map onto distinct bug-scrub severities."""
        payload = {
            "items": [
                {
                    "id": "c",
                    "type": "change",
                    "valid": False,
                    "issues": [
                        {"level": "ERROR", "path": "a.md", "message": "e"},
                        {"level": "WARNING", "path": "b.md", "message": "w"},
                        {"level": "INFO", "path": "c.md", "message": "i"},
                    ],
                }
            ],
            "version": "1.0",
        }
        mock_run.return_value = subprocess.CompletedProcess(
            args=["openspec", "validate"],
            returncode=1,
            stdout=json.dumps(payload),
            stderr="",
        )

        result = collect_openspec.collect("/fake/project")

        assert [f.severity for f in result.findings] == [
            "high",
            "medium",
            "info",
        ]

    @patch("collect_openspec.shutil.which", return_value="/usr/bin/openspec")
    @patch("collect_openspec.subprocess.run")
    def test_unparseable_output_errors_loudly(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Non-JSON output must not degrade to a silent zero-finding pass.

        A collector that returns ok/0-findings when it failed to understand
        the tool is indistinguishable from a clean repo -- the exact failure
        that hid the old regex bug.  Raw output is preserved for diagnosis.
        """
        mock_run.return_value = subprocess.CompletedProcess(
            args=["openspec", "validate"],
            returncode=1,
            stdout=self.SAMPLE_VALIDATION_TEXT,
            stderr="",
        )

        result = collect_openspec.collect("/fake/project")

        assert result.status == "error"
        assert result.findings == []
        assert any("JSON" in m for m in result.messages)
        # The raw output survives rather than being discarded.
        assert any("broken-probe" in m for m in result.messages)

    @patch("collect_openspec.shutil.which", return_value=None)
    def test_tool_not_on_path(self, mock_which: MagicMock) -> None:
        """When openspec is not on PATH, returns skipped status."""
        result = collect_openspec.collect("/fake/project")

        assert result.source == "openspec"
        assert result.status == "skipped"
        assert any("not found" in m for m in result.messages)
        assert result.findings == []

    @patch("collect_openspec.shutil.which", return_value="/usr/bin/openspec")
    @patch(
        "collect_openspec.subprocess.run",
        side_effect=FileNotFoundError(
            "No such file or directory: 'openspec'"
        ),
    )
    def test_tool_not_available_file_not_found(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """FileNotFoundError during subprocess.run returns skipped status."""
        result = collect_openspec.collect("/fake/project")

        assert result.source == "openspec"
        assert result.status == "skipped"
        assert any("FileNotFoundError" in m for m in result.messages)

    @patch("collect_openspec.shutil.which", return_value="/usr/bin/openspec")
    @patch("collect_openspec.subprocess.run")
    def test_no_issues(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Clean openspec validate yields ok with no findings."""
        clean = {
            "items": [
                {
                    "id": "add-adaptive-model-router",
                    "type": "change",
                    "valid": True,
                    "issues": [],
                    "durationMs": 6,
                }
            ],
            "summary": {"totals": {"items": 1, "passed": 1, "failed": 0}},
            "version": "1.0",
            "root": {"path": "/fake/project", "source": "nearest"},
        }
        mock_run.return_value = subprocess.CompletedProcess(
            args=["openspec", "validate"],
            returncode=0,
            stdout=json.dumps(clean),
            stderr="",
        )

        result = collect_openspec.collect("/fake/project")

        assert result.status == "ok"
        assert result.findings == []
        assert result.duration_ms >= 0

    @patch("collect_openspec.shutil.which", return_value="/usr/bin/openspec")
    @patch(
        "collect_openspec.subprocess.run",
        side_effect=subprocess.TimeoutExpired(
            cmd="openspec validate", timeout=120
        ),
    )
    def test_timeout(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """TimeoutExpired returns error status."""
        result = collect_openspec.collect("/fake/project")

        assert result.status == "error"
        assert any("timed out" in m for m in result.messages)

    @patch("collect_openspec.shutil.which", return_value="/usr/bin/openspec")
    @patch("collect_openspec.subprocess.run")
    def test_nonzero_exit_message(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Non-zero exit code is reported in messages.

        A failing validation exits 1 while still emitting a well-formed JSON
        report, so the run is still status "ok" -- the collector ran fine, the
        specs did not.
        """
        mock_run.return_value = subprocess.CompletedProcess(
            args=["openspec", "validate"],
            returncode=1,
            stdout=self.SAMPLE_VALIDATION_JSON,
            stderr="",
        )

        result = collect_openspec.collect("/fake/project")

        assert result.status == "ok"
        assert any("exited with code 1" in m for m in result.messages)

    @patch("collect_openspec.shutil.which", return_value="/usr/bin/openspec")
    @patch("collect_openspec.subprocess.run")
    def test_stderr_is_surfaced_not_merged(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """stderr is reported as a message, never merged into the JSON parse.

        The CLI keeps --json output clean on stdout and puts diagnostics on
        stderr.  Concatenating the two (as this collector used to) would make
        any stderr chatter corrupt the payload.
        """
        mock_run.return_value = subprocess.CompletedProcess(
            args=["openspec", "validate"],
            returncode=1,
            stdout=self.SAMPLE_VALIDATION_JSON,
            stderr="warning: telemetry disabled\n",
        )

        result = collect_openspec.collect("/fake/project")

        assert result.status == "ok"
        assert len(result.findings) == 2
        assert any("telemetry disabled" in m for m in result.messages)
