#!/usr/bin/env python3
"""Generate ``change-context.md``'s Contract Ref column from citations (design D8).

The Requirement Traceability Matrix's Contract Ref column has always been
hand-filled — ``skills/implement-feature/SKILL.md`` instructed the
implementer to map each requirement to the contract file it validates, and
nothing checked the mapping. This script replaces the hand-fill with a
join: the matrix's ordinal Req ID (``<capability>.<N>``, sequential per
capability) and the traceability model's derived slug id
(``<capability>.<slug-of-heading>``) are both derived from the *same* parse
of the change's spec delta, so a row and its citations are joined by
**position** in that one parse — never by name similarity, which would be
D1's inference reintroduced at the matrix layer.

Usage::

    python scripts/generate_contract_refs.py --change <id>              # write in place
    python scripts/generate_contract_refs.py --change <id> --check      # exit 1 on drift
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PACKAGE_ROOT / "src"
_SCRIPTS = _PACKAGE_ROOT / "scripts"
for _p in (_SRC, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import check_traceability as gate  # noqa: E402

from gen_eval.traceability import parse_delta, requirement_id  # noqa: E402

_REPO_ROOT = _PACKAGE_ROOT.parent.parent

DEFAULT_CONTRACTS_ROOT = _REPO_ROOT / "openspec" / "contracts"
DEFAULT_SPECS_ROOT = _REPO_ROOT / "openspec" / "specs"
DEFAULT_CHANGES_ROOT = _REPO_ROOT / "openspec" / "changes"
DEFAULT_REPO_ROOT = _REPO_ROOT

_PLACEHOLDER = "---"


def ordinal_rows(changes_root: Path, change_id: str) -> list[tuple[str, str, str]]:
    """``[(ordinal_req_id, capability, heading), ...]``, the matrix's own order.

    Per capability (directory scan order, matching the existing convention
    of one contiguous block per capability), ADDED requirements then
    MODIFIED, each in the order they appear in the delta file — the same
    parse :func:`citation_map` implicitly agrees with via the shared
    ``requirement_id`` derivation, so a row and its citations are joined by
    parse position rather than by re-matching names.
    """
    rows: list[tuple[str, str, str]] = []
    specs_dir = changes_root / change_id / "specs"
    if not specs_dir.is_dir():
        return rows
    for capability_dir in sorted(p for p in specs_dir.iterdir() if p.is_dir()):
        spec_file = capability_dir / "spec.md"
        if not spec_file.is_file():
            continue
        capability = capability_dir.name
        delta = parse_delta(spec_file.read_text(encoding="utf-8"))
        headings = [h for h, _ in delta.added] + [h for h, _ in delta.modified]
        for n, heading in enumerate(headings, start=1):
            rows.append((f"{capability}.{n}", capability, heading))
    return rows


def citation_map(contracts_root: Path, repo_root: Path) -> dict[str, list[str]]:
    """Requirement slug id -> sorted contract document rel paths citing it.

    Scans every capability under ``contracts_root`` (cross-capability
    citations are real, D9), reusing ``check_traceability``'s own document
    discovery so a document this script would flag as malformed there is
    silently skipped here rather than crashing generation — this script's
    job is best-effort reference generation, not the gate itself.
    """
    mapping: dict[str, set[str]] = {}
    if not contracts_root.is_dir():
        return {}
    for capability_dir in sorted(p for p in contracts_root.iterdir() if p.is_dir()):
        documents, misplaced, _malformed = gate.discover_capability(
            contracts_root, capability_dir.name, repo_root
        )
        for doc in documents + misplaced:
            for unit in doc.units:
                if unit.block is None or unit.block.excluded is not None:
                    continue
                for req_id in unit.block.requirements or []:
                    mapping.setdefault(req_id, set()).add(doc.rel_path)
    return {key: sorted(paths) for key, paths in mapping.items()}


def generate(
    *,
    changes_root: Path,
    contracts_root: Path,
    repo_root: Path,
    change_id: str,
) -> dict[str, str]:
    """``{ordinal_req_id: contract_ref_cell_text}`` for every matrix row."""
    rows = ordinal_rows(changes_root, change_id)
    citations = citation_map(contracts_root, repo_root)
    result: dict[str, str] = {}
    for ordinal_id, capability, heading in rows:
        slug_id = requirement_id(capability, heading)
        docs = citations.get(slug_id, [])
        result[ordinal_id] = ", ".join(docs) if docs else _PLACEHOLDER
    return result


def _split_row(line: str) -> list[str] | None:
    stripped = line.rstrip("\n")
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def rewrite_contract_ref_column(markdown_text: str, refs: dict[str, str]) -> str:
    """Replace the Contract Ref cell of every matrix row named in ``refs``.

    Locates the ``## Requirement Traceability Matrix`` section, its header
    row (to find the Contract Ref column position — robust to column
    reordering), and its separator row, then rewrites the Contract Ref cell
    of every data row whose first cell (the Req ID) is a key in ``refs``.
    Rows outside the matrix, and matrix rows not in ``refs`` (e.g. a change
    with no spec delta rows for some reason), are left untouched.
    """
    lines = markdown_text.splitlines(keepends=True)
    out: list[str] = []
    in_matrix = False
    header_seen = False
    separator_seen = False
    contract_ref_index: int | None = None

    for line in lines:
        stripped = line.rstrip("\n")

        if stripped.startswith("## "):
            in_matrix = stripped.strip() == "## Requirement Traceability Matrix"
            header_seen = False
            separator_seen = False
            out.append(line)
            continue

        if in_matrix and not header_seen:
            cells = _split_row(line)
            if cells is not None:
                header_seen = True
                if "Contract Ref" in cells:
                    contract_ref_index = cells.index("Contract Ref")
            out.append(line)
            continue

        if in_matrix and header_seen and not separator_seen:
            separator_seen = True
            out.append(line)
            continue

        if in_matrix and separator_seen and contract_ref_index is not None:
            cells = _split_row(line)
            if cells is not None and cells and cells[0] in refs:
                cells[contract_ref_index] = refs[cells[0]]
                out.append("| " + " | ".join(cells) + " |\n")
                continue

        out.append(line)

    return "".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--change", dest="change_id", required=True)
    parser.add_argument("--contracts-root", type=Path, default=DEFAULT_CONTRACTS_ROOT)
    parser.add_argument("--changes-root", type=Path, default=DEFAULT_CHANGES_ROOT)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--change-context", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="exit 1 on drift; do not write")
    args = parser.parse_args(argv)

    change_context_path = args.change_context or (
        args.changes_root / args.change_id / "change-context.md"
    )
    if not change_context_path.is_file():
        sys.stderr.write(f"{change_context_path}: no such file\n")
        return 1

    refs = generate(
        changes_root=args.changes_root,
        contracts_root=args.contracts_root,
        repo_root=args.repo_root,
        change_id=args.change_id,
    )
    original = change_context_path.read_text(encoding="utf-8")
    updated = rewrite_contract_ref_column(original, refs)

    if args.check:
        if original != updated:
            sys.stderr.write(f"{change_context_path}: Contract Ref column is out of date\n")
            return 1
        print(f"{change_context_path}: Contract Ref column up to date ({len(refs)} rows)")
        return 0

    change_context_path.write_text(updated, encoding="utf-8")
    print(f"{change_context_path}: Contract Ref column regenerated ({len(refs)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
