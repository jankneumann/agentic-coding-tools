#!/usr/bin/env python3
"""Build an interactive HTML atlas from the committed architecture graph.

Usage::

    python build_atlas.py                       # write docs/architecture-analysis/atlas/index.html
    python build_atlas.py --check               # exit 2 if the written page is stale
    python build_atlas.py --output /tmp/a.html  # write elsewhere
    python build_atlas.py --json-only           # emit the view-model, skip rendering

Exit codes follow the convention the other architecture producers use:
``0`` success or fresh, ``1`` input/IO error, ``2`` drift detected in check mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Scripts in this repo are invoked directly rather than imported as a package,
# so the sibling modules are resolved by putting this directory on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from atlas_model import AtlasInputError, build_view_model, load_graph  # noqa: E402
from atlas_render import render_page  # noqa: E402

DEFAULT_GRAPH = Path("docs/architecture-analysis/architecture.graph.json")
DEFAULT_OUTPUT = Path("docs/architecture-analysis/atlas/index.html")


def find_repo_root(start: Path) -> Path:
    """Walk upward to the git root so the tool works from any subdirectory."""
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="build_atlas",
        description="Render the architecture graph as a self-contained HTML atlas.",
    )
    parser.add_argument(
        "--repo-root", type=Path, default=None,
        help="Repository root (default: nearest ancestor containing .git).",
    )
    parser.add_argument(
        "--graph", type=Path, default=None,
        help=f"Architecture graph JSON (default: {DEFAULT_GRAPH}).",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help=f"Destination HTML file (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Do not write; exit 2 if the existing output differs from a fresh render.",
    )
    parser.add_argument(
        "--json-only", action="store_true",
        help="Print the view-model as JSON to stdout instead of rendering HTML.",
    )
    parser.add_argument(
        "--no-coverage", action="store_true",
        help="Skip the on-disk coverage scan (faster; drops the coverage banner).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    repo_root = (args.repo_root or find_repo_root(Path.cwd())).resolve()
    graph_path = args.graph or (repo_root / DEFAULT_GRAPH)
    output_path = args.output or (repo_root / DEFAULT_OUTPUT)

    try:
        graph = load_graph(graph_path)
        payload = build_view_model(graph, repo_root, measure=not args.no_coverage)
    except AtlasInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json_only:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    html = render_page(payload)

    if args.check:
        if not output_path.is_file():
            print(f"drift: {output_path} does not exist", file=sys.stderr)
            return 2
        if output_path.read_text(encoding="utf-8") != html:
            print(
                f"drift: {output_path} is stale; re-run without --check to refresh",
                file=sys.stderr,
            )
            return 2
        print(f"fresh: {output_path}")
        return 0

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot write {output_path}: {exc}", file=sys.stderr)
        return 1

    meta = payload["meta"]
    size_kb = round(len(html.encode("utf-8")) / 1024)
    print(
        f"wrote {output_path} ({size_kb} KB) — "
        f"{meta['moduleCount']} files, {meta['nodeCount']} symbols, {meta['edgeCount']} edges"
    )
    for cov in payload.get("coverage") or []:
        if not cov["filesOnDisk"]:
            continue
        if cov["filesMatched"] >= cov["filesOnDisk"] and not cov["filesMissing"]:
            continue
        # Print filesMatched, the same numerator `percent` is derived from. Using
        # filesInGraph here made the line contradict its own percentage.
        line = (
            f"  coverage {cov['language']}: <={cov['filesMatched']}/{cov['filesOnDisk']} "
            f"files (<={cov['percent']}%), from {cov['filesInGraph']} distinct name(s)"
        )
        if cov["filesMissing"]:
            line += f" — {cov['filesMissing']} graph file(s) absent from disk (stale)"
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
