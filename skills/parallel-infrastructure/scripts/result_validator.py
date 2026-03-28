"""Result validation for Phase C1 of parallel-implement-feature.

Validates work-queue results from completed packages:
1. JSON Schema validation (delegates to scripts/validate_work_result.py)
2. Revision matching (contracts_revision and plan_revision match expected)
3. Output key verification (declared result_keys present in result)
4. Scope compliance and verification consistency

Usage:
    from result_validator import validate_package_result

    result = validate_package_result(
        result_data=package_result_json,
        package_def=package_from_work_packages_yaml,
        expected_contracts_revision=1,
        expected_plan_revision=1,
    )
    assert result["valid"] is True
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Import base validation from scripts/validate_work_result.py
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from validate_work_result import (
    load_schema,
    validate_result as validate_result_base,
)


def validate_revision_match(
    result_data: dict[str, Any],
    expected_contracts_revision: int,
    expected_plan_revision: int,
) -> list[str]:
    """Check that the result's revisions match the orchestrator's expected values.

    A mismatch indicates the package was working against stale contracts
    or an outdated plan — its output may be invalid.
    """
    errors = []

    actual_contracts = result_data.get("contracts_revision")
    if actual_contracts != expected_contracts_revision:
        errors.append(
            f"  contracts_revision mismatch: "
            f"result={actual_contracts}, expected={expected_contracts_revision}"
        )

    actual_plan = result_data.get("plan_revision")
    if actual_plan != expected_plan_revision:
        errors.append(
            f"  plan_revision mismatch: "
            f"result={actual_plan}, expected={expected_plan_revision}"
        )

    return errors


def validate_output_keys(
    result_data: dict[str, Any],
    package_def: dict[str, Any],
) -> list[str]:
    """Check that all declared output result_keys are present in the result.

    The work-packages.yaml declares which keys a package must produce.
    The work-queue result embeds verification step evidence with metrics
    that should contain these keys, or they should appear in the result's
    top-level scope_check, verification, etc.

    For simplicity, we check across:
    - verification.steps[].evidence.metrics keys
    - scope_check keys
    - files_modified (if "files_modified" is a declared key)
    """
    errors = []
    declared_keys = set(package_def.get("outputs", {}).get("result_keys", []))
    if not declared_keys:
        return errors

    # Collect all keys present in the result
    available_keys: set[str] = set()

    # files_modified is always present in the result schema
    if result_data.get("files_modified") is not None:
        available_keys.add("files_modified")

    # Verification step metrics
    for step in result_data.get("verification", {}).get("steps", []):
        metrics = step.get("evidence", {}).get("metrics", {})
        available_keys.update(metrics.keys())

    # Top-level result keys
    for key in ["merge_commit", "test_count", "pass_count", "lint_passed"]:
        if key in result_data:
            available_keys.add(key)

    # Check if any verification step has result_keys in its evidence
    for step in result_data.get("verification", {}).get("steps", []):
        evidence = step.get("evidence", {})
        for key in evidence.get("artifacts", []):
            available_keys.add(key)

    missing = declared_keys - available_keys
    if missing:
        errors.append(
            f"  Missing declared output keys: {sorted(missing)}"
        )

    return errors


def validate_package_result(
    result_data: dict[str, Any],
    package_def: dict[str, Any],
    expected_contracts_revision: int,
    expected_plan_revision: int,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full Phase C1 validation of a package's work-queue result.

    Combines:
    1. Base validation (schema, scope compliance, verification consistency)
    2. Revision matching
    3. Output key verification

    Returns:
        Dict with:
        - valid: bool
        - checks: dict of check_name -> {passed, errors}
    """
    # Start with base validation
    base_result = validate_result_base(result_data, schema)

    # Add revision matching
    revision_errors = validate_revision_match(
        result_data, expected_contracts_revision, expected_plan_revision
    )
    base_result["checks"]["revision_match"] = {
        "passed": not revision_errors,
        "errors": revision_errors,
    }
    if revision_errors:
        base_result["valid"] = False

    # Add output key verification
    output_errors = validate_output_keys(result_data, package_def)
    base_result["checks"]["output_keys"] = {
        "passed": not output_errors,
        "errors": output_errors,
    }
    if output_errors:
        base_result["valid"] = False

    return base_result
