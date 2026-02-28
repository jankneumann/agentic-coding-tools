#!/usr/bin/env python3
"""Validate work-queue result payloads against work-queue-result.schema.json.

Performs:
1. JSON Schema validation
2. Scope check: files_modified ⊆ write_allow minus deny
3. Verification consistency: result.verification.passed matches all steps

Callable as a library function or via CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:
    sys.exit("jsonschema is required: pip install jsonschema")

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "openspec"
    / "schemas"
    / "work-queue-result.schema.json"
)


def load_schema(path: Path | None = None) -> dict[str, Any]:
    """Load the work-queue-result JSON schema."""
    schema_path = path or SCHEMA_PATH
    with open(schema_path) as f:
        return json.load(f)


def validate_schema(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Validate data against JSON schema, return list of error strings."""
    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path)
        errors.append(f"  {path}: {error.message}" if path else f"  {error.message}")
    return errors


def validate_scope_compliance(data: dict[str, Any]) -> list[str]:
    """Check that files_modified ⊆ write_allow and not in deny."""
    errors = []
    scope = data.get("scope", {})
    write_allow = scope.get("write_allow", [])
    deny = scope.get("deny", [])
    files_modified = data.get("files_modified", [])

    for f in files_modified:
        allowed = any(fnmatch(f, pattern) for pattern in write_allow)
        denied = any(fnmatch(f, pattern) for pattern in deny)

        if denied:
            errors.append(f"  '{f}' matches a deny pattern")
        elif not allowed:
            errors.append(f"  '{f}' not covered by any write_allow pattern")

    return errors


def validate_verification_consistency(data: dict[str, Any]) -> list[str]:
    """Check that verification.passed is consistent with step results."""
    errors = []
    verification = data.get("verification", {})
    overall_passed = verification.get("passed")
    steps = verification.get("steps", [])

    if not steps:
        return errors

    all_steps_passed = all(s.get("passed", False) for s in steps)

    if overall_passed and not all_steps_passed:
        failing = [s["name"] for s in steps if not s.get("passed", False)]
        errors.append(
            f"  verification.passed=true but steps failed: {failing}"
        )

    if not overall_passed and all_steps_passed:
        errors.append(
            "  verification.passed=false but all steps passed"
        )

    return errors


def validate_result(
    data: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full validation of a work-queue result payload.

    Returns a results dict with:
      - valid: bool
      - checks: dict of check_name -> {passed, errors}
    """
    if schema is None:
        schema = load_schema()

    results: dict[str, Any] = {"valid": True, "checks": {}}

    # 1. JSON Schema validation
    schema_errors = validate_schema(data, schema)
    results["checks"]["schema"] = {"passed": not schema_errors, "errors": schema_errors}
    if schema_errors:
        results["valid"] = False

    # 2. Scope compliance
    scope_errors = validate_scope_compliance(data)
    results["checks"]["scope_compliance"] = {
        "passed": not scope_errors,
        "errors": scope_errors,
    }
    if scope_errors:
        results["valid"] = False

    # 3. Verification consistency
    verification_errors = validate_verification_consistency(data)
    results["checks"]["verification_consistency"] = {
        "passed": not verification_errors,
        "errors": verification_errors,
    }
    if verification_errors:
        results["valid"] = False

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate work-queue result payloads against schema"
    )
    parser.add_argument("path", type=Path, help="Path to result JSON file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Path to work-queue-result.schema.json",
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"Error: {args.path} not found", file=sys.stderr)
        return 1

    with open(args.path) as f:
        data = json.load(f)

    schema = load_schema(args.schema)
    results = validate_result(data, schema)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        status = "VALID" if results["valid"] else "INVALID"
        print(f"work-queue-result validation: {status}")
        for check_name, check_result in results["checks"].items():
            symbol = "pass" if check_result["passed"] else "FAIL"
            print(f"  [{symbol}] {check_name}")
            for err in check_result.get("errors", []):
                print(f"    {err}")

    return 0 if results["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
