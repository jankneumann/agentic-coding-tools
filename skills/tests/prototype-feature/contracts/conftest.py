"""Shared fixtures for prototype-feature contract schema tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CHANGE_DIR = Path(__file__).resolve().parents[3].parent / "openspec" / "changes" / "add-prototyping-stage"
SCHEMA_DIR = CHANGE_DIR / "contracts" / "schemas"


@pytest.fixture(scope="session")
def variant_descriptor_schema() -> dict:
    return json.loads((SCHEMA_DIR / "variant-descriptor.schema.json").read_text())


@pytest.fixture(scope="session")
def synthesis_plan_schema() -> dict:
    return json.loads((SCHEMA_DIR / "synthesis-plan.schema.json").read_text())


@pytest.fixture()
def valid_descriptor() -> dict:
    """A canonical VariantDescriptor that satisfies every required field."""
    return {
        "variant_id": "v1",
        "angle": "simplest",
        "vendor": "claude-opus-4-6",
        "branch": "prototype/add-prototyping-stage/v1",
        "automated_scores": {
            "smoke": {"pass": True, "report": "all checks green"},
            "spec": {"covered": 4, "total": 5, "missing": ["scenario-3"]},
        },
        "human_picks": {
            "data_model": True,
            "api": False,
            "tests": True,
            "layout": False,
        },
        "synthesis_hint": "prefer this variant's data model for convergence",
    }


@pytest.fixture()
def valid_synthesis_plan() -> dict:
    """A canonical SynthesisPlan covering all four aspects with a finding."""
    return {
        "change_id": "add-prototyping-stage",
        "per_aspect_picks": {
            "data_model": {"source": "v1", "rationale": "cleanest VariantDescriptor decomposition"},
            "api": {"source": "v2"},
            "tests": {"source": "rewrite", "rationale": "none of the variants test edge cases"},
            "layout": {"source": "v3"},
        },
        "recommended_findings": [
            {
                "type": "convergence.prefer-variant-data-model",
                "criticality": "high",
                "description": "Variant v1's nested automated_scores structure is the canonical shape.",
                "source_variants": ["v1"],
            }
        ],
        "synthesis_notes": "v1 wins on data model; v2 on API; v3 on layout; tests need fresh authoring.",
    }
