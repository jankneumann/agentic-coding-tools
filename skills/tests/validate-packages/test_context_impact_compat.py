"""Backward-compatibility proof for the ri-08 schema change.

Measured on 3b74b74e, **24 of 62** work-packages.yaml files under
openspec/changes/** already fail validate_work_packages.py — missing top-level
`contracts`, missing `outputs`, missing `verification.steps[].evidence`, and
`impl:` lock keys outside the schema's namespace pattern. That debt predates
ri-08 and spans archived changes.

So "every work-packages.yaml validates" is not an assertion this suite can make:
it would fail on an unmodified tree for reasons this change did not cause, and a
gate that cannot pass proves nothing. The passable and honest assertion is that
no file gains an error attributable to `context_impact` — which isolates exactly
the constraint this change introduces and stays meaningful once the pre-existing
debt is repaired.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml
from wp_fixtures import SCHEMA_PATH

REPO_ROOT = Path(__file__).resolve().parents[3]
CHANGES_DIR = REPO_ROOT / "openspec" / "changes"


def _work_package_files() -> list[Path]:
    if not CHANGES_DIR.is_dir():  # pragma: no cover - repository layout guard
        return []
    return sorted(CHANGES_DIR.rglob("work-packages.yaml"))


WORK_PACKAGE_FILES = _work_package_files()


def test_the_repository_actually_has_work_package_files_to_check():
    """Guard against the sweep silently checking nothing."""
    assert WORK_PACKAGE_FILES, "expected work-packages.yaml files under openspec/changes"


@pytest.mark.parametrize(
    "path", WORK_PACKAGE_FILES, ids=lambda p: str(p.relative_to(CHANGES_DIR))
)
def test_no_existing_work_packages_file_gains_a_context_impact_error(path: Path):
    schema = json.loads(SCHEMA_PATH.read_text())
    document = yaml.safe_load(path.read_text())
    if document is None:
        pytest.skip("empty document")

    validator = jsonschema.Draft202012Validator(schema)
    offending = [
        error
        for error in validator.iter_errors(document)
        if "context_impact" in error.message
        or "context_impact" in [str(part) for part in error.absolute_path]
    ]
    assert not offending, [error.message for error in offending]


def test_context_impact_is_absent_from_every_legacy_file_or_valid_where_present():
    """Any file that already declares the block must satisfy the new constraints."""
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(schema)

    declaring = []
    for path in WORK_PACKAGE_FILES:
        document = yaml.safe_load(path.read_text())
        if not document:
            continue
        for package in document.get("packages") or []:
            if isinstance(package, dict) and "context_impact" in package:
                declaring.append((path, package))

    for path, package in declaring:
        errors = [
            error.message
            for error in validator.iter_errors({"packages": [package]})
            if "context_impact" in error.message
        ]
        assert not errors, f"{path}: {errors}"
