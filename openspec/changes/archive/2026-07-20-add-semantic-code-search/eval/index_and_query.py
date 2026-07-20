#!/usr/bin/env python3
"""Semantic query driver for the spike gate (task 0.2, design D9).

Drives stock cocoindex-code (`ccc`) to produce the semantic results JSON that run_eval.py
consumes. Kept separate from run_eval.py so the deterministic ripgrep baseline needs no
external dependencies, while the semantic half is fully reproducible wherever an embedding
backend is reachable.

Prerequisites (NOT satisfiable in a PyPI-only-allowlisted cloud sandbox — see spike-report.md):
  1. `pip install "cocoindex-code[embeddings-local]"` (local model) OR base + a LiteLLM key.
  2. A reachable embedder:
       - local: HuggingFace model download (huggingface.co), OR
       - cloud: a LiteLLM provider endpoint + API key (e.g. OPENAI_API_KEY).
  3. `ccc init` + `ccc index` run once against the repo root.

Usage (from repo root, with ccc on PATH):
  python3 openspec/changes/add-semantic-code-search/eval/index_and_query.py \
      --ccc /path/to/venv/bin/ccc --out eval/semantic-results.json
  python3 openspec/changes/add-semantic-code-search/eval/run_eval.py \
      --semantic openspec/changes/add-semantic-code-search/eval/semantic-results.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]


def load_tasks() -> list[dict]:
    import yaml

    return yaml.safe_load((HERE / "eval-set.yaml").read_text())["tasks"]


def ccc_search(ccc: str, query: str, k: int) -> list[str]:
    """Run `ccc search --json` and return ranked repo-relative file paths (best first).

    Deduplicates files across chunk hits, preserving first-seen (best) order — the eval
    scores at file granularity, but cocoindex returns chunk-level results.
    """
    cmd = [ccc, "search", query, "--json", "--limit", str(k * 4), "--path", "**"]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120)
    if out.returncode != 0:
        print(f"WARN: ccc search failed for {query!r}: {out.stderr[:200]}", file=sys.stderr)
        return []
    resp = json.loads(out.stdout)
    seen: list[str] = []
    for r in resp.get("results", []):
        fp = r.get("file_path", "")
        # Normalize to repo-relative posix.
        try:
            rel = str(Path(fp).resolve().relative_to(REPO_ROOT))
        except ValueError:
            rel = fp
        if rel not in seen:
            seen.append(rel)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccc", default="ccc", help="path to the ccc entrypoint")
    ap.add_argument("--out", type=Path, default=HERE / "semantic-results.json")
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    results = {}
    for t in load_tasks():
        files = ccc_search(args.ccc, t["query"], args.k)
        results[t["id"]] = files
        print(f"{t['id']}: {files[:args.k]}")

    args.out.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
