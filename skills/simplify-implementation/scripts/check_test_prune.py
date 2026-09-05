#!/usr/bin/env python3
"""Gate the /simplify-implementation test-prune phase: test-only diff + justified removals.

The prune phase deletes tests that assert implementation instead of behavior.
That is a *coverage-reducing* edit, so it gets its own commit range and its own
gate — ``check_test_contract.py`` deliberately treats removed assertions as a
contract break and must therefore be baselined **after** this range.

This script checks the prune range ``--base``..``--head``:

1. **Test-only** — a production file changed inside the prune range is a
   violation. Pruning tests and editing production code in one commit makes the
   two indistinguishable in review and in ``git bisect``.
2. **Inventory** — reports removed test files and removed test functions.
3. **Ledger** — when anything was removed, every removal must be justified in a
   prune ledger (``--ledger``): a reason code, plus the test that still covers
   the behavior whenever the removed test covered real behavior.

Usage:
    python3 check_test_prune.py --base <pre-prune-sha> --head <post-prune-sha> \\
        --ledger docs/simplify-implementation/test-prune-ledger.md
    python3 check_test_prune.py --base <sha> --head <sha> --json

Exit codes:
    0 — prune range is test-only and every removal is justified
    2 — violation (production file in range, or unjustified removal)
    1 — usage / git / ledger-parse error
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_test_contract import is_test_path  # noqa: E402  (path set above)


# Reason codes accepted in a prune ledger.
#
# NO_BEHAVIOR reasons mean the removed test asserted no observable behavior, so
# there is nothing left to cover. Every other reason means the test *did* touch
# real behavior — the ledger must then name where that behavior still lives.
NO_BEHAVIOR_REASONS = frozenset(
    {
        "source-mirroring",
        "vacuous",
        "library-under-test",
        "accessor-only",
        "self-mocking",
    }
)
COVERAGE_REQUIRED_REASONS = frozenset(
    {
        "change-detector",
        "duplicative",
        "unreviewed-snapshot",
    }
)
VALID_REASONS = NO_BEHAVIOR_REASONS | COVERAGE_REQUIRED_REASONS

# Removed test declarations, per language.
REMOVED_TEST_RES = (
    re.compile(r"^-\s*(?:async\s+)?def\s+(test_\w+)"),                 # Python
    re.compile(r"""^-\s*(?:it|test)(?:\.\w+)?\s*\(\s*['"`](.+?)['"`]"""),  # JS/TS
    re.compile(r"^-\s*func\s+(Test\w+)\s*\("),                          # Go
    re.compile(r"^-\s*fn\s+(\w*test\w*)\s*\(", re.IGNORECASE),          # Rust
)

_LEDGER_REMOVED = re.compile(r"^\s*[-*]?\s*removed:\s*(\S+)", re.IGNORECASE)
_LEDGER_FIELD = re.compile(r"^\s*[-*]?\s*(reason|covered-by):\s*(.+?)\s*$", re.IGNORECASE)


@dataclass
class Removal:
    """One removed test, addressed as ``path`` or ``path::name``."""

    path: str
    name: str | None = None

    @property
    def qualified(self) -> str:
        return f"{self.path}::{self.name}" if self.name else self.path


@dataclass
class LedgerEntry:
    target: str
    reason: str | None = None
    covered_by: str | None = None


@dataclass
class PruneResult:
    base: str
    head: str
    clean: bool
    production_files_touched: list[str] = field(default_factory=list)
    removed_test_files: list[str] = field(default_factory=list)
    removed_tests: list[str] = field(default_factory=list)
    unjustified: list[str] = field(default_factory=list)
    ledger_errors: list[str] = field(default_factory=list)
    ledger_path: str | None = None


def _run_git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(
            proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed"
        )
    return proc.stdout


def changed_paths(repo: Path, base: str, head: str) -> list[str]:
    out = _run_git(["diff", "--name-only", f"{base}...{head}"], repo)
    return [line.strip() for line in out.splitlines() if line.strip()]


def deleted_paths(repo: Path, base: str, head: str) -> list[str]:
    out = _run_git(["diff", "--name-only", "--diff-filter=D", f"{base}...{head}"], repo)
    return [line.strip() for line in out.splitlines() if line.strip()]


def scan_removed_tests(diff_text: str) -> list[Removal]:
    """Collect removed test declarations from a unified diff, test files only."""
    removals: list[Removal] = []
    seen: set[str] = set()
    current: str | None = None
    in_test_file = False
    pending_old: str | None = None

    for raw in diff_text.splitlines():
        if raw.startswith("--- "):
            pending_old = _strip_diff_path(raw.partition(" ")[2])
            continue
        if raw.startswith("+++ "):
            new_path = _strip_diff_path(raw.partition(" ")[2])
            current = new_path if new_path is not None else pending_old
            in_test_file = bool(current and is_test_path(current))
            pending_old = None
            continue
        if not in_test_file or current is None or not raw.startswith("-"):
            continue
        if raw.startswith("---"):
            continue
        for pattern in REMOVED_TEST_RES:
            match = pattern.match(raw)
            if match:
                removal = Removal(path=current, name=match.group(1))
                if removal.qualified not in seen:
                    seen.add(removal.qualified)
                    removals.append(removal)
                break

    return removals


def _strip_diff_path(path: str) -> str | None:
    path = path.strip().strip('"').strip("'")
    if path == "/dev/null":
        return None
    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]
    return path or None


def parse_ledger(text: str) -> tuple[list[LedgerEntry], list[str]]:
    """Parse a prune ledger into entries plus a list of validation errors."""
    entries: list[LedgerEntry] = []
    errors: list[str] = []
    current: LedgerEntry | None = None

    for raw in text.splitlines():
        removed = _LEDGER_REMOVED.match(raw)
        if removed:
            current = LedgerEntry(target=removed.group(1).strip().strip("`"))
            entries.append(current)
            continue
        field_match = _LEDGER_FIELD.match(raw)
        if field_match and current is not None:
            key, value = field_match.group(1).lower(), field_match.group(2).strip().strip("`")
            if key == "reason":
                current.reason = value
            else:
                current.covered_by = value

    for entry in entries:
        if entry.reason is None:
            errors.append(f"{entry.target}: missing `reason:`")
            continue
        if entry.reason not in VALID_REASONS:
            errors.append(
                f"{entry.target}: unknown reason {entry.reason!r} "
                f"(valid: {', '.join(sorted(VALID_REASONS))})"
            )
            continue
        covered = (entry.covered_by or "").strip().lower()
        if entry.reason in COVERAGE_REQUIRED_REASONS and covered in ("", "none", "n/a"):
            errors.append(
                f"{entry.target}: reason {entry.reason!r} covered real behavior — "
                f"`covered-by:` must name the test that still pins it"
            )

    return entries, errors


def _is_justified(removal: Removal, targets: set[str]) -> bool:
    """A removal is justified by its own qualified name or by a file-level entry."""
    return removal.qualified in targets or removal.path in targets


def evaluate(
    repo: Path, base: str, head: str, ledger: Path | None
) -> PruneResult:
    changed = changed_paths(repo, base, head)
    production = [p for p in changed if not is_test_path(p)]
    removed_files = [p for p in deleted_paths(repo, base, head) if is_test_path(p)]

    diff_text = _run_git(["diff", f"{base}...{head}", "--unified=0"], repo)
    removals = scan_removed_tests(diff_text)

    ledger_errors: list[str] = []
    targets: set[str] = set()
    if (removals or removed_files) and ledger is None:
        ledger_errors.append(
            "tests were removed but no --ledger was supplied; "
            "every removal must be justified"
        )
    elif ledger is not None:
        if not ledger.exists():
            raise RuntimeError(f"ledger not found: {ledger}")
        entries, ledger_errors = parse_ledger(ledger.read_text(encoding="utf-8"))
        targets = {e.target for e in entries}

    unjustified = [r.qualified for r in removals if not _is_justified(r, targets)]
    # A deleted file whose tests this scanner cannot parse (snapshots, an
    # unsupported language) still needs a file-level entry of its own.
    files_with_parsed_tests = {r.path for r in removals}
    unjustified += [
        path
        for path in removed_files
        if path not in targets and path not in files_with_parsed_tests
    ]

    clean = not production and not unjustified and not ledger_errors
    return PruneResult(
        base=base,
        head=head,
        clean=clean,
        production_files_touched=production,
        removed_test_files=removed_files,
        removed_tests=[r.qualified for r in removals],
        unjustified=sorted(set(unjustified)),
        ledger_errors=ledger_errors,
        ledger_path=str(ledger) if ledger else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate the /simplify-implementation test-prune range (test-only diff + justified removals)"
    )
    parser.add_argument("--base", required=True, help="Tip before the prune commits")
    parser.add_argument("--head", default="HEAD", help="Tip after the prune commits")
    parser.add_argument("--ledger", type=Path, help="Path to the prune ledger")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--json", action="store_true", help="Emit JSON result")
    args = parser.parse_args(argv)

    try:
        result = evaluate(args.repo.resolve(), args.base, args.head, args.ledger)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(asdict(result), indent=2))
        return 0 if result.clean else 2

    if result.clean:
        print(
            f"Test prune: OK\n"
            f"  range: {result.base}...{result.head}\n"
            f"  removed test files: {len(result.removed_test_files)}\n"
            f"  removed tests: {len(result.removed_tests)}\n"
            f"  ledger: {result.ledger_path or 'not required (nothing removed)'}"
        )
        return 0

    print(
        f"Test prune: BLOCKED\n  range: {result.base}...{result.head}",
        file=sys.stderr,
    )
    if result.production_files_touched:
        print(
            "  production files changed in the prune range "
            f"({len(result.production_files_touched)}) — prune commits must be test-only:",
            file=sys.stderr,
        )
        for path in result.production_files_touched[:20]:
            print(f"    {path}", file=sys.stderr)
        print(
            "  action: move production edits into a separate refactor(...) commit "
            "after the prune range.",
            file=sys.stderr,
        )
    if result.ledger_errors:
        print(f"  ledger errors ({len(result.ledger_errors)}):", file=sys.stderr)
        for err in result.ledger_errors[:20]:
            print(f"    {err}", file=sys.stderr)
    if result.unjustified:
        print(
            f"  removals with no ledger entry ({len(result.unjustified)}):",
            file=sys.stderr,
        )
        for item in result.unjustified[:20]:
            print(f"    {item}", file=sys.stderr)
        print(
            "  action: add `removed:` / `reason:` / `covered-by:` entries, or restore "
            "the test. A test you cannot justify deleting is a test you keep.",
            file=sys.stderr,
        )

    return 2


if __name__ == "__main__":
    sys.exit(main())
