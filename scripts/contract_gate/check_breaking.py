#!/usr/bin/env python3
"""Contract breaking-change gate (OpenSpec change generate-coordinator-clients-from-contracts, D4).

Compares every promoted OpenAPI document (``openspec/contracts/**/openapi/*.yaml``)
that this branch changes against its version at the merge base, using
``oasdiff breaking -f json``, and fails on any ERR-level finding that no touched
OpenSpec change directory acknowledges.

Acknowledgements live in ``openspec/changes/<id>/contracts/accepted-breaking-changes.yaml``
(or the archived ``openspec/changes/archive/<date>-<id>/...``) as::

    accepted:
      - document: openspec/contracts/<cap>/openapi/<name>.yaml
        operation: "METHOD /path"
        rule_id: <oasdiff check id>
        rationale: <why>

Only exact ``(document, operation, rule_id)`` matches suppress a finding, and only
files inside change directories this branch touches are read. Acknowledgements
that match nothing are printed as warnings.

Change-local contracts (``openspec/changes/**``) are never gated. Added promoted
documents are reported and pass. Deleted promoted documents produce the finding
``(document, "*", "contract-document-deleted")``. Renames are not detected
(``--no-renames``): a rename is a delete plus an add, so it needs that
acknowledgement too — moving a published document is breaking for its clients.

Exit codes: 0 pass, 1 unacknowledged breaking change, 2 apparatus error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

ACK_FILENAME = "accepted-breaking-changes.yaml"
DELETED_RULE = "contract-document-deleted"

# (base_file, head_file) -> oasdiff stdout
OasdiffRunner = Callable[[str, str], str]


class GateError(Exception):
    """Apparatus failure: the gate could not produce a verdict."""


@dataclass(frozen=True)
class Finding:
    document: str
    operation: str  # "METHOD /path", or "*" for document-level findings
    rule_id: str
    text: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.document, self.operation, self.rule_id)


# --- oasdiff output -----------------------------------------------------------
#
# Field names (id, text, level, operation, path) come from oasdiff's ApiChange
# JSON as emitted by `oasdiff breaking -f json` (v1.33.0). `level` is the
# checker.Level integer (ERR=3, WARN=2, INFO=1); string spellings are accepted
# defensively. These assumptions are confirmed by the gate's first CI run
# against the real binary; unknown extra fields are ignored.

_ERROR_STRINGS = {"err", "error"}


def is_error_level(level: object) -> bool:
    if isinstance(level, bool):
        return False
    if isinstance(level, int):
        return level == 3
    if isinstance(level, str):
        return level.strip().lower() in _ERROR_STRINGS
    return False


def parse_oasdiff_output(stdout: str) -> list[dict]:
    """Parse `oasdiff breaking -f json` output; empty/null means no changes."""
    if not stdout.strip():
        return []
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise GateError(f"oasdiff produced non-JSON output: {exc}") from exc
    if data is None:
        return []
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise GateError("oasdiff JSON output is not a list of objects")
    return data


def breaking_findings(document: str, stdout: str) -> list[Finding]:
    findings = []
    for change in parse_oasdiff_output(stdout):
        if not is_error_level(change.get("level")):
            continue
        method = str(change.get("operation") or "").upper()
        path = str(change.get("path") or "")
        operation = f"{method} {path}".strip() or "*"
        findings.append(
            Finding(
                document=document,
                operation=operation,
                rule_id=str(change.get("id") or "<unknown-rule>"),
                text=str(change.get("text") or ""),
            )
        )
    return findings


def subprocess_oasdiff(binary: str) -> OasdiffRunner:
    def run(base_file: str, head_file: str) -> str:
        proc = subprocess.run(
            [binary, "breaking", "-f", "json", base_file, head_file],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise GateError(
                f"oasdiff exited {proc.returncode} comparing {head_file}: {proc.stderr.strip()}"
            )
        return proc.stdout

    return run


# --- git ----------------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def is_promoted_contract(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return (
        len(parts) >= 4
        and parts[:2] == ("openspec", "contracts")
        and parts[-2] == "openapi"
        and parts[-1].endswith(".yaml")
    )


def change_dir_of(path: str) -> str | None:
    """The OpenSpec change directory a path lives in, if any."""
    parts = PurePosixPath(path).parts
    if len(parts) < 4 or parts[:2] != ("openspec", "changes"):
        return None
    if parts[2] == "archive":
        return "/".join(parts[:4]) if len(parts) >= 5 else None
    return "/".join(parts[:3])


# --- acknowledgements ---------------------------------------------------------


def load_acknowledgements(repo_root: Path, change_dirs: set[str]) -> dict[tuple, str]:
    """Map (document, operation, rule_id) -> the ack file that declared it."""
    acks: dict[tuple, str] = {}
    for change_dir in sorted(change_dirs):
        rel = f"{change_dir}/contracts/{ACK_FILENAME}"
        ack_file = repo_root / rel
        if not ack_file.is_file():
            continue
        try:
            data = yaml.safe_load(ack_file.read_text()) or {}
        except yaml.YAMLError as exc:
            raise GateError(f"{rel}: invalid YAML: {exc}") from exc
        entries = data.get("accepted") if isinstance(data, dict) else None
        if entries is None:
            continue
        if not isinstance(entries, list):
            raise GateError(f"{rel}: 'accepted' must be a list")
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise GateError(f"{rel}: accepted[{i}] must be a mapping")
            missing = [
                k for k in ("document", "operation", "rule_id") if not entry.get(k)
            ]
            if missing:
                raise GateError(f"{rel}: accepted[{i}] missing {', '.join(missing)}")
            key = (
                str(entry["document"]),
                str(entry["operation"]),
                str(entry["rule_id"]),
            )
            acks.setdefault(key, rel)
    return acks


# --- gate ---------------------------------------------------------------------


def run_gate(*, repo_root: Path, base: str, run_oasdiff: OasdiffRunner) -> int:
    try:
        return _run_gate(repo_root, base, run_oasdiff)
    except GateError as exc:
        print(f"ERROR: {exc}")
        return 2


def _run_gate(repo_root: Path, base: str, run_oasdiff: OasdiffRunner) -> int:
    merge_base = _git(repo_root, "merge-base", base, "HEAD").strip()
    diff = _git(repo_root, "diff", "--no-renames", "--name-status", merge_base, "HEAD")

    changes: list[tuple[str, str]] = []
    for line in diff.splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        changes.append((status[:1], path))

    contracts = [(s, p) for s, p in changes if is_promoted_contract(p)]
    if not contracts:
        print("no promoted contracts changed")
        return 0

    findings: list[Finding] = []
    for status, path in contracts:
        if status == "A":
            print(f"NEW       {path} (no base version; not compared)")
        elif status == "D":
            findings.append(
                Finding(path, "*", DELETED_RULE, "promoted contract document deleted")
            )
        else:
            base_text = _git(repo_root, "show", f"{merge_base}:{path}")
            with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
                tmp.write(base_text)
            try:
                stdout = run_oasdiff(tmp.name, str(repo_root / path))
            finally:
                Path(tmp.name).unlink(missing_ok=True)
            print(f"COMPARED  {path}")
            findings.extend(breaking_findings(path, stdout))

    touched = {d for _, p in changes if (d := change_dir_of(p))}
    acks = load_acknowledgements(repo_root, touched)

    used: set[tuple] = set()
    unacknowledged: list[Finding] = []
    for finding in findings:
        if finding.key in acks:
            used.add(finding.key)
            print(
                f"ACKNOWLEDGED  {finding.document}  {finding.operation}  {finding.rule_id}"
                f"  (by {acks[finding.key]})"
            )
        else:
            unacknowledged.append(finding)

    for key, source in acks.items():
        if key not in used:
            doc, op, rule = key
            print(
                f"WARNING   stale acknowledgement in {source}: {doc}  {op}  {rule} matched nothing"
            )

    for finding in unacknowledged:
        print(
            f"BREAKING  {finding.document}  {finding.operation}  {finding.rule_id}: {finding.text}"
        )

    if unacknowledged:
        print(
            f"\n{len(unacknowledged)} unacknowledged breaking change(s). To accept one, add "
            f"{{document, operation, rule_id, rationale}} to "
            f"openspec/changes/<id>/contracts/{ACK_FILENAME} in a change this branch touches."
        )
        return 1
    print("contract breaking-change gate passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base", default="origin/main", help="ref to merge-base against"
    )
    parser.add_argument(
        "--oasdiff", default="oasdiff", help="path to the oasdiff binary"
    )
    parser.add_argument("--repo-root", default=".", type=Path)
    args = parser.parse_args(argv)
    return run_gate(
        repo_root=args.repo_root.resolve(),
        base=args.base,
        run_oasdiff=subprocess_oasdiff(args.oasdiff),
    )


if __name__ == "__main__":
    sys.exit(main())
