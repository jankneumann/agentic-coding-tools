"""Two-pass semantic decomposer for markdown proposals.

Orchestrates four passes to decompose a proposal into a roadmap:

  Pass 1 — Structural scan (enhanced deterministic parsing)
  Pass 2 — Semantic item classification (LLM-driven)
  Pass 3 — Two-tier dependency inference (deterministic scope + LLM analyst)
  Pass 4 — Validation (archive cross-check, cycle breaking, path normalization)

Falls back to the structural-only ``decompose()`` from ``decomposer.py``
when no LLM client is available.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Import shared modules
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
_RUNTIME_DIR = _SCRIPTS_DIR.parent.parent / "roadmap-runtime" / "scripts"
for p in [str(_SCRIPTS_DIR), str(_RUNTIME_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from decomposer import (  # type: ignore[import-untyped]
    _break_cycles,
    _classify_sections,
    _extract_table_items,
    _generate_clean_id,
    _parse_sections,
    build_dependency_dag,
    decompose,
    make_repo_relative,
    scan_archive_state,
    validate_proposal,
)
from models import (  # type: ignore[import-untyped]
    DepEdge,
    DepEdgeSource,
    Effort,
    ItemStatus,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Candidate block from Pass 1
# ---------------------------------------------------------------------------
@dataclass
class _CandidateBlock:
    """A text block identified by Pass 1 as potentially containing a
    roadmap item.  Pass 2 decides whether to promote, discard, or merge."""

    index: int
    title: str
    body: str
    source_line: int
    section_level: int = 2
    from_table: bool = False


# ---------------------------------------------------------------------------
# Pass 2 — LLM prompt template
# ---------------------------------------------------------------------------

# WHY each instruction exists is commented inline so a future maintainer
# can distinguish load-bearing rules from cosmetic choices.

_PASS2_SYSTEM_PROMPT = """\
You are a roadmap decomposer.  You receive candidate text blocks extracted
from a software proposal, and your job is to classify each as a real
roadmap item or noise.

Output ONLY valid JSON matching this schema — no markdown, no preamble:

{
  "items": [
    {
      "decision": "yes" | "no" | "merge",
      // "merge" means this block refines an earlier item — specify merge_with.
      "merge_with": "<item_id to merge with>",  // only if decision = "merge"

      // The following fields are required when decision = "yes":
      "item_id": "<kebab-case-id>",
      // WHY kebab-case: matches OpenSpec change-id conventions so the ID
      // can be used directly as a directory name and branch suffix.
      // Do NOT use numeric prefixes like "ri-01-" or section numbers.

      "title": "<concise one-line title>",

      "description": "<2-3 sentence description, sentence-ended>",
      // WHY sentence-ended: downstream consumers truncate at arbitrary
      // boundaries if the description isn't a complete sentence.

      "acceptance_outcomes": ["<individually testable outcome>", ...],
      // WHY individually testable: each outcome becomes a checkbox in
      // the implementation task list.  Colon-ending bullet headers
      // like "Every call should emit spans with:" are NOT outcomes.

      "effort": "XS" | "S" | "M" | "L" | "XL",
      // Estimate based on scope: XS=trivial fix, S=small, M=moderate,
      // L=multi-day, XL=multi-week.

      "kind": "phase" | "non-phase"
      // "phase" = new capability or bootstrap item.
      // "non-phase" = spec-sync, tooling, meta, documentation-only.
    }
  ]
}

Classification rules:
- A block is "yes" if it describes a DISTINCT capability, feature, or
  deliverable that requires implementation work.
- A block is "no" if it is:
  - An example or code snippet illustrating how something WOULD work
  - A meta-section (recommended ordering, summary, table of contents)
  - Pure prose/narrative without actionable content
  - A constraints section (non-functional requirements belong on items,
    not as standalone items)
- A block is "merge" if it refines or extends an earlier "yes" item
  (e.g., sub-requirements of a broader capability).

IMPORTANT:
- Do NOT create items from YAML/code examples embedded in the proposal.
- Do NOT collapse multiple distinct items into one.
- Priority tables may have one item per ROW — each row is a candidate.
- Sub-sections (§3.1, §3.2, etc.) may each be distinct items even though
  they share a parent section.
"""

_PASS2_USER_TEMPLATE = """\
## Proposal text

{proposal_text}

## Candidate blocks from structural scan

{candidate_blocks}

## Already-archived change IDs (do not duplicate these)

{archived_ids}

## Instructions

Classify each candidate block above.  For each "yes" item, provide all
required fields.  Return ONLY the JSON object.
"""


# ---------------------------------------------------------------------------
# Pass 3 — Dependency inference prompt (Tier B)
# ---------------------------------------------------------------------------
_PASS3_TIER_B_SYSTEM = """\
You are a dependency analyst.  Given pairs of roadmap items, determine
whether item B functionally depends on item A — meaning A must be
completed before B can begin.

Output ONLY valid JSON:
{
  "verdicts": [
    {
      "item_a": "<id>",
      "item_b": "<id>",
      "depends_on": "yes" | "no" | "unclear",
      "rationale": "<one sentence explaining why>",
      "confidence": "low" | "medium" | "high"
    }
  ]
}

Rules:
- A dependency is FUNCTIONAL (B needs A's output/artifact/API), not
  chronological (A happens to come first in the document).
- "unclear" means you cannot determine the relationship from the
  descriptions alone.
- Infrastructure items do NOT automatically block feature items unless
  the feature specifically needs that infrastructure's output.
"""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def semantic_decompose(
    proposal_text: str,
    source_path: str,
    repo_root: Path | None = None,
    llm_client: object | None = None,
) -> Roadmap:
    """Decompose a markdown proposal into a Roadmap using the four-pass
    architecture.

    Args:
        proposal_text: Full markdown text of the proposal.
        source_path: Path to the source proposal file.
        repo_root: Repository root for archive scanning and path
            normalization.  Falls back to cwd if not provided.
        llm_client: An ``LlmClient`` instance.  When ``None``, falls
            back to the structural-only ``decompose()`` with
            post-processing.

    Returns:
        A Roadmap with candidate items and dependency DAG.
    """
    if repo_root is None:
        repo_root = Path.cwd()

    # Normalize source path
    source_path = make_repo_relative(source_path, repo_root)

    # Scan repo state for archive cross-check
    archive_state = scan_archive_state(repo_root)

    if llm_client is None:
        return _fallback_structural(proposal_text, source_path, repo_root, archive_state)

    return _full_semantic(
        proposal_text, source_path, repo_root, archive_state, llm_client
    )


# ---------------------------------------------------------------------------
# Fallback path (no LLM available)
# ---------------------------------------------------------------------------
def _fallback_structural(
    proposal_text: str,
    source_path: str,
    repo_root: Path,
    archive_state: dict[str, str],
) -> Roadmap:
    """Structural-only decomposition with post-processing.

    Uses the existing ``decompose()`` function, then applies:
    - Clean ID generation (no ri- prefix)
    - change_id population
    - Archive cross-check
    """
    roadmap = decompose(proposal_text, source_path)

    # Post-process: clean IDs, change_id, archive status
    id_remap: dict[str, str] = {}
    seen_ids: set[str] = set()
    for item in roadmap.items:
        clean_id = _generate_clean_id(item.title)
        # Collision detection: append suffix if ID already used
        base_id = clean_id
        suffix = 2
        while clean_id in seen_ids:
            clean_id = f"{base_id}-{suffix}"
            suffix += 1
        seen_ids.add(clean_id)
        id_remap[item.item_id] = clean_id
        item.item_id = clean_id
        item.change_id = clean_id

        # Archive cross-check
        if clean_id in archive_state:
            status_str = archive_state[clean_id]
            if status_str == "completed":
                item.status = ItemStatus.COMPLETED
            elif status_str == "in_progress":
                item.status = ItemStatus.IN_PROGRESS

    # Remap dependency references
    for item in roadmap.items:
        item.depends_on = [id_remap.get(d, d) for d in item.depends_on]

    return roadmap


# ---------------------------------------------------------------------------
# Full semantic path (LLM available)
# ---------------------------------------------------------------------------
def _full_semantic(
    proposal_text: str,
    source_path: str,
    repo_root: Path,
    archive_state: dict[str, str],
    llm_client: object,
) -> Roadmap:
    """Full four-pass semantic decomposition."""

    # ------------------------------------------------------------------
    # Pass 1 — Structural scan
    # ------------------------------------------------------------------
    errors = validate_proposal(proposal_text)
    if errors:
        raise ValueError(f"Proposal validation failed: {'; '.join(errors)}")

    sections = _parse_sections(proposal_text)
    sections = _classify_sections(sections)

    candidates: list[_CandidateBlock] = []
    for i, section in enumerate(sections):
        candidates.append(
            _CandidateBlock(
                index=i,
                title=section.title,
                body=section.body,
                source_line=section.line_start,
                section_level=section.level,
            )
        )
        # Also extract table rows from this section's body
        table_items = _extract_table_items(section.body)
        for ti in table_items:
            candidates.append(
                _CandidateBlock(
                    index=len(candidates),
                    title=ti.title,
                    body=ti.body,
                    source_line=ti.line_start,
                    section_level=ti.level,
                    from_table=True,
                )
            )

    if not candidates:
        raise ValueError("No candidate blocks found in proposal")

    # ------------------------------------------------------------------
    # Pass 2 — Semantic item classification (single batch LLM call)
    # ------------------------------------------------------------------
    candidate_text = "\n".join(
        f"[Block {c.index}] (line {c.source_line}, "
        f"{'table row' if c.from_table else f'H{c.section_level}'})\n"
        f"Title: {c.title}\n"
        f"Body: {c.body[:500]}\n"
        for c in candidates
    )

    archived_ids_text = ", ".join(sorted(archive_state.keys())) or "(none)"

    user_prompt = _PASS2_USER_TEMPLATE.format(
        proposal_text=proposal_text[:8000],  # trim to fit context
        candidate_blocks=candidate_text,
        archived_ids=archived_ids_text,
    )

    from llm_client import LlmResult, extract_json  # type: ignore[import-untyped]

    result: LlmResult = llm_client.structured_call(  # type: ignore[union-attr]
        system=_PASS2_SYSTEM_PROMPT,
        user=user_prompt,
    )

    parsed = extract_json(result.content)
    if not parsed or not isinstance(parsed, dict) or "items" not in parsed:
        logger.warning(
            "LLM returned invalid JSON for Pass 2, falling back to structural"
        )
        return _fallback_structural(
            proposal_text, source_path, repo_root, archive_state
        )

    # Build RoadmapItems from LLM output
    items: list[RoadmapItem] = []
    seen_ids: set[str] = set()
    merge_map: dict[str, str] = {}  # block title → merge target item_id
    priority = 1

    for entry in parsed["items"]:
        decision = entry.get("decision", "no")

        if decision == "no":
            continue

        if decision == "merge":
            merge_target = entry.get("merge_with")
            if merge_target:
                # Find the item and append description
                for item in items:
                    if item.item_id == merge_target:
                        extra_desc = entry.get("description", "")
                        if extra_desc and item.description:
                            item.description = f"{item.description} {extra_desc}"
                        extra_outcomes = entry.get("acceptance_outcomes", [])
                        item.acceptance_outcomes.extend(extra_outcomes)
                        break
            continue

        # decision == "yes"
        item_id = entry.get("item_id", "")
        if not item_id:
            continue

        # Ensure unique IDs
        base_id = item_id
        suffix = 2
        while item_id in seen_ids:
            item_id = f"{base_id}-{suffix}"
            suffix += 1
        seen_ids.add(item_id)

        # Map effort string to enum
        effort_str = entry.get("effort", "M").upper()
        try:
            effort = Effort(effort_str)
        except ValueError:
            effort = Effort.M

        kind = entry.get("kind", "phase")

        item = RoadmapItem(
            item_id=item_id,
            title=entry.get("title", ""),
            status=ItemStatus.CANDIDATE,
            priority=priority,
            effort=effort,
            description=entry.get("description"),
            acceptance_outcomes=entry.get("acceptance_outcomes", []),
            change_id=item_id,
            rationale=f"kind: {kind}" if kind == "non-phase" else None,
        )
        items.append(item)
        priority += 1

    if not items:
        logger.warning("LLM produced no items, falling back to structural")
        return _fallback_structural(
            proposal_text, source_path, repo_root, archive_state
        )

    # ------------------------------------------------------------------
    # Pass 3 — Dependency inference
    # ------------------------------------------------------------------
    items = _infer_dependencies(items, proposal_text, llm_client, archive_state)

    # ------------------------------------------------------------------
    # Pass 4 — Validation
    # ------------------------------------------------------------------

    # Archive cross-check
    for item in items:
        if item.item_id in archive_state:
            status_str = archive_state[item.item_id]
            if status_str == "completed":
                item.status = ItemStatus.COMPLETED
            elif status_str == "in_progress":
                item.status = ItemStatus.IN_PROGRESS

    # Cycle breaking (prefer low-confidence LLM edges)
    _break_cycles_by_confidence(items)

    # Build roadmap
    slug = re.sub(r"[^a-z0-9]+", "-", Path(source_path).stem.lower()).strip("-")
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id=f"roadmap-{slug}",
        source_proposal=source_path,
        items=items,
        created_at=datetime.now(timezone.utc).isoformat(),
        status=RoadmapStatus.PLANNING,
    )

    if roadmap.has_cycle():
        # Last resort — use the standard cycle breaker
        _break_cycles(items)
        if roadmap.has_cycle():
            raise RuntimeError("BUG: dependency DAG contains cycles after breaking")

    return roadmap


# ---------------------------------------------------------------------------
# Pass 3 — Dependency inference helpers
# ---------------------------------------------------------------------------
def _infer_dependencies(
    items: list[RoadmapItem],
    proposal_text: str,
    llm_client: object,
    archive_state: dict[str, str],
) -> list[RoadmapItem]:
    """Two-tier dependency inference.

    Tier A: deterministic scope overlap (when both items have scope).
    Tier B-0: cheap pruning (skip obviously independent pairs).
    Tier B: LLM analyst for remaining pairs.
    """
    from llm_client import extract_json  # type: ignore[import-untyped]

    # Tier A: deterministic scope overlap
    _apply_tier_a(items)

    # Build pairs for Tier B (items without scope)
    tier_b_pairs: list[tuple[RoadmapItem, RoadmapItem]] = []
    for i, item_a in enumerate(items):
        for item_b in items[i + 1 :]:
            # Skip if already connected via Tier A or explicit edges
            if item_b.item_id in item_a.depends_on or item_a.item_id in item_b.depends_on:
                continue

            # Tier B-0: cheap pruning
            if _tier_b0_can_prune(item_a, item_b, items):
                continue

            tier_b_pairs.append((item_a, item_b))

    # Tier B: LLM analyst dispatch (batched)
    if tier_b_pairs:
        _apply_tier_b(tier_b_pairs, llm_client)

    return items


def _apply_tier_a(items: list[RoadmapItem]) -> None:
    """Tier A: add edges based on declared scope overlap."""
    for i, item_a in enumerate(items):
        if not item_a.scope:
            continue
        for item_b in items[i + 1 :]:
            if not item_b.scope:
                continue

            rationale = _check_scope_overlap(item_a.scope, item_b.scope)
            if rationale:
                # Add edge: higher priority depends on lower priority
                if item_a.priority < item_b.priority:
                    item_b.depends_on.append(item_a.item_id)
                    item_b.dep_edges.append(
                        DepEdge(
                            id=item_a.item_id,
                            source=DepEdgeSource.DETERMINISTIC,
                            rationale=rationale,
                        )
                    )
                else:
                    item_a.depends_on.append(item_b.item_id)
                    item_a.dep_edges.append(
                        DepEdge(
                            id=item_b.item_id,
                            source=DepEdgeSource.DETERMINISTIC,
                            rationale=rationale,
                        )
                    )


def _check_scope_overlap(scope_a: object, scope_b: object) -> str:
    """Check for overlap between two Scope objects.

    Delegates to shared ``scope_overlap.check_scope_overlap()`` from
    ``roadmap-runtime/scripts/scope_overlap.py``.
    """
    from scope_overlap import check_scope_overlap  # type: ignore[import-untyped]

    return check_scope_overlap(
        write_a=getattr(scope_a, "write_allow", []),
        read_a=getattr(scope_a, "read_allow", []),
        lock_a=getattr(scope_a, "lock_keys", []),
        write_b=getattr(scope_b, "write_allow", []),
        read_b=getattr(scope_b, "read_allow", []),
        lock_b=getattr(scope_b, "lock_keys", []),
    )


def _tier_b0_can_prune(
    item_a: RoadmapItem,
    item_b: RoadmapItem,
    all_items: list[RoadmapItem],
) -> bool:
    """Tier B-0: cheap pruning before LLM dispatch.

    Returns True if the pair can be skipped (obviously independent).
    Only SKIPS dispatch — never ADDS edges.
    """
    # Rule 1: if already transitively connected, skip
    if _is_transitively_connected(item_a, item_b, all_items):
        return True

    # Rule 2: if titles share no significant words, skip
    words_a = set(re.findall(r"\b\w{4,}\b", item_a.title.lower()))
    words_b = set(re.findall(r"\b\w{4,}\b", item_b.title.lower()))
    common = {"with", "that", "this", "from", "have", "will", "should",
              "must", "each", "when", "then", "also", "into", "more"}
    meaningful_overlap = (words_a & words_b) - common
    # If both items also have no description overlap, prune
    if not meaningful_overlap:
        desc_words_a = set(re.findall(r"\b\w{5,}\b", (item_a.description or "").lower()))
        desc_words_b = set(re.findall(r"\b\w{5,}\b", (item_b.description or "").lower()))
        desc_overlap = (desc_words_a & desc_words_b) - common
        if len(desc_overlap) < 3:
            return True

    return False


def _is_transitively_connected(
    item_a: RoadmapItem,
    item_b: RoadmapItem,
    all_items: list[RoadmapItem],
) -> bool:
    """Check if item_a and item_b are already transitively connected."""
    id_map = {it.item_id: it for it in all_items}
    visited: set[str] = set()

    def _reachable(start: str, target: str) -> bool:
        if start == target:
            return True
        if start in visited:
            return False
        visited.add(start)
        item = id_map.get(start)
        if item:
            for dep in item.depends_on:
                if _reachable(dep, target):
                    return True
        return False

    return _reachable(item_a.item_id, item_b.item_id) or _reachable(
        item_b.item_id, item_a.item_id
    )


def _apply_tier_b(
    pairs: list[tuple[RoadmapItem, RoadmapItem]],
    llm_client: object,
) -> None:
    """Tier B: LLM analyst dispatch for dependency inference.

    Batches pairs into groups of 10 for cost efficiency.
    Applies conservative policy: unclear/low-confidence → keep edge.
    """
    from llm_client import extract_json  # type: ignore[import-untyped]

    BATCH_SIZE = 10
    MAX_PAIRS = 50

    if len(pairs) > MAX_PAIRS:
        logger.warning(
            "Tier B: %d pairs exceed ceiling (%d), adding conservative edges for excess",
            len(pairs), MAX_PAIRS,
        )
        # Add conservative edges for excess pairs
        for item_a, item_b in pairs[MAX_PAIRS:]:
            if item_a.priority < item_b.priority:
                item_b.depends_on.append(item_a.item_id)
                item_b.dep_edges.append(
                    DepEdge(
                        id=item_a.item_id,
                        source=DepEdgeSource.CEILING_SKIPPED,
                        rationale="ceiling-skipped: too many pairs for LLM dispatch",
                        confidence="low",
                    )
                )
        pairs = pairs[:MAX_PAIRS]

    # Batch dispatch
    for batch_start in range(0, len(pairs), BATCH_SIZE):
        batch = pairs[batch_start : batch_start + BATCH_SIZE]
        _dispatch_tier_b_batch(batch, llm_client)


def _dispatch_tier_b_batch(
    batch: list[tuple[RoadmapItem, RoadmapItem]],
    llm_client: object,
) -> None:
    """Dispatch a batch of pairs to the LLM analyst."""
    from llm_client import LlmResult, extract_json  # type: ignore[import-untyped]

    pairs_text = "\n".join(
        f"Pair {i+1}:\n"
        f"  Item A ({a.item_id}): {a.title}\n"
        f"    Description: {(a.description or '')[:200]}\n"
        f"  Item B ({b.item_id}): {b.title}\n"
        f"    Description: {(b.description or '')[:200]}\n"
        for i, (a, b) in enumerate(batch)
    )

    user_prompt = (
        f"Analyze these {len(batch)} pairs of roadmap items and determine "
        f"functional dependencies.\n\n{pairs_text}"
    )

    try:
        result: LlmResult = llm_client.structured_call(  # type: ignore[union-attr]
            system=_PASS3_TIER_B_SYSTEM,
            user=user_prompt,
            max_tokens=4096,
        )

        parsed = extract_json(result.content)
        if not parsed or not isinstance(parsed, dict):
            logger.warning("Tier B: invalid JSON response, applying conservative policy")
            _apply_conservative_batch(batch)
            return

        verdicts = parsed.get("verdicts", [])
        verdict_map: dict[tuple[str, str], dict] = {}
        for v in verdicts:
            key = (v.get("item_a", ""), v.get("item_b", ""))
            verdict_map[key] = v

        for item_a, item_b in batch:
            key = (item_a.item_id, item_b.item_id)
            verdict = verdict_map.get(key)
            if verdict:
                _apply_verdict(item_a, item_b, verdict)
            else:
                # No verdict for this pair — conservative: add edge
                _apply_conservative_edge(item_a, item_b, "no verdict returned")

    except Exception as exc:  # noqa: BLE001
        logger.warning("Tier B dispatch failed: %s, applying conservative policy", exc)
        _apply_conservative_batch(batch)


def _apply_verdict(
    item_a: RoadmapItem,
    item_b: RoadmapItem,
    verdict: dict,
) -> None:
    """Apply a single Tier B verdict with conservative policy.

    Conservative: unclear/low-confidence → keep edge.
    """
    depends_on = verdict.get("depends_on", "unclear")
    confidence = verdict.get("confidence", "low")
    rationale = verdict.get("rationale", "")

    if depends_on == "yes":
        # A must complete before B
        if item_a.priority < item_b.priority:
            item_b.depends_on.append(item_a.item_id)
            item_b.dep_edges.append(
                DepEdge(
                    id=item_a.item_id,
                    source=DepEdgeSource.LLM,
                    rationale=rationale,
                    confidence=confidence,
                )
            )
        else:
            item_a.depends_on.append(item_b.item_id)
            item_a.dep_edges.append(
                DepEdge(
                    id=item_b.item_id,
                    source=DepEdgeSource.LLM,
                    rationale=rationale,
                    confidence=confidence,
                )
            )
    elif depends_on == "no" and confidence in ("medium", "high"):
        # Confident no-dependency — skip edge
        pass
    else:
        # Conservative fallback: unclear or low-confidence "no"
        _apply_conservative_edge(
            item_a, item_b,
            f"conservative-fallback: {depends_on}/{confidence}",
        )


def _apply_conservative_edge(
    item_a: RoadmapItem,
    item_b: RoadmapItem,
    rationale: str,
) -> None:
    """Add a conservative edge (higher priority blocks lower)."""
    if item_a.priority < item_b.priority:
        if item_a.item_id not in item_b.depends_on:
            item_b.depends_on.append(item_a.item_id)
            item_b.dep_edges.append(
                DepEdge(
                    id=item_a.item_id,
                    source=DepEdgeSource.LLM,
                    rationale=rationale,
                    confidence="low",
                )
            )


def _apply_conservative_batch(
    batch: list[tuple[RoadmapItem, RoadmapItem]],
) -> None:
    """Apply conservative policy to all pairs in a batch."""
    for item_a, item_b in batch:
        _apply_conservative_edge(item_a, item_b, "conservative-fallback: llm-error")


# ---------------------------------------------------------------------------
# Confidence-aware cycle breaking
# ---------------------------------------------------------------------------
def _break_cycles_by_confidence(items: list[RoadmapItem]) -> None:
    """Break cycles by removing lowest-confidence LLM edges first.

    Falls back to standard DFS back-edge removal when all edges in
    a cycle are deterministic or explicit.
    """
    id_map = {it.item_id: it for it in items}
    max_iterations = 100

    for _ in range(max_iterations):
        cycle = _find_cycle(items)
        if not cycle:
            return

        # Find the lowest-confidence LLM edge in the cycle
        best_edge_to_remove: tuple[str, str] | None = None
        best_confidence_rank = 999

        confidence_rank = {"low": 0, "medium": 1, "high": 2}

        for i in range(len(cycle)):
            from_id = cycle[i]
            to_id = cycle[(i + 1) % len(cycle)]
            item = id_map.get(from_id)
            if not item:
                continue

            for edge in item.dep_edges:
                if edge.id == to_id and edge.source == DepEdgeSource.LLM:
                    rank = confidence_rank.get(edge.confidence or "low", 0)
                    if rank < best_confidence_rank:
                        best_confidence_rank = rank
                        best_edge_to_remove = (from_id, to_id)

        if best_edge_to_remove:
            from_item = id_map[best_edge_to_remove[0]]
            to_id = best_edge_to_remove[1]
            if to_id in from_item.depends_on:
                from_item.depends_on.remove(to_id)
            from_item.dep_edges = [
                e for e in from_item.dep_edges if e.id != to_id
            ]
        else:
            # No LLM edges — remove any back-edge
            from_id = cycle[-1]
            to_id = cycle[0]
            item = id_map.get(from_id)
            if item and to_id in item.depends_on:
                item.depends_on.remove(to_id)
                item.dep_edges = [e for e in item.dep_edges if e.id != to_id]


def _find_cycle(items: list[RoadmapItem]) -> list[str] | None:
    """Find a cycle in the dependency graph.  Returns the cycle path or None."""
    id_map = {it.item_id: it for it in items}
    visited: set[str] = set()
    in_stack: set[str] = set()
    path: list[str] = []

    def _dfs(item_id: str) -> list[str] | None:
        if item_id in in_stack:
            # Found cycle — extract it
            cycle_start = path.index(item_id)
            return path[cycle_start:]
        if item_id in visited:
            return None
        visited.add(item_id)
        in_stack.add(item_id)
        path.append(item_id)

        item = id_map.get(item_id)
        if item:
            for dep in item.depends_on:
                result = _dfs(dep)
                if result is not None:
                    return result

        path.pop()
        in_stack.discard(item_id)
        return None

    for it in items:
        result = _dfs(it.item_id)
        if result is not None:
            return result
    return None
