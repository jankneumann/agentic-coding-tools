#!/usr/bin/env python3
"""Fail a work package that invalidates context it never declared (ri-08).

Enforcement keys off *whether the declaration exists*, not on a global mode:

| Package state          | Implied surface not declared | Result               |
|------------------------|------------------------------|----------------------|
| has `context_impact`   | no rationale                 | `undeclared` -> exit 1 |
| has `context_impact`   | rationale with `approved_by` | `rationalized` -> pass |
| has `context_impact`   | nothing implied              | `declared` -> pass     |
| no `context_impact`    | anything implied             | `unmigrated` -> pass    |

That split is what lets the gate be strict without a flag day: every package in
the repository predates the field, so a single strict mode would fail all of
them. Declaring the block is opt-in but one-way — once you declare, you must be
complete. `--strict-legacy` promotes `unmigrated` to a failure so the repository
can flip to full enforcement in one flag once migration is done.

Usage:
    validate_context_impact.py <work-packages.yaml> --base <ref>
    validate_context_impact.py <work-packages.yaml> --changed-file <path> ...
    validate_context_impact.py <work-packages.yaml> --base main --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    sys.exit("pyyaml is required: pip install pyyaml")

from context_impact import (  # noqa: E402
    ContextImpactRulesError,
    ImpactRules,
    declared_rationale,
    declared_surfaces,
    infer_surfaces,
    load_rules,
)

#: Statuses that make the gate exit non-zero, most severe first. Order matters:
#: a package can be both `undeclared` and `spurious_rationale`, and reporting the
#: weaker one would understate the problem.
FAILING_STATUSES = ("undeclared", "spurious_rationale")


@dataclass(frozen=True)
class ContextImpactResult:
    """The gate's verdict for one work package."""

    package_id: str
    status: str
    declared: tuple[str, ...] | None
    implied: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    undeclared: tuple[str, ...] = ()
    rationalized: tuple[str, ...] = ()
    spurious: tuple[str, ...] = ()

    @property
    def failed(self) -> bool:
        """Whether this result fails the gate in the default mode."""
        return self.status in FAILING_STATUSES

    def failed_under(self, *, strict_legacy: bool) -> bool:
        """Whether this result fails, accounting for `--strict-legacy`."""
        if self.failed:
            return True
        return strict_legacy and self.status == "unmigrated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "status": self.status,
            "declared": sorted(self.declared) if self.declared is not None else None,
            "implied": {s: list(p) for s, p in sorted(self.implied.items())},
            "undeclared": list(self.undeclared),
            "rationalized": list(self.rationalized),
            "spurious": list(self.spurious),
        }


def evaluate(
    package: Mapping[str, Any],
    changed_files: Sequence[str],
    rules: ImpactRules,
    contract_files: Sequence[str] = (),
) -> ContextImpactResult:
    """Compare what a package declared against what its changed files imply."""
    package_id = str(package.get("package_id", "<unknown>"))
    implied = infer_surfaces(package, changed_files, rules, contract_files)
    declared = declared_surfaces(package)

    if declared is None:
        # No block at all: a compatibility result, reporting the inferred
        # surfaces so adopting the declaration is a paste rather than a puzzle.
        return ContextImpactResult(
            package_id=package_id,
            status="unmigrated",
            declared=None,
            implied=implied,
        )

    rationale = declared_rationale(package)
    missing = sorted(set(implied) - declared)
    rationalized = tuple(s for s in missing if _is_approved(rationale.get(s)))
    undeclared = tuple(s for s in missing if s not in rationalized)
    spurious = tuple(sorted(set(rationale) - set(implied)))

    if undeclared:
        status = "undeclared"
    elif spurious:
        status = "spurious_rationale"
    elif rationalized:
        status = "rationalized"
    else:
        status = "declared"

    return ContextImpactResult(
        package_id=package_id,
        status=status,
        declared=tuple(sorted(declared)),
        implied=implied,
        undeclared=undeclared,
        rationalized=rationalized,
        spurious=spurious,
    )


def _is_approved(entry: Any) -> bool:
    """A rationale silences the gate only when it is attributable."""
    return (
        isinstance(entry, Mapping)
        and bool(str(entry.get("reason", "")).strip())
        and bool(str(entry.get("approved_by", "")).strip())
    )


def changed_files_from_git(base: str, repo_root: Path) -> tuple[str, ...]:
    """Files changed on this branch relative to ``base``."""
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(
            f"git diff against {base!r} failed: {completed.stderr.strip()}"
        )
    return tuple(line for line in completed.stdout.splitlines() if line)


def contract_files_of(document: Mapping[str, Any]) -> tuple[str, ...]:
    contracts = document.get("contracts") or {}
    openapi = contracts.get("openapi") or {}
    return tuple(openapi.get("files") or ())


def _render(results: Sequence[ContextImpactResult], strict_legacy: bool) -> str:
    lines = []
    for result in results:
        marker = "FAIL" if result.failed_under(strict_legacy=strict_legacy) else "ok"
        lines.append(f"  [{marker}] {result.package_id}: {result.status}")
        if result.undeclared:
            for surface in result.undeclared:
                files = ", ".join(result.implied.get(surface, ())[:5])
                lines.append(f"      undeclared surface {surface!r} implied by: {files}")
        if result.spurious:
            lines.append(
                f"      rationale for surfaces that are not implied: "
                f"{', '.join(result.spurious)}"
            )
        if result.status == "unmigrated" and result.implied:
            lines.append(
                f"      add context_impact.surfaces: [{', '.join(sorted(result.implied))}]"
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate work-package context-impact declarations"
    )
    parser.add_argument("path", type=Path, help="Path to work-packages.yaml")
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--base",
        help="Git ref to diff against (uses `git diff --name-only <base>...HEAD`)",
    )
    source.add_argument(
        "--changed-file",
        action="append",
        default=[],
        metavar="PATH",
        help="Explicit changed file (repeatable). Skips git entirely.",
    )
    parser.add_argument(
        "--rules", type=Path, default=None, help="Override the impact rule table"
    )
    parser.add_argument(
        "--strict-legacy",
        action="store_true",
        help="Treat packages with no context_impact block as failures",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    if not args.path.is_file():
        print(f"work-packages file not found: {args.path}", file=sys.stderr)
        return 2

    try:
        rules = load_rules(args.rules)
    except ContextImpactRulesError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    document = yaml.safe_load(args.path.read_text()) or {}
    packages = document.get("packages") or []
    contract_files = contract_files_of(document)

    if args.base:
        changed = changed_files_from_git(args.base, args.path.resolve().parent)
    else:
        changed = tuple(args.changed_file)

    results = [
        evaluate(package, changed, rules, contract_files) for package in packages
    ]
    failed = [r for r in results if r.failed_under(strict_legacy=args.strict_legacy)]
    exit_code = 1 if failed else 0

    if args.json:
        print(
            json.dumps(
                {
                    "path": str(args.path),
                    "rules": str(rules.source),
                    "strict_legacy": args.strict_legacy,
                    "changed_file_count": len(changed),
                    "exit_code": exit_code,
                    "packages": [r.to_dict() for r in results],
                },
                indent=2,
            )
        )
        return exit_code

    verdict = "INVALID" if failed else "VALID"
    print(f"context-impact validation: {verdict}")
    if results:
        print(_render(results, args.strict_legacy))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
