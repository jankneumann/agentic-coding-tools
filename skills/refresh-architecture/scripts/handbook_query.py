"""Progressive-disclosure reads over the behavior handbook (R4, design D5).

This is the agent-facing half of Behavior-Guided Progressive Disclosure: a
consumer asks for one level at a time and pays only for what it asked for.
The level boundaries are enforced here rather than left to the caller — an L2
response never carries L3 content, and an L3 response covers exactly one unit.

Typical planner sequence::

    handbook_query.py --locate "retry on tool timeout"   # rank candidates
    handbook_query.py --level l3 --unit bh:task-retry    # open the winner

Evidence returned at L3 is verified against the working tree on the way out, so
a planner never edits against a locator that has silently rotted.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from handbook_schema import (
    L1_TOKEN_BUDGET,
    L2_CARD_TOKEN_BUDGET,
    L3_TOKEN_BUDGET,
    _iter_locators,
    card_projection,
    estimate_tokens,
)
from verify_locators import resolve_locator

logger = logging.getLogger(__name__)

#: Tokens ignored when scoring a free-text behavior query.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
        "in", "is", "it", "of", "on", "or", "that", "the", "to", "when", "with",
    }
)


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in _STOPWORDS}


def _card(unit: dict[str, Any]) -> dict[str, Any]:
    """Return the L2 projection of a behavior unit (never L3 content).

    Shares :func:`handbook_schema.card_projection` with the validator so what is
    budget-checked at synthesis time is exactly what is served here.
    """
    return card_projection(unit)


def _unit_files(handbook: dict[str, Any], unit_id: str) -> set[str]:
    detail = (handbook.get("unit_details") or {}).get(unit_id) or {}
    return {
        str(loc.get("file"))
        for loc in _iter_locators(detail)
        if loc.get("file")
    }


def query_l1(handbook: dict[str, Any]) -> dict[str, Any]:
    """Return the system-flow overview."""
    flows = handbook.get("system_flows") or []
    return {
        "level": "l1",
        "system_flows": flows,
        "unit_count": len(handbook.get("behavior_units") or []),
        "uncovered_count": len(handbook.get("uncovered") or []),
        "tokens": estimate_tokens(flows),
        "budget": L1_TOKEN_BUDGET,
    }


def query_l2(
    handbook: dict[str, Any],
    *,
    files: list[str] | None = None,
    text: str | None = None,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Return behavior unit cards, optionally filtered.

    ``files`` filters to units with evidence in those paths (the reviewer entry
    point); ``text`` filters by free-text relevance (the planner entry point).
    """
    units = handbook.get("behavior_units") or []
    cards = [_card(u) for u in units]

    if files:
        wanted = {str(f) for f in files}
        cards = [
            c for c in cards
            if _unit_files(handbook, str(c["id"])) & wanted
        ]

    if text:
        query = _tokens(text)
        scored = [
            (c, len(query & _tokens(json.dumps(c, ensure_ascii=False))))
            for c in cards
        ]
        cards = [c for c, score in sorted(scored, key=lambda p: -p[1]) if score > 0]

    return {
        "level": "l2",
        "cards": cards,
        "tokens": estimate_tokens(cards),
        "budget_per_card": L2_CARD_TOKEN_BUDGET,
    }


def query_l3(
    handbook: dict[str, Any], unit_id: str, *, repo_root: Path | str
) -> dict[str, Any]:
    """Return one unit's full detail with per-locator verification status."""
    units = {u.get("id"): u for u in handbook.get("behavior_units") or []}
    detail = (handbook.get("unit_details") or {}).get(unit_id)
    if unit_id not in units or detail is None:
        return {"level": "l3", "error": "unknown_unit", "unit_id": unit_id}

    statuses: list[dict[str, Any]] = []
    for locator in _iter_locators(detail):
        status, why = resolve_locator(locator, repo_root)
        statuses.append(
            {
                "node_id": locator.get("node_id"),
                "file": locator.get("file"),
                "span": locator.get("span"),
                "status": status,
                "detail": why,
            }
        )

    return {
        "level": "l3",
        "unit": _card(units[unit_id]),
        "detail": detail,
        "evidence_status": statuses,
        "tokens": estimate_tokens(detail),
        "budget": L3_TOKEN_BUDGET,
    }


def locate(handbook: dict[str, Any], description: str) -> dict[str, Any]:
    """Rank behavior units against a natural-language change request.

    Scoring is lexical overlap against the unit card plus its member node names,
    which keeps localization dependency-free and deterministic. The result is
    source-grounded evidence for planning, not L3 content.
    """
    query = _tokens(description)
    candidates: list[dict[str, Any]] = []

    for unit in handbook.get("behavior_units") or []:
        card = _card(unit)
        haystack = _tokens(json.dumps(card, ensure_ascii=False))
        # Rank against full membership even though the card only previews it —
        # localization should see every node, the reader should not.
        haystack |= _tokens(" ".join(str(n) for n in unit.get("member_nodes") or []))
        score = len(query & haystack)
        if score:
            candidates.append({**card, "score": score})

    candidates.sort(key=lambda c: (-c["score"], str(c["id"])))
    return {
        "level": "locate",
        "query": description,
        "candidates": candidates,
        "tokens": estimate_tokens(candidates),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Progressive-disclosure reads over architecture.behaviors.json"
    )
    parser.add_argument("--handbook", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--level", choices=["l1", "l2", "l3"])
    parser.add_argument("--unit", help="Behavior unit id (required for --level l3)")
    parser.add_argument("--filter", dest="text", help="Free-text filter for --level l2")
    parser.add_argument(
        "--files",
        help="Comma-separated file list for --level l2 (reviewer entry point)",
    )
    parser.add_argument("--locate", help="Rank behavior units for a change request")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    handbook_path = Path(args.handbook)
    if not handbook_path.is_file():
        logger.error("handbook not found: %s", handbook_path)
        return 1
    handbook = json.loads(handbook_path.read_text(encoding="utf-8"))

    if args.locate:
        payload: dict[str, Any] = locate(handbook, args.locate)
    elif args.level == "l3":
        if not args.unit:
            logger.error("--level l3 requires --unit")
            return 1
        payload = query_l3(handbook, args.unit, repo_root=args.repo_root)
    elif args.level == "l2":
        payload = query_l2(
            handbook,
            files=args.files.split(",") if args.files else None,
            text=args.text,
            repo_root=args.repo_root,
        )
    else:
        payload = query_l1(handbook)

    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
