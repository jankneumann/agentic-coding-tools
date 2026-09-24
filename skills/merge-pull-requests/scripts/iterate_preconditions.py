"""Fail-closed iterate-skill pairing for merge-plan nodes."""

from __future__ import annotations

from typing import Any


def iterate_precondition_error(
    node: dict[str, Any],
    *,
    proposal_approved: bool,
) -> str | None:
    """Return a blocking reason if the node/skill pairing is illegal.

    ``/iterate-on-plan`` requires an unapproved proposal.
    ``/iterate-on-implementation`` requires an approved proposal.
    """

    skill = node["definition"].get("remediation_skill")
    kind = node["definition"].get("kind")
    if skill == "iterate-on-plan" or kind == "plan":
        if proposal_approved:
            return "iterate-on-plan requires an unapproved proposal"
        return None
    if skill == "iterate-on-implementation" or kind == "implementation":
        if not proposal_approved:
            return "iterate-on-implementation requires an approved proposal"
        return None
    return None
