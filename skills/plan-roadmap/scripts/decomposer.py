"""Deterministic validation for LLM-generated roadmaps.

Roadmap *generation* is done by a premium model (a dispatched Claude subagent
or an external vendor) reading the full proposal against the output contract in
``templates/generation-prompt.md``. This module is the deterministic backstop:
it checks proposal readiness before generation and validates the generated
``roadmap.yaml`` afterwards (schema conformance, id uniqueness, dependency
referential integrity, DAG acyclicity).

It intentionally contains *no* keyword extraction. The old keyword-driven
``decompose()`` was brittle — proposals that didn't use a hardcoded vocabulary
were rejected or thin-extracted before the model ever reasoned about them. The
model now does all semantic work; Python only validates input→output where the
mapping is crisp.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Import shared runtime models
# ---------------------------------------------------------------------------
_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from models import (  # type: ignore[import-untyped]
    ROADMAP_SCHEMA,
    Roadmap,
    validate_against_schema,
)

# Heading pattern: captures level (number of #) and text
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Proposal readiness (pre-generation)
# ---------------------------------------------------------------------------
def validate_proposal(text: str) -> list[str]:
    """Check a proposal is structurally fit to hand to the generator.

    This is a *readiness* gate, not a content gate. The generator (a premium
    model) reads the full prose, so we do not require any particular capability
    vocabulary or section layout — only that there is real, sectioned content
    to reason about. Returns a list of error messages (empty = ready).
    """
    errors: list[str] = []

    if not text or not text.strip():
        errors.append("Proposal is empty.")
        return errors

    if not _HEADING_RE.search(text):
        errors.append(
            "Proposal has no markdown headings — add at least one section "
            "(see openspec/schemas/roadmap/templates/proposal.md for the "
            "recommended layout)."
        )

    return errors


# ---------------------------------------------------------------------------
# Roadmap validation (post-generation)
# ---------------------------------------------------------------------------
def validate_roadmap(data: dict, repo_root: Path) -> list[str]:
    """Validate a generated roadmap mapping against the contract.

    Layers the deterministic checks the model cannot be trusted to get right
    every time:

    1. JSON-schema conformance (``roadmap.schema.json``).
    2. ``item_id`` uniqueness.
    3. ``depends_on`` referential integrity (every referenced id exists; no
       self-dependency).
    4. DAG acyclicity.

    Args:
        data: Parsed roadmap mapping (e.g. ``yaml.safe_load(...)``).
        repo_root: Repository root used to resolve the schema path.

    Returns:
        List of human-readable error messages (empty = valid). The messages
        are written to be fed straight back to the generator for a repair pass.
    """
    if not isinstance(data, dict):
        return ["Roadmap is not a mapping — expected a YAML object at the top level."]

    # 1. Schema conformance. Stop here on failure: the semantic checks below
    #    assume well-formed items, so reporting parse errors on malformed data
    #    would just be noise on top of the schema errors.
    schema_errors = validate_against_schema(data, ROADMAP_SCHEMA, repo_root)
    if schema_errors:
        return [f"Schema: {e}" for e in schema_errors]

    try:
        roadmap = Roadmap.from_dict(data)
    except (KeyError, ValueError, TypeError) as exc:
        return [f"Could not parse roadmap into model: {exc}"]

    errors: list[str] = []

    # 2. item_id uniqueness
    ids = [item.item_id for item in roadmap.items]
    seen: set[str] = set()
    dupes: set[str] = set()
    for item_id in ids:
        if item_id in seen:
            dupes.add(item_id)
        seen.add(item_id)
    for item_id in sorted(dupes):
        errors.append(f"Duplicate item_id {item_id!r} — every item_id must be unique.")

    # 3. depends_on referential integrity
    id_set = set(ids)
    for item in roadmap.items:
        for dep in item.depends_on:
            if dep == item.item_id:
                errors.append(f"Item {item.item_id!r} depends on itself.")
            elif dep not in id_set:
                errors.append(
                    f"Item {item.item_id!r} depends on {dep!r}, which is not a "
                    f"declared item_id."
                )

    # 4. DAG acyclicity (only meaningful once references resolve)
    if not any("depends on" in e for e in errors) and roadmap.has_cycle():
        errors.append(
            "Dependency graph contains a cycle — depends_on edges must form a DAG."
        )

    # 5. Every item must declare at least one acceptance_outcome. The
    #    generation prompt asks for 1–5 measurable outcomes; if the generator
    #    omits the field or emits an empty list the roadmap is incomplete and
    #    autopilot has no acceptance signal to gate on.
    for item in roadmap.items:
        if not item.acceptance_outcomes:
            errors.append(
                f"Item {item.item_id!r} has no acceptance_outcomes — "
                "every item must list at least one measurable, observable outcome."
            )

    return errors


# ---------------------------------------------------------------------------
# Repo state scanning (archive cross-check)
# ---------------------------------------------------------------------------
def scan_archive_state(repo_root: Path) -> dict[str, str]:
    """Build a ``{change_id: status}`` map from the OpenSpec changes tree.

    Archived changes (``openspec/changes/archive/YYYY-MM-DD-<id>/``) map to
    ``completed``; active change dirs map to ``in_progress``. Used to flag
    roadmap items that duplicate work already done or in flight.
    """
    state: dict[str, str] = {}

    archive_dir = repo_root / "openspec" / "changes" / "archive"
    if archive_dir.is_dir():
        for entry in archive_dir.iterdir():
            if entry.is_dir():
                name = entry.name
                # Strip date prefix (YYYY-MM-DD-)
                if len(name) > 11 and name[4] == "-" and name[7] == "-" and name[10] == "-":
                    change_id = name[11:]
                else:
                    change_id = name
                state[change_id] = "completed"

    changes_dir = repo_root / "openspec" / "changes"
    if changes_dir.is_dir():
        for entry in changes_dir.iterdir():
            if entry.is_dir() and entry.name != "archive":
                if entry.name not in state:
                    state[entry.name] = "in_progress"

    return state


def make_repo_relative(path: str, repo_root: Path) -> str:
    """Normalize an absolute path to repo-relative when possible."""
    try:
        p = Path(path)
        if p.is_absolute():
            return str(p.relative_to(repo_root))
    except (ValueError, TypeError):
        pass
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` looking for the openspec schema dir."""
    for candidate in [start, *start.parents]:
        if (candidate / "openspec" / "schemas" / "roadmap.schema.json").exists():
            return candidate
    return Path.cwd()


def _cmd_validate(args: argparse.Namespace) -> int:
    roadmap_path = Path(args.roadmap).resolve()
    if not roadmap_path.exists():
        print(f"error: roadmap not found: {roadmap_path}", file=sys.stderr)
        return 2

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _find_repo_root(roadmap_path)

    try:
        data = yaml.safe_load(roadmap_path.read_text())
    except yaml.YAMLError as exc:
        print(f"INVALID: YAML parse error: {exc}", file=sys.stderr)
        return 1

    errors = validate_roadmap(data, repo_root)
    if errors:
        print(f"INVALID: {roadmap_path} ({len(errors)} error(s))", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"OK: {roadmap_path} is a valid roadmap.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="decomposer",
        description="Deterministic validation for LLM-generated roadmaps.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser(
        "validate", help="Validate a generated roadmap.yaml against the contract."
    )
    p_validate.add_argument("roadmap", help="Path to the roadmap.yaml to validate.")
    p_validate.add_argument(
        "--repo-root",
        default=None,
        help="Repository root for schema resolution (default: auto-detect).",
    )
    p_validate.set_defaults(func=_cmd_validate)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
