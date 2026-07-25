"""CLI transport client using subprocess execution."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from gen_eval.models import ActionStep

from .base import StepContext, StepResult


class CliClient:
    """Execute CLI commands as subprocesses with JSON output parsing."""

    def __init__(
        self,
        command: str,
        json_flag: str | None = None,
        default_timeout: float = 30.0,
    ) -> None:
        self._command = command
        self._json_flag = json_flag
        self._default_timeout = default_timeout

    # ------------------------------------------------------------------
    # TransportClient protocol
    # ------------------------------------------------------------------

    async def execute(self, step: ActionStep, context: StepContext) -> StepResult:
        """Run the CLI command described by *step*."""
        start = time.perf_counter()
        try:
            # Build command line
            parts: list[str] = [self._command]
            if step.command:
                parts.append(step.command)
            if step.args:
                for arg in step.args:
                    # Variable interpolation
                    for var_key, var_val in context.variables.items():
                        arg = arg.replace(f"${{{var_key}}}", str(var_val))
                    parts.append(arg)
            if self._json_flag:
                parts.extend(self._json_flag.split())

            timeout = step.timeout_seconds or context.timeout_seconds

            proc = await asyncio.create_subprocess_exec(
                *parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            exit_code = proc.returncode or 0
            raw_out = stdout.decode("utf-8", errors="replace").strip()
            raw_err = stderr.decode("utf-8", errors="replace").strip()

            # Try parsing JSON from stdout
            body: dict[str, Any] = {}
            if raw_out:
                try:
                    parsed = json.loads(raw_out)
                    body = parsed if isinstance(parsed, dict) else {"result": parsed}
                except json.JSONDecodeError:
                    body = {"raw": raw_out}

            # stderr is *data*, not a failure signal.
            #
            # It used to be assigned to StepResult.error, and the evaluator
            # short-circuits to status="error" on any result.error before it
            # compares expectations. That made every well-behaved CLI — one
            # that prints diagnostics to stderr — an unconditional error
            # regardless of its exit code, so `expect.exit_code` could never
            # assert a failure path and `expect.error_contains` was
            # unreachable on this transport. Both fields exist precisely to
            # assert failures.
            #
            # The process ran; whatever it exited with is the verdict's
            # business. Surfacing stderr in the body keeps it assertable —
            # `error_contains` already searches str(body) — while reserving
            # `error` for the exception path below, where the command could
            # not be executed at all.
            if raw_err:
                body["stderr"] = raw_err

            elapsed = (time.perf_counter() - start) * 1000
            return StepResult(
                body=body,
                exit_code=exit_code,
                error=None,
                duration_ms=elapsed,
            )
        except TimeoutError:
            elapsed = (time.perf_counter() - start) * 1000
            return StepResult(error="Command timed out", duration_ms=elapsed)
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return StepResult(error=str(exc), duration_ms=elapsed)

    async def health_check(self) -> bool:
        """Check that the CLI binary is callable."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._command,
                "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return proc.returncode == 0
        except Exception:
            return False

    async def cleanup(self) -> None:
        """No persistent resources to release."""
