"""Claude Code agent backend for evaluation.

Executes tasks via the Claude Code CLI (`claude` command)
and captures output, timing, and token usage.
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
from shared.sandbox_activation import (  # noqa: E402
    resolve_activation_context,
    resolve_requested_isolation,
)
from shared.vendor_process_surfaces import (  # noqa: E402
    VendorProcessInvocation,
    run_vendor_process_async,
)

_AGENT_ID = "claude-local"
_DISPATCH_MODE = "alternative"


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
                surface="evaluation_claude_code",
                argv=tuple(cmd),
                cwd=worktree_root,
                env=env,
                timeout_seconds=timeout,
                isolation=isolation,
                activation_context=activation_context,
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
                token_usage=TokenUsage(),  # CLI doesn't report tokens directly
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
