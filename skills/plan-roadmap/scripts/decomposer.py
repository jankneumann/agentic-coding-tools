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
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Import shared runtime models
# ---------------------------------------------------------------------------
_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from models import (  # type: ignore[import-untyped]
    ROADMAP_SCHEMA,
    ItemStatus,
    Roadmap,
    is_valid_item_ref,
    load_all_roadmaps_strict,
    parse_item_ref,
    validate_against_schema,
)

# change_id safety is defined next to the derivation that produces it, so the
# validator and the scaffolder can never disagree about what is a legal id.
from scaffolder import validate_change_id  # noqa: E402

# Heading pattern: captures level (number of #) and text
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

#: Statuses in which an item has *ceded* its change_id rather than claiming it.
#: `skipped` and `superseded` are how a roadmap hands a change to another
#: roadmap's item, so the duplicate-change_id check must not count them.
_CEDED_STATUSES = frozenset({ItemStatus.SKIPPED, ItemStatus.SUPERSEDED})

#: Filename of the handoff `autopilot-roadmap` writes when its replan gate proceeds.
REPLAN_REQUEST_FILENAME = "replan-request.json"

#: Statuses the replan contract preserves verbatim. An item in one of these has
#: either already been built, been handed to another roadmap, or is being worked
#: on right now — re-decomposing it would rewrite history or race a running
#: agent, so it can never enter the replan scope, and traversal stops there.
_PRESERVED_STATUSES = frozenset(
    {ItemStatus.COMPLETED, ItemStatus.SUPERSEDED, ItemStatus.IN_PROGRESS}
)


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
    3. ``change_id`` uniqueness among items that declare one.
    4. ``depends_on`` referential integrity (every referenced id exists; no
       self-dependency).
    5. DAG acyclicity.

    ``change_id`` presence is deliberately *not* required: several roadmaps
    predate the field and would fail retroactively. ``plan-roadmap`` populates
    it via ``scaffolder.populate_change_ids`` before saving; this check only
    catches two items claiming the same change directory.

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

    # 3. change_id safety and uniqueness (only among items that declare one —
    #    presence is optional so pre-existing roadmaps without the field stay
    #    valid). Safety is checked here so a malformed id is rejected at
    #    validation time rather than when it reaches the filesystem.
    change_seen: dict[str, str] = {}
    for item in roadmap.items:
        if not item.change_id:
            continue
        id_error = validate_change_id(item.change_id)
        if id_error:
            errors.append(f"Item {item.item_id!r}: {id_error}")
            continue
        if item.change_id in change_seen:
            errors.append(
                f"Item {item.item_id!r} and {change_seen[item.change_id]!r} both "
                f"declare change_id {item.change_id!r} — two items cannot share a "
                f"change directory."
            )
        else:
            change_seen[item.change_id] = item.item_id

    # 4. depends_on referential integrity
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
    2. No ``external_depends_on`` ref points at a ``superseded`` item.
       ``superseded`` is terminal and is NOT ``completed``, so readiness
       withholds the dependent forever — silently, since a non-ready item just
       does not appear in ``ready_items()``. The edge has to be repointed at
       the successor; this turns the permanent stall into a loud failure at the
       moment the supersession is recorded.
    3. Repo-wide acyclicity across the combined edge set: in-roadmap
       ``depends_on`` edges plus fully-qualified ``external_depends_on`` edges,
       treated as one global graph over ``<roadmap-id>:<item-id>`` nodes.
    4. No ``change_id`` is claimed by two different roadmaps.

    Read-only and side-effect-free. Returns a list of human-readable error
    messages (empty = valid).
    """
    # Strict load: a roadmap that silently fails to parse, or a duplicated
    # roadmap_id that silently overwrites another, would make every check below
    # fail open — refs into the dropped workspace, cycles through it, and
    # change_ids it claims all become invisible. Report those first.
    roadmaps, errors = load_all_roadmaps_strict(repo_root)

    # Global node set: every fully-qualified item_ref that exists, plus the
    # item behind each ref (check 1b needs the target's status and its
    # superseded_by edge, not just its existence).
    items_by_ref: dict[str, Any] = {}
    for roadmap_id, roadmap in roadmaps.items():
        for item in roadmap.items:
            items_by_ref[f"{roadmap_id}:{item.item_id}"] = item
    node_ids: set[str] = set(items_by_ref)

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

    # 1b. No external_depends_on may point at a superseded item.
    #
    #     `superseded` is terminal (ri-17) and is not `completed`, so
    #     `completed_external_refs` never contains the target and
    #     `Roadmap.ready_items` withholds the dependent on every run — forever,
    #     and silently, because a non-ready item is simply absent from the
    #     returned list. Blocking is the right semantics (the work moved), but
    #     it has to be said out loud, with the successor named, so the operator
    #     can repoint the edge instead of watching an item never come up.
    for roadmap_id, roadmap in sorted(roadmaps.items()):
        for item in roadmap.items:
            for ref in item.external_depends_on:
                target = items_by_ref.get(ref)
                if target is None:
                    continue  # unresolvable — already reported above
                if target.status.value != ItemStatus.SUPERSEDED.value:
                    continue
                successors = list(target.superseded_by)
                remedy = (
                    f"repoint it at {', '.join(successors)}"
                    if successors
                    else (
                        "record the successor in that item's superseded_by "
                        "edge and repoint this dependency at it"
                    )
                )
                errors.append(
                    f"{roadmap_id}:{item.item_id} external_depends_on ref "
                    f"{ref!r} points at a superseded item, which can never "
                    f"become completed — {roadmap_id}:{item.item_id} would "
                    f"stay non-ready forever. Fix: {remedy}."
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
    #
    #    An item in a ceded state does NOT claim its change_id: `skipped` and
    #    `superseded` are precisely how a roadmap hands ownership to another
    #    roadmap's item, so counting them would make ceding impossible and leave
    #    the duplicate permanently unresolvable. (Found in practice: the
    #    repo-improvement roadmap skipped four router changes to cede them to
    #    dispatch-governance, and this check still reported the collision.)
    change_owners: dict[str, list[str]] = {}
    for roadmap_id, roadmap in sorted(roadmaps.items()):
        seen_here: dict[str, str] = {}
        for item in roadmap.items:
            if not item.change_id:
                continue
            if item.status in _CEDED_STATUSES:
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
# Replan mode (the deterministic half of `/plan-roadmap --replan <roadmap-id>`)
# ---------------------------------------------------------------------------
def compute_replan_scope(roadmap: Roadmap, seeds: list[str]) -> list[str]:
    """Return the affected subgraph: ``seeds`` + their non-preserved dependents.

    Walks *forward* along dependency edges (``A depends_on B`` means A is a
    dependent of B) from every seed. An item in a preserved status
    (:data:`_PRESERVED_STATUSES`) is neither included nor traversed through: a
    completed item is a barrier, because everything downstream of it depends on
    work that still exists and was not invalidated by the failure. Read-only.
    """
    dependents: dict[str, list[str]] = {item.item_id: [] for item in roadmap.items}
    for item in roadmap.items:
        for dep in item.depends_on:
            if dep in dependents:
                dependents[dep].append(item.item_id)

    by_id = {item.item_id: item for item in roadmap.items}

    def _preserved(item_id: str) -> bool:
        item = by_id.get(item_id)
        if item is None:
            return True
        return item.status in _PRESERVED_STATUSES or bool(item.superseded_by)

    scope: set[str] = set()
    queue = [s for s in seeds if s in by_id and not _preserved(s)]
    while queue:
        current = queue.pop()
        if current in scope:
            continue
        scope.add(current)
        for child in dependents.get(current, []):
            if child not in scope and not _preserved(child):
                queue.append(child)
    return sorted(scope)


def load_replan_request(workspace: Path) -> dict[str, Any]:
    """Load ``<workspace>/replan-request.json``.

    Raises ``FileNotFoundError`` when it is absent — replan mode is driven by
    that file, and running without one would re-decompose a roadmap nobody
    asked to re-decompose.
    """
    path = workspace / REPLAN_REQUEST_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"No replan request at {path}. Replan mode is driven by a "
            f"{REPLAN_REQUEST_FILENAME} written by autopilot-roadmap when its "
            f"replan gate proceeds; without one there is nothing to replan."
        )
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def _load_roadmap_mapping(workspace: Path) -> tuple[dict[str, Any], Roadmap]:
    data = yaml.safe_load((workspace / "roadmap.yaml").read_text())
    return data, Roadmap.from_dict(data)


def _replan_seeds(roadmap: Roadmap, request: dict[str, Any]) -> list[str]:
    """Seed items for the scope walk.

    ``replan_required`` on the roadmap is authoritative — it is what the
    orchestrator actually wrote. The request's list is the fallback for a
    roadmap whose statuses were hand-edited after the request was written.
    """
    seeds = sorted(
        item.item_id
        for item in roadmap.items
        if item.status == ItemStatus.REPLAN_REQUIRED
    )
    if seeds:
        return seeds
    known = {item.item_id for item in roadmap.items}
    return sorted(i for i in request.get("replan_required_items", []) if i in known)


#: Matches the status line of an item parked for replanning, in the block style
#: `save_roadmap` emits (optionally quoted).
_REPLAN_STATUS_LINE = re.compile(
    r"^(?P<indent>\s*)status:\s*(?P<q>['\"]?)replan_required(?P=q)\s*$"
)


def flip_replan_required_to_approved(text: str) -> tuple[str, int]:
    """Rewrite ``status: replan_required`` -> ``status: approved`` in YAML text.

    A line edit rather than a load/dump round-trip: the replan contract requires
    every preserved item to stay *byte-identical*, and re-serializing the whole
    roadmap would renormalize quoting, key order, and empty collections across
    items the replan never touched. Returns ``(new_text, lines_changed)``.
    """
    out: list[str] = []
    changed = 0
    for line in text.splitlines(keepends=True):
        match = _REPLAN_STATUS_LINE.match(line.rstrip("\n"))
        if match:
            newline = "\n" if line.endswith("\n") else ""
            out.append(f"{match.group('indent')}status: approved{newline}")
            changed += 1
        else:
            out.append(line)
    return "".join(out), changed


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


def _resolve_workspace(target: str, repo_root: Path) -> Path:
    """Accept either a workspace path or a bare ``<roadmap-id>``.

    ``/plan-roadmap --replan <roadmap-id>`` names the roadmap, not the
    directory, so the id form resolves under ``openspec/roadmaps/``.
    """
    candidate = Path(target)
    if candidate.is_dir():
        return candidate.resolve()
    return (repo_root / "openspec" / "roadmaps" / target).resolve()


def _replan_workspace(args: argparse.Namespace) -> tuple[Path, Path, dict[str, Any]] | int:
    """Shared preamble: resolve the workspace and load the request file."""
    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else _find_repo_root(Path.cwd())
    )
    workspace = _resolve_workspace(args.workspace, repo_root)
    if not (workspace / "roadmap.yaml").exists():
        print(
            f"error: no roadmap.yaml in {workspace} — pass a roadmap workspace "
            f"directory or a roadmap-id under openspec/roadmaps/.",
            file=sys.stderr,
        )
        return 2
    try:
        request = load_replan_request(workspace)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(
            f"error: {workspace / REPLAN_REQUEST_FILENAME} is not valid JSON: {exc}",
            file=sys.stderr,
        )
        return 2
    return repo_root, workspace, request


def _cmd_replan_scope(args: argparse.Namespace) -> int:
    resolved = _replan_workspace(args)
    if isinstance(resolved, int):
        return resolved
    _repo_root, workspace, request = resolved

    _data, roadmap = _load_roadmap_mapping(workspace)
    seeds = _replan_seeds(roadmap, request)
    scope = compute_replan_scope(roadmap, seeds)
    by_id = {item.item_id: item for item in roadmap.items}

    payload = {
        "roadmap_id": roadmap.roadmap_id,
        "source_proposal": roadmap.source_proposal,
        "failed_item_id": request.get("failed_item_id"),
        "failure_reason": request.get("failure_reason"),
        "learning_entry": request.get("learning_entry"),
        "seed_items": seeds,
        "scope_items": scope,
        # Everything the host must copy through untouched.
        "preserved_items": sorted(
            item.item_id
            for item in roadmap.items
            if item.status in _PRESERVED_STATUSES or item.superseded_by
        ),
        "items": [
            {
                "item_id": item_id,
                "title": by_id[item_id].title,
                "status": by_id[item_id].status.value,
                "effort": by_id[item_id].effort.value,
                "depends_on": list(by_id[item_id].depends_on),
                "change_id": by_id[item_id].change_id,
            }
            for item_id in scope
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_replan_finish(args: argparse.Namespace) -> int:
    resolved = _replan_workspace(args)
    if isinstance(resolved, int):
        return resolved
    repo_root, workspace, _request = resolved

    roadmap_path = workspace / "roadmap.yaml"
    original = roadmap_path.read_text()
    _data, roadmap = _load_roadmap_mapping(workspace)
    expected = sum(
        1 for item in roadmap.items if item.status == ItemStatus.REPLAN_REQUIRED
    )

    updated, changed = flip_replan_required_to_approved(original)
    if changed != expected:
        print(
            f"error: expected to approve {expected} replan_required item(s) but "
            f"matched {changed} status line(s) — roadmap.yaml is not in the block "
            f"style this rewrite understands. Roadmap left unchanged.",
            file=sys.stderr,
        )
        return 1

    roadmap_path.write_text(updated)
    errors = validate_roadmap(yaml.safe_load(updated), repo_root)
    if errors:
        # Restore and keep the request file: a broken re-decomposition must stay
        # retryable rather than silently consuming its own trigger.
        roadmap_path.write_text(original)
        print(
            f"INVALID: replan left {roadmap_path} invalid ({len(errors)} error(s)) — "
            f"roadmap restored, {REPLAN_REQUEST_FILENAME} kept.",
            file=sys.stderr,
        )
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    (workspace / REPLAN_REQUEST_FILENAME).unlink()
    print(
        f"OK: {changed} item(s) approved, {REPLAN_REQUEST_FILENAME} removed, "
        f"{roadmap_path} is a valid roadmap."
    )
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

    p_replan_scope = sub.add_parser(
        "replan-scope",
        help=(
            "Print the affected subgraph for a replan: every replan_required "
            "item plus its transitive non-preserved dependents."
        ),
    )
    p_replan_scope.add_argument(
        "workspace", help="Roadmap workspace directory, or a bare <roadmap-id>."
    )
    p_replan_scope.add_argument(
        "--repo-root",
        default=None,
        help="Repository root for <roadmap-id> resolution (default: auto-detect).",
    )
    p_replan_scope.set_defaults(func=_cmd_replan_scope)

    p_replan_finish = sub.add_parser(
        "replan-finish",
        help=(
            "Close out a replan: approve the re-decomposed items, validate the "
            "roadmap, and delete the replan request."
        ),
    )
    p_replan_finish.add_argument(
        "workspace", help="Roadmap workspace directory, or a bare <roadmap-id>."
    )
    p_replan_finish.add_argument(
        "--repo-root",
        default=None,
        help="Repository root for schema resolution (default: auto-detect).",
    )
    p_replan_finish.set_defaults(func=_cmd_replan_finish)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
