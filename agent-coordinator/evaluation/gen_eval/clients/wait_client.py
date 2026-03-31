"""Wait transport client -- simple asyncio.sleep for timing scenarios."""

from __future__ import annotations

import asyncio
import time

from evaluation.gen_eval.models import ActionStep

from .base import StepContext, StepResult


class WaitClient:
    """Pause execution for a specified number of seconds."""

    async def execute(self, step: ActionStep, context: StepContext) -> StepResult:
        """Sleep for ``step.seconds`` (default 1.0)."""
        seconds = step.seconds if step.seconds is not None else 1.0
        start = time.perf_counter()
        try:
            await asyncio.wait_for(asyncio.sleep(seconds), timeout=context.timeout_seconds)
        except TimeoutError:
            elapsed = (time.perf_counter() - start) * 1000
            return StepResult(
                error=f"Wait of {seconds}s exceeded step timeout of {context.timeout_seconds}s",
                duration_ms=elapsed,
            )
        elapsed = (time.perf_counter() - start) * 1000
        return StepResult(
            body={"waited_seconds": seconds},
            duration_ms=elapsed,
        )

    async def health_check(self) -> bool:
        """Always healthy -- no external dependency."""
        return True

    async def cleanup(self) -> None:
        """Nothing to clean up."""
