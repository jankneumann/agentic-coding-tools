"""Tests for review_dispatcher — config-driven multi-vendor dispatch."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from review_dispatcher import (
    CliConfig,
    CliVendorAdapter,
    ErrorClass,
    ModeConfig,
    PollConfig,
    ReviewOrchestrator,
    _orchestrator_for_dispatch,
    ReviewResult,
    SdkConfig,
    SdkVendorAdapter,
    VendorResultProtocolError,
    parse_vendor_result_envelope,
    classify_error,
    create_review_snapshot,
    review_snapshot_path,
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
    api_key_env: str = "",
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
        api_key_env=api_key_env,
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


def _resolved_primary(vendor: str = "codex") -> str:
    """Primary model label when cli.model is null (archetypes.yaml premium)."""
    from review_dispatcher import _resolve_review_model_spec

    model, _ = _resolve_review_model_spec(vendor)
    return model or "(default)"


class _LedgerStub:
    """In-memory completion-ledger boundary for async adapter contract tests."""

    def __init__(self) -> None:
        self.submissions: list[dict[str, object]] = []
        self.completions: list[dict[str, object]] = []
        self.submit_response: dict[str, object] = {
            "status": "ok",
            "data": {
                "success": True,
                "task_id": "ledger-123",
                "status": "claimed",
            },
        }
        self.complete_response: dict[str, object] = {
            "status": "ok",
            "data": {"success": True, "status": "completed"},
        }

    def submit(self, **kwargs: object) -> dict[str, object]:
        self.submissions.append(kwargs)
        return self.submit_response


    def complete(self, **kwargs: object) -> dict[str, object]:
        self.completions.append(kwargs)
        return self.complete_response


def test_parse_vendor_result_envelope_accepts_submitted_task() -> None:
    envelope = parse_vendor_result_envelope('{"version": 1, "state": "submitted", "vendor_task_id": "task-123"}')
    assert envelope.version == 1
    assert envelope.state == "submitted"
    assert envelope.vendor_task_id == "task-123"
    assert envelope.is_terminal is False


def test_parse_vendor_result_envelope_rejects_malformed_json_without_regex_fallback() -> None:
    with pytest.raises(VendorResultProtocolError, match="invalid JSON"):
        parse_vendor_result_envelope("task completed: 123")


def test_parse_vendor_result_envelope_rejects_nonterminal_state_without_task_id() -> None:
    with pytest.raises(VendorResultProtocolError, match="vendor_task_id"):
        parse_vendor_result_envelope('{"version": 1, "state": "running"}')


def test_parse_vendor_result_envelope_rejects_unknown_version() -> None:
    with pytest.raises(VendorResultProtocolError, match="version"):
        parse_vendor_result_envelope('{"version": 2, "state": "succeeded"}')


def test_parse_vendor_result_envelope_requires_result_on_success() -> None:
    with pytest.raises(VendorResultProtocolError, match="result"):
        parse_vendor_result_envelope('{"version": 1, "state": "succeeded"}')


def test_parse_vendor_result_envelope_requires_error_on_failure() -> None:
    with pytest.raises(VendorResultProtocolError, match="error"):
        parse_vendor_result_envelope('{"version": 1, "state": "failed"}')


def test_parse_vendor_result_envelope_rejects_schema_drift() -> None:
    with pytest.raises(VendorResultProtocolError, match="unexpected field"):
        parse_vendor_result_envelope(
            '{"version": 1, "state": "succeeded", "result": {}, "status": "done"}'
        )


@pytest.mark.parametrize(
    "payload",
    [
        '{"version": true, "state": "succeeded", "result": {}}',
        '{"version": 1.0, "state": "succeeded", "result": {}}',
        '{"version": 1, "state": "failed", "error": {"message": "failed", "code": 5}}',
        '{"version": 1, "state": "failed", "error": {"message": "failed", "code": ""}}',
    ],
)
def test_parser_rejects_values_disallowed_by_the_json_schema(payload: str) -> None:
    with pytest.raises(VendorResultProtocolError):
        parse_vendor_result_envelope(payload)


@pytest.mark.parametrize(
    "payload",
    [
        '{"version": 1, "state": "cancelled", "error": {"message": ""}}',
        '{"version": 1, "state": "succeeded", "vendor_task_id": "", "result": {}}',
    ],
)
def test_parse_vendor_result_envelope_enforces_schema_string_lengths(
    payload: str,
) -> None:
    with pytest.raises(VendorResultProtocolError, match="must not be empty"):
        parse_vendor_result_envelope(payload)



def test_openai_compatible_endpoint_is_discovered_after_cli_and_sdk() -> None:
    orchestrator = ReviewOrchestrator.from_config_dict({
        "agents": [
            {
                "agent_id": "local-openai",
                "type": "local",
                "transport": "http",
                "endpoint_kind": "local",
                "base_url": "http://127.0.0.1:11434/v1",
            },
        ],
    })

    reviewers = orchestrator.discover_reviewers(dispatch_mode="review")

    assert [reviewer.agent_id for reviewer in reviewers] == ["local-openai"]
    assert reviewers[0].dispatch_tier == "openai"
    assert orchestrator.openai_adapters["local-openai"].base_url == (
        "http://127.0.0.1:11434/v1"
    )


def test_cli_keeps_precedence_over_openai_compatible_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("shutil.which", lambda _command: "/usr/bin/vendor")
    orchestrator = ReviewOrchestrator.from_config_dict({
        "agents": [
            {
                "agent_id": "codex-local",
                "type": "codex",
                "transport": "mcp",
                "endpoint_kind": "local",
                "base_url": "http://127.0.0.1:11434/v1",
                "cli": {
                    "command": "codex",
                    "dispatch_modes": {"review": {"args": ["exec"]}},
                    "model_flag": "-m",
                },
            },
        ],
    })

    reviewers = orchestrator.discover_reviewers(dispatch_mode="review")

    assert reviewers[0].dispatch_tier == "cli"


def test_config_parser_preserves_per_mode_isolation() -> None:
    orchestrator = ReviewOrchestrator.from_config_dict({
        "agents": [
            {
                "agent_id": "codex-local",
                "type": "codex",
                "transport": "mcp",
                "cli": {
                    "command": "codex",
                    "dispatch_modes": {
                        "review": {"args": ["exec"], "isolation": "sandbox"},
                        "alternative": {"args": ["exec"]},
                    },
                    "model_flag": "-m",
                },
            }
        ]
    })

    modes = orchestrator.adapters["codex-local"].cli_config.dispatch_modes
    assert modes["review"].isolation == "sandbox"
    assert modes["alternative"].isolation is None

def test_openai_compatible_discovery_path_dispatches_review(tmp_path: Path) -> None:
    orchestrator = ReviewOrchestrator.from_config_dict({
        "agents": [{
            "agent_id": "local-openai",
            "type": "local",
            "transport": "http",
            "endpoint_kind": "local",
            "base_url": "http://127.0.0.1:11434/v1",
        }],
    })
    adapter = orchestrator.openai_adapters["local-openai"]
    adapter.dispatch = MagicMock(return_value=ReviewResult(vendor="local", success=True, findings={"findings": []}))

    results = orchestrator.dispatch_and_wait(
        review_type="implementation",
        dispatch_mode="review",
        prompt="review",
        cwd=tmp_path,
    )

    assert len(results) == 1
    assert results[0].success is True
    adapter.dispatch.assert_called_once()


VALID_FINDINGS_JSON = json.dumps({
    "review_type": "plan",
    "target": "test-feature",
    "reviewer_vendor": "test",
    "findings": [
        {"id": 1, "type": "security", "criticality": "high",
         "description": "test", "disposition": "fix",
         "axis": "security", "severity": "critical"},
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

    def test_unavailable_402(self) -> None:
        assert classify_error("Provider returned HTTP 402") == ErrorClass.UNAVAILABLE

    def test_unavailable_insufficient_credits(self) -> None:
        # The OpenRouter 402 body pi leaks to stdout (issue #383)
        body = json.dumps({"error": {
            "message": "Insufficient credits. Add more using "
                       "https://openrouter.ai/settings/credits",
            "code": 402,
        }})
        assert classify_error(body) == ErrorClass.UNAVAILABLE

    def test_unavailable_takes_priority_over_capacity(self) -> None:
        # A billing body mentioning limits must not be mistaken for a 429
        text = "402 Payment Required: purchase credits to raise your rate limit"
        assert classify_error(text) == ErrorClass.UNAVAILABLE

    def test_402_inside_larger_number_is_not_billing(self) -> None:
        assert classify_error("processed 8,402 items with errors") == ErrorClass.UNKNOWN


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

    def test_agy_flags(self) -> None:
        # E7: agy ignores stdin and a trailing positional — the prompt must be
        # the value of --prompt (prompt_via_flag).
        adapter = CliVendorAdapter(
            agent_id="antigravity-local",
            vendor="antigravity",
            cli_config=CliConfig(
                command="agy",
                dispatch_modes={
                    "review": ModeConfig(args=["--print", "--mode", "plan"]),
                },
                model_flag="--model",
                prompt_via_flag="--prompt",
            ),
        )
        cmd = adapter.build_command("review", "prompt")
        assert cmd == ["agy", "--print", "--mode", "plan", "--prompt", "prompt"]
        # Prompt is the value of --prompt, not a trailing positional
        assert cmd[-2:] == ["--prompt", "prompt"]

    def test_grok_flags(self) -> None:
        # E2: grok delivers the prompt under a subprocess pipe via
        # --prompt-file /dev/stdin (prompt_via_stdin=True).
        adapter = CliVendorAdapter(
            agent_id="grok-local",
            vendor="grok",
            cli_config=CliConfig(
                command="grok",
                dispatch_modes={
                    "review": ModeConfig(args=[
                        "--prompt-file", "/dev/stdin",
                        "--output-format", "json",
                    ]),
                },
                model_flag="-m",
                prompt_via_stdin=True,
            ),
        )
        cmd = adapter.build_command("review", "prompt")
        assert cmd == [
            "grok", "--prompt-file", "/dev/stdin", "--output-format", "json",
        ]
        assert "prompt" not in cmd  # prompt goes via stdin, not positional

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

    @patch("shutil.which", return_value="/usr/bin/pi")
    def test_declared_credential_unset_fails_closed(
        self, _mock: MagicMock, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A binary on PATH whose declared credential env var is unset cannot
        serve a request and must not count as available (issue #383)."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        adapter = _adapter(api_key_env="OPENROUTER_API_KEY")
        assert adapter.can_dispatch("review") is False

    @patch("shutil.which", return_value="/usr/bin/pi")
    def test_declared_credential_set_is_available(
        self, _mock: MagicMock, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        adapter = _adapter(api_key_env="OPENROUTER_API_KEY")
        assert adapter.can_dispatch("review") is True


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
        assert result.models_attempted == [_resolved_primary(), "o3"]
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
        assert result.models_attempted == [_resolved_primary(), "o3", "gpt-4.1"]
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
        assert result.models_attempted == [_resolved_primary()]  # No fallback attempted

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
    def test_invalid_json_error_carries_stdout_excerpt(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """The raw output must never be silently discarded — the error string
        carries an excerpt so operators can see what the vendor actually said
        (the 'dispatcher loses raw' pathology, issue #383)."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Not valid JSON at all", stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert "Not valid JSON at all" in (result.error or "")

    @patch("review_dispatcher.subprocess.run")
    def test_pi_exit_zero_with_402_body_on_stdout(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """pi exits 0 with the provider's 402 body on stdout (issue #383):
        classified vendor_unavailable, no fallback burn, raw text preserved."""
        body = json.dumps({"error": {
            "message": "Insufficient credits. Add more using "
                       "https://openrouter.ai/settings/credits",
            "code": 402,
        }})
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=body, stderr="",
        )
        adapter = _adapter(model_fallbacks=["fallback-model"])
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is False
        assert result.error_class == ErrorClass.UNAVAILABLE
        assert result.models_attempted == [_resolved_primary()]  # account-scoped: no fallback
        assert "Insufficient credits" in (result.error or "")

    @patch("review_dispatcher.subprocess.run")
    def test_unavailable_nonzero_exit_no_fallback(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr="402 Payment Required: insufficient credits",
        )
        adapter = _adapter(model_fallbacks=["o3"])
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is False
        assert result.error_class == ErrorClass.UNAVAILABLE
        assert result.models_attempted == [_resolved_primary()]

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

    @patch("review_dispatcher.subprocess.run")
    def test_grok_structured_output_dict(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """grok --output-format json nests the object under structuredOutput (E6)."""
        envelope = json.dumps({
            "text": "done",
            "structuredOutput": json.loads(VALID_FINDINGS_JSON),
            "usage": {},
        })
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=envelope, stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.findings is not None
        assert len(result.findings["findings"]) == 1

    @patch("review_dispatcher.subprocess.run")
    def test_grok_structured_output_json_string(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """grok structuredOutput as a JSON-string is tolerated."""
        envelope = json.dumps({
            "text": "done",
            "structuredOutput": VALID_FINDINGS_JSON,
        })
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=envelope, stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.findings is not None
        assert len(result.findings["findings"]) == 1

    @patch("review_dispatcher.subprocess.run")
    def test_antigravity_response_json_string(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """agy JSON mode nests schema-valid JSON text under response."""
        envelope = json.dumps({"response": VALID_FINDINGS_JSON, "usage": {}})
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=envelope, stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.findings is not None
        assert len(result.findings["findings"]) == 1

    @patch("review_dispatcher.subprocess.run")
    def test_antigravity_structured_output_dict(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """agy JSON mode may return the schema object under structured_output."""
        envelope = json.dumps(
            {"structured_output": json.loads(VALID_FINDINGS_JSON)}
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=envelope, stderr="",
        )
        result = _adapter().dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.findings is not None
        assert len(result.findings["findings"]) == 1

    @patch("review_dispatcher.subprocess.run")
    def test_grok_envelope_missing_findings_key(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """grok envelope whose structuredOutput lacks 'findings' → fails."""
        envelope = json.dumps({
            "text": "done",
            "structuredOutput": {"review_type": "plan", "target": "test"},
        })
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=envelope, stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is False

    @patch("review_dispatcher.subprocess.run")
    def test_pi_ndjson_event_stream(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """pi --mode json emits an NDJSON event stream (E8); the findings live
        in the final assistant message_end event, not as a single JSON blob."""
        stream = "\n".join([
            json.dumps({"type": "session", "id": "s1"}),
            json.dumps({"type": "message_update", "message": {
                "role": "assistant", "content": [{"type": "text", "text": "thinking"}],
            }}),
            json.dumps({"type": "message_end", "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Findings:\n" + VALID_FINDINGS_JSON}],
            }}),
            json.dumps({"type": "agent_settled"}),
        ])
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=stream, stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.findings is not None
        assert len(result.findings["findings"]) == 1

    @patch("review_dispatcher.subprocess.run")
    def test_pi_ndjson_findings_object_on_own_line(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        """A bare findings object emitted on its own NDJSON line is picked up."""
        stream = "\n".join([
            json.dumps({"type": "session", "id": "s1"}),
            VALID_FINDINGS_JSON,
            json.dumps({"type": "agent_settled"}),
        ])
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=stream, stderr="",
        )
        adapter = _adapter()
        result = adapter.dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.findings is not None
        assert len(result.findings["findings"]) == 1


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class TestOrchestrator:
    def test_from_config_dict_propagates_prompt_via_flag(self) -> None:
        """prompt_via_flag must survive from_config_dict into the CliConfig so
        antigravity's prompt is dispatched as ``--prompt <value>`` (E7), not a
        trailing positional."""
        cfg = {"agents": [{
            "agent_id": "antigravity-local",
            "type": "antigravity",
            "cli": {
                "command": "agy",
                "model_flag": "--model",
                "model": "gemini-3.6-flash",
                "prompt_via_flag": "--prompt",
                "dispatch_modes": {"review": {"args": ["--mode", "plan"]}},
            },
        }]}
        orch = ReviewOrchestrator.from_config_dict(cfg)
        adapter = orch.adapters["antigravity-local"]
        assert adapter.cli_config.prompt_via_flag == "--prompt"
        cmd = adapter.build_command("review", "REVIEW THIS", None)
        assert "--prompt" in cmd
        # The prompt is the value of --prompt, not a bare trailing positional:
        # it must be immediately preceded by the flag.
        assert cmd[cmd.index("--prompt") + 1] == "REVIEW THIS"
        assert cmd[-2] == "--prompt"

    def test_from_config_dict_propagates_api_key_env(self) -> None:
        """cli.api_key_env must survive from_config_dict so availability
        checks can fail closed on a missing credential (issue #383)."""
        cfg = {"agents": [{
            "agent_id": "pi-local",
            "type": "pi",
            "cli": {
                "command": "pi",
                "model_flag": "--model",
                "model": "moonshotai/kimi-k3",
                "api_key_env": "OPENROUTER_API_KEY",
                "dispatch_modes": {"review": {"args": ["-p"]}},
            },
        }]}
        orch = ReviewOrchestrator.from_config_dict(cfg)
        assert orch.adapters["pi-local"].cli_config.api_key_env == "OPENROUTER_API_KEY"

    def test_discover_reviewers(self) -> None:
        adapters = {
            "codex-local": _adapter("codex-local", "codex"),
            "grok-local": _adapter("grok-local", "grok", command="grok"),
        }
        orch = ReviewOrchestrator(adapters)
        with patch("shutil.which", return_value="/usr/bin/mock"):
            reviewers = orch.discover_reviewers()
        assert len(reviewers) == 2

    def test_discover_excludes_vendor(self) -> None:
        adapters = {
            "codex-local": _adapter("codex-local", "codex"),
            "grok-local": _adapter("grok-local", "grok", command="grok"),
        }
        orch = ReviewOrchestrator(adapters)
        with patch("shutil.which", return_value="/usr/bin/mock"):
            reviewers = orch.discover_reviewers(exclude_vendor="codex")
        assert len(reviewers) == 1
        assert reviewers[0].vendor == "grok"

    def test_write_manifest(self, tmp_path: Path) -> None:
        orch = ReviewOrchestrator({})
        results = [
            ReviewResult(
                vendor="codex",
                success=True,
                model_used="gpt-5.4",
                models_attempted=["gpt-5.4"],
                elapsed_seconds=120.5,
                async_dispatch=True,
                task_id="vendor-task-7",
                ledger_task_id="ledger-task-9",
            ),
            ReviewResult(vendor="grok", success=False, error="429 capacity",
                        error_class=ErrorClass.CAPACITY,
                        models_attempted=["(default)", "grok-4.5"]),
        ]
        output = tmp_path / "reviews" / "review-manifest.json"
        orch.write_manifest(results, output, "plan", "test-feature")
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["quorum_requested"] == 2
        assert data["quorum_received"] == 1
        assert data["dispatches"][0]["success"] is True
        assert data["dispatches"][0]["async_dispatch"] is True
        assert data["dispatches"][0]["task_id"] == "vendor-task-7"
        assert data["dispatches"][0]["ledger_task_id"] == "ledger-task-9"
        assert data["dispatches"][1]["error_class"] == "capacity_exhausted"


# ---------------------------------------------------------------------------
# Async dispatch + polling tests
# ---------------------------------------------------------------------------

def _async_adapter(*, ledger: _LedgerStub | None = None) -> CliVendorAdapter:
    """Create adapter with async mode and injected ledger boundaries."""
    ledger = ledger or _LedgerStub()
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
                        interval_seconds=1,
                        timeout_seconds=5,
                    ),
                ),
            },
            model_flag="-m",
        ),
        ledger_submitter=ledger.submit,
        ledger_completer=ledger.complete,
    )


def _vendor_envelope(
    state: str,
    *,
    result: dict[str, object] | None = None,
    error: dict[str, object] | None = None,
) -> str:
    return json.dumps({
        "version": 1,
        "state": state,
        "vendor_task_id": "abc123",
        **({"result": result} if result is not None else {}),
        **({"error": error} if error is not None else {}),
    })


class TestAsyncDispatch:
    @patch("review_dispatcher.subprocess.run")
    def test_async_submit_reads_task_id_from_structured_envelope(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        ledger = _LedgerStub()
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_vendor_envelope("submitted"), stderr="",
        )
        adapter = _async_adapter(ledger=ledger)

        result = adapter.dispatch_async("alternative", "prompt", cwd=tmp_path)

        assert result.success is True
        assert result.task_id == "abc123"
        assert result.ledger_task_id == "ledger-123"
        assert result.async_dispatch is True
        assert len(ledger.submissions) == 1
        assert ledger.submissions[0]["claim_immediately"] is True
        assert ledger.completions == []

    @patch("review_dispatcher.subprocess.run")
    def test_async_submit_rejects_ledger_row_not_atomically_claimed(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        ledger = _LedgerStub()
        ledger.submit_response = {
            "status": "ok",
            "data": {
                "success": True,
                "task_id": "ledger-123",
                "status": "pending",
            },
        }
        adapter = _async_adapter(ledger=ledger)

        result = adapter.dispatch_async("alternative", "prompt", cwd=tmp_path)

        assert result.success is False
        assert "did not return claimed status" in (result.error or "")
        mock_run.assert_not_called()

    @patch("review_dispatcher.subprocess.run")
    def test_async_submit_does_not_launch_when_completion_ledger_is_unavailable(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        ledger = _LedgerStub()
        ledger.submit_response = {
            "status": "skipped",
            "reason": "coordinator_unavailable",
        }
        adapter = _async_adapter(ledger=ledger)

        result = adapter.dispatch_async("alternative", "prompt", cwd=tmp_path)

        assert result.success is False
        assert "completion ledger" in (result.error or "").lower()
        mock_run.assert_not_called()

    @patch("review_dispatcher.subprocess.run")
    def test_async_submit_oserror_completes_claimed_ledger(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        ledger = _LedgerStub()
        mock_run.side_effect = FileNotFoundError("vendor CLI disappeared")
        adapter = _async_adapter(ledger=ledger)

        result = adapter.dispatch_async("alternative", "prompt", cwd=tmp_path)

        assert result.success is False
        assert "vendor CLI disappeared" in (result.error or "")
        assert len(ledger.completions) == 1
        assert ledger.completions[0]["success"] is False


    @patch("review_dispatcher.subprocess.run")
    def test_async_submit_rejects_unknown_result_protocol_before_ledger_or_launch(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        ledger = _LedgerStub()
        adapter = _async_adapter(ledger=ledger)
        poll = adapter.cli_config.dispatch_modes["alternative"].poll
        assert poll is not None
        poll.result_protocol = "vendor-envelope-v2"

        result = adapter.dispatch_async("alternative", "prompt", cwd=tmp_path)

        assert result.success is False
        assert "unsupported result protocol" in (result.error or "").lower()
        assert ledger.submissions == []
        assert ledger.completions == []
        mock_run.assert_not_called()


    @patch("review_dispatcher.subprocess.run")
    def test_async_capacity_callback_fires_before_successful_fallback(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="429 capacity",
            ),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=_vendor_envelope("submitted"), stderr="",
            ),
        ]
        adapter = _async_adapter()
        adapter.cli_config.model = "gpt-primary"
        adapter.cli_config.model_fallbacks = ["gpt-fallback"]
        observations: list[ReviewResult] = []

        result = adapter.dispatch_async(
            "alternative",
            "prompt",
            cwd=tmp_path,
            capacity_callback=observations.append,
        )

        assert result.success is True
        assert len(observations) == 1
        assert observations[0].agent_id == "codex-remote"
        assert observations[0].capacity_scope == "model"
        assert observations[0].capacity_model == "gpt-primary"

    @patch("review_dispatcher.subprocess.run")
    def test_async_submit_rejects_text_without_regex_fallback(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Submitted! task: abc123\n", stderr="",
        )
        adapter = _async_adapter()

        result = adapter.dispatch_async("alternative", "prompt", cwd=tmp_path)

        assert result.success is False
        assert "Invalid structured async submission" in (result.error or "")

    @patch("review_dispatcher.subprocess.run")
    def test_async_not_configured(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        adapter = _async_adapter()
        result = adapter.dispatch_async("review", "prompt", cwd=tmp_path)
        assert result.success is False
        assert "not configured for async" in (result.error or "")

    @patch("review_dispatcher.subprocess.run")
    @patch("review_dispatcher.time.sleep")
    def test_poll_success_completes_ledger_before_consuming_findings(
        self, mock_sleep: MagicMock, mock_run: MagicMock, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        findings = json.loads(VALID_FINDINGS_JSON)
        ledger = _LedgerStub()
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_vendor_envelope("succeeded", result=findings),
            stderr="",
        )
        adapter = _async_adapter(ledger=ledger)
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            interval_seconds=1,
            timeout_seconds=10,
        )

        monkeypatch.setenv("AGENT_ID", "different-process-agent")
        result = adapter.poll_for_result(
            "abc123", poll_cfg, ledger_task_id="ledger-123",
        )

        assert result.success is True
        assert result.findings is not None
        assert len(result.findings["findings"]) == 1
        assert result.task_id == "abc123"
        assert result.ledger_task_id == "ledger-123"
        assert ledger.completions[0]["success"] is True
        assert ledger.completions[0]["agent_id"] is None
        assert ledger.completions[0]["result"] == {
            "vendor_result": {
                "version": 1,
                "state": "succeeded",
                "vendor_task_id": "abc123",
                "result": findings,
                "error": None,
            }
        }

    @patch("review_dispatcher.subprocess.run")
    def test_poll_does_not_rewrite_empty_result_as_clean_findings(
        self, mock_run: MagicMock,
    ) -> None:
        ledger = _LedgerStub()
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_vendor_envelope("succeeded", result={}),
            stderr="",
        )
        adapter = _async_adapter(ledger=ledger)
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            interval_seconds=1,
            timeout_seconds=10,
        )

        result = adapter.poll_for_result(
            "abc123", poll_cfg, ledger_task_id="ledger-123",
        )

        assert result.success is False
        assert result.error is not None
        assert ledger.completions[0]["success"] is False

    @patch("review_dispatcher.subprocess.run")
    def test_poll_placeholder_is_unsuccessful(
        self, mock_run: MagicMock,
    ) -> None:
        payload = json.loads(VALID_FINDINGS_JSON)
        payload["findings"][0]["description"] = "Placeholder while review runs"
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_vendor_envelope("succeeded", result=payload),
            stderr="",
        )
        ledger = _LedgerStub()
        adapter = _async_adapter(ledger=ledger)
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            interval_seconds=1,
            timeout_seconds=10,
        )

        result = adapter.poll_for_result(
            "abc123", poll_cfg, ledger_task_id="ledger-123",
        )

        assert result.success is False
        assert result.error == "non_substantive_placeholder"
        assert result.task_id == "abc123"

        assert ledger.completions[0]["success"] is False
        assert ledger.completions[0]["error_message"] == result.error

    @patch("review_dispatcher.subprocess.run")
    def test_poll_preserves_ingestion_error_when_ledger_completion_fails(
        self, mock_run: MagicMock,
    ) -> None:
        payload = json.loads(VALID_FINDINGS_JSON)
        payload["findings"][0]["description"] = "Placeholder while review runs"
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_vendor_envelope("succeeded", result=payload),
            stderr="",
        )
        ledger = _LedgerStub()
        ledger.complete_response = {
            "status": "skipped",
            "reason": "coordinator_unavailable",
        }
        adapter = _async_adapter(ledger=ledger)
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            interval_seconds=1,
            timeout_seconds=10,
        )

        result = adapter.poll_for_result(
            "abc123", poll_cfg, ledger_task_id="ledger-123",
        )

        assert result.success is False
        assert "non_substantive_placeholder" in (result.error or "")
        assert "completion ledger update failed" in (result.error or "").lower()


    @patch("review_dispatcher.subprocess.run")
    def test_poll_accepts_clean_findings_when_remote_runtime_is_unknown(
        self, mock_run: MagicMock,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_vendor_envelope("succeeded", result={"findings": []}),
            stderr="",
        )
        adapter = _async_adapter()
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            interval_seconds=1,
            timeout_seconds=10,
        )

        result = adapter.poll_for_result(
            "abc123", poll_cfg, ledger_task_id="ledger-123",
        )

        assert result.success is True
        assert result.findings == {"findings": []}

    @patch("review_dispatcher.subprocess.run")
    def test_poll_rejects_clean_findings_when_submission_runtime_is_fast(
        self, mock_run: MagicMock,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_vendor_envelope("succeeded", result={"findings": []}),
            stderr="",
        )
        adapter = _async_adapter()
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            interval_seconds=1,
            timeout_seconds=10,
        )

        result = adapter.poll_for_result(
            "abc123",
            poll_cfg,
            review_started_at=time.monotonic(),
            ledger_task_id="ledger-123",
        )

        assert result.success is False
        assert result.error == "empty_findings_too_fast"
        assert result.task_id == "abc123"

    @patch("review_dispatcher.subprocess.run")
    def test_poll_oserror_completes_claimed_ledger(
        self, mock_run: MagicMock,
    ) -> None:
        ledger = _LedgerStub()
        mock_run.side_effect = FileNotFoundError("status CLI disappeared")
        adapter = _async_adapter(ledger=ledger)
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            interval_seconds=1,
            timeout_seconds=10,
        )

        result = adapter.poll_for_result(
            "abc123", poll_cfg, ledger_task_id="ledger-123",
        )

        assert result.success is False
        assert "status CLI disappeared" in (result.error or "")
        assert len(ledger.completions) == 1
        assert ledger.completions[0]["success"] is False


    @patch("review_dispatcher.subprocess.run")
    @patch("review_dispatcher.time.sleep")
    def test_poll_terminal_failure_completes_ledger(
        self, mock_sleep: MagicMock, mock_run: MagicMock,
    ) -> None:
        ledger = _LedgerStub()
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_vendor_envelope(
                "failed",
                error={"code": "vendor_failed", "message": "something broke"},
            ),
            stderr="",
        )
        adapter = _async_adapter(ledger=ledger)
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            interval_seconds=1,
            timeout_seconds=10,
        )

        result = adapter.poll_for_result(
            "abc123", poll_cfg, ledger_task_id="ledger-123",
        )

        assert result.success is False
        assert "something broke" in (result.error or "").lower()
        assert ledger.completions[0]["success"] is False

    @patch("review_dispatcher.subprocess.run")
    def test_poll_rejects_status_for_a_different_vendor_task(
        self, mock_run: MagicMock,
    ) -> None:
        ledger = _LedgerStub()
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "version": 1,
                    "state": "failed",
                    "vendor_task_id": "different-task",
                    "error": {
                        "code": "vendor_failed",
                        "message": "wrong task",
                    },
                }
            ),
            stderr="",
        )
        adapter = _async_adapter(ledger=ledger)
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            interval_seconds=1,
            timeout_seconds=10,
        )

        result = adapter.poll_for_result(
            "abc123", poll_cfg, ledger_task_id="ledger-123",
        )

        assert result.success is False
        assert "does not match submitted task" in (result.error or "")
        assert ledger.completions[0]["success"] is False

    @patch("review_dispatcher.subprocess.run")
    @patch("review_dispatcher.time.sleep")
    @patch("review_dispatcher.time.monotonic")
    def test_poll_timeout(
        self, mock_time: MagicMock, mock_sleep: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_time.side_effect = [0, 0, 1, 3, 6, 100]
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_vendor_envelope("running"), stderr="",
        )
        adapter = _async_adapter()
        poll_cfg = PollConfig(
            command_template=["codex", "cloud", "status", "{task_id}"],
            interval_seconds=1,
            timeout_seconds=5,
        )

        result = adapter.poll_for_result(
            "abc123", poll_cfg, ledger_task_id="ledger-123",
        )

        assert result.success is False
        assert "timed out" in (result.error or "").lower()

    @patch("review_dispatcher.subprocess.run")
    def test_terminal_result_is_not_consumed_when_ledger_completion_fails(
        self, mock_run: MagicMock,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_vendor_envelope(
                "succeeded", result=json.loads(VALID_FINDINGS_JSON),
            ),
            stderr="",
        )
        ledger = _LedgerStub()
        ledger.complete_response = {
            "status": "skipped",
            "reason": "coordinator_unavailable",
        }
        adapter = _async_adapter(ledger=ledger)
        poll_cfg = adapter.cli_config.dispatch_modes["alternative"].poll
        assert poll_cfg is not None

        result = adapter.poll_for_result(
            "abc123", poll_cfg, ledger_task_id="ledger-123",
        )

        assert result.success is False
        assert result.findings is None
        assert "completion ledger" in (result.error or "").lower()


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
    @patch("review_dispatcher.SdkVendorAdapter._call_sdk")
    def test_unsupported_mode_is_rejected_before_sdk_call(
        self, mock_call: MagicMock, tmp_path: Path,
    ) -> None:
        adapter = _sdk_adapter()

        result = adapter.dispatch(
            "alternative", "prompt", cwd=tmp_path, api_key="sk-test",
        )

        assert result.success is False
        assert result.error == "SDK dispatch mode 'alternative' is unsupported"
        mock_call.assert_not_called()

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
    def test_dispatch_parse_failure_does_not_invent_raw_null(
        self, mock_call: MagicMock, tmp_path: Path,
    ) -> None:
        mock_call.return_value = None
        adapter = _sdk_adapter()

        result = adapter.dispatch(
            "review", "prompt", cwd=tmp_path, api_key="sk-test",
        )

        assert result.raw_stdout is None

    @patch("review_dispatcher.SdkVendorAdapter._call_sdk")
    def test_dispatch_placeholder_is_unsuccessful(
        self, mock_call: MagicMock, tmp_path: Path,
    ) -> None:
        payload = json.loads(VALID_FINDINGS_JSON)
        payload["findings"][0]["description"] = "Placeholder pending plan artifact review."
        mock_call.return_value = payload
        adapter = _sdk_adapter()

        result = adapter.dispatch(
            "review", "prompt", cwd=tmp_path, api_key="sk-test",
        )

        assert result.success is False
        assert result.error == "non_substantive_placeholder"
        assert result.raw_stdout == json.dumps(payload)

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
    def test_capacity_callback_fires_before_successful_model_fallback(
        self, mock_call: MagicMock, tmp_path: Path,
    ) -> None:
        from review_dispatcher import _SdkCapacityError

        mock_call.side_effect = [
            _SdkCapacityError(),
            json.loads(VALID_FINDINGS_JSON),
        ]
        adapter = _sdk_adapter(model_fallbacks=["claude-haiku-4-5-20251001"])
        observations: list[ReviewResult] = []

        result = adapter.dispatch(
            "review",
            "prompt",
            cwd=tmp_path,
            api_key="sk-test",
            capacity_callback=observations.append,
        )

        assert result.success is True
        assert len(observations) == 1
        assert observations[0].agent_id == "claude-remote"
        assert observations[0].capacity_scope == "model"
        assert observations[0].capacity_model == "claude-sonnet-4-6"

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

    def test_cli_skipped_when_declared_credential_unset(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Tier-1 selection must not report a vendor whose CLI is on PATH but
        whose declared credential is unset (issue #383: 5/5 available while pi
        could not serve a single request)."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cli_adapters = {
            "pi-local": _adapter(
                "pi-local", "pi", command="pi",
                api_key_env="OPENROUTER_API_KEY",
            ),
        }
        orch = ReviewOrchestrator(cli_adapters, {})
        with patch("shutil.which", return_value="/usr/bin/pi"):
            reviewers = orch.discover_reviewers()
        assert reviewers == []

    def test_skip_when_nothing_available(self) -> None:
        """When neither CLI nor SDK is available, vendor is skipped."""
        cli_adapters = {
            "pi-local": _adapter("pi-local", "pi", command="pi"),
        }
        sdk_adapters = {
            "pi-remote": SdkVendorAdapter(
                agent_id="pi-remote",
                vendor="pi",
                sdk_config=SdkConfig(
                    package="openrouter",
                    model="moonshotai/kimi-k3",
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


class TestDispatchRobustness:
    """Coerce, repair, judgment ingest, fast-empty, sidecars."""

    @patch("review_dispatcher.subprocess.run")
    def test_bug_type_is_coerced_to_valid_findings(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        payload = {
            "findings": [
                {
                    "id": 1,
                    "type": "bug",
                    "criticality": "high",
                    "description": "Critical: off by one",
                    "disposition": "fix",
                    "axis": "correctness",
                    "severity": "critical",
                }
            ]
        }
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(payload), stderr="",
        )
        result = _adapter().dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.findings is not None
        assert result.findings["findings"][0]["type"] == "correctness"
        assert result.coercions

    @patch("review_dispatcher.subprocess.run")
    def test_schema_repair_retry_succeeds(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="not json", stderr="",
            ),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=VALID_FINDINGS_JSON, stderr="",
            ),
        ]
        result = _adapter().dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert mock_run.call_count == 2

    @patch("review_dispatcher.subprocess.run")
    def test_schema_repair_is_not_unbounded(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not json", stderr="",
        )
        result = _adapter().dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is False
        assert mock_run.call_count == 2

    @patch("review_dispatcher.subprocess.run")
    def test_cli_findings_are_stamped_judgment(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=VALID_FINDINGS_JSON, stderr="",
        )
        result = _adapter().dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is True
        assert result.findings is not None
        assert result.findings["findings"][0]["evidence_class"] == "judgment"

    @patch("review_dispatcher.subprocess.run")
    def test_payload_cannot_self_promote_to_deterministic(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        payload = json.loads(VALID_FINDINGS_JSON)
        payload["findings"][0]["evidence_class"] = "deterministic"
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(payload), stderr="",
        )
        result = _adapter().dispatch("review", "prompt", cwd=tmp_path)
        assert result.findings is not None
        assert result.findings["findings"][0]["evidence_class"] == "judgment"

    @patch("review_dispatcher.subprocess.run")
    def test_fast_empty_findings_are_unsuccessful(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"findings": []}', stderr="",
        )
        result = _adapter().dispatch("review", "prompt", cwd=tmp_path)
        assert result.success is False
        assert result.error == "empty_findings_too_fast"

    @pytest.mark.parametrize("description", [
        "Placeholder while review runs",
        "Placeholder while review is in progress",
        "Placeholder pending review",
        "Placeholder until analysis finishes",
    ])
    def test_nonempty_placeholder_is_unsuccessful(
        self, description: str,
    ) -> None:
        payload = json.dumps({
            "review_type": "plan",
            "target": "test-feature",
            "reviewer_vendor": "grok",
            "findings": [{
                "id": 1,
                "type": "correctness",
                "criticality": "medium",
                "description": description,
                "disposition": "fix",
                "axis": "correctness",
                "severity": "critical",
            }],
        })

        result = _adapter(vendor="grok")._ingest_stdout(
            payload,
            "",
            elapsed=16.0,
            model_name="grok-4.5",
            models_attempted=["grok-4.5"],
        )

        assert result.success is False
        assert result.findings is None
        assert result.error == "non_substantive_placeholder"
        assert result.raw_stdout == payload

    def test_placeholder_wrapper_is_unsuccessful_after_grace_period(self) -> None:
        envelope = json.dumps({
            "text": "Placeholder while review runs",
            "structuredOutput": {"findings": []},
        })

        result = _adapter(vendor="grok")._ingest_stdout(
            envelope,
            "",
            elapsed=16.0,
            model_name="grok-4.5",
            models_attempted=["grok-4.5"],
        )

        assert result.success is False
        assert result.findings is None
        assert result.error == "non_substantive_placeholder"
        assert result.raw_stdout == envelope

    def test_substantive_finding_with_placeholder_context_succeeds(self) -> None:
        envelope = json.dumps({
            "text": "Placeholder marker appeared in the source fixture.",
            "structuredOutput": json.loads(VALID_FINDINGS_JSON),
        })

        result = _adapter(vendor="grok")._ingest_stdout(
            envelope,
            "",
            elapsed=16.0,
            model_name="grok-4.5",
            models_attempted=["grok-4.5"],
        )

        assert result.success is True
        assert result.findings is not None
        assert result.findings["findings"][0]["description"] == "test"

    def test_real_finding_starting_with_review_pending_succeeds(self) -> None:
        payload = json.loads(VALID_FINDINGS_JSON)
        payload["findings"][0]["description"] = (
            "Review pending state is never cleared when the dispatcher times out"
        )

        result = _adapter()._ingest_stdout(
            json.dumps(payload),
            "",
            elapsed=16.0,
            model_name="test-model",
            models_attempted=["test-model"],
        )

        assert result.success is True

    @patch("review_dispatcher.subprocess.run")
    def test_placeholder_does_not_trigger_schema_repair(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        payload = json.loads(VALID_FINDINGS_JSON)
        payload["findings"][0]["description"] = "Placeholder while review runs"
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(payload), stderr="",
        )

        result = _adapter().dispatch("review", "prompt", cwd=tmp_path)

        assert result.success is False
        assert result.error == "non_substantive_placeholder"
        assert mock_run.call_count == 1

    @patch("review_dispatcher.subprocess.run")
    def test_raw_stdout_is_kept_on_success(
        self, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=VALID_FINDINGS_JSON, stderr="",
        )
        result = _adapter().dispatch("review", "prompt", cwd=tmp_path)
        assert result.raw_stdout == VALID_FINDINGS_JSON

    def test_timeout_for_claude_exceeds_historical_300s(self) -> None:
        from review_findings_schema import timeout_for_vendor

        assert timeout_for_vendor("claude_code") >= 720
        assert timeout_for_vendor("claude_code", override=120) == 120


# ---------------------------------------------------------------------------
# Concurrent dispatch (OpenSpec pack-and-parallelize-vendor-review D2/D4)
# ---------------------------------------------------------------------------

_STUB_SLEEP_SECONDS = 2.0
_CONCURRENT_WALL_LIMIT_SECONDS = 3.0


def _write_sleep_stub(path: Path, stamp_path: Path, sleep_seconds: float) -> None:
    """Write an executable fake vendor CLI that sleeps, then prints findings."""
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, time\n"
        "from pathlib import Path\n"
        f"stamp = Path({str(stamp_path)!r})\n"
        "stamp.write_text(json.dumps({\n"
        '    "start": time.time(),\n'
        '    "cwd": os.getcwd(),\n'
        '    "pid": os.getpid(),\n'
        "}))\n"
        f"time.sleep({sleep_seconds!r})\n"
        "data = json.loads(stamp.read_text())\n"
        'data["end"] = time.time()\n'
        "stamp.write_text(json.dumps(data))\n"
        f"print({VALID_FINDINGS_JSON!r})\n"
    )
    path.chmod(0o755)


def _intervals_overlap(a: dict[str, float], b: dict[str, float]) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


class TestConcurrentDispatch:
    """D4: two 2s stubs finish in <3s with overlapping subprocess lifetimes."""

    def test_concurrent_stub_vendors_overlap_under_three_seconds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        stamp_a = tmp_path / "codex-stamp.json"
        stamp_b = tmp_path / "grok-stamp.json"
        _write_sleep_stub(bin_dir / "review-stub-codex", stamp_a, _STUB_SLEEP_SECONDS)
        _write_sleep_stub(bin_dir / "review-stub-grok", stamp_b, _STUB_SLEEP_SECONDS)
        monkeypatch.setenv(
            "PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        )

        adapters = {
            "codex-local": _adapter(
                "codex-local", "codex", command="review-stub-codex",
            ),
            "grok-local": _adapter(
                "grok-local", "grok", command="review-stub-grok",
            ),
        }
        orch = ReviewOrchestrator(adapters)
        started = time.monotonic()
        results = orch.dispatch_and_wait(
            review_type="plan",
            dispatch_mode="review",
            prompt="Review this packet",
            cwd=tmp_path,
            timeout_seconds=15,
        )
        elapsed = time.monotonic() - started

        assert elapsed < _CONCURRENT_WALL_LIMIT_SECONDS, (
            f"concurrent dispatch took {elapsed:.2f}s; sequential 2s stubs "
            "would take >=4s, overlap must finish in <3s"
        )
        assert elapsed < 4.0  # sequential dispatch is a bug (spec scenario)
        assert len(results) == 2
        assert all(r.success for r in results)

        a = json.loads(stamp_a.read_text())
        b = json.loads(stamp_b.read_text())
        assert _intervals_overlap(a, b), (
            f"subprocess lifetimes did not overlap: codex={a} grok={b}"
        )
        assert a["cwd"] == str(tmp_path)
        assert b["cwd"] == str(tmp_path)

    def test_async_poll_starts_without_waiting_for_slow_submit(self, tmp_path: Path) -> None:
        """A completed submission starts polling while peers still submit."""
        submit_ends: list[float] = []
        poll_starts: list[float] = []
        lock = threading.Lock()

        def _async_cli(agent_id: str, vendor: str) -> CliVendorAdapter:
            return CliVendorAdapter(
                agent_id=agent_id,
                vendor=vendor,
                cli_config=CliConfig(
                    command=f"cloud-{vendor}",
                    dispatch_modes={
                        "review": ModeConfig(
                            args=["cloud", "exec"],
                            async_dispatch=True,
                            poll=PollConfig(
                                command_template=["status", "{task_id}"],
                                interval_seconds=1,
                                timeout_seconds=10,
                            ),
                        ),
                    },
                    model_flag="-m",
                ),
            )

        adapters = {
            "codex-remote": _async_cli("codex-remote", "codex"),
            "grok-remote": _async_cli("grok-remote", "grok"),
        }

        def fake_submit(self: CliVendorAdapter, mode: str, prompt: str, cwd: Path) -> ReviewResult:
            delay = 0.05 if self.vendor == "codex" else 0.35
            time.sleep(delay)
            with lock:
                submit_ends.append(time.monotonic())
            return ReviewResult(
                vendor=self.vendor,
                success=True,
                async_dispatch=True,
                task_id=f"task-{self.vendor}",
                ledger_task_id=f"ledger-{self.vendor}",
            )

        def fake_poll(
            self: CliVendorAdapter,
            task_id: str,
            poll_config: PollConfig,
            cwd: Path | None = None,
            *,
            review_started_at: float | None = None,
            ledger_task_id: str | None = None,
        ) -> ReviewResult:
            assert review_started_at is not None
            assert ledger_task_id == f"ledger-{self.vendor}"
            with lock:
                poll_starts.append(time.monotonic())
            return ReviewResult(
                vendor=self.vendor,
                success=True,
                findings=json.loads(VALID_FINDINGS_JSON),
                task_id=task_id,
            )

        orch = ReviewOrchestrator(adapters)
        with patch("shutil.which", return_value="/usr/bin/mock"), patch.object(
            CliVendorAdapter, "dispatch_async", fake_submit,
        ), patch.object(CliVendorAdapter, "poll_for_result", fake_poll):
            results = orch.dispatch_and_wait(
                review_type="plan",
                dispatch_mode="review",
                prompt="Review this packet",
                cwd=tmp_path,
                timeout_seconds=15,
            )

        assert len(results) == 2
        assert all(r.success for r in results)
        assert len(submit_ends) == 2
        assert len(poll_starts) == 2
        assert min(poll_starts) < max(submit_ends), (
            "fast async vendor waited for every peer submission "
            f"(submit_ends={submit_ends}, poll_starts={poll_starts})"
        )

    def test_result_callback_fires_in_completion_order(
        self, tmp_path: Path,
    ) -> None:
        callback_results: list[tuple[str, int]] = []
        second_completed = threading.Event()
        first = _adapter("codex-local", "codex")
        second = _adapter("grok-local", "grok")

        def first_dispatch(*_args: object, **_kwargs: object) -> ReviewResult:
            assert second_completed.wait(timeout=1.0)
            return ReviewResult(vendor="codex", success=True)

        def second_dispatch(*_args: object, **_kwargs: object) -> ReviewResult:
            time.sleep(0.02)
            return ReviewResult(vendor="grok", success=True)

        def on_result(result: ReviewResult, expected_count: int) -> None:
            callback_results.append((result.vendor, expected_count))
            if result.vendor == "grok":
                second_completed.set()

        orch = ReviewOrchestrator({"codex-local": first, "grok-local": second})
        with (
            patch("shutil.which", return_value="/usr/bin/mock"),
            patch.object(first, "dispatch", side_effect=first_dispatch),
            patch.object(second, "dispatch", side_effect=second_dispatch),
        ):
            results = orch.dispatch_and_wait(
                review_type="plan",
                dispatch_mode="review",
                prompt="Review this packet",
                cwd=tmp_path,
                result_callback=on_result,
            )

        assert callback_results == [("grok", 2), ("codex", 2)]
        assert [result.vendor for result in results] == ["codex", "grok"]

    def test_async_poll_starts_before_slow_sync_finishes(
        self, tmp_path: Path,
    ) -> None:
        poll_started = threading.Event()
        sync = _adapter("codex-local", "codex")
        async_adapter = CliVendorAdapter(
            agent_id="grok-remote",
            vendor="grok",
            cli_config=CliConfig(
                command="cloud-grok",
                dispatch_modes={
                    "review": ModeConfig(
                        args=["cloud", "exec"],
                        async_dispatch=True,
                        poll=PollConfig(
                            command_template=["status", "{task_id}"],
                            interval_seconds=1,
                            timeout_seconds=10,
                        ),
                    ),
                },
                model_flag="-m",
            ),
        )

        def slow_sync(*_args: object, **_kwargs: object) -> ReviewResult:
            if not poll_started.wait(timeout=0.5):
                return ReviewResult(vendor="codex", success=False, error="poll delayed")
            return ReviewResult(vendor="codex", success=True)

        def poll_result(*_args: object, **_kwargs: object) -> ReviewResult:
            poll_started.set()
            return ReviewResult(vendor="grok", success=True)

        orch = ReviewOrchestrator({
            "codex-local": sync,
            "grok-remote": async_adapter,
        })
        with (
            patch("shutil.which", return_value="/usr/bin/mock"),
            patch.object(sync, "dispatch", side_effect=slow_sync),
            patch.object(
                async_adapter,
                "dispatch_async",
                return_value=ReviewResult(
                    vendor="grok",
                    success=True,
                    async_dispatch=True,
                    task_id="task-grok",
                    ledger_task_id="ledger-grok",
                ),
            ),
            patch.object(
                async_adapter, "poll_for_result", side_effect=poll_result,
            ),
        ):
            results = orch.dispatch_and_wait(
                review_type="plan",
                dispatch_mode="review",
                prompt="Review this packet",
                cwd=tmp_path,
            )

        assert all(result.success for result in results)

    def test_result_callback_waits_for_async_poll(self, tmp_path: Path) -> None:
        adapter = CliVendorAdapter(
            agent_id="grok-remote",
            vendor="grok",
            cli_config=CliConfig(
                command="cloud-grok",
                dispatch_modes={
                    "review": ModeConfig(
                        args=["cloud", "exec"],
                        async_dispatch=True,
                        poll=PollConfig(
                            command_template=["status", "{task_id}"],
                            interval_seconds=1,
                            timeout_seconds=10,
                        ),
                    ),
                },
                model_flag="-m",
            ),
        )
        callbacks: list[ReviewResult] = []
        submission = ReviewResult(
            vendor="grok",
            success=True,
            async_dispatch=True,
            task_id="task-grok",
            ledger_task_id="ledger-grok",
        )
        terminal = ReviewResult(
            vendor="grok", success=True, findings=json.loads(VALID_FINDINGS_JSON),
        )
        orch = ReviewOrchestrator({"grok-remote": adapter})

        with (
            patch("shutil.which", return_value="/usr/bin/mock"),
            patch.object(adapter, "dispatch_async", return_value=submission),
            patch.object(adapter, "poll_for_result", return_value=terminal),
        ):
            results = orch.dispatch_and_wait(
                review_type="plan",
                dispatch_mode="review",
                prompt="Review this packet",
                cwd=tmp_path,
                result_callback=lambda result, _count: callbacks.append(result),
            )

        assert callbacks == [terminal]
        assert results == [terminal]


class TestConcurrentGitSnapshotFallback:
    """D2: shared cwd is the default; snapshot is the git-lock escape hatch."""

    def test_concurrent_git_access_error_retries_on_snapshot_path(
        self, tmp_path: Path,
    ) -> None:
        adapter = _adapter("codex-local", "codex")
        snapshot = (
            tmp_path / ".git-worktrees" / ".review-snapshots" / "round-1" / "codex"
        )
        cwds: list[Path] = []

        def fake_dispatch(
            mode: str,
            prompt: str,
            cwd: Path,
            timeout_seconds: int = 300,
            **_kwargs: object,
        ) -> ReviewResult:
            cwds.append(Path(cwd))
            if len(cwds) == 1:
                return ReviewResult(
                    vendor="codex",
                    success=False,
                    error=(
                        "fatal: Unable to create '.git/index.lock': File exists. "
                        "Another git process seems to be running in this repository"
                    ),
                )
            return ReviewResult(
                vendor="codex",
                success=True,
                findings=json.loads(VALID_FINDINGS_JSON),
            )

        packet = tmp_path / "round-1" / "review-packet.md"
        packet.parent.mkdir()
        packet.write_text("# packet\n")
        orch = ReviewOrchestrator({"codex-local": adapter})

        with (
            patch("shutil.which", return_value="/usr/bin/codex"),
            patch.object(adapter, "dispatch", side_effect=fake_dispatch),
            patch(
                "review_dispatcher.create_review_snapshot",
                return_value=snapshot,
            ) as mock_create,
            patch("review_dispatcher.destroy_review_snapshot") as mock_destroy,
        ):
            results = orch.dispatch_and_wait(
                review_type="plan",
                dispatch_mode="review",
                prompt="Review this packet",
                cwd=tmp_path,
                timeout_seconds=15,
                packet_path=packet,
            )

        assert len(results) == 1
        assert results[0].success is True
        assert cwds[0] == tmp_path
        assert cwds[1] == snapshot
        mock_create.assert_called_once()
        assert mock_create.call_args.args[1] == "round-1"
        assert mock_create.call_args.args[2] == "codex"
        mock_destroy.assert_called_once()
        mock_destroy.assert_called_with(snapshot, tmp_path)

    def test_non_git_error_does_not_create_snapshot(self, tmp_path: Path) -> None:
        adapter = _adapter("codex-local", "codex")
        cwds: list[Path] = []

        def fake_dispatch(
            mode: str,
            prompt: str,
            cwd: Path,
            timeout_seconds: int = 300,
            **_kwargs: object,
        ) -> ReviewResult:
            cwds.append(Path(cwd))
            return ReviewResult(
                vendor="codex",
                success=False,
                error="401 UNAUTHENTICATED token expired",
                error_class=ErrorClass.AUTH,
            )

        orch = ReviewOrchestrator({"codex-local": adapter})
        with (
            patch("shutil.which", return_value="/usr/bin/codex"),
            patch.object(adapter, "dispatch", side_effect=fake_dispatch),
            patch("review_dispatcher.create_review_snapshot") as mock_create,
        ):
            results = orch.dispatch_and_wait(
                review_type="plan",
                dispatch_mode="review",
                prompt="review",
                cwd=tmp_path,
                timeout_seconds=15,
            )

        assert len(results) == 1
        assert results[0].success is False
        assert cwds == [tmp_path]
        mock_create.assert_not_called()

    def test_review_snapshot_path_layout(self, tmp_path: Path) -> None:
        with patch("review_dispatcher._main_repo_from_cwd", return_value=tmp_path):
            dest = review_snapshot_path(tmp_path, "round-1", "codex")
        assert dest == (
            tmp_path / ".git-worktrees" / ".review-snapshots" / "round-1" / "codex"
        )

    def test_create_review_snapshot_uses_detached_worktree(
        self, tmp_path: Path,
    ) -> None:
        dest = tmp_path / ".git-worktrees" / ".review-snapshots" / "round-1" / "codex"
        with (
            patch("review_dispatcher._main_repo_from_cwd", return_value=tmp_path),
            patch("review_dispatcher.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            result = create_review_snapshot(tmp_path, "round-1", "codex")
        assert result == dest
        cmd = mock_run.call_args.args[0]
        assert cmd[:4] == ["git", "worktree", "add", "--detach"]
        assert str(dest) in cmd
        assert "HEAD" in cmd


def test_dispatch_prefers_review_cwd_agents_yaml(
    tmp_path: Path,
) -> None:
    local = tmp_path / "agent-coordinator" / "agents.yaml"
    local.parent.mkdir()
    local.write_text("agents: {}\n")
    expected = ReviewOrchestrator({})

    with (
        patch.object(
            ReviewOrchestrator, "_find_local_agents_yaml", return_value=local
        ) as find_local,
        patch.object(
            ReviewOrchestrator, "from_agents_yaml", return_value=expected
        ) as from_local,
        patch.object(ReviewOrchestrator, "from_coordinator") as from_coordinator,
    ):
        actual = _orchestrator_for_dispatch(None, tmp_path)

    assert actual is expected
    find_local.assert_called_once_with(tmp_path)
    from_local.assert_called_once_with(local)
    from_coordinator.assert_not_called()


def test_dispatch_explicit_agents_yaml_bypasses_local_and_coordinator(
    tmp_path: Path,
) -> None:
    explicit = tmp_path / "explicit-agents.yaml"
    expected = ReviewOrchestrator({})

    with (
        patch.object(
            ReviewOrchestrator, "from_agents_yaml", return_value=expected
        ) as from_explicit,
        patch.object(
            ReviewOrchestrator, "_find_local_agents_yaml"
        ) as find_local,
        patch.object(ReviewOrchestrator, "from_coordinator") as from_coordinator,
    ):
        actual = _orchestrator_for_dispatch(str(explicit), tmp_path)

    assert actual is expected
    from_explicit.assert_called_once_with(explicit)
    find_local.assert_not_called()
    from_coordinator.assert_not_called()


def test_dispatch_without_local_config_falls_back_to_global_disk(
    tmp_path: Path,
) -> None:
    empty = ReviewOrchestrator({})
    expected = ReviewOrchestrator({})

    with (
        patch.object(
            ReviewOrchestrator, "_find_local_agents_yaml", return_value=None
        ),
        patch.object(
            ReviewOrchestrator, "from_coordinator", return_value=empty
        ) as from_coordinator,
        patch.object(
            ReviewOrchestrator, "from_agents_yaml", return_value=expected
        ) as from_global,
    ):
        actual = _orchestrator_for_dispatch(None, tmp_path)

    assert actual is expected
    from_coordinator.assert_called_once_with()
    from_global.assert_called_once_with()


def test_dispatch_preserves_sdk_only_coordinator_roster(
    tmp_path: Path,
) -> None:
    coordinator = ReviewOrchestrator({}, {"sdk-agent": object()})

    with (
        patch.object(
            ReviewOrchestrator, "_find_local_agents_yaml", return_value=None
        ),
        patch.object(
            ReviewOrchestrator, "from_coordinator", return_value=coordinator
        ),
        patch.object(ReviewOrchestrator, "from_agents_yaml") as from_disk,
    ):
        actual = _orchestrator_for_dispatch(None, tmp_path)

    assert actual is coordinator
    from_disk.assert_not_called()


def test_repo_antigravity_schema_review_uses_json_output_mode() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    orchestrator = ReviewOrchestrator.from_agents_yaml(
        repo_root / "agent-coordinator" / "agents.yaml"
    )
    adapter = orchestrator.adapters["antigravity-local"]

    command = adapter.build_command("review", "review", "gemini-3.8-flash-high")

    schema_index = command.index("--json-schema")
    output_index = command.index("--output-format")
    assert command[output_index + 1] == "json"
    assert output_index < schema_index
    schema = json.loads(command[schema_index + 1])
    assert schema["type"] == "object"
    assert command[command.index("--prompt") + 1] == "review"


@patch("review_dispatcher.subprocess.run")
def test_repo_antigravity_live_dispatch_pairs_json_mode_and_schema(
    mock_run: MagicMock, tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    orchestrator = ReviewOrchestrator.from_agents_yaml(
        repo_root / "agent-coordinator" / "agents.yaml"
    )
    adapter = orchestrator.adapters["antigravity-local"]
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=json.dumps({"response": VALID_FINDINGS_JSON}), stderr="",
    )

    result = adapter.dispatch(
        "review", "review this", cwd=tmp_path,
        archetype_model="gemini-3.8-flash-high",
    )

    assert result.success is True
    command = mock_run.call_args.args[0]
    output_index = command.index("--output-format")
    schema_index = command.index("--json-schema")
    assert command[output_index + 1] == "json"
    assert output_index < schema_index
    assert json.loads(command[schema_index + 1])["type"] == "object"


def test_review_result_preserves_exact_lane_and_capacity_metadata() -> None:
    result = ReviewResult(
        vendor="codex",
        success=False,
        agent_id="codex-local",
        error_class=ErrorClass.CAPACITY,
        capacity_scope="model",
        capacity_model="gpt-5.6",
        capacity_reset_at="2026-09-16T12:30:00Z",
        capacity_retry_after_seconds=120,
    )

    assert result.agent_id == "codex-local"
    assert result.capacity_scope == "model"
    assert result.capacity_model == "gpt-5.6"
    assert result.capacity_reset_at == "2026-09-16T12:30:00Z"
    assert result.capacity_retry_after_seconds == 120


def test_collect_reports_terminal_capacity_once_with_exact_lane(tmp_path: Path) -> None:
    adapter = _adapter("codex-local", "codex")
    terminal = ReviewResult(
        vendor="codex",
        success=False,
        error="429 capacity",
        error_class=ErrorClass.CAPACITY,
    )
    orchestrator = ReviewOrchestrator({"codex-local": adapter})

    with (
        patch("shutil.which", return_value="/usr/bin/codex"),
        patch.object(adapter, "dispatch", return_value=terminal),
        patch("review_dispatcher.report_vendor_limit_result", create=True) as report,
    ):
        results = orchestrator.dispatch_and_wait(
            review_type="plan",
            dispatch_mode="review",
            prompt="Review this packet",
            cwd=tmp_path,
        )

    assert results[0].agent_id == "codex-local"
    report.assert_called_once_with(results[0])


def test_model_capacity_callback_fires_before_successful_fallback(
    tmp_path: Path,
) -> None:
    adapter = _adapter(
        "codex-local",
        "codex",
        model="gpt-primary",
        model_fallbacks=["gpt-fallback"],
    )
    attempts = [
        MagicMock(returncode=1, stdout="", stderr="429 capacity"),
        MagicMock(returncode=0, stdout=VALID_FINDINGS_JSON, stderr=""),
    ]
    observations: list[ReviewResult] = []

    with patch("subprocess.run", side_effect=attempts):
        result = adapter.dispatch(
            "review",
            "Review this packet",
            tmp_path,
            capacity_callback=observations.append,
        )

    assert result.success is True
    assert len(observations) == 1
    assert observations[0].agent_id == "codex-local"
    assert observations[0].capacity_scope == "model"
    assert observations[0].capacity_model == "gpt-primary"


def test_capacity_reporting_failure_does_not_mask_successful_fallback(
    tmp_path: Path,
) -> None:
    adapter = _adapter(
        "codex-local",
        "codex",
        model="gpt-primary",
        model_fallbacks=["gpt-fallback"],
    )
    attempts = [
        MagicMock(returncode=1, stdout="", stderr="429 capacity"),
        MagicMock(returncode=0, stdout=VALID_FINDINGS_JSON, stderr=""),
    ]

    def broken_reporter(_result: ReviewResult) -> None:
        raise RuntimeError("coordinator unavailable")

    with patch("subprocess.run", side_effect=attempts):
        result = adapter.dispatch(
            "review",
            "Review this packet",
            tmp_path,
            capacity_callback=broken_reporter,
        )

    assert result.success is True
    assert result.model_used == "gpt-fallback"


def test_all_models_exhausted_reports_intermediate_models_and_terminal_lane_once(
    tmp_path: Path,
) -> None:
    adapter = _adapter(
        "codex-local",
        "codex",
        model="gpt-primary",
        model_fallbacks=["gpt-fallback"],
    )
    orchestrator = ReviewOrchestrator({"codex-local": adapter})

    with (
        patch("shutil.which", return_value="/usr/bin/codex"),
        patch(
            "subprocess.run",
            return_value=MagicMock(returncode=1, stdout="", stderr="429 capacity"),
        ),
        patch("review_dispatcher.report_vendor_limit_result") as report,
    ):
        results = orchestrator.dispatch_and_wait(
            review_type="plan",
            dispatch_mode="review",
            prompt="Review this packet",
            cwd=tmp_path,
        )

    assert results[0].error_class == ErrorClass.CAPACITY
    assert report.call_count == 2
    intermediate, terminal = [call.args[0] for call in report.call_args_list]
    assert intermediate.capacity_scope == "model"
    assert intermediate.capacity_model == "gpt-primary"
    assert terminal is results[0]
    assert terminal.capacity_scope is None


def test_single_model_exhaustion_is_reported_only_by_collector(
    tmp_path: Path,
) -> None:
    adapter = _adapter("codex-local", "codex", model="gpt-primary")
    orchestrator = ReviewOrchestrator({"codex-local": adapter})

    with (
        patch("shutil.which", return_value="/usr/bin/codex"),
        patch("review_dispatcher._derived_tier_fallbacks", return_value=[]),
        patch(
            "subprocess.run",
            return_value=MagicMock(returncode=1, stdout="", stderr="429 capacity"),
        ),
        patch("review_dispatcher.report_vendor_limit_result") as report,
    ):
        results = orchestrator.dispatch_and_wait(
            review_type="plan",
            dispatch_mode="review",
            prompt="Review this packet",
            cwd=tmp_path,
        )

    assert results[0].error_class == ErrorClass.CAPACITY
    report.assert_called_once_with(results[0])


def test_direct_registry_dispatch_shape_has_explicit_principal_and_scope(tmp_path: Path) -> None:
    registry = tmp_path / "agents.yaml"
    registry.write_text(
        "credential_vendors: [anthropic]\n"
        "agents:\n"
        "  claude-remote:\n"
        "    type: claude_code\n"
        "    api_key: ${CLAUDE_WEB_API_KEY}\n"
        "    vendor_credentials: [anthropic]\n"
        "    sdk: {package: anthropic, model: claude-test}\n"
        "  local:\n"
        "    type: local\n"
        "    endpoint_kind: local\n"
        "    base_url: http://localhost:11434/v1\n"
    )
    data = ReviewOrchestrator._config_from_agents_yaml(registry)
    assert data is not None
    by_id = {entry["agent_id"]: entry for entry in data["agents"]}
    assert by_id["claude-remote"]["principal_id"] == (
        "spiffe://coordinator.rotkohl.ai/agent/claude-remote"
    )
    assert by_id["claude-remote"]["vendor_credentials"] == ["anthropic"]
    assert by_id["local"]["principal_id"] is None
    assert by_id["local"]["vendor_credentials"] == []
    assert "openbao_role_id" not in by_id["claude-remote"]


def test_sdk_config_uses_principal_and_vendor_scope() -> None:
    orchestrator = ReviewOrchestrator.from_config_dict({
        "agents": [{
            "agent_id": "claude-remote", "type": "claude_code",
            "principal_id": "spiffe://coordinator.rotkohl.ai/agent/claude-remote",
            "vendor_credentials": ["anthropic"],
            "sdk": {"package": "anthropic", "model": "claude-test", "api_key_env": "ANTHROPIC_API_KEY"},
        }],
    })
    assert orchestrator.credential_requests["claude-remote"] == (
        "spiffe://coordinator.rotkohl.ai/agent/claude-remote", "anthropic"
    )
    assert orchestrator.credential_scopes[
        "spiffe://coordinator.rotkohl.ai/agent/claude-remote"
    ] == ("anthropic",)


def test_openrouter_config_uses_openrouter_vendor_id() -> None:
    orchestrator = ReviewOrchestrator.from_config_dict({
        "agents": [{
            "agent_id": "pi-local", "type": "pi",
            "principal_id": "spiffe://coordinator.rotkohl.ai/agent/pi-local",
            "vendor_credentials": ["openrouter"],
            "endpoint_kind": "openrouter", "base_url": "https://openrouter.ai/api/v1",
        }],
    })
    assert orchestrator.openai_credential_requests["pi-local"] == (
        "spiffe://coordinator.rotkohl.ai/agent/pi-local", "openrouter"
    )


def test_sdk_dispatch_resolves_scoped_principal_and_vendor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAO_ADDR", "http://localhost:8200")
    orchestrator = ReviewOrchestrator.from_config_dict({"agents": [{
        "agent_id": "claude-remote", "type": "claude_code",
        "principal_id": "spiffe://coordinator.rotkohl.ai/agent/claude-remote",
        "vendor_credentials": ["anthropic"],
        "sdk": {"package": "anthropic", "model": "claude-test"},
    }]})
    adapter = orchestrator.sdk_adapters["claude-remote"]
    adapter.can_dispatch = MagicMock(return_value=True)
    adapter.dispatch = MagicMock(return_value=ReviewResult(vendor="claude_code", success=True))
    with patch("api_key_resolver.ApiKeyResolver.resolve", return_value="bao-key") as resolve:
        results = orchestrator.dispatch_and_wait("implementation", "review", "review", tmp_path)
    assert results[0].success is True
    resolve.assert_called_once_with(
        "spiffe://coordinator.rotkohl.ai/agent/claude-remote", "anthropic"
    )
    assert adapter.dispatch.call_args.args[-1] == "bao-key"


def test_openai_dispatch_resolves_scoped_principal_and_vendor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAO_ADDR", "http://localhost:8200")
    orchestrator = ReviewOrchestrator.from_config_dict({"agents": [{
        "agent_id": "pi-local", "type": "pi",
        "principal_id": "spiffe://coordinator.rotkohl.ai/agent/pi-local",
        "vendor_credentials": ["openrouter"],
        "endpoint_kind": "openrouter", "base_url": "https://openrouter.ai/api/v1",
    }]})
    adapter = orchestrator.openai_adapters["pi-local"]
    adapter.can_dispatch = MagicMock(return_value=True)
    adapter.dispatch = MagicMock(return_value=ReviewResult(vendor="pi", success=True))
    with patch("api_key_resolver.ApiKeyResolver.resolve", return_value="bao-key") as resolve:
        results = orchestrator.dispatch_and_wait("implementation", "review", "review", tmp_path)
    assert results[0].success is True
    resolve.assert_called_once_with("spiffe://coordinator.rotkohl.ai/agent/pi-local", "openrouter")
    assert adapter.dispatch.call_args.args[-1] == "bao-key"


def test_configured_bao_keyless_local_endpoint_needs_no_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAO_ADDR", "http://localhost:8200")
    orchestrator = ReviewOrchestrator.from_config_dict({"agents": [{
        "agent_id": "local", "type": "local", "principal_id": None,
        "vendor_credentials": [], "endpoint_kind": "local",
        "base_url": "http://127.0.0.1:11434/v1",
    }]})
    adapter = orchestrator.openai_adapters["local"]
    adapter.dispatch = MagicMock(return_value=ReviewResult(vendor="local", success=True))
    with patch("api_key_resolver.ApiKeyResolver.resolve") as resolve:
        results = orchestrator.dispatch_and_wait("implementation", "review", "review", tmp_path)
    assert results[0].success is True
    resolve.assert_not_called()
    assert adapter.dispatch.call_args.args[-1] is None


def test_configured_bao_sdk_failure_is_sanitized_and_does_not_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from openbao_credentials import BaoCredentialError, ErrorCode

    monkeypatch.setenv("BAO_ADDR", "http://localhost:8200")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ambient-key")
    orchestrator = ReviewOrchestrator.from_config_dict({"agents": [{
        "agent_id": "claude-remote", "type": "claude_code",
        "principal_id": "spiffe://coordinator.rotkohl.ai/agent/claude-remote",
        "vendor_credentials": ["anthropic"],
        "sdk": {"package": "anthropic", "model": "claude-test", "api_key_env": "ANTHROPIC_API_KEY"},
    }]})
    adapter = orchestrator.sdk_adapters["claude-remote"]
    adapter.can_dispatch = MagicMock(return_value=True)
    adapter.dispatch = MagicMock()
    with patch(
        "api_key_resolver.ApiKeyResolver.resolve",
        side_effect=BaoCredentialError(ErrorCode.BACKEND_UNAVAILABLE),
    ):
        results = orchestrator.dispatch_and_wait("implementation", "review", "review", tmp_path)
    assert results[0].success is False
    assert results[0].error_class == ErrorClass.AUTH
    assert "BACKEND_UNAVAILABLE" in (results[0].error or "")
    assert "ambient-key" not in (results[0].error or "")
    adapter.dispatch.assert_not_called()


@pytest.mark.parametrize("agent", [
    "    api_key: ${KEY}\n    vendor_credentials: [unknown]\n",
    "    vendor_credentials: [anthropic]\n",
])
def test_direct_registry_rejects_invalid_vendor_scope(tmp_path: Path, agent: str) -> None:
    registry = tmp_path / "agents.yaml"
    registry.write_text(
        "credential_vendors: [anthropic]\n"
        "agents:\n"
        "  local:\n"
        "    type: local\n"
        "    endpoint_kind: local\n"
        "    base_url: http://localhost:11434/v1\n"
        f"{agent}"
    )
    assert ReviewOrchestrator._config_from_agents_yaml(registry) is None
