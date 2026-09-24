"""Codex agent backend for evaluation.

Executes tasks via the Codex CLI and captures results.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

from ..config import AblationFlags, AgentBackendConfig
from ..metrics import TokenUsage
from .base import BackendResult

_SKILLS_ROOT = Path(__file__).resolve().parents[3] / "skills"
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))
from shared.vendor_process_surfaces import (  # noqa: E402
    VendorProcessInvocation,
    run_vendor_process_async,
)


class CodexBackend:
    """Backend that executes tasks via Codex CLI."""

    def __init__(
        self,
        command: str = "codex",
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
        return "codex"

    async def execute_task(
        self,
        task_description: str,
        affected_files: list[str],
        working_dir: str,
        ablation: AblationFlags,
        timeout_seconds: int = 300,
    ) -> BackendResult:
        """Execute a task via codex CLI."""
        timeout = timeout_seconds if timeout_seconds is not None else self._timeout
        start_time = time.time()

        files_context = "\n".join(f"- {f}" for f in affected_files)
        prompt = f"{task_description}\n\nFiles to work on:\n{files_context}"

        cmd = [self._command, *self._args, prompt]

        try:
            env = {**os.environ, **self._env}
            result = await run_vendor_process_async(VendorProcessInvocation(
                surface="evaluation_codex",
                argv=tuple(cmd),
                cwd=Path(working_dir),
                env=env,
                timeout_seconds=timeout,
                isolation="none",
            ))
            wall_clock = time.time() - start_time
            if result.timed_out:
                raise TimeoutError
            output = result.stdout
            err_output = result.stderr

            return BackendResult(
                success=result.returncode == 0,
                output=output,
                wall_clock_seconds=wall_clock,
                token_usage=TokenUsage(),
                error=err_output if result.returncode != 0 else None,
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
        """Check if codex CLI is available."""
        return shutil.which(self._command) is not None

    @classmethod
    def from_config(cls, config: AgentBackendConfig) -> CodexBackend:
        return cls(
            command=config.command,
            args=config.args,
            env=config.env,
            timeout_seconds=config.timeout_seconds,
        )
