"""Gemini/Jules agent backend for evaluation.

Executes tasks via the Gemini/Jules CLI and captures results.
"""

from __future__ import annotations

import asyncio
import shutil
import time

from ..config import AblationFlags, AgentBackendConfig
from ..metrics import TokenUsage
from .base import BackendResult


class GeminiJulesBackend:
    """Backend that executes tasks via Gemini/Jules CLI."""

    def __init__(
        self,
        command: str = "jules",
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
        return "gemini_jules"

    async def execute_task(
        self,
        task_description: str,
        affected_files: list[str],
        working_dir: str,
        ablation: AblationFlags,
        timeout_seconds: int = 300,
    ) -> BackendResult:
        """Execute a task via jules CLI."""
        timeout = timeout_seconds or self._timeout
        start_time = time.time()

        files_context = "\n".join(f"- {f}" for f in affected_files)
        prompt = f"{task_description}\n\nFiles to work on:\n{files_context}"

        cmd = [self._command, *self._args, prompt]

        try:
            import os
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
                token_usage=TokenUsage(),
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
        """Check if jules CLI is available."""
        return shutil.which(self._command) is not None

    @classmethod
    def from_config(cls, config: AgentBackendConfig) -> GeminiJulesBackend:
        return cls(
            command=config.command,
            args=config.args,
            env=config.env,
            timeout_seconds=config.timeout_seconds,
        )
