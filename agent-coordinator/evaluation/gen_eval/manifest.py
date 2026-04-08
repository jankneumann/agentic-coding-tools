"""Scenario-pack manifest loading and visibility filtering.

Loads YAML manifests that classify scenarios by visibility (public vs holdout),
provenance, and promotion status. Provides filtering utilities used by generators
and the orchestrator to enforce visibility boundaries at runtime.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import ManifestEntry, Scenario, ScenarioPackManifest, ScenarioVerdict

logger = logging.getLogger(__name__)


def load_manifest(path: Path) -> ScenarioPackManifest:
    """Load a scenario-pack manifest from a YAML file.

    Args:
        path: Path to the manifest YAML file.

    Returns:
        Parsed and validated ScenarioPackManifest.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        ValueError: If the manifest YAML is malformed or fails validation.
    """
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError(f"Empty manifest file: {path}")

    if not isinstance(raw, dict):
        raise ValueError(f"Manifest must be a YAML mapping, got {type(raw).__name__}")

    try:
        return ScenarioPackManifest(**raw)
    except ValidationError as e:
        raise ValueError(f"Invalid manifest {path}: {e}") from e


def load_manifests_from_dirs(dirs: Sequence[str | Path]) -> ScenarioPackManifest:
    """Load and merge manifests from multiple directories.

    Looks for ``manifest.yaml`` or ``manifest.yml`` in each directory.
    Returns a merged manifest with all entries combined.
    """
    all_entries: list[ManifestEntry] = []

    for d in dirs:
        dir_path = Path(d)
        for name in ("manifest.yaml", "manifest.yml"):
            manifest_path = dir_path / name
            if manifest_path.exists():
                try:
                    manifest = load_manifest(manifest_path)
                    all_entries.extend(manifest.entries)
                except (ValueError, FileNotFoundError) as e:
                    logger.warning("Failed to load manifest %s: %s", manifest_path, e)

    return ScenarioPackManifest(entries=all_entries)


def filter_scenarios_by_visibility(
    scenarios: list[Scenario],
    manifest: ScenarioPackManifest,
    visibility: str,
    *,
    strict: bool = False,
) -> list[Scenario]:
    """Filter scenarios to only those matching the given visibility.

    Args:
        scenarios: List of scenarios to filter.
        manifest: The manifest providing visibility metadata.
        visibility: Target visibility (``"public"`` or ``"holdout"``).
        strict: If True, exclude scenarios not present in the manifest.
            If False, scenarios without manifest entries are included
            (treated as unclassified).

    Returns:
        Filtered list of scenarios.
    """
    allowed_ids = manifest.ids_by_visibility(visibility)
    all_manifest_ids = {e.scenario_id for e in manifest.entries}

    result: list[Scenario] = []
    for s in scenarios:
        if s.id in allowed_ids:
            result.append(s)
        elif not strict and s.id not in all_manifest_ids:
            # Unclassified scenario — include in non-strict mode
            result.append(s)

    return result


def group_verdicts_by_visibility(
    verdicts: list[ScenarioVerdict],
    manifest: ScenarioPackManifest,
) -> dict[str, list[ScenarioVerdict]]:
    """Group verdicts by their manifest visibility.

    Returns a dict with keys ``"public"``, ``"holdout"``, and ``"unclassified"``.
    """
    public_ids = manifest.public_ids()
    holdout_ids = manifest.holdout_ids()

    groups: dict[str, list[ScenarioVerdict]] = {
        "public": [],
        "holdout": [],
        "unclassified": [],
    }

    for v in verdicts:
        if v.scenario_id in public_ids:
            groups["public"].append(v)
        elif v.scenario_id in holdout_ids:
            groups["holdout"].append(v)
        else:
            groups["unclassified"].append(v)

    return groups
