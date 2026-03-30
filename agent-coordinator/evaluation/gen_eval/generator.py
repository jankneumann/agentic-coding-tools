"""Template-based scenario generator.

Loads YAML scenario templates, expands Jinja2 parameterization
(combinatorial, capped at max_expansions), and validates each
expanded scenario against the Scenario Pydantic model.
"""

from __future__ import annotations

import itertools
import logging
from pathlib import Path
from typing import Any

import yaml
from jinja2 import BaseLoader, Environment, StrictUndefined, TemplateSyntaxError, UndefinedError
from pydantic import ValidationError

from .config import GenEvalConfig
from .descriptor import InterfaceDescriptor
from .models import EvalFeedback, Scenario

logger = logging.getLogger(__name__)


class TemplateGenerator:
    """Generates scenarios from YAML templates with Jinja2 parameterization.

    Loads YAML files from scenario_dirs declared in the descriptor,
    expands Jinja2 parameters (combinatorial), validates each expansion
    against the Scenario model, and filters by categories/priority/endpoints.

    Implements the ScenarioGenerator protocol.
    """

    def __init__(
        self,
        descriptor: InterfaceDescriptor,
        config: GenEvalConfig,
        feedback: EvalFeedback | None = None,
    ) -> None:
        self.descriptor = descriptor
        self.config = config
        self.feedback = feedback
        self.max_expansions = config.max_expansions
        self._jinja_env = Environment(loader=BaseLoader(), undefined=StrictUndefined)

    async def generate(
        self,
        focus_areas: list[str] | None = None,
        count: int = 10,
    ) -> list[Scenario]:
        """Load templates, expand parameters, validate, and return scenarios."""
        raw_templates = self._load_templates()
        scenarios: list[Scenario] = []

        for raw in raw_templates:
            expanded = self._expand_parameters(raw)
            for item in expanded:
                scenario = self._validate(item)
                if scenario is not None:
                    scenarios.append(scenario)

        # Apply filters
        scenarios = self._filter(scenarios, focus_areas)

        # Cap at requested count
        return scenarios[:count]

    def _load_templates(self) -> list[dict[str, Any]]:
        """Load all YAML files from scenario_dirs."""
        templates: list[dict[str, Any]] = []
        for scenario_dir in self.descriptor.scenario_dirs:
            dir_path = Path(scenario_dir)
            if not dir_path.is_dir():
                logger.warning("Scenario directory not found: %s", dir_path)
                continue
            for yaml_file in sorted(dir_path.glob("*.yaml")):
                try:
                    with open(yaml_file) as f:
                        data = yaml.safe_load(f)
                    if data is None:
                        continue
                    # Support single scenario or list of scenarios
                    if isinstance(data, list):
                        templates.extend(data)
                    else:
                        templates.append(data)
                except yaml.YAMLError as e:
                    logger.warning("Failed to parse YAML %s: %s", yaml_file, e)
        return templates

    def _expand_parameters(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Expand Jinja2 parameterization in a template.

        If the template has a 'parameters' dict mapping names to lists of
        values, compute the combinatorial product (capped at max_expansions)
        and render Jinja2 expressions in string fields.
        """
        params = raw.get("parameters")
        if not params:
            return [raw]

        # Build all combinations
        keys = list(params.keys())
        values = [v if isinstance(v, list) else [v] for v in (params[k] for k in keys)]
        combos = list(itertools.islice(itertools.product(*values), self.max_expansions))

        expanded: list[dict[str, Any]] = []
        for i, combo in enumerate(combos):
            context = dict(zip(keys, combo))
            try:
                rendered = self._render_dict(raw, context)
                # Update ID to be unique per expansion
                base_id = rendered.get("id", "scenario")
                rendered["id"] = f"{base_id}-{i}"
                # Remove parameters from expanded scenario
                rendered.pop("parameters", None)
                expanded.append(rendered)
            except (TemplateSyntaxError, UndefinedError) as e:
                logger.warning(
                    "Jinja2 render error for template %s combo %s: %s",
                    raw.get("id", "unknown"),
                    context,
                    e,
                )
        return expanded

    def _render_dict(self, data: Any, context: dict[str, Any]) -> Any:
        """Recursively render Jinja2 templates in dict/list/string values."""
        if isinstance(data, str):
            return self._render_string(data, context)
        if isinstance(data, dict):
            return {k: self._render_dict(v, context) for k, v in data.items()}
        if isinstance(data, list):
            return [self._render_dict(item, context) for item in data]
        return data

    def _render_string(self, text: str, context: dict[str, Any]) -> str:
        """Render a single string through Jinja2 if it contains template syntax."""
        if "{{" not in text and "{%" not in text:
            return text
        template = self._jinja_env.from_string(text)
        return template.render(context)

    def _validate(self, raw: dict[str, Any]) -> Scenario | None:
        """Validate a raw dict against the Scenario Pydantic model.

        Returns None and logs if validation fails.
        """
        try:
            return Scenario(**raw)
        except (ValidationError, TypeError) as e:
            logger.warning(
                "Invalid scenario %s: %s",
                raw.get("id", "unknown"),
                e,
            )
            return None

    def _filter(
        self,
        scenarios: list[Scenario],
        focus_areas: list[str] | None = None,
    ) -> list[Scenario]:
        """Filter scenarios by focus areas and feedback."""
        if focus_areas:
            scenarios = [
                s
                for s in scenarios
                if s.category in focus_areas or any(tag in focus_areas for tag in s.tags)
            ]

        if self.feedback and self.feedback.under_tested_categories:
            # Prioritize under-tested categories
            priority = []
            rest = []
            for s in scenarios:
                if s.category in self.feedback.under_tested_categories:
                    priority.append(s)
                else:
                    rest.append(s)
            scenarios = priority + rest

        # Sort by priority (lower = higher priority)
        scenarios.sort(key=lambda s: s.priority)
        return scenarios
