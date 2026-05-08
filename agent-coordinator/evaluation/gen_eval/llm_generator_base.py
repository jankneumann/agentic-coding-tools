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
from .models import EvalFeedback, Scenario, ScenarioSource
from .openspec_seed import ParsedScenario, render_constraints_section

logger = logging.getLogger(__name__)


class LLMGeneratorMixin:
    """Mixin providing shared prompt building and output parsing for LLM generators.

    Both CLIGenerator and SDKGenerator inherit from this to avoid duplicating
    prompt construction, interface formatting, feedback formatting, and
    YAML output parsing logic.

    Subclasses must set ``self.descriptor``, ``self.config``, and
    ``self.feedback`` before calling any mixin methods. Subclasses MAY also
    set ``self.openspec_scenarios`` (a list of ParsedScenario) — when
    populated and non-empty, ``_build_prompt`` prepends a
    ``# OpenSpec Scenarios (constraints)`` section produced by
    :func:`render_constraints_section`. When unset or empty the prompt is
    byte-identical to the pre-change cli-augmented prompt.
    """

    descriptor: InterfaceDescriptor
    config: GenEvalConfig
    feedback: EvalFeedback | None
    openspec_scenarios: list[ParsedScenario] | None = None

    def _build_system_prompt(self) -> str:
        return textwrap.dedent("""\
            You are a test scenario generator. Output ONLY valid YAML — a list
            of scenario objects. No markdown fences, no commentary.
            Each scenario must have: id, name, description, category, interfaces,
            steps (each with id, transport, and transport-specific fields).
            Set generated_by to "llm".""")

    def _build_prompt(self, focus_areas: list[str] | None, count: int) -> str:
        parts: list[str] = []
        # OpenSpec scenarios (constraints) section — only emitted when
        # --openspec-change was passed AND parsing produced scenarios.
        # Backward compat: when openspec_scenarios is None or empty, the
        # rest of the prompt is byte-identical to the pre-change
        # cli-augmented prompt.
        scenarios = getattr(self, "openspec_scenarios", None)
        if scenarios:
            parts.append(render_constraints_section(scenarios))
            parts.append("")

        parts.append(f"Generate {count} test scenarios for: {self.descriptor.project}")
        parts.append(f"\nInterfaces:\n{self._format_interfaces()}")

        if focus_areas:
            parts.append(f"\nFocus on: {', '.join(focus_areas)}")

        if self.feedback:
            parts.append(self._format_feedback())

        return "\n".join(parts)

    def _scenario_source_for_index(self, index: int) -> str | None:
        """Return ``source.openspec_scenario`` ref for the Nth generated scenario.

        When openspec_scenarios is populated, generated Scenario objects are
        rotationally tagged with the source ref of the seed scenario at
        ``index % len(openspec_scenarios)``. Returns None when no openspec
        seeds were supplied (preserves prior cli-augmented behavior).
        """
        scenarios = getattr(self, "openspec_scenarios", None)
        if not scenarios:
            return None
        return scenarios[index % len(scenarios)].source_ref

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
        for idx, item in enumerate(items):
            try:
                # Force generated_by to "llm"
                item["generated_by"] = "llm"
                scenario = Scenario(**item)
            except (ValidationError, TypeError) as e:
                logger.warning("Invalid LLM scenario %s: %s", item.get("id", "?"), e)
                continue

            # Tag with OpenSpec scenario source when seeds are present.
            # Backward compat: when no seeds were supplied, source.openspec_scenario
            # is left unset so the field is absent from emitted Scenario objects.
            source_ref = self._scenario_source_for_index(idx)
            if source_ref is not None:
                if scenario.source is None:
                    scenario = scenario.model_copy(
                        update={"source": ScenarioSource(openspec_scenario=source_ref)}
                    )
                else:
                    new_source = scenario.source.model_copy(
                        update={"openspec_scenario": source_ref}
                    )
                    scenario = scenario.model_copy(update={"source": new_source})
            scenarios.append(scenario)

        return scenarios
