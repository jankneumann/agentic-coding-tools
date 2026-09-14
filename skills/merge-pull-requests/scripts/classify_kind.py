"""Classify merge-plan nodes as plan, implementation, or automation."""

from __future__ import annotations

from typing import Any, Iterable

AUTOMATION_ORIGINS = frozenset(
    {"dependabot", "renovate", "sentinel", "bolt", "palette", "jules"}
)
KIND_TO_SKILL = {
    "plan": "iterate-on-plan",
    "implementation": "iterate-on-implementation",
    "automation": "none",
}


def change_id_from_pr(pr: dict[str, Any]) -> str | None:
    explicit = pr.get("change_id")
    if explicit:
        return str(explicit)
    branch = str(pr.get("branch") or "")
    if branch.startswith("openspec/"):
        return branch.removeprefix("openspec/")
    return None


def _files(changed_files: Iterable[str]) -> list[str]:
    return [str(path) for path in changed_files]


def _heuristic_kind(pr: dict[str, Any], files: list[str]) -> str:
    origin = str(pr.get("origin", "other"))
    if origin in AUTOMATION_ORIGINS:
        return "automation"
    change_id = change_id_from_pr(pr)
    prefix = f"openspec/changes/{change_id}/" if change_id else None
    if prefix and files and all(path.startswith(prefix) for path in files):
        return "plan"
    return "implementation"


def _remediation_skill(kind: str, change_id: str | None) -> str:
    if kind == "plan":
        return "iterate-on-plan"
    if kind == "automation":
        return "none"
    if change_id:
        return "iterate-on-implementation"
    return "quick-task"


def classify_kind(
    pr: dict[str, Any],
    changed_files: Iterable[str],
    *,
    kind_override: str | None = None,
) -> dict[str, Any]:
    """Return definition fields for kind, change_id, and remediation_skill.

    After an operator override, persisted values are authoritative; pass
    ``kind_override`` instead of re-running the heuristic as authority.
    """

    files = _files(changed_files)
    overridden = kind_override is not None
    kind = kind_override if kind_override is not None else _heuristic_kind(pr, files)
    if kind not in KIND_TO_SKILL:
        raise ValueError(f"unknown kind {kind!r}")
    change_id = change_id_from_pr(pr)
    skill = _remediation_skill(kind, change_id)
    if kind_override == "plan":
        skill = "iterate-on-plan"
    elif kind_override == "implementation":
        skill = "iterate-on-implementation" if change_id else "quick-task"
    elif kind_override == "automation":
        skill = "none"
    return {
        "kind": kind,
        "change_id": change_id,
        "remediation_skill": skill,
        "kind_overridden": overridden,
    }


def classify_ci_failure(
    pr: dict[str, Any],
    staleness: dict[str, Any],
    ci_state: str,
) -> str | None:
    """Return a CI-failure class for failing nodes, else None."""

    if ci_state not in {"blocked", "dirty"}:
        return None
    supplied = pr.get("ci_failure_class")
    if supplied in {"transient", "pr_specific", "stale_base"}:
        return str(supplied)
    if staleness.get("ci_merge_base_stale"):
        return "stale_base"
    return "pr_specific"
