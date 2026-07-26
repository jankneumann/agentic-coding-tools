"""Antigravity (agy) agent backend for evaluation.

Executes tasks via the Antigravity CLI (`agy`) in headless mode. Antigravity is
Google's agentic harness and runs the Gemini model family; the CLI is
Claude-shaped, emitting plain markdown/text to stdout.

Empirical Phase 1 finding E7 (design.md § Empirical CLI findings): `agy` ignores
stdin and a trailing positional — the prompt must be the VALUE of ``--prompt``
(``-p``). This backend therefore attaches the prompt to the flag, unlike the
stdin/positional shapes used by grok and pi.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time

from ..config import AblationFlags, AgentBackendConfig
from ..metrics import TokenUsage
from .base import BackendResult


class AntigravityBackend:
    """Backend that executes tasks via the Antigravity (`agy`) CLI."""

    def __init__(
        self,
        command: str = "agy",
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
        return "antigravity"

    def _build_command(self, prompt: str) -> list[str]:
        """Argv for a headless run (E7: prompt is the value of ``--prompt``)."""
        return [self._command, "--prompt", prompt, *self._args]

    def _stdin_input(self, prompt: str) -> str | None:
        """`agy` reads the prompt from the flag, never stdin (E7)."""
        return None

    async def execute_task(
        self,
        task_description: str,
        affected_files: list[str],
        working_dir: str,
        ablation: AblationFlags,
        timeout_seconds: int = 300,
    ) -> BackendResult:
        """Execute a task via the `agy` CLI."""
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

            output = stdout.decode("utf-8", errors="replace")
            err_output = stderr.decode("utf-8", errors="replace")

            return BackendResult(
                success=process.returncode == 0,
                output=output,
                wall_clock_seconds=wall_clock,
                token_usage=TokenUsage(),  # agy CLI does not report tokens
                error=err_output if process.returncode != 0 else None,
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
        """Check if the `agy` CLI is available."""
        return shutil.which(self._command) is not None

    @classmethod
    def from_config(cls, config: AgentBackendConfig) -> AntigravityBackend:
        return cls(
            command=config.command,
            args=config.args,
            env=config.env,
            timeout_seconds=config.timeout_seconds,
        )
