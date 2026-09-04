#!/usr/bin/env python3
"""Validate a simplify review artifact and render its prune ledger.

The artifact (``simplify-review.json``) is the contract between the two roles of
``/simplify-implementation``: the **Review** role writes it, the **Apply** role
consumes it. It is a review-findings document with ``review_type: simplify``,
governed by ``schemas/simplify-review.schema.json`` (a copy of the change's
contract) composed by ``allOf`` over the canonical
``openspec/schemas/review-findings.schema.json``, which is resolved through
``parallel-infrastructure/scripts/review_findings_schema.py``.

Two subcommands:

``validate <artifact>``
    Check the artifact against both documents. Exits ``2`` when it does not
    conform, naming the failing finding and the failing path, so a broken
    reviewer is visible rather than silently accepted.

``render-ledger <artifact> [--out <path>]``
    Emit ``test-prune-ledger.md`` from every ``test_quality`` finding with
    ``disposition: fix``, in the exact format ``check_test_prune.py`` parses.
    The ledger is the *reviewer's* decision: rendering it means the Apply role
    cannot justify a deletion the Review role did not make, and the existing
    prune gate becomes a check that the implementer did what the reviewer said.
    A finding's removal target is its ``test_id`` (a test nodeid) when present,
    otherwise its ``file_path`` — which ``check_test_prune.py`` accepts as a
    file-level entry covering every test in that file.

Usage:
    python3 simplify_review.py validate openspec/changes/<id>/simplify-review.json
    python3 simplify_review.py validate <artifact> --json
    python3 simplify_review.py render-ledger <artifact> --out <ledger.md>

Exit codes:
    0 — artifact conforms / ledger rendered
    2 — artifact does not conform (validate only)
    1 — usage, I/O, or missing-dependency error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CONTRACT_FILENAME = "simplify-review.schema.json"
CANONICAL_FILENAME = "review-findings.schema.json"

# Installed layout: <skill-base-dir>/scripts/simplify_review.py, with the
# sibling skill at <skill-base-dir>/../parallel-infrastructure/scripts.
_HERE = Path(__file__).resolve()
DEFAULT_CONTRACT_PATH = _HERE.parent.parent / "schemas" / CONTRACT_FILENAME
_SIBLING_SCRIPTS = _HERE.parents[2] / "parallel-infrastructure" / "scripts"


class HelperError(RuntimeError):
    """Anything that makes the artifact unreadable or unvalidatable (exit 1)."""


def find_canonical_schema_path() -> Path:
    """Locate the canonical review-findings schema.

    Prefers ``review_findings_schema.find_schema_path()`` — the single source of
    truth for this lookup — and falls back to the same walk-up (repo-root
    ``openspec/schemas``, then a skill-local ``install_assets`` copy) when the
    sibling skill is not installed alongside this one.
    """
    if _SIBLING_SCRIPTS.is_dir() and str(_SIBLING_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SIBLING_SCRIPTS))
    try:
        from review_findings_schema import find_schema_path  # noqa: PLC0415
    except ImportError:
        pass
    else:
        return find_schema_path()

    bases = [_HERE, *_HERE.parents]
    for relative in (
        Path("openspec") / "schemas" / CANONICAL_FILENAME,
        Path("install_assets") / "openspec" / "schemas" / CANONICAL_FILENAME,
    ):
        for base in bases:
            candidate = base / relative
            if candidate.is_file():
                return candidate
    raise HelperError(
        f"could not locate {CANONICAL_FILENAME} in openspec/schemas or "
        f"install_assets/openspec/schemas above {_HERE}"
    )


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HelperError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HelperError(f"{label} is not valid JSON ({path}): {exc}") from exc


def _format_path(parts: list[Any]) -> str:
    if not parts:
        return "<document>"
    out = str(parts[0])
    for part in parts[1:]:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def _finding_id(document: dict[str, Any], parts: list[Any]) -> int | None:
    if len(parts) < 2 or parts[0] != "findings" or not isinstance(parts[1], int):
        return None
    findings = document.get("findings")
    if not isinstance(findings, list) or parts[1] >= len(findings):
        return None
    finding = findings[parts[1]]
    return finding.get("id") if isinstance(finding, dict) else None


def validate_document(
    document: dict[str, Any], contract_path: Path
) -> list[dict[str, Any]]:
    """Return one record per schema violation (empty when the artifact conforms)."""
    try:
        from jsonschema import Draft202012Validator  # noqa: PLC0415
        from referencing import Registry, Resource  # noqa: PLC0415
        from referencing.jsonschema import DRAFT202012  # noqa: PLC0415
    except ImportError as exc:
        raise HelperError(
            "validation requires `jsonschema` and `referencing`; install them "
            "(they are declared dependencies of skills/pyproject.toml) and re-run — "
            f"an unvalidated artifact is not a passing one ({exc})"
        ) from exc

    contract = load_json(contract_path, "contract schema")
    canonical = load_json(find_canonical_schema_path(), "canonical schema")
    registry = Registry().with_resources(
        [
            (doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
            for doc in (canonical, contract)
        ]
    )
    validator = Draft202012Validator(contract, registry=registry)

    records: list[dict[str, Any]] = []
    for error in validator.iter_errors(document):
        parts = list(error.absolute_path)
        records.append(
            {
                "finding_id": _finding_id(document, parts),
                "path": _format_path(parts),
                "message": error.message,
            }
        )
    records.sort(key=lambda record: (record["path"], record["message"]))
    return records


def render_ledger(document: dict[str, Any]) -> str:
    """Render `test-prune-ledger.md` from the artifact's prune decisions."""
    lines = [
        "# Test prune ledger",
        "",
        "Rendered by `simplify_review.py render-ledger` from the simplify review",
        "artifact. Edit the artifact, not this file.",
        "",
    ]
    for finding in document.get("findings", []):
        if finding.get("type") != "test_quality" or finding.get("disposition") != "fix":
            continue
        prune = finding.get("prune") or {}
        reason = prune.get("reason")
        target = finding.get("test_id") or finding.get("file_path")
        if not reason or not target:
            raise HelperError(
                f"finding {finding.get('id')}: a test_quality finding with "
                "disposition fix needs `prune.reason` and a removal target "
                "(`test_id`, or `file_path` for a file-level removal)"
            )
        covered_by = prune.get("covered_by") or "none"
        lines += [
            f"- removed: {target}",
            f"  reason: {reason}",
            f"  covered-by: {covered_by}",
            "",
        ]
    return "\n".join(lines)


def _cmd_validate(args: argparse.Namespace) -> int:
    document = load_json(args.artifact, "artifact")
    errors = validate_document(document, args.contract)

    if args.json:
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
        return 2 if errors else 0

    if not errors:
        print(
            f"Simplify review artifact: OK\n"
            f"  artifact: {args.artifact}\n"
            f"  findings: {len(document.get('findings', []))}"
        )
        return 0

    print(
        f"Simplify review artifact: INVALID ({len(errors)} error(s))\n"
        f"  artifact: {args.artifact}",
        file=sys.stderr,
    )
    for record in errors:
        where = (
            f"finding {record['finding_id']} at {record['path']}"
            if record["finding_id"] is not None
            else record["path"]
        )
        print(f"    {where}: {record['message']}", file=sys.stderr)
    return 2


def _cmd_render_ledger(args: argparse.Namespace) -> int:
    document = load_json(args.artifact, "artifact")
    text = render_ledger(document)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"Prune ledger written: {args.out}")
    else:
        print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a simplify review artifact and render its prune ledger"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Check the artifact against its schemas")
    validate.add_argument("artifact", type=Path, help="Path to simplify-review.json")
    validate.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT_PATH,
        help="Contract schema (default: the copy bundled with this skill)",
    )
    validate.add_argument("--json", action="store_true", help="Emit JSON result")
    validate.set_defaults(func=_cmd_validate)

    render = sub.add_parser(
        "render-ledger", help="Emit test-prune-ledger.md from the artifact"
    )
    render.add_argument("artifact", type=Path, help="Path to simplify-review.json")
    render.add_argument("--out", type=Path, help="Ledger path (default: stdout)")
    render.set_defaults(func=_cmd_render_ledger)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except HelperError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
