"""Grok (xAI) agent backend for evaluation.

Executes tasks via the `grok` CLI (xAI subscription, never OpenRouter) and reads
a structured JSON envelope rather than scraping stdout.

Empirical Phase 1 findings (design.md § Empirical CLI findings):
- E2: the prompt is delivered on stdin via ``--prompt-file /dev/stdin``.
- E6: ``--output-format json`` emits an envelope whose conforming payload lives
  under ``.structuredOutput``; token usage, when present, is under ``.usage``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from ..config import AblationFlags, AgentBackendConfig
from ..metrics import TokenUsage
from .base import BackendResult

_SKILLS_ROOT = Path(__file__).resolve().parents[3] / "skills"
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))
from shared.sandbox_activation import (  # noqa: E402
    resolve_activation_context,
    resolve_requested_isolation,
)
from shared.vendor_process_surfaces import (  # noqa: E402
    VendorProcessInvocation,
    run_vendor_process_async,
)

_AGENT_ID = "grok-local"
_DISPATCH_MODE = "alternative"


class GrokBackend:
    """Backend that executes tasks via the `grok` CLI with JSON output."""

    def __init__(
        self,
        command: str = "grok",
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
        return "grok"

    def _build_command(self, prompt: str) -> list[str]:
        """Argv requesting a JSON envelope, prompt fed on stdin (E2/E6)."""
        return [
            self._command,
            "--prompt-file",
            "/dev/stdin",
            "--output-format",
            "json",
            *self._args,
        ]

    def _stdin_input(self, prompt: str) -> str | None:
        """`grok` reads the prompt from stdin (`--prompt-file /dev/stdin`)."""
        return prompt

    @staticmethod
    def _extract_usage(envelope: dict[str, Any]) -> TokenUsage:
        usage = envelope.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
        output_tokens = int(
            usage.get("output_tokens", usage.get("completion_tokens", 0))
        )
        total = int(usage.get("total_tokens", input_tokens + output_tokens))
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
        )

    def _parse_envelope(self, stdout: str) -> tuple[str, TokenUsage]:
        """Parse the ``--output-format json`` envelope (E6).

        The structured result lives under ``.structuredOutput``; if absent, fall
        back to a plain text field. Raises ``ValueError`` on non-JSON output so
        the caller can surface a parse failure rather than silently succeeding.
        """
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"grok did not emit a JSON envelope: {exc}"
            ) from exc

        if not isinstance(envelope, dict):
            raise ValueError("grok JSON envelope is not an object")

        if "structuredOutput" in envelope:
            output = json.dumps(envelope["structuredOutput"])
        else:
            output = str(
                envelope.get("output")
                or envelope.get("text")
                or envelope.get("content")
                or ""
            )
        return output, self._extract_usage(envelope)

    async def execute_task(
        self,
        task_description: str,
        affected_files: list[str],
        working_dir: str,
        ablation: AblationFlags,
        timeout_seconds: int = 300,
    ) -> BackendResult:
        """Execute a task via the `grok` CLI and parse the JSON envelope."""
        timeout = timeout_seconds if timeout_seconds is not None else self._timeout
        start_time = time.time()

        files_context = "\n".join(f"- {f}" for f in affected_files)
        prompt = f"{task_description}\n\nFiles to work on:\n{files_context}"

        cmd = self._build_command(prompt)

        try:
            env = {**os.environ, **self._env}
            worktree_root = Path(working_dir)
            isolation = resolve_requested_isolation(
                _AGENT_ID, _DISPATCH_MODE, worktree_root=worktree_root,
            )
            activation_context = (
                resolve_activation_context(
                    agent_id=_AGENT_ID,
                    dispatch_mode=_DISPATCH_MODE,
                    model="evaluation-default",
                    worktree_root=worktree_root,
                )
                if isolation == "sandbox"
                else None
            )
            result = await run_vendor_process_async(VendorProcessInvocation(
                surface="evaluation_grok",
                argv=tuple(cmd),
                cwd=worktree_root,
                env=env,
                timeout_seconds=timeout,
                isolation=isolation,
                stdin_text=self._stdin_input(prompt),
                activation_context=activation_context,
            ))
            wall_clock = time.time() - start_time
            if result.timed_out:
                raise TimeoutError
            raw = result.stdout
            err_output = result.stderr

            if result.returncode != 0:
                return BackendResult(
                    success=False,
                    output=raw,
                    wall_clock_seconds=wall_clock,
                    error=err_output or f"grok exited {result.returncode}",
                )

            try:
                output, usage = self._parse_envelope(raw)
            except ValueError as exc:
                return BackendResult(
                    success=False,
                    output=raw,
                    wall_clock_seconds=wall_clock,
                    error=str(exc),
                )

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
        """Check if the `grok` CLI is available."""
        return shutil.which(self._command) is not None

    @classmethod
    def from_config(cls, config: AgentBackendConfig) -> GrokBackend:
        return cls(
            command=config.command,
            args=config.args,
            env=config.env,
            timeout_seconds=config.timeout_seconds,
        )
