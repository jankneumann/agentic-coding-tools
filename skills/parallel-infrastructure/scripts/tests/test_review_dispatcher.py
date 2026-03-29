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
    ReviewResult,
    SdkConfig,
    SdkVendorAdapter,
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


# ---------------------------------------------------------------------------
# SDK adapter tests
# ---------------------------------------------------------------------------

def _sdk_config(
    package: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    model_fallbacks: list[str] | None = None,
) -> SdkConfig:
    return SdkConfig(
        package=package,
        model=model,
        model_fallbacks=model_fallbacks or [],
        api_key_env="ANTHROPIC_API_KEY",
        max_tokens=16384,
    )


def _sdk_adapter(
    agent_id: str = "claude-remote",
    vendor: str = "claude_code",
    **kwargs: object,
) -> SdkVendorAdapter:
    return SdkVendorAdapter(
        agent_id=agent_id,
        vendor=vendor,
        sdk_config=_sdk_config(**kwargs),  # type: ignore[arg-type]
        openbao_role_id="test-role",
    )


class TestSdkCanDispatch:
    def test_review_mode_with_importable_package(self) -> None:
        """SDK can dispatch review when package is importable."""
        adapter = _sdk_adapter()
        with patch.object(adapter, "_can_import_sdk", return_value=True):
            assert adapter.can_dispatch("review") is True

    def test_alternative_mode_rejected(self) -> None:
        """SDK does not support alternative mode."""
        adapter = _sdk_adapter()
        assert adapter.can_dispatch("alternative") is False

    def test_review_mode_without_package(self) -> None:
        """SDK cannot dispatch when package is not importable."""
        adapter = _sdk_adapter()
        with patch.object(adapter, "_can_import_sdk", return_value=False):
            assert adapter.can_dispatch("review") is False


class TestSdkDispatch:
    def test_dispatch_without_api_key(self, tmp_path: Path) -> None:
        """SDK dispatch fails when no API key provided."""
        adapter = _sdk_adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path, api_key=None)
        assert result.success is False
        assert "No API key" in (result.error or "")

    @patch("review_dispatcher.SdkVendorAdapter._call_sdk")
    def test_dispatch_success(self, mock_call: MagicMock, tmp_path: Path) -> None:
        """SDK dispatch succeeds with valid findings."""
        mock_call.return_value = json.loads(VALID_FINDINGS_JSON)
        adapter = _sdk_adapter()
        result = adapter.dispatch(
            "review", "prompt", cwd=tmp_path, api_key="sk-test",
        )
        assert result.success is True
        assert result.findings is not None
        assert result.model_used == "claude-sonnet-4-6"

    @patch("review_dispatcher.SdkVendorAdapter._call_sdk")
    def test_dispatch_model_fallback(self, mock_call: MagicMock, tmp_path: Path) -> None:
        """SDK dispatch falls back on capacity error."""
        from review_dispatcher import _SdkCapacityError
        mock_call.side_effect = [
            _SdkCapacityError(),
            json.loads(VALID_FINDINGS_JSON),
        ]
        adapter = _sdk_adapter(model_fallbacks=["claude-haiku-4-5-20251001"])
        result = adapter.dispatch(
            "review", "prompt", cwd=tmp_path, api_key="sk-test",
        )
        assert result.success is True
        assert result.models_attempted == [
            "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
        ]

    @patch("review_dispatcher.SdkVendorAdapter._call_sdk")
    def test_dispatch_auth_error_no_fallback(
        self, mock_call: MagicMock, tmp_path: Path,
    ) -> None:
        """SDK auth error does not trigger model fallback."""
        from review_dispatcher import _SdkAuthError
        mock_call.side_effect = _SdkAuthError("Invalid key")
        adapter = _sdk_adapter(model_fallbacks=["claude-haiku-4-5-20251001"])
        result = adapter.dispatch(
            "review", "prompt", cwd=tmp_path, api_key="sk-bad",
        )
        assert result.success is False
        assert result.error_class == ErrorClass.AUTH
        assert result.models_attempted == ["claude-sonnet-4-6"]


# ---------------------------------------------------------------------------
# Three-tier selection tests
# ---------------------------------------------------------------------------

class TestThreeTierSelection:
    def test_cli_preferred_over_sdk(self) -> None:
        """When CLI is installed, CLI is selected over SDK."""
        cli_adapters = {
            "claude-local": _adapter("claude-local", "claude_code", command="claude"),
        }
        sdk_adapters = {
            "claude-remote": _sdk_adapter("claude-remote", "claude_code"),
        }
        orch = ReviewOrchestrator(cli_adapters, sdk_adapters)
        with patch("shutil.which", return_value="/usr/bin/claude"):
            reviewers = orch.discover_reviewers()
        assert len(reviewers) == 1
        assert reviewers[0].dispatch_tier == "cli"
        assert reviewers[0].agent_id == "claude-local"

    def test_sdk_fallback_when_cli_missing(self) -> None:
        """When CLI is not installed, SDK is selected."""
        cli_adapters = {
            "codex-local": _adapter("codex-local", "codex", command="codex"),
        }
        sdk_adapters = {
            "codex-remote": SdkVendorAdapter(
                agent_id="codex-remote",
                vendor="codex",
                sdk_config=SdkConfig(
                    package="openai",
                    model="gpt-5.4",
                    api_key_env="OPENAI_API_KEY",
                ),
            ),
        }
        orch = ReviewOrchestrator(cli_adapters, sdk_adapters)
        with patch("shutil.which", return_value=None):
            with patch.object(
                SdkVendorAdapter, "can_dispatch", return_value=True,
            ):
                reviewers = orch.discover_reviewers()
        assert len(reviewers) == 1
        assert reviewers[0].dispatch_tier == "sdk"
        assert reviewers[0].agent_id == "codex-remote"

    def test_skip_when_nothing_available(self) -> None:
        """When neither CLI nor SDK is available, vendor is skipped."""
        cli_adapters = {
            "gemini-local": _adapter("gemini-local", "gemini", command="gemini"),
        }
        sdk_adapters = {
            "gemini-remote": SdkVendorAdapter(
                agent_id="gemini-remote",
                vendor="gemini",
                sdk_config=SdkConfig(
                    package="google-generativeai",
                    model="gemini-2.5-pro",
                ),
            ),
        }
        orch = ReviewOrchestrator(cli_adapters, sdk_adapters)
        with patch("shutil.which", return_value=None):
            with patch.object(
                SdkVendorAdapter, "can_dispatch", return_value=False,
            ):
                reviewers = orch.discover_reviewers()
        assert len(reviewers) == 0

    def test_mixed_cli_and_sdk(self) -> None:
        """Mixed: one vendor via CLI, another via SDK."""
        cli_adapters = {
            "claude-local": _adapter("claude-local", "claude_code", command="claude"),
            "codex-local": _adapter("codex-local", "codex", command="codex"),
        }
        sdk_adapters = {
            "codex-remote": SdkVendorAdapter(
                agent_id="codex-remote",
                vendor="codex",
                sdk_config=SdkConfig(package="openai", model="gpt-5.4"),
            ),
        }
        orch = ReviewOrchestrator(cli_adapters, sdk_adapters)

        def which_side_effect(cmd: str) -> str | None:
            return "/usr/bin/claude" if cmd == "claude" else None

        with patch("shutil.which", side_effect=which_side_effect):
            with patch.object(
                SdkVendorAdapter, "can_dispatch", return_value=True,
            ):
                reviewers = orch.discover_reviewers()

        assert len(reviewers) == 2
        tiers = {r.vendor: r.dispatch_tier for r in reviewers}
        assert tiers["claude_code"] == "cli"
        assert tiers["codex"] == "sdk"

    def test_deduplication_by_vendor(self) -> None:
        """At most one reviewer per vendor type."""
        cli_adapters = {
            "claude-local": _adapter("claude-local", "claude_code", command="claude"),
        }
        sdk_adapters = {
            "claude-remote": _sdk_adapter("claude-remote", "claude_code"),
        }
        orch = ReviewOrchestrator(cli_adapters, sdk_adapters)
        with patch("shutil.which", return_value="/usr/bin/claude"):
            reviewers = orch.discover_reviewers()
        assert len(reviewers) == 1

    def test_exclude_vendor(self) -> None:
        """Excluded vendors are omitted from discovery."""
        cli_adapters = {
            "claude-local": _adapter("claude-local", "claude_code", command="claude"),
            "codex-local": _adapter("codex-local", "codex", command="codex"),
        }
        orch = ReviewOrchestrator(cli_adapters)
        with patch("shutil.which", return_value="/usr/bin/mock"):
            reviewers = orch.discover_reviewers(exclude_vendor="claude_code")
        assert len(reviewers) == 1
        assert reviewers[0].vendor == "codex"
