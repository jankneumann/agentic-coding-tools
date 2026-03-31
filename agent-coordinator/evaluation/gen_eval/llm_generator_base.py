"""Shared base for LLM-powered generators (CLI and SDK).

Extracts duplicated prompt-building and output-parsing logic that was
previously copy-pasted between CLIGenerator and SDKGenerator.
"""

from __future__ import annotations

import logging
import textwrap
from typing import Any

import yaml
from pydantic import ValidationError

from .config import GenEvalConfig
from .descriptor import InterfaceDescriptor
from .models import EvalFeedback, Scenario

logger = logging.getLogger(__name__)


class LLMGeneratorMixin:
    """Mixin providing shared prompt building and output parsing for LLM generators.

    Both CLIGenerator and SDKGenerator inherit from this to avoid duplicating
    prompt construction, interface formatting, feedback formatting, and
    YAML output parsing logic.

    Subclasses must set ``self.descriptor``, ``self.config``, and
    ``self.feedback`` before calling any mixin methods.
    """

    descriptor: InterfaceDescriptor
    config: GenEvalConfig
    feedback: EvalFeedback | None

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
