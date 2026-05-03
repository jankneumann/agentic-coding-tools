"""Shared fixtures for the variant-descriptor / synthesis-plan tests.

Imports the canonical ``variant_descriptor`` module from
``skills/parallel-infrastructure/scripts/`` by injecting that path
into ``sys.path``. The directory has no ``__init__.py`` (intentional —
otherwise pytest's rootdir-based discovery would shadow the canonical
module on sys.path; same fix used for ``skills/tests/worktree/``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "parallel-infrastructure" / "scripts"
)
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

CHANGE_DIR = (
    Path(__file__).resolve().parents[3]
    / "openspec"
    / "changes"
    / "add-prototyping-stage"
)
SCHEMA_DIR = CHANGE_DIR / "contracts" / "schemas"


@pytest.fixture(scope="session")
def variant_descriptor_schema() -> dict:
    return json.loads(
        (SCHEMA_DIR / "variant-descriptor.schema.json").read_text()
    )


@pytest.fixture(scope="session")
def synthesis_plan_schema() -> dict:
    return json.loads((SCHEMA_DIR / "synthesis-plan.schema.json").read_text())


@pytest.fixture
def descriptor_v1() -> dict:
    """Variant 1 — picks data_model + tests."""
    return {
        "variant_id": "v1",
        "angle": "simplest",
        "vendor": "claude-opus-4-7",
        "branch": "prototype/add-foo/v1",
        "automated_scores": {
            "smoke": {"pass": True, "report": "all green"},
            "spec": {"covered": 5, "total": 6, "missing": ["scenario-3"]},
        },
        "human_picks": {
            "data_model": True,
            "api": False,
            "tests": True,
            "layout": False,
        },
        "synthesis_hint": "v1 nailed the data model — keep it",
    }


@pytest.fixture
def descriptor_v2() -> dict:
    """Variant 2 — picks api only."""
    return {
        "variant_id": "v2",
        "angle": "extensible",
        "vendor": "gpt-5-codex",
        "branch": "prototype/add-foo/v2",
        "automated_scores": {
            "smoke": {"pass": True, "report": "all green"},
            "spec": {"covered": 6, "total": 6, "missing": []},
        },
        "human_picks": {
            "data_model": False,
            "api": True,
            "tests": False,
            "layout": False,
        },
    }


@pytest.fixture
def descriptor_v3() -> dict:
    """Variant 3 — picks layout only."""
    return {
        "variant_id": "v3",
        "angle": "pragmatic",
        "vendor": "gemini-2.5-pro",
        "branch": "prototype/add-foo/v3",
        "automated_scores": {
            "smoke": {"pass": False, "report": "container failed to start"},
            "spec": {"covered": 4, "total": 6, "missing": ["scenario-2", "scenario-5"]},
        },
        "human_picks": {
            "data_model": False,
            "api": False,
            "tests": False,
            "layout": True,
        },
    }
