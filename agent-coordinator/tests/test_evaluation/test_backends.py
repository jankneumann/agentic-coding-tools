"""Tests for the evaluation agent backends (add-agy-grok-pi-harnesses task 2.6).

Covers the full first-class roster — Claude Code, Codex, antigravity, grok, pi —
plus the `build_backend` factory that makes the retired Gemini/Jules backend
absent (evaluation-framework: "requesting one SHALL raise a structured error
naming the supported roster").

The vendor-specific dispatch shapes and output parsers are exercised through
pure helpers (`_build_command`, `_stdin_input`, `_parse_envelope`,
`_parse_ndjson`) so the empirical Phase 1 contracts (E6/E7/E8) are asserted
without invoking the real CLIs.
"""

from __future__ import annotations

import json

import pytest

from evaluation.backends import (
    AntigravityBackend,
    ClaudeCodeBackend,
    CodexBackend,
    GrokBackend,
    PiBackend,
    UnknownBackendError,
    build_backend,
)
from evaluation.config import AgentBackendConfig


class TestBackendIdentity:
    def test_names(self) -> None:
        assert AntigravityBackend().name == "antigravity"
        assert GrokBackend().name == "grok"
        assert PiBackend().name == "pi"

    def test_default_commands(self) -> None:
        assert AntigravityBackend()._command == "agy"
        assert GrokBackend()._command == "grok"
        assert PiBackend()._command == "pi"


class TestBuildBackendFactory:
    """The factory is the pluggable-adapter seam for the roster migration."""

    @pytest.mark.parametrize(
        "name,cls",
        [
            ("claude_code", ClaudeCodeBackend),
            ("codex", CodexBackend),
            ("antigravity", AntigravityBackend),
            ("grok", GrokBackend),
            ("pi", PiBackend),
        ],
    )
    def test_builds_each_supported_backend(self, name: str, cls: type) -> None:
        cfg = AgentBackendConfig(name=name, command="x")
        backend = build_backend(cfg)
        assert isinstance(backend, cls)

    @pytest.mark.parametrize("retired", ["gemini_jules", "gemini", "jules"])
    def test_retired_gemini_jules_backend_is_absent(self, retired: str) -> None:
        cfg = AgentBackendConfig(name=retired, command="jules")
        with pytest.raises(UnknownBackendError) as exc_info:
            build_backend(cfg)
        # The structured error names the supported roster so an operator can
        # see what to migrate to.
        message = str(exc_info.value)
        assert retired in message
        for supported in ("antigravity", "grok", "pi", "claude_code", "codex"):
            assert supported in message

    def test_unknown_backend_raises_structured_error(self) -> None:
        cfg = AgentBackendConfig(name="does-not-exist", command="x")
        with pytest.raises(UnknownBackendError):
            build_backend(cfg)


class TestAntigravityDispatchShape:
    """E7: agy ignores stdin — the prompt is the VALUE of --prompt."""

    def test_prompt_attaches_to_flag_not_stdin(self) -> None:
        backend = AntigravityBackend(args=["--model", "gemini-3.6-flash-low"])
        cmd = backend._build_command("do the thing")
        assert cmd[0] == "agy"
        # prompt is the value immediately after --prompt, never a trailing
        # positional and never fed via stdin.
        assert "--prompt" in cmd
        assert cmd[cmd.index("--prompt") + 1] == "do the thing"
        assert cmd[-1] != "do the thing"
        assert backend._stdin_input("do the thing") is None


class TestGrokDispatchShape:
    """E2 + E6: prompt via stdin, JSON envelope via --output-format json."""

    def test_command_requests_json_and_reads_stdin(self) -> None:
        backend = GrokBackend()
        cmd = backend._build_command("review this")
        assert cmd[0] == "grok"
        assert "--output-format" in cmd
        assert cmd[cmd.index("--output-format") + 1] == "json"
        assert "--prompt-file" in cmd
        assert cmd[cmd.index("--prompt-file") + 1] == "/dev/stdin"
        # prompt is delivered on stdin, not on argv.
        assert backend._stdin_input("review this") == "review this"
        assert "review this" not in cmd

    def test_parse_envelope_reads_structured_output(self) -> None:
        envelope = {
            "structuredOutput": {"findings": [{"id": "F1", "severity": "high"}]},
            "usage": {
                "input_tokens": 120,
                "output_tokens": 45,
                "total_tokens": 165,
            },
        }
        output, usage = GrokBackend()._parse_envelope(json.dumps(envelope))
        # Structured payload is preserved (round-trips), not stdout-scraped.
        assert json.loads(output) == envelope["structuredOutput"]
        assert usage.input_tokens == 120
        assert usage.output_tokens == 45
        assert usage.total_tokens == 165

    def test_parse_envelope_falls_back_to_text_field(self) -> None:
        envelope = {"output": "plain text answer"}
        output, _ = GrokBackend()._parse_envelope(json.dumps(envelope))
        assert output == "plain text answer"

    def test_parse_envelope_rejects_non_json(self) -> None:
        with pytest.raises(ValueError):
            GrokBackend()._parse_envelope("not json at all")


class TestPiDispatchShape:
    """E3 + E8: --provider openrouter, trailing-positional prompt, NDJSON out."""

    def test_command_uses_openrouter_and_trailing_positional(self) -> None:
        backend = PiBackend()
        cmd = backend._build_command("solve it")
        assert cmd[0] == "pi"
        assert "--provider" in cmd
        assert cmd[cmd.index("--provider") + 1] == "openrouter"
        # E8: prompt is the trailing positional argument.
        assert cmd[-1] == "solve it"
        assert backend._stdin_input("solve it") is None

    def test_parse_ndjson_concatenates_assistant_text(self) -> None:
        events = [
            {"type": "message_start"},
            {
                "type": "agent_end",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Hello"},
                        {"type": "tool_use", "name": "edit"},
                        {"type": "text", "text": " world"},
                    ],
                },
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                },
            },
        ]
        stdout = "\n".join(json.dumps(e) for e in events) + "\n"
        output, usage = PiBackend()._parse_ndjson(stdout)
        assert output == "Hello world"
        assert usage.input_tokens == 10
        assert usage.total_tokens == 15

    def test_parse_ndjson_tolerates_blank_and_partial_lines(self) -> None:
        stdout = (
            "\n"
            + json.dumps(
                {
                    "type": "message_end",
                    "message": {
                        "content": [{"type": "text", "text": "answer"}]
                    },
                }
            )
            + "\n"
            + "{ this is not valid json\n"  # a truncated trailing line
        )
        output, _ = PiBackend()._parse_ndjson(stdout)
        assert output == "answer"
