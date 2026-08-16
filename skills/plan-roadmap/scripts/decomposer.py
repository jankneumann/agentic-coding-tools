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
    is_valid_item_ref,
    load_all_roadmaps_strict,
    parse_item_ref,
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

    # 3b. Cross-roadmap edge grammar. Resolution across workspaces is a
    #     repo-wide concern (see validate_cross_roadmap); here we only enforce
    #     that each external_depends_on / superseded_by entry is a well-formed
    #     '<roadmap-id>:<item-id>' item_ref, which is single-roadmap-local and
    #     needs no filesystem scan.
    for item in roadmap.items:
        for ref in item.external_depends_on:
            if not is_valid_item_ref(ref):
                errors.append(
                    f"Item {item.item_id!r} has malformed external_depends_on "
                    f"ref {ref!r} — expected '<roadmap-id>:<item-id>'."
                )
        for ref in item.superseded_by:
            if not is_valid_item_ref(ref):
                errors.append(
                    f"Item {item.item_id!r} has malformed superseded_by "
                    f"ref {ref!r} — expected '<roadmap-id>:<item-id>'."
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
# Repo-wide cross-roadmap validation
# ---------------------------------------------------------------------------
def validate_cross_roadmap(repo_root: Path) -> list[str]:
    """Validate cross-roadmap invariants over ALL roadmap workspaces.

    Scans every ``openspec/roadmaps/*/roadmap.yaml`` under ``repo_root`` and
    checks the things a single-roadmap validation cannot see:

    1. ``external_depends_on`` / ``superseded_by`` item_refs resolve — the
       referenced ``<roadmap-id>`` exists among the loaded roadmaps and the
       ``<item-id>`` exists within it. Unresolvable refs fail.
    2. Repo-wide acyclicity across the combined edge set: in-roadmap
       ``depends_on`` edges plus fully-qualified ``external_depends_on`` edges,
       treated as one global graph over ``<roadmap-id>:<item-id>`` nodes.
    3. No ``change_id`` is claimed by two different roadmaps.

    Read-only and side-effect-free. Returns a list of human-readable error
    messages (empty = valid).
    """
    # Strict load: a roadmap that silently fails to parse, or a duplicated
    # roadmap_id that silently overwrites another, would make every check below
    # fail open — refs into the dropped workspace, cycles through it, and
    # change_ids it claims all become invisible. Report those first.
    roadmaps, errors = load_all_roadmaps_strict(repo_root)

    # Global node set: every fully-qualified item_ref that exists.
    node_ids: set[str] = set()
    for roadmap_id, roadmap in roadmaps.items():
        for item in roadmap.items:
            node_ids.add(f"{roadmap_id}:{item.item_id}")

    # 1. External ref resolution (external_depends_on + superseded_by).
    for roadmap_id, roadmap in sorted(roadmaps.items()):
        for item in roadmap.items:
            for field_name in ("external_depends_on", "superseded_by"):
                for ref in getattr(item, field_name):
                    if not is_valid_item_ref(ref):
                        errors.append(
                            f"{roadmap_id}:{item.item_id} has malformed "
                            f"{field_name} ref {ref!r} — expected "
                            f"'<roadmap-id>:<item-id>'."
                        )
                        continue
                    target_roadmap, _ = parse_item_ref(ref)
                    if target_roadmap not in roadmaps:
                        errors.append(
                            f"{roadmap_id}:{item.item_id} {field_name} ref "
                            f"{ref!r} points at unknown roadmap "
                            f"{target_roadmap!r}."
                        )
                    elif ref not in node_ids:
                        errors.append(
                            f"{roadmap_id}:{item.item_id} {field_name} ref "
                            f"{ref!r} does not resolve to a declared item."
                        )

    # 2. Repo-wide acyclicity over depends_on + external_depends_on edges.
    #    Only build edges to nodes that exist so an unresolved ref surfaces as a
    #    resolution error above, not confusing cycle noise.
    adjacency: dict[str, list[str]] = {}
    for roadmap_id, roadmap in roadmaps.items():
        for item in roadmap.items:
            node = f"{roadmap_id}:{item.item_id}"
            neighbors: list[str] = []
            for dep in item.depends_on:
                dep_ref = f"{roadmap_id}:{dep}"
                if dep_ref in node_ids:
                    neighbors.append(dep_ref)
            for ref in item.external_depends_on:
                if is_valid_item_ref(ref) and ref in node_ids:
                    neighbors.append(ref)
            adjacency[node] = neighbors

    cycle = _find_global_cycle(adjacency)
    if cycle:
        errors.append(
            "Cross-roadmap dependency cycle detected across combined "
            "depends_on + external_depends_on edges: " + " -> ".join(cycle)
        )

    # 3. Duplicate change_id — both across roadmaps and within one.
    #    A change_id names exactly one OpenSpec change directory, so two items
    #    claiming it means one change's completion silently satisfies both. The
    #    intra-roadmap case is checked here rather than in validate_roadmap
    #    because both cases have the same cause and the same fix, and a
    #    per-roadmap check would report the cross-roadmap case twice.
    change_owners: dict[str, list[str]] = {}
    for roadmap_id, roadmap in sorted(roadmaps.items()):
        seen_here: dict[str, str] = {}
        for item in roadmap.items:
            if not item.change_id:
                continue
            if item.change_id in seen_here:
                errors.append(
                    f"change_id {item.change_id!r} is claimed twice within "
                    f"roadmap {roadmap_id!r}: by items "
                    f"{seen_here[item.change_id]!r} and {item.item_id!r}."
                )
                continue
            seen_here[item.change_id] = item.item_id
            change_owners.setdefault(item.change_id, []).append(roadmap_id)
    for change_id, owners in sorted(change_owners.items()):
        if len(owners) > 1:
            errors.append(
                f"change_id {change_id!r} is claimed by multiple roadmaps: "
                f"{', '.join(sorted(owners))}."
            )

    return errors


def _find_global_cycle(adjacency: dict[str, list[str]]) -> list[str] | None:
    """Return a node path forming a cycle, or None if the graph is acyclic."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in adjacency}
    path: list[str] = []

    def _dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        path.append(node)
        for nxt in adjacency.get(node, []):
            if color.get(nxt, BLACK) == GRAY:
                # Found back-edge: slice the path from the recurrence point.
                idx = path.index(nxt)
                return path[idx:] + [nxt]
            if color.get(nxt, BLACK) == WHITE:
                found = _dfs(nxt)
                if found:
                    return found
        path.pop()
        color[node] = BLACK
        return None

    for start in adjacency:
        if color[start] == WHITE:
            found = _dfs(start)
            if found:
                return found
    return None


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


def _cmd_validate_repo(args: argparse.Namespace) -> int:
    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else _find_repo_root(Path.cwd())
    )
    errors = validate_cross_roadmap(repo_root)
    if errors:
        print(
            f"INVALID: cross-roadmap validation ({len(errors)} error(s))",
            file=sys.stderr,
        )
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("OK: cross-roadmap edges resolve, graph is acyclic, no duplicate change_id.")
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

    p_validate_repo = sub.add_parser(
        "validate-repo",
        help="Validate cross-roadmap edges across all openspec/roadmaps workspaces.",
    )
    p_validate_repo.add_argument(
        "--repo-root",
        default=None,
        help="Repository root to scan (default: auto-detect from cwd).",
    )
    p_validate_repo.set_defaults(func=_cmd_validate_repo)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
