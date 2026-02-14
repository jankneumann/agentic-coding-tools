#!/usr/bin/env python3
"""Parallel zones insight module — thin wrapper around parallel_zones.py.

Identifies independent subgraphs in the canonical architecture graph to
determine which modules can be safely modified in parallel.

This module delegates to the existing parallel_zones logic but conforms to the
Layer 2 insight module interface (--input-dir / --output).

Usage:
    python scripts/insights/parallel_zones.py --input-dir .architecture --output .architecture/parallel_zones.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import parallel_zones as pz  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Parallel modification zone analyzer for architecture graphs.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(".architecture"),
        help="Directory containing architecture.graph.json (default: .architecture)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".architecture/parallel_zones.json"),
        help="Output path for parallel_zones.json (default: .architecture/parallel_zones.json)",
    )
    parser.add_argument(
        "--impact-threshold",
        type=int,
        default=10,
        help="Threshold for high-impact modules (default: 10)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    graph_path = args.input_dir / "architecture.graph.json"

    # Delegate to the original parallel_zones module with its expected args
    return pz.main([
        "--graph", str(graph_path),
        "--output", str(args.output),
        "--impact-threshold", str(args.impact_threshold),
    ])


if __name__ == "__main__":
    sys.exit(main())
