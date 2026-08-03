"""Document builders shared by the validate-packages test modules.

These live in a named module rather than in ``conftest.py`` because several
sibling suites under ``skills/tests/`` also define a ``conftest`` module; a bare
``from conftest import ...`` resolves to whichever one pytest imported first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "validate-packages"
SCRIPTS_DIR = SKILL_DIR / "scripts"
INSTALL_SCHEMAS = SKILL_DIR / "install_assets" / "openspec" / "schemas"

SCHEMA_PATH = INSTALL_SCHEMAS / "work-packages.schema.json"
RULES_PATH = INSTALL_SCHEMAS / "context-impact-rules.yaml"

SURFACES = (
    "capabilities",
    "apis",
    "architecture",
    "decisions",
    "documentation",
    "semantic_code",
)


def minimal_package(**overrides: Any) -> dict[str, Any]:
    """A work package satisfying every currently-required field.

    Overrides are merged shallowly so a test can add ``context_impact`` or swap
    a scope without restating the whole structure.
    """
    package: dict[str, Any] = {
        "package_id": "wp-example",
        "task_type": "implementation",
        "description": "Example package.",
        "depends_on": [],
        "priority": 5,
        "locks": {"files": [], "keys": []},
        "scope": {"write_allow": ["src/**"], "read_allow": ["**"]},
        "worktree": {"name": "example"},
        "timeout_minutes": 60,
        "retry_budget": 1,
        "min_trust_level": 2,
        "verification": {
            "tier_required": "B",
            "steps": [
                {
                    "name": "tests",
                    "kind": "command",
                    "command": "pytest -q",
                    "evidence": {"artifacts": [], "result_keys": ["tests_passed"]},
                }
            ],
        },
        "outputs": {"result_keys": ["tests_passed"]},
    }
    package.update(overrides)
    return package


def minimal_document(*packages: dict[str, Any]) -> dict[str, Any]:
    """A work-packages document satisfying every currently-required field."""
    return {
        "schema_version": 1,
        "feature": {"id": "example-feature", "plan_revision": 1},
        "contracts": {
            "revision": 1,
            "openapi": {
                "primary": "contracts/openapi/v1.yaml",
                "files": ["contracts/openapi/v1.yaml"],
            },
        },
        "packages": list(packages) or [minimal_package()],
    }
