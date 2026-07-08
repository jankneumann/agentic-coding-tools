"""Load and validate agent trajectory scenario YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import AgentScenario


class ScenarioLoadError(ValueError):
    """Raised when a scenario YAML is malformed or fails validation."""


def load_scenario(path: str | Path) -> AgentScenario:
    """Parse and validate a single scenario YAML file.

    The resolved absolute path is recorded as ``source_path`` so downstream
    findings can point back at the originating scenario file.
    """
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScenarioLoadError(f"failed to read scenario {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScenarioLoadError(f"scenario {p} must be a YAML mapping, got {type(raw).__name__}")
    raw.setdefault("source_path", str(p.resolve()))
    try:
        return AgentScenario.model_validate(raw)
    except ValidationError as exc:
        raise ScenarioLoadError(f"scenario {p} failed validation: {exc}") from exc


def load_scenarios(directory: str | Path) -> list[AgentScenario]:
    """Load every ``*.scenario.yaml`` under ``directory`` (sorted by path)."""
    d = Path(directory)
    scenarios = [load_scenario(f) for f in sorted(d.glob("*.scenario.yaml"))]
    return scenarios
