"""SDK-based scenario generator.

Same generation logic as CLIGenerator but uses Anthropic/OpenAI SDK
directly. Implements the ScenarioGenerator protocol.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from .config import GenEvalConfig
from .descriptor import InterfaceDescriptor
from .models import EvalFeedback, Scenario

logger = logging.getLogger(__name__)


class SDKBackend:
    """Direct SDK-based LLM execution (per-token cost).

    Supports Anthropic and OpenAI SDKs.
    """

    def __init__(
        self,
        provider: Literal["anthropic", "openai"] = "anthropic",
        model: str = "claude-sonnet-4-6",
        api_key_env: str = "ANTHROPIC_API_KEY",
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key_env = api_key_env

    @property
    def name(self) -> str:
        return f"sdk:{self.provider}/{self.model}"

    @property
    def is_subscription_covered(self) -> bool:
        return False

    async def is_available(self) -> bool:
        """Check if the API key environment variable is set."""
        return bool(os.environ.get(self.api_key_env))

    async def run(self, prompt: str, system: str | None = None) -> str:
        """Execute via the appropriate SDK.

        Raises:
            SDKBackendError: On API failure or missing dependencies.
        """
        if self.provider == "anthropic":
            return await self._run_anthropic(prompt, system)
        elif self.provider == "openai":
            return await self._run_openai(prompt, system)
        else:
            raise SDKBackendError(f"Unsupported provider: {self.provider}")

    async def _run_anthropic(self, prompt: str, system: str | None) -> str:
        try:
            import anthropic
        except ImportError as e:
            raise SDKBackendError(
                "anthropic package not installed. Install with: pip install anthropic"
            ) from e

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise SDKBackendError(f"API key not found in {self.api_key_env}")

        try:
            client = anthropic.AsyncAnthropic(api_key=api_key)
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            response = await client.messages.create(**kwargs)
            # Extract text from response
            return response.content[0].text  # type: ignore[union-attr]
        except Exception as e:
            raise SDKBackendError(f"Anthropic API error: {e}") from e

    async def _run_openai(self, prompt: str, system: str | None) -> str:
        try:
            import openai
        except ImportError as e:
            raise SDKBackendError(
                "openai package not installed. Install with: pip install openai"
            ) from e

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise SDKBackendError(f"API key not found in {self.api_key_env}")

        try:
            client = openai.AsyncOpenAI(api_key=api_key)
            messages: list[dict[str, str]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=4096,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise SDKBackendError(f"OpenAI API error: {e}") from e


class SDKBackendError(Exception):
    """Raised when an SDK backend call fails."""


class SDKGenerator:
    """Generates scenarios via direct SDK calls.

    Uses the same prompt-building and parsing logic as CLIGenerator,
    but sends requests through the Anthropic/OpenAI SDK instead of
    a CLI subprocess.

    Implements the ScenarioGenerator protocol.
    """

    def __init__(
        self,
        descriptor: InterfaceDescriptor,
        config: GenEvalConfig,
        backend: SDKBackend | None = None,
        feedback: EvalFeedback | None = None,
    ) -> None:
        self.descriptor = descriptor
        self.config = config
        self.backend = backend or SDKBackend(
            provider=config.sdk_provider,  # type: ignore[arg-type]
            model=config.sdk_model,
            api_key_env=config.sdk_api_key_env,
        )
        self.feedback = feedback

    async def generate(
        self,
        focus_areas: list[str] | None = None,
        count: int = 10,
    ) -> list[Scenario]:
        """Generate scenarios via SDK LLM call."""
        prompt = self._build_prompt(focus_areas, count)
        system = self._build_system_prompt()

        try:
            raw_output = await self.backend.run(prompt, system=system)
        except SDKBackendError:
            logger.exception("SDK generation failed")
            raise

        return self._parse_output(raw_output)

    def _build_system_prompt(self) -> str:
        return (
            "You are a test scenario generator. Output ONLY valid YAML — a list "
            "of scenario objects. No markdown fences, no commentary. "
            "Each scenario must have: id, name, description, category, interfaces, "
            'steps (each with id, transport, and transport-specific fields). '
            'Set generated_by to "llm".'
        )

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
            parts.append(
                f"  Under-tested: {', '.join(self.feedback.under_tested_categories)}"
            )
        if self.feedback.suggested_focus:
            parts.append(f"  Focus on: {', '.join(self.feedback.suggested_focus)}")
        return "\n".join(parts)

    def _parse_output(self, raw: str) -> list[Scenario]:
        """Parse YAML output from LLM into validated Scenario objects."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            logger.warning("Failed to parse SDK YAML output: %s", e)
            return []

        if data is None:
            return []

        items: list[dict[str, Any]] = data if isinstance(data, list) else [data]
        scenarios: list[Scenario] = []
        for item in items:
            try:
                item["generated_by"] = "llm"
                scenarios.append(Scenario(**item))
            except (ValidationError, TypeError) as e:
                logger.warning("Invalid SDK scenario %s: %s", item.get("id", "?"), e)

        return scenarios
