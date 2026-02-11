"""Claude Code agent backend for evaluation.

Executes tasks via the Claude Code CLI (`claude` command)
and captures output, timing, and token usage.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time

from ..config import AblationFlags, AgentBackendConfig
from ..metrics import TokenUsage
from .base import BackendResult


class ClaudeCodeBackend:
    """Backend that executes tasks via Claude Code CLI."""

    def __init__(
        self,
        command: str = "claude",
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
        return "claude_code"

    async def execute_task(
        self,
        task_description: str,
        affected_files: list[str],
        working_dir: str,
        ablation: AblationFlags,
        timeout_seconds: int = 300,
    ) -> BackendResult:
        """Execute a task via claude CLI with --print flag."""
        timeout = timeout_seconds if timeout_seconds is not None else self._timeout
        start_time = time.time()

        # Build the prompt with file context
        files_context = "\n".join(f"- {f}" for f in affected_files)
        prompt = f"""{task_description}

Files to work on:
{files_context}

Coordination config:
- Locking: {"enabled" if ablation.locking else "disabled"}
- Memory: {"enabled" if ablation.memory else "disabled"}
- Parallelization: {"enabled" if ablation.parallelization else "disabled"}
"""

        cmd = [self._command, "--print", *self._args, prompt]

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
                token_usage=TokenUsage(),  # CLI doesn't report tokens directly
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
        """Check if claude CLI is available."""
        return shutil.which(self._command) is not None

    @classmethod
    def from_config(cls, config: AgentBackendConfig) -> ClaudeCodeBackend:
        return cls(
            command=config.command,
            args=config.args,
            env=config.env,
            timeout_seconds=config.timeout_seconds,
        )
