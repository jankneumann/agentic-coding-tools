#!/usr/bin/env python3
"""Implementation strategy selector for the automated-dev-loop feature.

Per-package decision logic for choosing between:
- "alternatives": 3 independent implementations + synthesis
- "lead_review": 1 implements + others review

Scoring criteria (each 0-1, threshold >= 2.0 for alternatives):
1. loc_estimate < 200 → 1.0
2. alternatives_count >= 2 → 1.0
3. package_kind in (algorithm, data_model) → 1.0
4. len(available_vendors) >= 3 → 1.0

Run via skills venv:
  skills/.venv/bin/python scripts/implementation_strategy_selector.py <work-packages.yaml>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is required: pip install pyyaml")


ALTERNATIVES_THRESHOLD = 2.0
ALTERNATIVES_KINDS = frozenset({"algorithm", "data_model"})
INTEGRATION_TYPES = frozenset({"integration", "integrate"})


def _score_loc(metadata: dict[str, Any]) -> float:
    """Score based on lines-of-code estimate."""
    loc = metadata.get("loc_estimate")
    if loc is None:
        return 0.0
    return 1.0 if loc < 200 else 0.0


def _score_alternatives_count(metadata: dict[str, Any]) -> float:
    """Score based on number of known alternative approaches."""
    count = metadata.get("alternatives_count")
    if count is None:
        return 0.0
    return 1.0 if count >= 2 else 0.0


def _score_package_kind(metadata: dict[str, Any]) -> float:
    """Score based on package kind (algorithm/data_model favors alternatives)."""
    kind = metadata.get("package_kind")
    if kind is None:
        return 0.0
    return 1.0 if kind in ALTERNATIVES_KINDS else 0.0


def _score_vendor_count(available_vendors: list[str]) -> float:
    """Score based on number of available vendors."""
    return 1.0 if len(available_vendors) >= 3 else 0.0


def _is_integration_package(package: dict[str, Any]) -> bool:
    """Check if a package is an integration-type package."""
    pkg_type = package.get("task_type", package.get("type", ""))
    pkg_id = package.get("package_id", package.get("id", ""))
    return pkg_type in INTEGRATION_TYPES or pkg_id.startswith("wp-integration")


def _compute_score(
    metadata: dict[str, Any],
    available_vendors: list[str],
) -> float:
    """Compute total strategy score for a package."""
    return (
        _score_loc(metadata)
        + _score_alternatives_count(metadata)
        + _score_package_kind(metadata)
        + _score_vendor_count(available_vendors)
    )


def select_lead_vendor(
    available_vendors: list[str],
    recall_fn: Callable[..., Any] | None = None,
) -> str:
    """Select the best vendor to be lead implementer.

    If recall_fn is provided, queries for recent loop_completion memories
    to find vendor effectiveness stats. Selects vendor with highest fix
    success rate.

    Falls back to first available vendor if recall_fn is None or returns
    no useful data.
    """
    if not available_vendors:
        return ""

    if recall_fn is not None:
        try:
            memories = recall_fn("loop_completion")
            if memories and isinstance(memories, list):
                # Extract vendor stats from memories
                vendor_scores: dict[str, float] = {}
                for memory in memories:
                    data = memory if isinstance(memory, dict) else {}
                    vendor = data.get("vendor")
                    success_rate = data.get("fix_success_rate")
                    if (
                        vendor
                        and vendor in available_vendors
                        and isinstance(success_rate, (int, float))
                    ):
                        # Keep best score per vendor
                        if vendor not in vendor_scores or success_rate > vendor_scores[vendor]:
                            vendor_scores[vendor] = success_rate

                if vendor_scores:
                    return max(vendor_scores, key=lambda v: vendor_scores[v])
        except Exception:
            pass  # Fall through to default

    return available_vendors[0]


def select_strategies(
    work_packages_path: Path,
    design_path: Path | None = None,
    available_vendors: list[str] | None = None,
    recall_fn: Callable[..., Any] | None = None,
) -> dict[str, str]:
    """Select implementation strategy for each work package.

    Args:
        work_packages_path: Path to work-packages.yaml.
        design_path: Optional path to design.md (reserved for future inference).
        available_vendors: List of available vendor names.
        recall_fn: Optional function to recall vendor effectiveness from
            coordinator memory.

    Returns:
        Mapping of package_id to strategy ("alternatives" or "lead_review").
    """
    if available_vendors is None:
        available_vendors = []

    with open(work_packages_path) as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}

    packages = data.get("packages", [])
    if not packages:
        return {}

    strategies: dict[str, str] = {}

    for package in packages:
        pkg_id = package.get("package_id", package.get("id", ""))
        if not pkg_id:
            continue

        # Integration packages always use lead_review
        if _is_integration_package(package):
            strategies[pkg_id] = "lead_review"
            continue

        metadata = package.get("metadata", {})
        if not metadata:
            # No metadata → default to lead_review
            strategies[pkg_id] = "lead_review"
            continue

        score = _compute_score(metadata, available_vendors)
        strategies[pkg_id] = "alternatives" if score >= ALTERNATIVES_THRESHOLD else "lead_review"

    return strategies


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Select implementation strategy per work package.",
    )
    parser.add_argument(
        "work_packages",
        type=Path,
        help="Path to work-packages.yaml",
    )
    parser.add_argument(
        "--design",
        type=Path,
        default=None,
        help="Path to design.md (optional)",
    )
    parser.add_argument(
        "--vendors",
        nargs="*",
        default=[],
        help="Available vendor names",
    )
    args = parser.parse_args()

    strategies = select_strategies(
        work_packages_path=args.work_packages,
        design_path=args.design,
        available_vendors=args.vendors,
    )

    print(json.dumps(strategies, indent=2))


if __name__ == "__main__":
    main()
