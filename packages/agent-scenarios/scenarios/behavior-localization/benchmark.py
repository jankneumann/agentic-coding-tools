#!/usr/bin/env python3
"""Behavior-localization benchmark: handbook BGPD vs. graph-only baseline (D7).

Measures the claim this change rests on — that a behavior map localizes changes
better, and cheaper, than the raw structural graph.

Ground truth comes from archived OpenSpec changes: each change's proposal text
is the request, and its ``work-packages.yaml`` ``scope.write_allow`` globs are
the files it was actually allowed to modify. Scenarios whose targets no longer
exist at HEAD are excluded and reported rather than silently dropped — an
archived change that predates a refactor is not evidence about today's map.

Two arms, same request, same k:

``graph``     lexical ranking over canonical graph node names and files, the
              honest baseline for "just give the agent the graph"
``handbook``  ``handbook_query --locate``, then the member files of the top-k
              behavior units

Metrics are file-level precision / recall / F1 plus the serialized token cost of
what each arm would put into a planner's context.

Usage::

    python3 benchmark.py --repo-root . --k 3
    python3 benchmark.py --repo-root . --json results.json
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML required: uv pip install pyyaml", file=sys.stderr)
    raise

SCRIPTS = "skills/refresh-architecture/scripts"

#: Only score targets under the subsystem the handbook was synthesized for.
TARGET_PREFIX = "agent-coordinator/src/"

_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in",
    "is", "it", "of", "on", "or", "that", "the", "to", "when", "with", "this",
    "we", "our", "not", "but", "can", "should", "must", "will", "its", "into",
    "change", "changes", "add", "adds", "update", "make", "use", "used",
})


def tokens(text: str) -> set[str]:
    return {
        t for t in re.split(r"[^a-z0-9]+", text.lower())
        if len(t) > 2 and t not in _STOPWORDS
    }


# --------------------------------------------------------------------------- #
# Ground truth mining
# --------------------------------------------------------------------------- #
def _expand(repo_root: Path, globs: list[str]) -> set[str]:
    """Expand write_allow globs to real files under the target prefix at HEAD."""
    out: set[str] = set()
    candidates = [
        p.relative_to(repo_root).as_posix()
        for p in (repo_root / TARGET_PREFIX).rglob("*.py")
        if p.is_file()
    ]
    for pattern in globs:
        pattern = pattern.strip()
        if not pattern.startswith(TARGET_PREFIX):
            continue
        for rel in candidates:
            if fnmatch.fnmatch(rel, pattern) or rel.startswith(pattern.rstrip("*/")):
                out.add(rel)
    return out


def _request_text(change_dir: Path) -> str:
    """Use the proposal's Why + What Changes as the change request."""
    proposal = change_dir / "proposal.md"
    if not proposal.is_file():
        return ""
    text = proposal.read_text(encoding="utf-8", errors="replace")
    parts = re.findall(
        r"##\s+(?:Why|What Changes)\s*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL
    )
    return " ".join(parts)[:4000]


def load_scenarios(repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Return ``(scenarios, excluded)`` mined from the archive."""
    scenarios: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []

    archive = repo_root / "openspec" / "changes" / "archive"
    for change_dir in sorted(archive.iterdir()):
        if not change_dir.is_dir():
            continue
        wp_path = change_dir / "work-packages.yaml"
        if not wp_path.is_file():
            excluded.append({"change": change_dir.name, "reason": "no_work_packages"})
            continue
        try:
            doc = yaml.safe_load(wp_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            excluded.append({"change": change_dir.name, "reason": "unparseable_yaml"})
            continue

        packages = doc.get("work_packages") or doc.get("packages") or []
        if not isinstance(packages, list):
            packages = []
        globs = [
            g
            for pkg in packages
            if isinstance(pkg, dict)
            for g in ((pkg.get("scope") or {}).get("write_allow") or [])
        ]
        truth = _expand(repo_root, globs)
        if not truth:
            excluded.append({"change": change_dir.name, "reason": "no_surviving_targets"})
            continue

        request = _request_text(change_dir)
        if not request.strip():
            excluded.append({"change": change_dir.name, "reason": "no_request_text"})
            continue

        scenarios.append(
            {"change": change_dir.name, "request": request, "truth": sorted(truth)}
        )
    return scenarios, excluded


# --------------------------------------------------------------------------- #
# Arms
# --------------------------------------------------------------------------- #
def _node_path(node: dict[str, Any]) -> str | None:
    sys.path.insert(0, str(Path(__file__).resolve()))
    from source_roots import resolve_node_path

    return resolve_node_path(node)


def graph_arm(graph: dict[str, Any], request: str, k: int) -> tuple[set[str], int]:
    """Baseline: rank graph nodes lexically, return the files of the top-k."""
    from source_roots import resolve_node_path

    query = tokens(request)
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for node in graph.get("nodes") or []:
        path = resolve_node_path(node)
        if not path or not path.startswith(TARGET_PREFIX):
            continue
        haystack = tokens(f"{node.get('name', '')} {node.get('id', '')} {path}")
        score = len(query & haystack)
        if score:
            scored.append((score, str(node.get("id")), node))

    scored.sort(key=lambda t: (-t[0], t[1]))
    top = scored[: k * 12]  # a unit is many nodes; give the baseline comparable width
    files = {resolve_node_path(n) or "" for _s, _i, n in top}
    payload = [{"id": i, "file": resolve_node_path(n)} for _s, i, n in top]
    return {f for f in files if f}, len(json.dumps(payload)) // 4


def handbook_arm(
    handbook: dict[str, Any], request: str, k: int, repo_root: Path
) -> tuple[set[str], int]:
    """BGPD: locate behavior units, then take their member files."""
    from handbook_query import locate

    result = locate(handbook, request)
    top = result["candidates"][:k]

    units = {u["id"]: u for u in handbook.get("behavior_units") or []}
    details = handbook.get("unit_details") or {}
    files: set[str] = set()
    for candidate in top:
        detail = details.get(candidate["id"]) or {}
        for section in ("evidence",):
            for locator in detail.get(section) or []:
                if locator.get("file"):
                    files.add(str(locator["file"]))
        for node_id in units.get(candidate["id"], {}).get("member_nodes") or []:
            node = _NODE_INDEX.get(node_id)
            if node:
                from source_roots import resolve_node_path

                path = resolve_node_path(node)
                if path and path.startswith(TARGET_PREFIX):
                    files.add(path)

    cost = len(json.dumps(top)) // 4
    return files, cost


_NODE_INDEX: dict[str, dict[str, Any]] = {}


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score(predicted: set[str], truth: set[str]) -> dict[str, float]:
    hits = len(predicted & truth)
    precision = hits / len(predicted) if predicted else 0.0
    recall = hits / len(truth) if truth else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "hits": hits}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--k", type=int, default=3, help="Top-k behavior units")
    parser.add_argument("--json", dest="json_out", help="Write full results here")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    sys.path.insert(0, str(repo_root / SCRIPTS))

    arch = repo_root / "docs" / "architecture-analysis"
    graph = json.loads((arch / "architecture.graph.json").read_text(encoding="utf-8"))
    hb_path = arch / "architecture.behaviors.json"
    if not hb_path.is_file():
        print("no committed handbook — run 'make architecture-handbook-synthesize'",
              file=sys.stderr)
        return 1
    handbook = json.loads(hb_path.read_text(encoding="utf-8"))

    global _NODE_INDEX
    _NODE_INDEX = {
        n["id"]: n for n in graph.get("nodes") or [] if isinstance(n, dict) and "id" in n
    }

    scenarios, excluded = load_scenarios(repo_root)
    if not scenarios:
        print("no usable scenarios mined from the archive", file=sys.stderr)
        return 1

    rows: list[dict[str, Any]] = []
    for sc in scenarios:
        truth = set(sc["truth"])
        g_files, g_cost = graph_arm(graph, sc["request"], args.k)
        h_files, h_cost = handbook_arm(handbook, sc["request"], args.k, repo_root)
        rows.append(
            {
                "change": sc["change"],
                "truth_size": len(truth),
                "graph": {**score(g_files, truth), "tokens": g_cost},
                "handbook": {**score(h_files, truth), "tokens": h_cost},
            }
        )

    def mean(arm: str, metric: str) -> float:
        return sum(r[arm][metric] for r in rows) / len(rows)

    summary = {
        "scenarios": len(rows),
        "excluded": len(excluded),
        "k": args.k,
        "graph": {m: round(mean("graph", m), 4)
                  for m in ("precision", "recall", "f1", "tokens")},
        "handbook": {m: round(mean("handbook", m), 4)
                     for m in ("precision", "recall", "f1", "tokens")},
    }
    summary["f1_delta_pp"] = round(
        (summary["handbook"]["f1"] - summary["graph"]["f1"]) * 100, 2
    )
    tok_g = summary["graph"]["tokens"]
    summary["token_delta_pct"] = round(
        ((summary["handbook"]["tokens"] - tok_g) / tok_g * 100) if tok_g else 0.0, 2
    )

    print(json.dumps({"summary": summary,
                      "excluded_reasons": _count(excluded)}, indent=2))

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"summary": summary, "rows": rows, "excluded": excluded},
                       indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return 0


def _count(excluded: list[dict[str, str]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in excluded:
        out[e["reason"]] = out.get(e["reason"], 0) + 1
    return out


if __name__ == "__main__":
    sys.exit(main())
