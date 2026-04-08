"""Scenario pack manifest model and loader (D6).

Manifests classify scenarios by visibility, provenance, determinism,
and ownership. Per-category YAML manifests avoid merge conflicts
when multiple agents add scenarios in parallel.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Visibility(StrEnum):
    """Scenario visibility for filtering."""

    public = "public"
    holdout = "holdout"


class Source(StrEnum):
    """Provenance of a scenario."""

    spec = "spec"
    contract = "contract"
    doc = "doc"
    incident = "incident"
    archive = "archive"
    manual = "manual"


class Determinism(StrEnum):
    """Expected execution determinism."""

    deterministic = "deterministic"
    bounded_nondeterministic = "bounded-nondeterministic"
    exploratory = "exploratory"


class PromotionStatus(StrEnum):
    """Workflow promotion stage."""

    draft = "draft"
    candidate = "candidate"
    approved = "approved"


class ScenarioManifestEntry(BaseModel):
    """A single scenario entry in a pack manifest."""

    id: str
    visibility: Visibility
    source: Source
    determinism: Determinism = Determinism.deterministic
    owner: str = ""
    promotion_status: PromotionStatus = PromotionStatus.draft


class ScenarioPackManifest(BaseModel):
    """A scenario pack manifest — per-category metadata."""

    pack: str
    scenarios: list[ScenarioManifestEntry] = Field(default_factory=list)


def load_manifests(manifest_dir: str | Path) -> dict[str, ScenarioPackManifest]:
    """Load all manifest YAML files from a directory.

    Returns a dict mapping pack name → manifest.
    """
    manifests: dict[str, ScenarioPackManifest] = {}
    dir_path = Path(manifest_dir)
    if not dir_path.is_dir():
        logger.warning("Manifest directory not found: %s", dir_path)
        return manifests

    for yaml_file in sorted(dir_path.glob("*.manifest.yaml")):
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            if data is None:
                continue
            manifest = ScenarioPackManifest(**data)
            manifests[manifest.pack] = manifest
        except (yaml.YAMLError, Exception) as e:
            logger.warning("Failed to load manifest %s: %s", yaml_file, e)

    return manifests


def get_scenario_visibility(
    manifests: dict[str, ScenarioPackManifest],
    scenario_id: str,
) -> Visibility | None:
    """Look up a scenario's visibility across all loaded manifests."""
    for manifest in manifests.values():
        for entry in manifest.scenarios:
            if entry.id == scenario_id:
                return entry.visibility
    return None


def filter_by_visibility(
    manifests: dict[str, ScenarioPackManifest],
    scenario_ids: list[str],
    visibility_filter: str = "public",
) -> list[str]:
    """Filter scenario IDs by visibility.

    Args:
        manifests: Loaded manifests.
        scenario_ids: IDs to filter.
        visibility_filter: "public" (default), "holdout", or "all".

    Returns:
        Filtered list of scenario IDs. Scenarios not in any manifest
        are treated as public.
    """
    if visibility_filter == "all":
        return scenario_ids

    target = Visibility(visibility_filter)
    result: list[str] = []
    for sid in scenario_ids:
        vis = get_scenario_visibility(manifests, sid)
        if vis is None or vis == target:
            result.append(sid)
    return result
