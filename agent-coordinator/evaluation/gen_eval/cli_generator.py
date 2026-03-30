"""CLI-based scenario generator.

Builds prompts from descriptor + templates + feedback, executes via
``claude --print`` or ``codex`` subprocess, and parses YAML output
into Scenario objects. Implements the ScenarioGenerator protocol.
"""

from __future__ import annotations

import asyncio
import logging
import textwrap
from typing import Any

import yaml
from pydantic import ValidationError

from .config import GenEvalConfig
from .descriptor import InterfaceDescriptor
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
        cmd_args = [self.command, *self.args]
        if system:
            # Prepend system instruction to prompt
            full_prompt = f"[System]: {system}\n\n{prompt}"
        else:
            full_prompt = prompt

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(full_prompt.encode()),
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


class CLIGenerator:
    """Generates scenarios by prompting an LLM via CLI subprocess.

    Builds a structured prompt from the interface descriptor, existing
    templates, and evaluation feedback, then executes via CLIBackend
    and parses YAML output into validated Scenario objects.

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

    def _build_system_prompt(self) -> str:
        return textwrap.dedent("""\
            You are a test scenario generator. Output ONLY valid YAML — a list
            of scenario objects. No markdown fences, no commentary.
            Each scenario must have: id, name, description, category, interfaces,
            steps (each with id, transport, and transport-specific fields).
            Set generated_by to "llm".""")

    def _build_prompt(self, focus_areas: list[str] | None, count: int) -> str:
        parts: list[str] = []
        parts.append(f"Generate {count} test scenarios for: {self.descriptor.project}")
        parts.append(f"\nInterfaces:\n{self._format_interfaces()}")

        if focus_areas:
            parts.append(f"\nFocus on: {', '.join(focus_areas)}")

        if self.feedback:
            parts.append(self._format_feedback())

        return "\n".join(parts)

    def _format_interfaces(self) -> str:
        lines: list[str] = []
        for iface in self.descriptor.all_interfaces():
            lines.append(f"  - {iface}")
        return "\n".join(lines) or "  (none)"

    def _format_feedback(self) -> str:
        if not self.feedback:
            return ""
        parts: list[str] = ["\nPrevious evaluation feedback:"]
        if self.feedback.failing_interfaces:
            parts.append(f"  Failing: {', '.join(self.feedback.failing_interfaces)}")
        if self.feedback.under_tested_categories:
            parts.append(f"  Under-tested: {', '.join(self.feedback.under_tested_categories)}")
        if self.feedback.suggested_focus:
            parts.append(f"  Focus on: {', '.join(self.feedback.suggested_focus)}")
        return "\n".join(parts)

    def _parse_output(self, raw: str) -> list[Scenario]:
        """Parse YAML output from LLM into validated Scenario objects."""
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            logger.warning("Failed to parse LLM YAML output: %s", e)
            return []

        if data is None:
            return []

        items: list[dict[str, Any]] = data if isinstance(data, list) else [data]
        scenarios: list[Scenario] = []
        for item in items:
            try:
                # Force generated_by to "llm"
                item["generated_by"] = "llm"
                scenarios.append(Scenario(**item))
            except (ValidationError, TypeError) as e:
                logger.warning("Invalid LLM scenario %s: %s", item.get("id", "?"), e)

        return scenarios
