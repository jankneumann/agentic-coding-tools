"""Shared fixture builders for the requirement-traceability gate's tests
(wp-gate, tasks 3.1-3.16).

Every builder writes under an injected root (never a repo-relative default)
so the gate's tests build their own tmp_path trees rather than fixture files
checked in under ``openspec/contracts/**`` — this package cannot and must
not write there (denied to wp-gate's ``write_allow``).

Imported by inserting this directory onto ``sys.path`` (see each test
file's header) rather than as a dotted package import, so no
``tests/fixtures/__init__.py`` is needed outside this task's own
``tests/fixtures/traceability/**`` scope.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "gate-test",
    "GIT_AUTHOR_EMAIL": "gate-test@example.invalid",
    "GIT_COMMITTER_NAME": "gate-test",
    "GIT_COMMITTER_EMAIL": "gate-test@example.invalid",
}


def write_spec(specs_root: Path, capability: str, headings: list[str]) -> None:
    """A minimal archived spec with one requirement per heading."""
    body = "## Requirements\n\n" + "\n\n".join(
        f"### Requirement: {h}\n\nThe system SHALL do the {h} thing.\n\n"
        f"#### Scenario: it happens\n\n- WHEN x\n- THEN y\n"
        for h in headings
    )
    target = specs_root / capability / "spec.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def write_delta(
    changes_root: Path,
    change_id: str,
    capability: str,
    *,
    added: list[str] | None = None,
    modified: list[str] | None = None,
    removed: list[str] | None = None,
    renamed: list[tuple[str, str]] | None = None,
) -> None:
    parts: list[str] = []
    if added:
        parts.append(
            "## ADDED Requirements\n\n"
            + "\n\n".join(
                f"### Requirement: {h}\n\nThe system SHALL do the {h} thing.\n" for h in added
            )
        )
    if modified:
        parts.append(
            "## MODIFIED Requirements\n\n"
            + "\n\n".join(
                f"### Requirement: {h}\n\nThe system SHALL do the {h} thing, revised.\n"
                for h in modified
            )
        )
    if removed:
        parts.append(
            "## REMOVED Requirements\n\n" + "\n\n".join(f"### Requirement: {h}\n" for h in removed)
        )
    if renamed:
        lines = ["## RENAMED Requirements\n"]
        for old, new in renamed:
            lines.append(f"- FROM: `### Requirement: {old}`")
            lines.append(f"- TO: `### Requirement: {new}`")
        parts.append("\n".join(lines))
    target = changes_root / change_id / "specs" / capability / "spec.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def _operation(operation_id: str, path: str, method: str = "get", **extra: Any) -> dict[str, Any]:
    op: dict[str, Any] = {"operationId": operation_id}
    op.update(extra)
    return {"path": path, "method": method, "op": op}


def write_openapi_doc(
    contracts_root: Path,
    capability: str,
    filename: str,
    operations: list[dict[str, Any]],
    *,
    location: str = "openapi",
) -> Path:
    """``operations``: list of dicts from :func:`op` below."""
    paths: dict[str, Any] = {}
    for entry in operations:
        paths.setdefault(entry["path"], {})[entry["method"]] = entry["op"]
    document = {
        "openapi": "3.1.0",
        "info": {"title": capability, "version": "1"},
        "paths": paths,
    }
    subdir = (
        contracts_root / capability
        if location == "root"
        else contracts_root / capability / location
    )
    subdir.mkdir(parents=True, exist_ok=True)
    target = subdir / filename
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return target


def op(operation_id: str, path: str, method: str = "get", **extra: Any) -> dict[str, Any]:
    """One entry for :func:`write_openapi_doc`'s ``operations`` list.

    ``extra`` may include ``x_traceability={"requirements": [...]}`` or
    ``x_traceability={"excluded": {"reason": ...}}`` — translated to the
    real ``x-traceability`` key (Python identifiers can't spell the dash).
    """
    if "x_traceability" in extra:
        extra["x-traceability"] = extra.pop("x_traceability")
    return _operation(operation_id, path, method, **extra)


def write_cli_doc(
    contracts_root: Path,
    capability: str,
    filename: str,
    commands: list[dict[str, Any]],
    *,
    tool_name: str | None = None,
    location: str = "cli",
) -> Path:
    document = {
        "contract_version": "1",
        "tool": {"name": tool_name or capability, "executable": tool_name or capability},
        "commands": commands,
    }
    subdir = (
        contracts_root / capability
        if location == "root"
        else contracts_root / capability / location
    )
    subdir.mkdir(parents=True, exist_ok=True)
    target = subdir / filename
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return target


def write_exclusions(
    contracts_root: Path,
    capability: str,
    entries: list[dict[str, str]] | None = None,
    *,
    raw_text: str | None = None,
) -> Path:
    target = contracts_root / capability / "traceability-exclusions.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    if raw_text is not None:
        target.write_text(raw_text, encoding="utf-8")
    else:
        target.write_text(
            yaml.safe_dump({"exclusions": entries or []}, sort_keys=False), encoding="utf-8"
        )
    return target


def git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=True,
        env=_GIT_ENV,
    )


def init_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    git(repo_root, "init", "-q", "-b", "main")
    git(repo_root, "config", "user.name", "gate-test")
    git(repo_root, "config", "user.email", "gate-test@example.invalid")


def commit_all(repo_root: Path, message: str) -> str:
    git(repo_root, "add", "-A")
    git(repo_root, "commit", "-q", "-m", message, "--allow-empty")
    return git(repo_root, "rev-parse", "HEAD").stdout.strip()


def checkout_branch(repo_root: Path, branch: str) -> None:
    """New branch from the current HEAD — the change's own branch, diverging
    from ``main`` at exactly the commit already made there. Without this,
    committing everything directly to ``main`` makes ``git merge-base main
    HEAD`` resolve to HEAD itself (they are the same ref), and every diff
    against it comes back empty regardless of what actually changed.
    """
    git(repo_root, "checkout", "-q", "-b", branch)
