#!/usr/bin/env python3
"""Validate work-queue result payloads against work-queue-result.schema.json.

Performs:
1. JSON Schema validation
2. Scope check: files_modified ⊆ write_allow minus deny
3. Verification consistency: steps are non-empty, no not_run step passes, and
   result.verification.passed matches all steps
4. Outcome consistency: an explicit outcome never claims more than the evidence
5. Commit resolution: git.head.commit resolves in the package worktree (only when
   a worktree path is supplied; otherwise recorded as skipped)

Callable as a library function or via CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:
    sys.exit("jsonschema is required: pip install jsonschema")

def _find_repo_root() -> Path:
    """Find the git repository root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: walk up from this file looking for .git
        p = Path(__file__).resolve().parent
        while p != p.parent:
            if (p / ".git").exists() or (p / "openspec").exists():
                return p
            p = p.parent
        return Path(__file__).resolve().parent.parent


SCHEMA_PATH = (
    _find_repo_root()
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
        errors.append(
            "  no verification steps: an empty step list cannot support "
            f"verification.passed={str(bool(overall_passed)).lower()}"
        )
        return errors

    for s in steps:
        if s.get("method") == "not_run" and s.get("passed", False):
            errors.append(
                f"  step '{s.get('name', '?')}' has method=not_run but passed=true"
            )

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


OUTCOMES = ("PASS", "ISSUES", "BLOCKED")
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
COMMIT_CHECK_TIMEOUT_SECONDS = 10


def derive_outcome(data: dict[str, Any]) -> str:
    """Derive PASS / ISSUES / BLOCKED from a result's evidence.

    This is the only derivation; every consumer calls it (directly or via
    ``effective_outcome``) so the rule lives in one place.
    """
    if data.get("status") == "failed":
        return "BLOCKED"
    verification = data.get("verification") or {}
    steps = verification.get("steps") or []
    scope_check = data.get("scope_check") or {}
    if (
        data.get("status") == "completed"
        and steps
        and all(s.get("passed") is True for s in steps)
        and verification.get("passed") is True
        and scope_check.get("passed") is not False
    ):
        return "PASS"
    return "ISSUES"


def effective_outcome(data: dict[str, Any]) -> str:
    """The explicit ``outcome`` when present, otherwise the derived one."""
    outcome = data.get("outcome")
    if outcome is not None:
        return outcome
    return derive_outcome(data)


def validate_outcome_consistency(data: dict[str, Any]) -> list[str]:
    """Reject an explicit outcome that claims more than the evidence.

    Downgrades (ISSUES/BLOCKED over passing evidence) are allowed.
    """
    errors: list[str] = []
    if "outcome" not in data:
        return errors
    outcome = data.get("outcome")
    if outcome not in OUTCOMES:
        errors.append(f"  outcome={outcome!r} is not one of {list(OUTCOMES)}")
        return errors
    derived = derive_outcome(data)
    if outcome == "PASS" and derived != "PASS":
        errors.append(
            f"  outcome=PASS but the evidence derives {derived}"
        )
    if data.get("status") == "failed" and outcome != "BLOCKED":
        errors.append(
            f"  status=failed requires outcome=BLOCKED, got outcome={outcome}"
        )
    return errors


# Variables that would point ``git`` at a repository other than the one at
# ``cwd``; an inherited value (as inside a git hook) must not redirect the check.
_GIT_LOCATION_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def validate_commit_resolves(
    data: dict[str, Any], worktree_path: str | Path,
) -> dict[str, Any]:
    """Check that ``git.head.commit`` resolves to a commit in ``worktree_path``."""
    commit = ((data.get("git") or {}).get("head") or {}).get("commit")
    path = Path(worktree_path)

    def _fail(msg: str) -> dict[str, Any]:
        return {"passed": False, "errors": [f"  {msg}"]}

    if not isinstance(commit, str) or not _COMMIT_RE.match(commit):
        return _fail(
            f"git.head.commit {commit!r} is not a 7-64 character hex SHA; "
            f"not checked against {path}"
        )
    if not path.is_dir():
        return _fail(f"commit {commit} not checked: worktree {path} is not a directory")
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
            cwd=path,
            env={
                k: v for k, v in os.environ.items() if k not in _GIT_LOCATION_ENV
            },
            capture_output=True,
            text=True,
            timeout=COMMIT_CHECK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _fail(f"commit {commit} check timed out in worktree {path}")
    except OSError as exc:
        return _fail(f"commit {commit} could not be checked in worktree {path}: {exc}")
    if proc.returncode != 0:
        return _fail(f"commit {commit} does not resolve in worktree {path}")
    return {"passed": True, "errors": []}


def validate_result(
    data: dict[str, Any],
    schema: dict[str, Any] | None = None,
    *,
    worktree_path: str | Path | None = None,
) -> dict[str, Any]:
    """Full validation of a work-queue result payload.

    Returns a results dict with:
      - valid: bool
      - checks: dict of check_name -> {passed, errors}; ``commit_resolves``
        carries ``skipped: true`` when no ``worktree_path`` was supplied.
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

    # 4. Outcome consistency
    outcome_errors = validate_outcome_consistency(data)
    results["checks"]["outcome_consistency"] = {
        "passed": not outcome_errors,
        "errors": outcome_errors,
    }
    if outcome_errors:
        results["valid"] = False

    # 5. Commit resolution (opt-in; a skip is recorded, never reported as checked)
    if worktree_path is None:
        results["checks"]["commit_resolves"] = {
            "passed": True,
            "skipped": True,
            "errors": [],
            "reason": "no worktree_path supplied",
        }
    else:
        commit_check = validate_commit_resolves(data, worktree_path)
        results["checks"]["commit_resolves"] = commit_check
        if not commit_check["passed"]:
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
    parser.add_argument(
        "--worktree",
        type=Path,
        default=None,
        help="Package worktree path; enables the commit_resolves check",
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"Error: {args.path} not found", file=sys.stderr)
        return 1

    with open(args.path) as f:
        data = json.load(f)

    schema = load_schema(args.schema)
    results = validate_result(data, schema, worktree_path=args.worktree)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        status = "VALID" if results["valid"] else "INVALID"
        print(f"work-queue-result validation: {status}")
        for check_name, check_result in results["checks"].items():
            if check_result.get("skipped"):
                symbol = "skip"
            else:
                symbol = "pass" if check_result["passed"] else "FAIL"
            print(f"  [{symbol}] {check_name}")
            for err in check_result.get("errors", []):
                print(f"    {err}")

    return 0 if results["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
