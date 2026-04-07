"""Multi-source scenario bootstrap for gen-eval scenario packs.

Bootstraps scenario seeds from:
- OpenSpec spec deltas (requirement scenarios)
- Contract artifacts (OpenAPI, JSON schema)
- Incidents (escaped defects)
- Archived OpenSpec exemplars
- Manual templates

Each bootstrapped scenario preserves source metadata in its manifest entry
so downstream users can distinguish normative from mined/inferred scenarios.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ScenarioSeed:
    """A bootstrapped scenario seed ready for manifest registration.

    Contains the minimal structure for a gen-eval scenario plus
    provenance metadata for the scenario-pack manifest.
    """

    scenario_id: str
    name: str
    description: str
    category: str
    source: str  # spec, contract, incident, archive, manual
    source_ref: str = ""  # e.g., requirement ID, contract path, incident ID
    visibility: str = "public"
    determinism: str = "deterministic"
    interfaces: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def bootstrap_from_spec_delta(spec_path: Path) -> list[ScenarioSeed]:
    """Bootstrap scenario seeds from an OpenSpec spec delta.

    Parses ``#### Scenario:`` blocks in the spec delta markdown and
    creates a seed for each one, linked to the originating requirement.

    Args:
        spec_path: Path to a spec delta markdown file.

    Returns:
        List of scenario seeds with ``source="spec"``.
    """
    if not spec_path.exists():
        logger.warning("Spec delta not found: %s", spec_path)
        return []

    text = spec_path.read_text()
    if not text.strip():
        logger.warning("Empty spec delta: %s", spec_path)
        return []

    seeds: list[ScenarioSeed] = []
    current_requirement = ""

    for line in text.splitlines():
        # Track requirement headings
        req_match = re.match(r"^###\s+Requirement:\s+(.+)", line)
        if req_match:
            current_requirement = req_match.group(1).strip()
            continue

        # Extract scenario blocks
        scenario_match = re.match(r"^####\s+Scenario:\s+(.+)", line)
        if scenario_match:
            scenario_name = scenario_match.group(1).strip()
            scenario_id = _slugify(scenario_name)
            seeds.append(
                ScenarioSeed(
                    scenario_id=scenario_id,
                    name=scenario_name,
                    description=f"From spec requirement: {current_requirement}",
                    category=_slugify(current_requirement) if current_requirement else "uncategorized",
                    source="spec",
                    source_ref=current_requirement,
                    tags=["bootstrapped", "spec-derived"],
                )
            )

    if not seeds:
        logger.warning("No scenario blocks found in spec delta: %s", spec_path)

    return seeds


def bootstrap_from_contract(contract_path: Path) -> list[ScenarioSeed]:
    """Bootstrap scenario seeds from a contract artifact.

    Supports OpenAPI YAML/JSON and JSON Schema files. Creates seeds
    for each endpoint or schema definition found.

    Args:
        contract_path: Path to contract file (OpenAPI or JSON Schema).

    Returns:
        List of scenario seeds with ``source="contract"``.
    """
    if not contract_path.exists():
        logger.warning("Contract not found: %s", contract_path)
        return []

    try:
        with open(contract_path) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.warning("Failed to parse contract %s: %s", contract_path, e)
        return []

    if not isinstance(data, dict):
        logger.warning("Contract is not a YAML mapping: %s", contract_path)
        return []

    seeds: list[ScenarioSeed] = []

    # OpenAPI paths
    paths = data.get("paths", {})
    if isinstance(paths, dict):
        for path_str, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method in ("get", "post", "put", "delete", "patch"):
                if method in methods:
                    op = methods[method]
                    op_id = op.get("operationId", f"{method}-{path_str}")
                    seeds.append(
                        ScenarioSeed(
                            scenario_id=_slugify(f"contract-{op_id}"),
                            name=f"Contract: {method.upper()} {path_str}",
                            description=op.get("summary", f"Test {method.upper()} {path_str}"),
                            category="contract-validation",
                            source="contract",
                            source_ref=f"{contract_path}#/paths/{path_str}/{method}",
                            interfaces=[f"{method.upper()} {path_str}"],
                            tags=["bootstrapped", "contract-derived"],
                        )
                    )

    if not seeds:
        logger.warning("No endpoints found in contract: %s", contract_path)

    return seeds


def bootstrap_from_incident(
    incident_id: str,
    description: str,
    affected_interfaces: list[str] | None = None,
) -> list[ScenarioSeed]:
    """Bootstrap a scenario seed from an incident report.

    Creates a single holdout-visibility seed representing the escaped
    defect, suitable for regression testing.

    Args:
        incident_id: Incident identifier (e.g., "INC-42").
        description: Description of the escaped defect.
        affected_interfaces: List of interfaces affected.

    Returns:
        List containing one scenario seed with ``source="incident"``.
    """
    return [
        ScenarioSeed(
            scenario_id=_slugify(f"incident-{incident_id}"),
            name=f"Incident regression: {incident_id}",
            description=description,
            category="incident-regression",
            source="incident",
            source_ref=incident_id,
            visibility="holdout",
            interfaces=affected_interfaces or [],
            tags=["bootstrapped", "incident-derived", incident_id],
        )
    ]


def bootstrap_from_archive(
    change_id: str,
    archive_path: Path,
) -> list[ScenarioSeed]:
    """Bootstrap scenario seeds from an archived OpenSpec change.

    Reads the archived proposal and session-log to extract patterns
    that could become scenario seeds.

    Args:
        change_id: The archived change ID.
        archive_path: Path to the archived change directory.

    Returns:
        List of scenario seeds with ``source="archive"``.
    """
    if not archive_path.exists():
        logger.warning("Archive path not found: %s", archive_path)
        return []

    seeds: list[ScenarioSeed] = []

    # Try to extract from spec deltas in the archive
    specs_dir = archive_path / "specs"
    if specs_dir.is_dir():
        for spec_file in sorted(specs_dir.rglob("*.md")):
            try:
                spec_seeds = bootstrap_from_spec_delta(spec_file)
                for seed in spec_seeds:
                    seed.source = "archive"
                    seed.source_ref = f"archive:{change_id}:{spec_file.name}"
                    seed.tags = ["bootstrapped", "archive-derived", change_id]
                seeds.extend(spec_seeds)
            except Exception as e:
                logger.warning(
                    "Failed to extract from archived spec %s: %s", spec_file, e
                )

    if not seeds:
        logger.warning("No scenario seeds extracted from archive: %s", change_id)

    return seeds


def seeds_to_manifest_entries(seeds: list[ScenarioSeed]) -> list[dict[str, Any]]:
    """Convert scenario seeds to manifest entry dicts.

    Returns dicts suitable for inclusion in a scenario-pack manifest YAML.
    """
    entries = []
    for seed in seeds:
        entry: dict[str, Any] = {
            "scenario_id": seed.scenario_id,
            "visibility": seed.visibility,
            "source": seed.source,
            "determinism": seed.determinism,
        }
        if seed.source_ref:
            if seed.source == "incident":
                entry["incident_ref"] = seed.source_ref
            entry["owner"] = seed.source_ref
        entries.append(entry)
    return entries


def seeds_to_scenario_yaml(seeds: list[ScenarioSeed]) -> list[dict[str, Any]]:
    """Convert scenario seeds to gen-eval scenario YAML dicts.

    Returns dicts that can be written as YAML scenario files.
    The steps are empty placeholders that need to be filled in.
    """
    scenarios = []
    for seed in seeds:
        scenario: dict[str, Any] = {
            "id": seed.scenario_id,
            "name": seed.name,
            "description": seed.description,
            "category": seed.category,
            "priority": 2,
            "interfaces": seed.interfaces or ["http"],
            "steps": seed.steps
            or [
                {
                    "id": f"{seed.scenario_id}-step1",
                    "transport": "http",
                    "method": "GET",
                    "endpoint": "/health",
                    "expect": {"status": 200},
                }
            ],
            "tags": seed.tags,
        }
        scenarios.append(scenario)
    return scenarios


def _slugify(text: str) -> str:
    """Convert text to a URL/ID-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:80]
