"""Schema and validator for the behavior handbook (Layer 2.5).

The handbook is a behavior-centric reading surface over the canonical
architecture graph. It deliberately owns *no* structural facts: behavior units
reference node IDs that must exist in ``architecture.graph.json`` (design D1),
so the graph stays the single source of truth for structure and the handbook
adds only grouping, narrative, and paths.

Token budgets (design D5) are enforced here rather than treated as style
guidance. The whole benefit of progressive disclosure is that a consumer never
loads Level 3 for units it did not need, and that only holds if each level
actually fits its budget.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from arch_utils.diagnostics import DiagnosticCollector
from arch_utils.graph_io import load_graph

logger = logging.getLogger(__name__)

#: Behavior unit IDs are ``bh:<kebab-name>``; flows are ``fl:<kebab-name>``.
UNIT_ID_PREFIX = "bh:"
FLOW_ID_PREFIX = "fl:"

#: Token budgets per disclosure level (design D5). Estimated at 4 chars/token.
L1_TOKEN_BUDGET = 400
L2_CARD_TOKEN_BUDGET = 150
L3_TOKEN_BUDGET = 1500

CHARS_PER_TOKEN = 4

REQUIRED_SECTIONS = ("system_flows", "behavior_units", "unit_details")
REQUIRED_SNAPSHOT_KEYS = ("generated_at", "git_sha", "handbook_version")
REQUIRED_LOCATOR_KEYS = ("node_id", "file", "span", "content_digest")
DETAIL_SECTIONS = (
    "triggers",
    "state_changes",
    "execution_paths",
    "exception_paths",
    "evidence",
)


def estimate_tokens(payload: Any) -> int:
    """Return a deterministic token estimate for *payload*.

    Uses a 4-chars-per-token approximation over compact JSON so the estimate is
    stable across runs and independent of any tokenizer dependency.
    """
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return len(text) // CHARS_PER_TOKEN


def _iter_locators(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every evidence locator inside one unit detail block."""
    out: list[dict[str, Any]] = []
    for entry in detail.get("evidence") or []:
        if isinstance(entry, dict):
            out.append(entry)
    for key in ("execution_paths", "exception_paths"):
        for path in detail.get(key) or []:
            if not isinstance(path, dict):
                continue
            for entry in path.get("evidence") or []:
                if isinstance(entry, dict):
                    out.append(entry)
    return out


#: Fields of a behavior unit that a consumer actually reads at L2. ``member_nodes``
#: is deliberately excluded: it is a machine-readable index used for referential
#: integrity and localization ranking, not narrative a reader loads. Inlining it
#: would put hundreds of node IDs into every card and defeat the budget.
CARD_NARRATIVE_FIELDS = (
    "id",
    "title",
    "responsibility",
    "inputs",
    "outputs",
    "depends_on",
)

#: Maximum member nodes previewed on a card; full membership is an L3 concern.
CARD_PRIMARY_NODE_LIMIT = 5


def card_projection(unit: dict[str, Any]) -> dict[str, Any]:
    """Return the L2 card a consumer is actually served.

    This is the unit of measurement for the L2 budget, and the exact payload
    :mod:`handbook_query` returns, so what is validated is what is loaded.
    """
    members = list(unit.get("member_nodes") or [])
    card = {field: unit.get(field) for field in CARD_NARRATIVE_FIELDS}
    card["member_node_count"] = len(members)
    card["primary_nodes"] = members[:CARD_PRIMARY_NODE_LIMIT]
    return card


def compute_budget_estimate(handbook: dict[str, Any]) -> dict[str, int]:
    """Return per-level token estimates recorded alongside the artifact."""
    units = handbook.get("behavior_units") or []
    details = handbook.get("unit_details") or {}
    card_costs = [estimate_tokens(card_projection(u)) for u in units] or [0]
    detail_costs = [estimate_tokens(d) for d in details.values()] or [0]
    return {
        "l1": estimate_tokens(handbook.get("system_flows") or []),
        "l2_cards": len(units),
        "l2_max_card": max(card_costs),
        "l2_total": sum(card_costs),
        "l3_max_unit": max(detail_costs),
    }


def _validate_locator(
    dc: DiagnosticCollector,
    locator: Any,
    node_ids: set[str],
    unit_id: str,
) -> None:
    if not isinstance(locator, dict):
        dc.error(
            "HANDBOOK_BAD_LOCATOR",
            f"{unit_id}: evidence entry is not an object",
            details={"behavior_unit": unit_id},
        )
        return
    missing = [k for k in REQUIRED_LOCATOR_KEYS if k not in locator]
    if missing:
        dc.error(
            "HANDBOOK_BAD_LOCATOR",
            f"{unit_id}: evidence locator missing {', '.join(missing)}",
            details={"behavior_unit": unit_id, "missing": missing},
        )
        return
    span = locator.get("span")
    if not isinstance(span, dict) or "start" not in span or "end" not in span:
        dc.error(
            "HANDBOOK_BAD_LOCATOR",
            f"{unit_id}: evidence locator span must have start and end",
            details={"behavior_unit": unit_id},
        )
    node_id = locator.get("node_id")
    if node_id not in node_ids:
        dc.error(
            "HANDBOOK_UNKNOWN_NODE",
            f"{unit_id}: evidence references unknown node {node_id!r}",
            node_id=str(node_id),
            details={"behavior_unit": unit_id},
        )


def validate_handbook(handbook: Any, graph: dict[str, Any]) -> DiagnosticCollector:
    """Validate *handbook* against *graph*, returning collected diagnostics.

    Referential integrity against the canonical graph and the per-level token
    budgets are both hard errors: a handbook that fails either is not promoted
    by the refresh pipeline.
    """
    dc = DiagnosticCollector()

    if not isinstance(handbook, dict):
        dc.error("HANDBOOK_MALFORMED", "handbook document must be an object")
        return dc

    for section in REQUIRED_SECTIONS:
        if section not in handbook:
            dc.error(
                "HANDBOOK_MISSING_SECTION",
                f"handbook is missing required section {section!r}",
                details={"section": section},
            )

    snapshot = handbook.get("snapshot")
    if not isinstance(snapshot, dict):
        dc.error("HANDBOOK_MISSING_SNAPSHOT", "handbook is missing its snapshot block")
    else:
        for key in REQUIRED_SNAPSHOT_KEYS:
            if key not in snapshot:
                dc.error(
                    "HANDBOOK_MISSING_SNAPSHOT",
                    f"snapshot is missing {key!r}",
                    details={"key": key},
                )

    node_ids = {n.get("id") for n in graph.get("nodes") or [] if isinstance(n, dict)}

    # -- Level 2: behavior units -------------------------------------------- #
    units = handbook.get("behavior_units") or []
    unit_ids: set[str] = set()
    for unit in units:
        if not isinstance(unit, dict):
            dc.error("HANDBOOK_MALFORMED", "behavior unit is not an object")
            continue
        unit_id = unit.get("id", "")
        if not isinstance(unit_id, str) or not unit_id.startswith(UNIT_ID_PREFIX):
            dc.error(
                "HANDBOOK_BAD_ID",
                f"behavior unit id {unit_id!r} must start with {UNIT_ID_PREFIX!r}",
                details={"behavior_unit": str(unit_id)},
            )
        if unit_id in unit_ids:
            dc.error(
                "HANDBOOK_DUPLICATE_ID",
                f"duplicate behavior unit id {unit_id!r}",
                details={"behavior_unit": unit_id},
            )
        unit_ids.add(unit_id)

        for node_id in unit.get("member_nodes") or []:
            if node_id not in node_ids:
                dc.error(
                    "HANDBOOK_UNKNOWN_NODE",
                    f"{unit_id}: member_nodes references unknown node {node_id!r}",
                    node_id=str(node_id),
                    details={"behavior_unit": unit_id},
                )

        cost = estimate_tokens(card_projection(unit))
        if cost > L2_CARD_TOKEN_BUDGET:
            dc.error(
                "HANDBOOK_BUDGET_EXCEEDED",
                f"{unit_id}: L2 card is {cost} tokens (budget {L2_CARD_TOKEN_BUDGET}) — "
                "tighten the card or split the unit",
                details={"level": "l2", "behavior_unit": unit_id, "tokens": cost,
                         "budget": L2_CARD_TOKEN_BUDGET},
            )

    for unit in units:
        if not isinstance(unit, dict):
            continue
        for dep in unit.get("depends_on") or []:
            if dep not in unit_ids:
                dc.error(
                    "HANDBOOK_UNKNOWN_UNIT",
                    f"{unit.get('id')}: depends_on references unknown unit {dep!r}",
                    details={"behavior_unit": unit.get("id"), "missing": dep},
                )

    # -- Level 1: system flows ---------------------------------------------- #
    flows = handbook.get("system_flows") or []
    for flow in flows:
        if not isinstance(flow, dict):
            dc.error("HANDBOOK_MALFORMED", "system flow is not an object")
            continue
        flow_id = flow.get("id", "")
        if not isinstance(flow_id, str) or not flow_id.startswith(FLOW_ID_PREFIX):
            dc.error(
                "HANDBOOK_BAD_ID",
                f"system flow id {flow_id!r} must start with {FLOW_ID_PREFIX!r}",
                details={"flow": str(flow_id)},
            )
        entry = flow.get("entry")
        if entry is not None and entry not in node_ids:
            dc.error(
                "HANDBOOK_UNKNOWN_NODE",
                f"{flow_id}: entry references unknown node {entry!r}",
                node_id=str(entry),
                details={"flow": flow_id},
            )

    l1_cost = estimate_tokens(flows)
    if l1_cost > L1_TOKEN_BUDGET:
        dc.error(
            "HANDBOOK_BUDGET_EXCEEDED",
            f"L1 overview is {l1_cost} tokens (budget {L1_TOKEN_BUDGET})",
            details={"level": "l1", "tokens": l1_cost, "budget": L1_TOKEN_BUDGET},
        )

    # -- Level 3: unit details ---------------------------------------------- #
    details = handbook.get("unit_details")
    if details is not None and not isinstance(details, dict):
        dc.error("HANDBOOK_MALFORMED", "unit_details must be an object")
        details = {}
    details = details or {}

    for unit_id in unit_ids:
        if unit_id not in details:
            dc.error(
                "HANDBOOK_MISSING_DETAIL",
                f"{unit_id}: has no unit_details entry",
                details={"behavior_unit": unit_id},
            )

    for unit_id, detail in details.items():
        if unit_id not in unit_ids:
            dc.error(
                "HANDBOOK_ORPHAN_DETAIL",
                f"unit_details contains {unit_id!r} with no matching behavior unit",
                details={"behavior_unit": unit_id},
            )
            continue
        if not isinstance(detail, dict):
            dc.error(
                "HANDBOOK_MALFORMED",
                f"{unit_id}: unit detail is not an object",
                details={"behavior_unit": unit_id},
            )
            continue
        for section in DETAIL_SECTIONS:
            if section not in detail:
                dc.error(
                    "HANDBOOK_MISSING_SECTION",
                    f"{unit_id}: unit detail is missing {section!r}",
                    details={"behavior_unit": unit_id, "section": section},
                )
        for locator in _iter_locators(detail):
            _validate_locator(dc, locator, node_ids, unit_id)

        cost = estimate_tokens(detail)
        if cost > L3_TOKEN_BUDGET:
            dc.error(
                "HANDBOOK_BUDGET_EXCEEDED",
                f"{unit_id}: L3 detail is {cost} tokens (budget {L3_TOKEN_BUDGET}) — "
                "split into two behavior units",
                details={"level": "l3", "behavior_unit": unit_id, "tokens": cost,
                         "budget": L3_TOKEN_BUDGET},
            )

    return dc


def validate_handbook_files(
    handbook_path: Path | str, graph_path: Path | str
) -> DiagnosticCollector:
    """Load both artifacts from disk and validate them."""
    handbook = load_graph(Path(handbook_path), quiet=True)
    graph = load_graph(Path(graph_path), quiet=True)
    if not handbook:
        dc = DiagnosticCollector()
        dc.error("HANDBOOK_MALFORMED", f"handbook not found or empty: {handbook_path}")
        return dc
    return validate_handbook(handbook, graph)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate architecture.behaviors.json")
    parser.add_argument("--handbook", required=True, help="Path to architecture.behaviors.json")
    parser.add_argument("--graph", required=True, help="Path to architecture.graph.json")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-finding output")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    dc = validate_handbook_files(args.handbook, args.graph)
    if not args.quiet:
        for item in dc.items:
            logger.info("[%s] %s: %s", item.severity, item.code, item.message)
    dc.print_summary()
    return dc.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
