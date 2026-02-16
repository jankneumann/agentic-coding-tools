"""Configuration schema for the architecture report generator.

Loads an optional YAML configuration file (``architecture.config.yaml``) and
provides typed dataclasses with sensible defaults.  Every field is optional —
projects that don't create a config file get identical behaviour to the
pre-config hardcoded defaults.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known section names (must stay in sync with generate_report)
# ---------------------------------------------------------------------------

KNOWN_SECTIONS: frozenset[str] = frozenset(
    {
        "system_overview",
        "module_map",
        "dependency_layers",
        "entry_points",
        "health",
        "impact_analysis",
        "code_health",
        "parallel_zones",
        "cross_layer_flows",
        "diagrams",
    }
)

DEFAULT_SECTIONS: list[str] = [
    "system_overview",
    "module_map",
    "dependency_layers",
    "entry_points",
    "health",
    "impact_analysis",
    "code_health",
    "parallel_zones",
    "cross_layer_flows",
    "diagrams",
]

# Default explanations and expected categories (match pre-config behaviour)
DEFAULT_CATEGORY_EXPLANATIONS: dict[str, str] = {
    "test_coverage": (
        "functions lack test references — consider adding tests for critical paths"
    ),
    "orphan": (
        "symbols are unreachable from any entrypoint — may be dead code or missing wiring"
    ),
    "disconnected_flow": (
        "MCP routes have no frontend callers — "
        "expected for an MCP server (clients are AI agents, not browsers)"
    ),
    "reachability": (
        "entrypoints have downstream dependencies but no DB writes or side effects"
    ),
}

DEFAULT_EXPECTED_CATEGORIES: set[str] = {"disconnected_flow"}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ProjectConfig:
    name: str = ""
    description: str = ""
    primary_language: str = ""  # empty ⇒ auto-detect
    protocol: str = ""  # empty ⇒ auto-detect; values: mcp, http, grpc, cli, auto


@dataclass
class PathsConfig:
    input_dir: str = "docs/architecture-analysis"
    output_report: str = "docs/architecture-analysis/architecture.report.md"


@dataclass
class ReportSectionsConfig:
    sections: list[str] = field(default_factory=lambda: list(DEFAULT_SECTIONS))


@dataclass
class HealthConfig:
    expected_categories: list[str] = field(
        default_factory=lambda: sorted(DEFAULT_EXPECTED_CATEGORIES)
    )
    category_explanations: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_CATEGORY_EXPLANATIONS)
    )
    severity_thresholds: dict[str, str] = field(default_factory=dict)


@dataclass
class BestPracticeRef:
    path: str = ""
    sections: list[str] = field(default_factory=list)


@dataclass
class ReportConfig:
    """Top-level configuration for the architecture report generator."""

    project: ProjectConfig = field(default_factory=ProjectConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    report: ReportSectionsConfig = field(default_factory=ReportSectionsConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    best_practices: list[BestPracticeRef] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _parse_project(raw: dict[str, Any]) -> ProjectConfig:
    return ProjectConfig(
        name=str(raw.get("name", "")),
        description=str(raw.get("description", "")),
        primary_language=str(raw.get("primary_language", "")),
        protocol=str(raw.get("protocol", "")),
    )


def _parse_paths(raw: dict[str, Any]) -> PathsConfig:
    return PathsConfig(
        input_dir=str(raw.get("input_dir", PathsConfig.input_dir)),
        output_report=str(raw.get("output_report", PathsConfig.output_report)),
    )


def _parse_report(raw: dict[str, Any]) -> ReportSectionsConfig:
    sections = raw.get("sections", DEFAULT_SECTIONS)
    if not isinstance(sections, list):
        warnings.warn("report.sections should be a list — using defaults", stacklevel=2)
        sections = list(DEFAULT_SECTIONS)

    # Validate section names
    for name in sections:
        if name not in KNOWN_SECTIONS:
            warnings.warn(
                f"Unknown report section '{name}' — will be ignored",
                stacklevel=2,
            )

    return ReportSectionsConfig(sections=list(sections))


def _parse_health(raw: dict[str, Any]) -> HealthConfig:
    expected = raw.get("expected_categories", sorted(DEFAULT_EXPECTED_CATEGORIES))
    if not isinstance(expected, list):
        warnings.warn(
            "health.expected_categories should be a list — using defaults",
            stacklevel=2,
        )
        expected = sorted(DEFAULT_EXPECTED_CATEGORIES)

    # Merge user explanations on top of defaults
    explanations = dict(DEFAULT_CATEGORY_EXPLANATIONS)
    user_explanations = raw.get("category_explanations", {})
    if isinstance(user_explanations, dict):
        explanations.update(user_explanations)

    thresholds = raw.get("severity_thresholds", {})
    if not isinstance(thresholds, dict):
        thresholds = {}

    return HealthConfig(
        expected_categories=[str(c) for c in expected],
        category_explanations={str(k): str(v) for k, v in explanations.items()},
        severity_thresholds={str(k): str(v) for k, v in thresholds.items()},
    )


def _parse_best_practices(raw: list[Any]) -> list[BestPracticeRef]:
    refs: list[BestPracticeRef] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        if not path:
            continue
        sections = item.get("sections", [])
        if not isinstance(sections, list):
            sections = []
        refs.append(BestPracticeRef(path=path, sections=[str(s) for s in sections]))
    return refs


def load_config(path: Path | None = None) -> ReportConfig:
    """Load a YAML config file and return a ``ReportConfig``.

    If *path* is ``None`` the default ``architecture.config.yaml`` in the
    current directory is tried.  If the file does not exist, a default
    ``ReportConfig`` is returned.
    """
    try:
        import yaml
    except ImportError:
        if path is not None:
            warnings.warn(
                "PyYAML is not installed — config file will be ignored. "
                "Install with: uv pip install PyYAML",
                stacklevel=2,
            )
        return ReportConfig()

    if path is None:
        path = Path("architecture.config.yaml")

    if not path.exists():
        return ReportConfig()

    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except Exception as exc:
        warnings.warn(f"Failed to parse config file {path}: {exc}", stacklevel=2)
        return ReportConfig()

    if not isinstance(raw, dict):
        return ReportConfig()

    # Warn on unknown top-level keys (forward-compatible)
    known_keys = {"project", "paths", "report", "health", "best_practices"}
    for key in raw:
        if key not in known_keys:
            warnings.warn(
                f"Unknown config key '{key}' — will be ignored",
                stacklevel=2,
            )

    # Warn on files referenced in best_practices that don't exist
    bp_raw = raw.get("best_practices", [])
    if isinstance(bp_raw, list):
        for item in bp_raw:
            if isinstance(item, dict):
                bp_path = item.get("path", "")
                if bp_path and not Path(bp_path).exists():
                    warnings.warn(
                        f"best_practices path '{bp_path}' does not exist",
                        stacklevel=2,
                    )

    return ReportConfig(
        project=_parse_project(raw.get("project", {})),
        paths=_parse_paths(raw.get("paths", {})),
        report=_parse_report(raw.get("report", {})),
        health=_parse_health(raw.get("health", {})),
        best_practices=_parse_best_practices(
            raw.get("best_practices", []) if isinstance(raw.get("best_practices"), list) else []
        ),
    )
