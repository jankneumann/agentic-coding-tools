#!/usr/bin/env python3
"""Core contract and graph operations for durable merge plans."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "contracts"
    / "merge-plan.schema.json"
)


class MergePlanValidationError(ValueError):
    """Raised when a merge plan violates its schema or DAG invariants."""


def _schema_error_message(error: Any) -> str:
    location = ".".join(str(part) for part in error.absolute_path)
    if location:
        return f"{location}: {error.message}"
    return error.message


def _validate_schema(plan: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(plan), key=lambda item: list(item.path))
    if errors:
        raise MergePlanValidationError(_schema_error_message(errors[0]))


def _validate_dag(plan: dict[str, Any]) -> None:
    nodes = plan["nodes"]
    numbers = [node["pr"] for node in nodes]
    if len(numbers) != len(set(numbers)):
        raise MergePlanValidationError("duplicate PR nodes are not allowed")

    known = set(numbers)
    dependencies: dict[int, list[int]] = {}
    for node in nodes:
        pr_number = node["pr"]
        depends_on = node["definition"]["depends_on"]
        if pr_number in depends_on:
            raise MergePlanValidationError(
                f"PR #{pr_number} cannot depend on itself",
            )
        unknown = sorted(set(depends_on) - known)
        if unknown:
            raise MergePlanValidationError(
                f"PR #{pr_number} depends on unknown PR #{unknown[0]}",
            )
        dependencies[pr_number] = depends_on

    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(pr_number: int) -> None:
        if pr_number in visiting:
            raise MergePlanValidationError("dependency cycle detected")
        if pr_number in visited:
            return
        visiting.add(pr_number)
        for dependency in dependencies[pr_number]:
            visit(dependency)
        visiting.remove(pr_number)
        visited.add(pr_number)

    for number in numbers:
        visit(number)


def _validate_execution_semantics(plan: dict[str, Any]) -> None:
    """Reject contradictory or privilege-expanding gate declarations.

    JSON Schema can constrain the vocabulary, but it cannot express the
    relationship between origin, gate markers, and automatic execution.  Keep
    those invariants in the same semantic validation layer as the DAG rules so
    every producer and consumer sees the same fail-closed contract.
    """

    for node in plan["nodes"]:
        number = node["pr"]
        origin = node["origin"]
        auto_executable = node["auto_executable"]
        gates = node["definition"]["gates"]

        if origin == "openspec":
            if auto_executable:
                raise MergePlanValidationError(
                    f"OpenSpec PR #{number} cannot be auto-executable",
                )
            if "proposal_acceptance" not in gates:
                raise MergePlanValidationError(
                    f"OpenSpec PR #{number} requires the proposal_acceptance gate",
                )

        if auto_executable and gates:
            raise MergePlanValidationError(
                f"auto-executable PR #{number} cannot carry human gates",
            )
        if not auto_executable and not gates:
            raise MergePlanValidationError(
                f"non-auto-executable PR #{number} must carry at least one gate",
            )


def validate_plan(plan: dict[str, Any]) -> None:
    """Validate the shipped JSON contract and producer-enforced DAG rules."""

    _validate_schema(plan)
    _validate_dag(plan)
    _validate_execution_semantics(plan)


def amend_plan(
    plan: dict[str, Any],
    prerequisite_node: dict[str, Any],
    *,
    affected_prs: list[int],
    reason: str,
) -> dict[str, Any]:
    """Append a discovered prerequisite and block affected pending nodes."""

    validate_plan(plan)
    amended = copy.deepcopy(plan)
    existing = {node["pr"]: node for node in amended["nodes"]}
    prerequisite = copy.deepcopy(prerequisite_node)
    prerequisite_number = prerequisite.get("pr")
    if prerequisite_number in existing:
        raise MergePlanValidationError(
            f"PR #{prerequisite_number} already exists in the merge plan",
        )
    unknown = sorted(set(affected_prs) - set(existing))
    if unknown:
        raise MergePlanValidationError(
            f"affected PR #{unknown[0]} is not present in the merge plan",
        )
    if not reason.strip():
        raise MergePlanValidationError("an amendment reason is required")

    prerequisite["definition"]["inserted_reason"] = reason.strip()
    amended["nodes"].append(prerequisite)
    for pr_number in affected_prs:
        node = existing[pr_number]
        dependencies = node["definition"]["depends_on"]
        if prerequisite_number not in dependencies:
            dependencies.append(prerequisite_number)
            dependencies.sort()
        if node["state"]["outcome"] == "pending":
            node["state"]["blocking_reason"] = (
                f"waiting for prerequisite #{prerequisite_number}: {reason.strip()}"
            )

    validate_plan(amended)
    return amended
