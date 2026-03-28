"""Tests for review_dispatcher — config-driven multi-vendor dispatch."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from review_dispatcher import (
    CliConfig,
    CliVendorAdapter,
    ErrorClass,
    ModeConfig,
    ReviewOrchestrator,
    classify_error,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cli_config(
    command: str = "codex",
    review_args: list[str] | None = None,
    model_flag: str = "-m",
    model: str | None = None,
    model_fallbacks: list[str] | None = None,
) -> CliConfig:
    return CliConfig(
        command=command,
        dispatch_modes={
            "review": ModeConfig(args=review_args or ["exec", "-s", "read-only"]),
            "alternative": ModeConfig(args=["exec", "-s", "workspace-write"]),
        },
        model_flag=model_flag,
        model=model,
        model_fallbacks=model_fallbacks or [],
    )


def _adapter(
    agent_id: str = "codex-local",
    vendor: str = "codex",
    **kwargs: object,
) -> CliVendorAdapter:
    return CliVendorAdapter(
        agent_id=agent_id,
        vendor=vendor,
        cli_config=_cli_config(**kwargs),  # type: ignore[arg-type]
    )


VALID_FINDINGS_JSON = json.dumps({
    "review_type": "plan",
    "target": "test-feature",
    "reviewer_vendor": "test",
    "findings": [
        {"id": 1, "type": "security", "criticality": "high",
         "description": "test", "disposition": "fix"},
    ],
})


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class TestErrorClassification:
    def test_capacity_429(self) -> None:
        assert classify_error("Error 429: rate limit exceeded") == ErrorClass.CAPACITY

    def test_capacity_exhausted(self) -> None:
        assert classify_error("MODEL_CAPACITY_EXHAUSTED") == ErrorClass.CAPACITY

    def test_auth_401(self) -> None:
        assert classify_error("HTTP 401 Unauthorized") == ErrorClass.AUTH

    def test_auth_unauthenticated(self) -> None:
        assert classify_error("UNAUTHENTICATED: token expired") == ErrorClass.AUTH

    def test_transient_500(self) -> None:
        assert classify_error("500 Internal Server Error") == ErrorClass.TRANSIENT

    def test_unknown(self) -> None:
        assert classify_error("Some random error message") == ErrorClass.UNKNOWN

    def test_auth_takes_priority_over_capacity(self) -> None:
        # If both patterns match, auth should win (checked first)
        assert classify_error("401 rate limit") == ErrorClass.AUTH


# ---------------------------------------------------------------------------
# Command building
# ---------------------------------------------------------------------------

class TestBuildCommand:
    def test_basic_review_no_model(self) -> None:
        adapter = _adapter()
        cmd = adapter.build_command("review", "Review this")
        assert cmd == ["codex", "exec", "-s", "read-only", "Review this"]

    def test_with_explicit_model(self) -> None:
        adapter = _adapter(model="o3")
        cmd = adapter.build_command("review", "Review this")
        assert cmd == ["codex", "exec", "-s", "read-only", "-m", "o3", "Review this"]

    def test_with_model_override(self) -> None:
        adapter = _adapter()
        cmd = adapter.build_command("review", "Review this", model="gpt-4.1")
        assert cmd == ["codex", "exec", "-s", "read-only", "-m", "gpt-4.1", "Review this"]

    def test_gemini_flags(self) -> None:
        adapter = _adapter(
            agent_id="gemini-local",
            vendor="gemini",
            command="gemini",
            review_args=["--approval-mode", "default", "-o", "json"],
            model_flag="-m",
        )
        cmd = adapter.build_command("review", "prompt")
        assert cmd == ["gemini", "--approval-mode", "default", "-o", "json", "prompt"]

    def test_claude_flags(self) -> None:
        adapter = _adapter(
            agent_id="claude-local",
            vendor="claude_code",
            command="claude",
            review_args=["--print", "--allowedTools", "Read,Grep,Glob"],
            model_flag="--model",
        )
        cmd = adapter.build_command("review", "prompt", model="claude-sonnet-4-6")
        assert cmd == ["claude", "--print", "--allowedTools", "Read,Grep,Glob",
                       "--model", "claude-sonnet-4-6", "prompt"]

    def test_alternative_mode(self) -> None:
        adapter = _adapter()
        cmd = adapter.build_command("alternative", "Implement this")
        assert cmd == ["codex", "exec", "-s", "workspace-write", "Implement this"]


# ---------------------------------------------------------------------------
# Can dispatch
# ---------------------------------------------------------------------------

class TestCanDispatch:
    @patch("shutil.which", return_value="/usr/bin/codex")
    def test_can_dispatch_when_binary_exists(self, _mock: MagicMock) -> None:
        adapter = _adapter()
        assert adapter.can_dispatch("review") is True

    @patch("shutil.which", return_value=None)
    def test_cannot_dispatch_missing_binary(self, _mock: MagicMock) -> None:
        adapter = _adapter()
        assert adapter.can_dispatch("review") is False

    @patch("shutil.which", return_value="/usr/bin/codex")
    def test_cannot_dispatch_unknown_mode(self, _mock: MagicMock) -> None:
        adapter = _adapter()
        assert adapter.can_dispatch("nonexistent_mode") is False


# ---------------------------------------------------------------------------
# Dispatch with mocked subprocess
# ---------------------------------------------------------------------------

class TestDispatch:
    @patch("review_dispatcher.subprocess.run")
    def test_successful_dispatch(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=VALID_FINDINGS_JSON, stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.findings is not None
        assert len(result.findings["findings"]) == 1

    @patch("review_dispatcher.subprocess.run")
    def test_capacity_error_triggers_fallback(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """429 on primary model → retry with fallback → succeed."""
        mock_run.side_effect = [
            # First call: primary model fails with 429
            subprocess.CompletedProcess(
                args=[], returncode=1, stdout="",
                stderr="429 MODEL_CAPACITY_EXHAUSTED",
            ),
            # Second call: fallback model succeeds
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=VALID_FINDINGS_JSON, stderr="",
            ),
        ]
        adapter = _adapter(model_fallbacks=["o3"])
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.models_attempted == ["(default)", "o3"]
        assert result.model_used == "o3"

    @patch("review_dispatcher.subprocess.run")
    def test_all_models_fail(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """All models in fallback chain fail."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr="429 RESOURCE_EXHAUSTED capacity",
        )
        adapter = _adapter(model_fallbacks=["o3", "gpt-4.1"])
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is False
        assert result.models_attempted == ["(default)", "o3", "gpt-4.1"]
        assert result.error_class == ErrorClass.CAPACITY

    @patch("review_dispatcher.subprocess.run")
    def test_auth_error_no_fallback(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Auth errors skip model fallback."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr="401 UNAUTHENTICATED token expired",
        )
        adapter = _adapter(model_fallbacks=["o3"])
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is False
        assert result.error_class == ErrorClass.AUTH
        assert result.models_attempted == ["(default)"]  # No fallback attempted

    @patch("review_dispatcher.subprocess.run")
    def test_timeout(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=10)
        adapter = _adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path, timeout_seconds=10)
        assert result.success is False
        assert "Timeout" in (result.error or "")

    @patch("review_dispatcher.subprocess.run")
    def test_invalid_json_output(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Not valid JSON at all", stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is False
        assert "Invalid JSON" in (result.error or "")

    @patch("review_dispatcher.subprocess.run")
    def test_json_embedded_in_text(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Vendor outputs text around JSON — parser extracts it."""
        output = f"Here are my findings:\n{VALID_FINDINGS_JSON}\nDone."
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=output, stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.findings is not None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class TestOrchestrator:
    def test_discover_reviewers(self) -> None:
        adapters = {
            "codex-local": _adapter("codex-local", "codex"),
            "gemini-local": _adapter("gemini-local", "gemini", command="gemini"),
        }
        orch = ReviewOrchestrator(adapters)
        with patch("shutil.which", return_value="/usr/bin/mock"):
            reviewers = orch.discover_reviewers()
        assert len(reviewers) == 2

    def test_discover_excludes_vendor(self) -> None:
        adapters = {
            "codex-local": _adapter("codex-local", "codex"),
            "gemini-local": _adapter("gemini-local", "gemini", command="gemini"),
        }
        orch = ReviewOrchestrator(adapters)
        with patch("shutil.which", return_value="/usr/bin/mock"):
            reviewers = orch.discover_reviewers(exclude_vendor="codex")
        assert len(reviewers) == 1
        assert reviewers[0].vendor == "gemini"

    def test_write_manifest(self, tmp_path: Path) -> None:
        from review_dispatcher import ReviewResult
        orch = ReviewOrchestrator({})
        results = [
            ReviewResult(vendor="codex", success=True, model_used="gpt-5.4",
                        models_attempted=["gpt-5.4"], elapsed_seconds=120.5),
            ReviewResult(vendor="gemini", success=False, error="429 capacity",
                        error_class=ErrorClass.CAPACITY,
                        models_attempted=["(default)", "gemini-2.5-pro"]),
        ]
        output = tmp_path / "reviews" / "review-manifest.json"
        orch.write_manifest(results, output, "plan", "test-feature")
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["quorum_requested"] == 2
        assert data["quorum_received"] == 1
        assert data["dispatches"][0]["success"] is True
        assert data["dispatches"][1]["error_class"] == "capacity_exhausted"


# ---------------------------------------------------------------------------
# Async dispatch + polling tests
# ---------------------------------------------------------------------------

def _async_adapter(**kwargs: object) -> CliVendorAdapter:
    """Create adapter with async mode configured."""
    from review_dispatcher import PollConfig
    return CliVendorAdapter(
        agent_id="codex-remote",
        vendor="codex",
        cli_config=CliConfig(
            command="codex",
            dispatch_modes={
                "review": ModeConfig(args=["exec", "-s", "read-only"]),
                "alternative": ModeConfig(
                    args=["cloud", "exec", "--env", "test-env"],
                    async_dispatch=True,
                    poll=PollConfig(
                        command_template=["codex", "cloud", "status", "{task_id}"],
                        task_id_pattern=r"task[_\s:]+(\w+)",
                        success_pattern="completed",
                        failure_pattern="failed|error",
                        interval_seconds=1,
                        timeout_seconds=5,
                    ),
                ),
            },
            model_flag="-m",
        ),
    )


class TestAsyncDispatch:
    @patch("review_dispatcher.subprocess.run")
    def test_async_submit_extracts_task_id(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """Async dispatch extracts task_id from output."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="Submitted! task: abc123\n", stderr="",
        )
        adapter = _async_adapter()
        result = adapter.dispatch_async("alternative", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.task_id == "abc123"
        assert result.async_dispatch is True

    @patch("review_dispatcher.subprocess.run")
    def test_async_submit_no_task_id(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """Async dispatch fails if task_id cannot be extracted."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="Something happened but no ID\n", stderr="",
        )
        adapter = _async_adapter()
        result = adapter.dispatch_async("alternative", "prompt", cwd=tmp_path)
        assert result.success is False
        assert "Could not extract task ID" in (result.error or "")

    @patch("review_dispatcher.subprocess.run")
    def test_async_not_configured(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """Async dispatch on sync mode returns error."""
        adapter = _async_adapter()
        result = adapter.dispatch_async("review", "prompt", cwd=tmp_path)
        assert result.success is False
        assert "not configured for async" in (result.error or "")

    @patch("review_dispatcher.subprocess.run")
    @patch("review_dispatcher.time.sleep")
    def test_poll_success(
        self, mock_sleep: MagicMock, mock_run: MagicMock,
    ) -> None:
        """Polling detects completion and parses findings."""
        from review_dispatcher import PollConfig
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=f"Status: completed\n{VALID_FINDINGS_JSON}",
            stderr="",
        )
        adapter = _async_adapter()
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            task_id_pattern=r"task[_\s:]+(\w+)",
            success_pattern="completed",
            interval_seconds=1,
            timeout_seconds=10,
        )
        result = adapter.poll_for_result("abc123", poll_cfg)
        assert result.success is True
        assert result.findings is not None
        assert result.task_id == "abc123"

    @patch("review_dispatcher.subprocess.run")
    @patch("review_dispatcher.time.sleep")
    def test_poll_failure(
        self, mock_sleep: MagicMock, mock_run: MagicMock,
    ) -> None:
        """Polling detects failure."""
        from review_dispatcher import PollConfig
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1,
            stdout="Status: failed\nError: something broke",
            stderr="",
        )
        adapter = _async_adapter()
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            task_id_pattern=r"task[_\s:]+(\w+)",
            success_pattern="completed",
            failure_pattern="failed",
            interval_seconds=1,
            timeout_seconds=10,
        )
        result = adapter.poll_for_result("abc123", poll_cfg)
        assert result.success is False
        assert "failed" in (result.error or "").lower()

    @patch("review_dispatcher.subprocess.run")
    @patch("review_dispatcher.time.sleep")
    @patch("review_dispatcher.time.monotonic")
    def test_poll_timeout(
        self, mock_time: MagicMock, mock_sleep: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """Polling times out when task doesn't complete."""
        from review_dispatcher import PollConfig
        # Simulate time passing beyond timeout
        mock_time.side_effect = [0, 0, 1, 3, 6, 100]
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="Status: running", stderr="",
        )
        adapter = _async_adapter()
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            task_id_pattern=r"task[_\s:]+(\w+)",
            success_pattern="completed",
            interval_seconds=1,
            timeout_seconds=5,
        )
        result = adapter.poll_for_result("abc123", poll_cfg)
        assert result.success is False
        assert "timed out" in (result.error or "").lower()
