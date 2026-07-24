"""pi agent backend for evaluation.

Executes tasks via the `pi` CLI against OpenRouter models (the harness that
reaches models outside the subscription CLIs, e.g. Kimi 3, Qwen3-Coder).

Empirical Phase 1 findings (design.md § Empirical CLI findings):
- E3: `pi` resolves ``OPENROUTER_API_KEY`` from the subprocess environment.
- E8: the prompt is a trailing positional argument; ``--mode json`` emits an
  NDJSON event stream (not a single envelope). Each message is its own
  ``message_end`` event carrying a ``role`` — ``pi`` echoes the prompt back as a
  ``role: "user"`` message, and the answer is the LAST ``role: "assistant"``
  message's ``content[]`` items where ``type == "text"`` (verified against a live
  ``pi --mode json`` transcript on 2026-07-24; see coordinator issue 035ffd93).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from typing import Any

from ..config import AblationFlags, AgentBackendConfig
from ..metrics import TokenUsage
from .base import BackendResult

# NDJSON events that carry the terminal assistant message (E8).
_TERMINAL_EVENTS = {"agent_end", "message_end"}


def _coerce_int(value: Any) -> int:
    """Best-effort int from an arbitrary JSON value (0 for non-numeric)."""
    return int(value) if isinstance(value, (int, float)) else 0


class PiBackend:
    """Backend that executes tasks via the `pi` CLI (OpenRouter, NDJSON)."""

    def __init__(
        self,
        command: str = "pi",
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        self._command = command
        self._args = args or []
        self._env = env or {}
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return "pi"

    def _build_command(self, prompt: str) -> list[str]:
        """Argv: OpenRouter provider, NDJSON mode, trailing-positional prompt (E8)."""
        return [
            self._command,
            "--provider",
            "openrouter",
            "--mode",
            "json",
            *self._args,
            prompt,
        ]

    def _stdin_input(self, prompt: str) -> str | None:
        """`pi` takes the prompt as a positional argument, not stdin (E8)."""
        return None

    @staticmethod
    def _assistant_message_texts(event: dict[str, Any]) -> list[str] | None:
        """Text items from a terminal event's assistant message ``content[]``.

        Returns ``None`` when the event is NOT an assistant message and must be
        ignored for answer extraction — most importantly the ``role: "user"``
        ``message_end`` in which ``pi`` echoes the prompt back (E8, verified
        against a live ``pi --mode json`` transcript on 2026-07-24). A message
        carrying no ``role`` at all is treated as in-scope for tolerance of
        older/edge shapes.
        """
        message = event.get("message")
        if isinstance(message, dict):
            if message.get("role") not in (None, "assistant"):
                return None
            content = message.get("content")
        else:
            content = event.get("content")
        if not isinstance(content, list):
            return None
        return [
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]

    def _parse_ndjson(self, stdout: str) -> tuple[str, TokenUsage]:
        """Stream-parse the NDJSON event log (E8).

        Takes the text content of the LAST assistant terminal event (the final
        answer) and sums any usage carried on events. Earlier assistant messages
        and the echoed ``role: "user"`` prompt are excluded — ``pi`` emits one
        ``message_end`` per message, so concatenating all of them would fold the
        prompt echo and intermediate turns into the result (bug fixed 2026-07-24,
        coordinator issue 035ffd93, after a live ``pi`` transcript disproved the
        earlier single-``agent_end`` assumption). Blank lines and a truncated
        trailing line are tolerated — the stream may be cut off without
        invalidating earlier events.
        """
        texts: list[str] = []
        input_tokens = output_tokens = total_tokens = 0

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # A partial/truncated line (common at stream end) — skip it.
                continue
            if not isinstance(event, dict):
                continue

            if event.get("type") in _TERMINAL_EVENTS:
                message_texts = self._assistant_message_texts(event)
                # Last assistant terminal message wins (the final answer); a
                # non-assistant message (e.g. the user echo) returns None → skip.
                if message_texts:
                    texts = message_texts

            usage = event.get("usage")
            if isinstance(usage, dict):
                input_tokens += _coerce_int(usage.get("input_tokens")) or _coerce_int(
                    usage.get("prompt_tokens")
                )
                output_tokens += _coerce_int(
                    usage.get("output_tokens")
                ) or _coerce_int(usage.get("completion_tokens"))
                total_tokens += _coerce_int(usage.get("total_tokens"))

        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens

        usage_obj = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )
        return "".join(texts), usage_obj

    async def execute_task(
        self,
        task_description: str,
        affected_files: list[str],
        working_dir: str,
        ablation: AblationFlags,
        timeout_seconds: int = 300,
    ) -> BackendResult:
        """Execute a task via the `pi` CLI and stream-parse the NDJSON output."""
        timeout = timeout_seconds if timeout_seconds is not None else self._timeout
        start_time = time.time()

        files_context = "\n".join(f"- {f}" for f in affected_files)
        prompt = f"{task_description}\n\nFiles to work on:\n{files_context}"

        cmd = self._build_command(prompt)

        try:
            env = {**os.environ, **self._env}
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            wall_clock = time.time() - start_time

            raw = stdout.decode("utf-8", errors="replace")
            err_output = stderr.decode("utf-8", errors="replace")

            if process.returncode != 0:
                return BackendResult(
                    success=False,
                    output=raw,
                    wall_clock_seconds=wall_clock,
                    error=err_output or f"pi exited {process.returncode}",
                )

            output, usage = self._parse_ndjson(raw)
            return BackendResult(
                success=True,
                output=output,
                wall_clock_seconds=wall_clock,
                token_usage=usage,
            )
        except TimeoutError:
            return BackendResult(
                success=False,
                wall_clock_seconds=time.time() - start_time,
                error=f"Timeout after {timeout}s",
            )
        except FileNotFoundError:
            return BackendResult(
                success=False,
                error=f"Command not found: {self._command}",
            )

    async def health_check(self) -> bool:
        """Check if the `pi` CLI is available."""
        return shutil.which(self._command) is not None

    @classmethod
    def from_config(cls, config: AgentBackendConfig) -> PiBackend:
        return cls(
            command=config.command,
            args=config.args,
            env=config.env,
            timeout_seconds=config.timeout_seconds,
        )
