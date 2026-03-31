"""CLI-based scenario generator.

Builds prompts from descriptor + templates + feedback, executes via
``claude --print`` or ``codex`` subprocess, and parses YAML output
into Scenario objects. Implements the ScenarioGenerator protocol.
"""

from __future__ import annotations

import asyncio
import logging

from .config import GenEvalConfig
from .descriptor import InterfaceDescriptor
from .llm_generator_base import LLMGeneratorMixin
from .models import EvalFeedback, Scenario

logger = logging.getLogger(__name__)


class CLIBackend:
    """Subprocess wrapper for CLI-based LLM execution (subscription-covered).

    Wraps ``claude --print``, ``codex``, or similar CLI tools that accept
    a prompt on stdin/args and return text output.
    """

    def __init__(
        self,
        command: str = "claude",
        args: list[str] | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.command = command
        self.args = args or ["--print"]
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return f"cli:{self.command}"

    @property
    def is_subscription_covered(self) -> bool:
        return True

    async def is_available(self) -> bool:
        """Check if the CLI command exists on PATH."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "which",
                self.command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        except (OSError, FileNotFoundError):
            return False

    async def run(self, prompt: str, system: str | None = None) -> str:
        """Execute the CLI tool with the given prompt.

        Returns:
            stdout text from the CLI process.

        Raises:
            CLIBackendError: On non-zero exit code or timeout.
        """
        if system:
            # Prepend system instruction to prompt
            full_prompt = f"[System]: {system}\n\n{prompt}"
        else:
            full_prompt = prompt

        cmd = [self.command, *self.args, full_prompt]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as e:
            raise CLIBackendError(
                f"CLI command timed out after {self.timeout_seconds}s",
                exit_code=-1,
                stderr="timeout",
            ) from e
        except (OSError, FileNotFoundError) as e:
            raise CLIBackendError(
                f"Failed to execute {self.command}: {e}",
                exit_code=-1,
                stderr=str(e),
            ) from e

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            raise CLIBackendError(
                f"CLI exited with code {proc.returncode}",
                exit_code=proc.returncode or -1,
                stderr=stderr_text,
            )

        return stdout_text


class CLIBackendError(Exception):
    """Raised when a CLI backend call fails."""

    def __init__(self, message: str, exit_code: int, stderr: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


class CLIGenerator(LLMGeneratorMixin):
    """Generates scenarios by prompting an LLM via CLI subprocess.

    Builds a structured prompt from the interface descriptor, existing
    templates, and evaluation feedback, then executes via CLIBackend
    and parses YAML output into validated Scenario objects.

    Prompt building and output parsing are inherited from LLMGeneratorMixin.

    Implements the ScenarioGenerator protocol.
    """

    def __init__(
        self,
        descriptor: InterfaceDescriptor,
        config: GenEvalConfig,
        backend: CLIBackend | None = None,
        feedback: EvalFeedback | None = None,
    ) -> None:
        self.descriptor = descriptor
        self.config = config
        self.backend = backend or CLIBackend(
            command=config.cli_command,
            args=config.cli_args,
        )
        self.feedback = feedback

    async def generate(
        self,
        focus_areas: list[str] | None = None,
        count: int = 10,
    ) -> list[Scenario]:
        """Generate scenarios via CLI LLM call."""
        prompt = self._build_prompt(focus_areas, count)
        system = self._build_system_prompt()

        try:
            raw_output = await self.backend.run(prompt, system=system)
        except CLIBackendError:
            logger.exception("CLI generation failed")
            raise

        return self._parse_output(raw_output)
