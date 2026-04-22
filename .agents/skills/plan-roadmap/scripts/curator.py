"""Host-assisted curation for plan-roadmap (Mode A).

The structural decomposer (``decomposer.decompose``) produces a draft
Roadmap from a markdown proposal using deterministic parsing only. That
draft usually needs semantic cleanup: narrative sections captured as
items, generic acceptance outcomes, unsized effort estimates, missing
dependency edges.

This module implements the **host-assisted** seam. Instead of calling an
external LLM API (``llm_client.py``), the skill emits a JSON request
describing the draft + per-item heuristic flags, hands off to the
orchestrating Claude Code agent for curation decisions, and then applies
the agent's JSON response to produce the final roadmap.

The alternative, headless mode (``semantic_decomposer.py``) remains
available for batch/CI callers (e.g., ``autopilot-roadmap``) where no
interactive agent is orchestrating. See SKILL.md for the mode matrix.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Import shared modules (same pattern as semantic_decomposer.py)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
_RUNTIME_DIR = _SCRIPTS_DIR.parent.parent / "roadmap-runtime" / "scripts"
for p in [str(_SCRIPTS_DIR), str(_RUNTIME_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from decomposer import _break_cycles, decompose  # type: ignore[import-untyped]
from models import (  # type: ignore[import-untyped]
    Effort,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
    load_roadmap,
    save_roadmap,
)

# ---------------------------------------------------------------------------
# Heuristic detectors — used to populate `heuristic_flags` in the request
# ---------------------------------------------------------------------------
_NARRATIVE_TITLES = re.compile(
    r"^\s*(context|goals?|overview|introduction|summary|background|"
    r"motivation|guiding\s+principles?|out\s+of\s+scope)\b",
    re.IGNORECASE,
)
_CONSTRAINT_TITLES = re.compile(
    r"^\s*(constraints?|requirements?|assumptions?|non-?functional)\b",
    re.IGNORECASE,
)
_PHASE_TITLES = re.compile(
    r"^\s*(phase|stage|milestone|step|iteration|sprint)\b",
    re.IGNORECASE,
)
_CAPABILITY_WORDS = re.compile(
    r"\b(capabilit|feature|component|module|service|endpoint|system|function)",
    re.IGNORECASE,
)


def _compute_heuristic_flags(item: RoadmapItem) -> list[str]:
    """Return machine-inferred hints for the agent. Ordering not load-bearing."""
    flags: list[str] = []
    title = item.title or ""

    if _NARRATIVE_TITLES.search(title):
        flags.append("likely-narrative")
    if _CONSTRAINT_TITLES.search(title):
        flags.append("likely-constraint")
    if _PHASE_TITLES.match(title):
        flags.append("phase-header")
    if _CAPABILITY_WORDS.search(title):
        flags.append("has-capability-keyword")

    # Generic acceptance outcome: the fallback "X is implemented and tested"
    synthetic = f"{title} is implemented and tested"
    if item.acceptance_outcomes and item.acceptance_outcomes == [synthetic]:
        flags.append("generic-acceptance")

    if item.effort == Effort.XS:
        flags.append("small-effort-estimate")
    if not item.depends_on:
        flags.append("no-dependencies-inferred")

    return flags


# ---------------------------------------------------------------------------
# Instruction text for the agent (embedded in the request file)
# ---------------------------------------------------------------------------
_INSTRUCTIONS = """\
# Curation request for plan-roadmap (host-assisted mode)

The structural decomposer produced a draft roadmap with the items listed
under `candidates`. Your job: reason about each item and emit a
`curation-response.json` file that conforms to
`skills/plan-roadmap/contracts/curation-response.schema.json`.

For each candidate, choose one action:

- **keep** — the item is a real deliverable. Optionally override `new_id`,
  `title`, `effort` (XS/S/M/L/XL), `priority` (1=highest), and `depends_on`.
  `depends_on` entries may reference the original_id of another candidate
  OR the new_id declared in another "keep" decision; IDs are normalized
  on apply.

- **drop** — the item is narrative, a constraint, a phase header, or
  otherwise not a deliverable.

- **merge** — the item overlaps with another and should be folded into it.
  Provide `merge_into` (original_id or new_id of the target).

Every decision must carry a `rationale` (one line, audited).

Priority heuristic: items with no inbound deps get priority 1, the next
topological layer gets 2, and so on. Priority ties between siblings are
fine.

Effort heuristic: XS = under a day, S = a day, M = 2-3 days,
L = a week, XL = two weeks. Pick the smallest plausible bucket.

After you write the response file, invoke:

    python skills/plan-roadmap/scripts/curator.py finalize \\
        --draft <draft_roadmap_ref> \\
        --decisions <response_path_hint> \\
        --out openspec/roadmap.yaml

The finalize command re-validates the DAG and writes the schema-valid
final roadmap.
"""


# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------
def build_curation_request(
    draft: Roadmap,
    draft_roadmap_ref: str,
    response_path_hint: str,
) -> dict:
    """Build a curation-request JSON payload from a draft roadmap.

    The request is a pure data structure. The caller decides where to
    write it (typically ``<out_dir>/curation-request.json``).
    """
    candidates: list[dict] = []
    for item in draft.items:
        excerpt = item.description or ""
        if len(excerpt) > 500:
            excerpt = excerpt[:500].rstrip() + "..."

        candidates.append({
            "original_id": item.item_id,
            "title": item.title,
            "body_excerpt": excerpt,
            "parsed_effort": item.effort.value,
            "parsed_priority": item.priority,
            "parsed_depends_on": list(item.depends_on),
            "parsed_acceptance_outcomes": list(item.acceptance_outcomes or []),
            "heuristic_flags": _compute_heuristic_flags(item),
        })

    return {
        "schema_version": 1,
        "source_proposal": draft.source_proposal,
        "draft_roadmap_ref": draft_roadmap_ref,
        "response_path_hint": response_path_hint,
        "instructions": _INSTRUCTIONS,
        "candidates": candidates,
    }


# ---------------------------------------------------------------------------
# Decision objects + parsing
# ---------------------------------------------------------------------------
@dataclass
class _Decision:
    original_id: str
    action: str  # keep | drop | merge
    rationale: str = ""
    new_id: str | None = None
    title: str | None = None
    effort: str | None = None
    priority: int | None = None
    depends_on: list[str] | None = None
    merge_into: str | None = None


def _parse_response(response: dict) -> list[_Decision]:
    """Validate schema-shape and return typed decisions.

    We don't depend on jsonschema here — keep curator.py importable in
    constrained environments. Full schema validation is in tests.
    """
    if response.get("schema_version") != 1:
        raise ValueError(f"Unsupported schema_version: {response.get('schema_version')}")
    decisions: list[_Decision] = []
    for raw in response.get("decisions", []):
        action = raw.get("action")
        if action not in ("keep", "drop", "merge"):
            raise ValueError(f"Invalid action: {action!r}")
        if action == "merge" and not raw.get("merge_into"):
            raise ValueError(f"action=merge requires merge_into (original_id={raw.get('original_id')})")
        decisions.append(_Decision(
            original_id=raw["original_id"],
            action=action,
            rationale=raw.get("rationale", ""),
            new_id=raw.get("new_id"),
            title=raw.get("title"),
            effort=raw.get("effort"),
            priority=raw.get("priority"),
            depends_on=raw.get("depends_on"),
            merge_into=raw.get("merge_into"),
        ))
    return decisions


# ---------------------------------------------------------------------------
# Curation application
# ---------------------------------------------------------------------------
def apply_curation(draft: Roadmap, response: dict) -> Roadmap:
    """Apply agent decisions to a draft roadmap.

    Semantics:
    - Items with no matching decision are preserved as-is.
    - action=drop removes the item.
    - action=keep applies overrides (new_id / title / effort / priority /
      depends_on) to the item.
    - action=merge removes the source item; its depends_on edges are
      rewritten to point to the merge target on any other item that
      depended on the source.
    - depends_on entries may reference original_ids or new_ids; both
      are normalized.

    Raises ValueError on invalid decisions (unknown original_id, merge
    cycles, merge target that was dropped).
    """
    decisions = _parse_response(response)
    decisions_by_orig = {d.original_id: d for d in decisions}

    orig_ids = {it.item_id for it in draft.items}
    for d in decisions:
        if d.original_id not in orig_ids:
            raise ValueError(f"Decision references unknown original_id: {d.original_id!r}")

    # Resolve merge chains: a -> b -> c becomes a -> c.
    # Also collapse keep's new_id rename in the same map.
    rename_map: dict[str, str | None] = {}
    for d in decisions:
        if d.action == "drop":
            rename_map[d.original_id] = None
        elif d.action == "keep":
            rename_map[d.original_id] = d.new_id or d.original_id
        elif d.action == "merge":
            rename_map[d.original_id] = d.merge_into

    # Chase chains. A keep-no-op looks like start -> start in rename_map
    # and terminates the walk immediately. A real cycle is when we revisit
    # an id we actually moved through.
    for start in list(rename_map.keys()):
        if rename_map[start] == start:
            continue  # keep no-op: item retains its original_id

        visited: set[str] = {start}
        curr: str | None = rename_map[start]
        while curr is not None and curr in rename_map:
            next_curr = rename_map[curr]
            if next_curr == curr:
                break  # fixed point: curr is a keep no-op, destination = curr
            if curr in visited:
                raise ValueError(f"Merge cycle detected at {curr!r} from {start!r}")
            visited.add(curr)
            curr = next_curr
        rename_map[start] = curr  # final destination (or None if dropped)

    # Items without decisions keep their original_id
    for it in draft.items:
        rename_map.setdefault(it.item_id, it.item_id)

    # Build the new item list
    new_items: list[RoadmapItem] = []
    seen_new_ids: set[str] = set()
    for orig_item in draft.items:
        decision = decisions_by_orig.get(orig_item.item_id)
        final_id = rename_map[orig_item.item_id]
        if final_id is None:
            continue  # dropped, directly or via merge chain to drop
        if decision is None or decision.action == "keep":
            if final_id in seen_new_ids:
                continue  # duplicate after rename; earlier item wins
            seen_new_ids.add(final_id)
            # Mutate in place; Roadmap/RoadmapItem are plain dataclasses
            orig_item.item_id = final_id
            if decision is not None:
                if decision.title is not None:
                    orig_item.title = decision.title
                if decision.effort is not None:
                    orig_item.effort = Effort(decision.effort)
                if decision.priority is not None:
                    orig_item.priority = decision.priority
                if decision.depends_on is not None:
                    orig_item.depends_on = list(decision.depends_on)
            new_items.append(orig_item)
        # drop / merge: skip the source item (its edges get rewired below)

    # Normalize depends_on across the surviving items: apply rename_map, drop
    # edges whose target was dropped entirely.
    kept_ids = {it.item_id for it in new_items}
    for it in new_items:
        rewritten: list[str] = []
        for dep in it.depends_on:
            target = rename_map.get(dep, dep)
            if target is None:
                continue  # dep was dropped
            if target == it.item_id:
                continue  # self-edge from merge
            if target not in kept_ids:
                # Unknown dep — could be a typo. Drop rather than fail; the
                # DAG validator would reject it anyway.
                continue
            if target not in rewritten:
                rewritten.append(target)
        it.depends_on = rewritten

    # Build new Roadmap (reuse draft metadata)
    curated = Roadmap(
        schema_version=draft.schema_version,
        roadmap_id=draft.roadmap_id,
        source_proposal=draft.source_proposal,
        items=new_items,
        created_at=draft.created_at,
        updated_at=datetime.now(timezone.utc).isoformat(),
        status=draft.status,
        policy=draft.policy,
    )

    _break_cycles(curated.items)
    if curated.has_cycle():
        raise RuntimeError("Cycle remained after _break_cycles — bug in apply_curation")

    return curated


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cmd_structural(args: argparse.Namespace) -> int:
    proposal_path = Path(args.proposal)
    if not proposal_path.exists():
        print(f"error: proposal not found: {proposal_path}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    text = proposal_path.read_text()
    draft = decompose(text, str(proposal_path))

    draft_path = out_dir / "roadmap.draft.yaml"
    request_path = out_dir / "curation-request.json"
    response_hint = out_dir / "curation-response.json"

    save_roadmap(draft, draft_path)
    request = build_curation_request(
        draft,
        draft_roadmap_ref=str(draft_path),
        response_path_hint=str(response_hint),
    )
    request_path.write_text(json.dumps(request, indent=2) + "\n")

    print(f"wrote {draft_path}")
    print(f"wrote {request_path}")
    print(f"  {len(draft.items)} draft items — agent should curate and write {response_hint}")
    return 0


def _cmd_finalize(args: argparse.Namespace) -> int:
    draft = load_roadmap(Path(args.draft))
    response = json.loads(Path(args.decisions).read_text())
    curated = apply_curation(draft, response)
    save_roadmap(curated, Path(args.out))
    print(f"wrote {args.out} ({len(curated.items)} items after curation)")
    return 0


def _cmd_decompose(args: argparse.Namespace) -> int:
    """Legacy one-shot: structural decomposition only, no curation.

    Mirrors the pre-host-assisted behavior. For headless semantic mode,
    use ``semantic_decomposer.py`` directly.
    """
    text = Path(args.proposal).read_text()
    roadmap = decompose(text, args.proposal)
    save_roadmap(roadmap, Path(args.out))
    print(f"wrote {args.out} ({len(roadmap.items)} items, structural only)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="curator",
        description="Host-assisted curation for plan-roadmap (Mode A)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_struct = sub.add_parser("structural", help="Run structural pass, emit draft + curation request")
    p_struct.add_argument("--proposal", required=True, help="Path to proposal markdown file")
    p_struct.add_argument("--out-dir", required=True, help="Directory for roadmap.draft.yaml + curation-request.json")
    p_struct.set_defaults(func=_cmd_structural)

    p_final = sub.add_parser("finalize", help="Apply curation decisions to produce final roadmap")
    p_final.add_argument("--draft", required=True, help="Path to roadmap.draft.yaml from structural pass")
    p_final.add_argument("--decisions", required=True, help="Path to curation-response.json from the agent")
    p_final.add_argument("--out", required=True, help="Path to write the final roadmap.yaml")
    p_final.set_defaults(func=_cmd_finalize)

    p_one = sub.add_parser("decompose", help="One-shot structural decomposition (no curation)")
    p_one.add_argument("--proposal", required=True)
    p_one.add_argument("--out", required=True)
    p_one.set_defaults(func=_cmd_decompose)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
