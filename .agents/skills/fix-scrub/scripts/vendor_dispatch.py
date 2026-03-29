"""Multi-vendor agent dispatch: round-robin routing of fix prompts to vendors."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def route_prompts_to_vendors(
    agent_prompts: list[tuple[str, str]],
    available_vendors: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Route agent-fix prompts to vendors per file-group using round-robin distribution.

    Maintains exclusive file ownership -- each file-group goes to exactly one vendor.

    Args:
        agent_prompts: List of (file_path, prompt_text) tuples from generate_prompts().
        available_vendors: List of vendor names to distribute across.

    Returns:
        Dict mapping vendor name to list of {"file": str, "prompt": str}.
    """
    if not agent_prompts or not available_vendors:
        return {}

    result: dict[str, list[dict[str, str]]] = {v: [] for v in available_vendors}

    for i, (file_path, prompt_text) in enumerate(agent_prompts):
        vendor = available_vendors[i % len(available_vendors)]
        result[vendor].append({"file": file_path, "prompt": prompt_text})

    # Remove vendors with no assignments
    return {v: items for v, items in result.items() if items}


def discover_vendors(
    requested_vendors: list[str] | None = None,
) -> list[str]:
    """Discover available vendors via ReviewOrchestrator.from_coordinator().

    Falls back to from_agents_yaml(), then to a default ["claude"] list.
    If requested_vendors is provided, filter to only those that are available.
    Emits warning for unavailable requested vendors.

    Args:
        requested_vendors: Optional list of vendor names to filter to.

    Returns:
        List of available vendor names.
    """
    available: list[str] = []

    try:
        # Add review_dispatcher's parent to path so we can import it
        dispatcher_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "parallel-infrastructure"
            / "scripts"
        )
        sys.path.insert(0, str(dispatcher_dir))
        from review_dispatcher import ReviewOrchestrator  # type: ignore[import-untyped]

        orch = ReviewOrchestrator.from_coordinator()
        if not orch.adapters:
            orch = ReviewOrchestrator.from_agents_yaml()

        if orch.adapters:
            # Extract unique vendor types from adapters
            seen: set[str] = set()
            for adapter in orch.adapters.values():
                if adapter.vendor not in seen:
                    seen.add(adapter.vendor)
                    available.append(adapter.vendor)
    except Exception:
        logger.warning("Could not load ReviewOrchestrator, using default vendors")

    if not available:
        logger.warning("No vendors discovered, falling back to ['claude']")
        available = ["claude"]

    if requested_vendors is not None:
        available_set = set(available)
        filtered: list[str] = []
        for rv in requested_vendors:
            if rv in available_set:
                filtered.append(rv)
            else:
                logger.warning(
                    "Requested vendor %r is not available (available: %s)",
                    rv,
                    available,
                )
        return filtered if filtered else available

    return available


def write_vendor_prompt_files(
    routed: dict[str, list[dict[str, str]]],
    output_dir: Path,
) -> list[Path]:
    """Write per-vendor prompt files as JSON.

    For each vendor in the routed dict, writes
    ``agent-fix-prompts-<vendor>.json`` containing a JSON array of
    {"file": str, "prompt": str} objects.

    Args:
        routed: Output of route_prompts_to_vendors().
        output_dir: Directory to write files into.

    Returns:
        List of paths to written files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for vendor, items in routed.items():
        path = output_dir / f"agent-fix-prompts-{vendor}.json"
        with open(path, "w") as f:
            json.dump(items, f, indent=2)
        written.append(path)

    return written
