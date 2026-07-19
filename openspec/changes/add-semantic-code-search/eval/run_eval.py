#!/usr/bin/env python3
"""Spike-gate eval runner (task 0.2, design D9).

Computes hit@k for three retrieval strategies over eval-set.yaml:

  1. ripgrep-phrase  — the naive literal-phrase grep (documented baseline; usually 0 hits)
  2. ripgrep-keyword — a FAIR lexical baseline: query tokenized (stopwords dropped), files
                       ranked by count of distinct query terms matched, top-k taken
  3. semantic        — cocoindex-code results, if a results JSON is supplied via --semantic

A "hit" = any of a task's expected_files appears in that strategy's top-k.

Usage:
  python3 run_eval.py                         # ripgrep baselines only (deterministic, no deps)
  python3 run_eval.py --semantic results.json # add the semantic column
  python3 run_eval.py --json                  # machine-readable summary

The semantic results JSON maps task id -> ordered list of file paths (best first):
  {"T1": ["agent-coordinator/src/locks.py", ...], "T2": [...], ...}
Produced by index_and_query.py (or any cocoindex-code run) so the gate math is reproducible.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]  # openspec/changes/<id>/eval -> repo root

STOPWORDS = {
    "how", "are", "is", "the", "a", "an", "does", "do", "it", "in", "to", "of", "for",
    "where", "what", "so", "as", "at", "on", "from", "with", "that", "this", "next",
    "can", "an", "its", "it's", "up", "by", "or", "and", "run", "runs", "running",
    "gets", "get", "pick", "know", "leave", "which", "uses", "use", "two", "same",
}


def load_eval_set() -> dict:
    import yaml  # pyyaml is already a repo dep

    return yaml.safe_load((HERE / "eval-set.yaml").read_text())


def _rg(pattern_args: list[str]) -> list[str]:
    """Run ripgrep, return matching file paths (repo-relative), empty on no match."""
    cmd = ["rg", "-l", "-i", *pattern_args, "--", str(REPO_ROOT)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        print("ERROR: ripgrep (rg) not found", file=sys.stderr)
        return []
    if out.returncode not in (0, 1):  # 1 = no matches, which is fine
        return []
    files = []
    for line in out.stdout.splitlines():
        p = Path(line)
        try:
            files.append(str(p.resolve().relative_to(REPO_ROOT)))
        except ValueError:
            files.append(line)
    return files


def _rg_counts(term: str) -> dict[str, int]:
    """Run ripgrep -c, return {repo-relative path: match count} for one term."""
    cmd = ["rg", "-c", "-i", "-e", term, "--", str(REPO_ROOT)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return {}
    if out.returncode not in (0, 1):
        return {}
    counts: dict[str, int] = {}
    for line in out.stdout.splitlines():
        path, _, cnt = line.rpartition(":")
        if not path:
            continue
        try:
            rel = str(Path(path).resolve().relative_to(REPO_ROOT))
        except ValueError:
            rel = path
        try:
            counts[rel] = int(cnt)
        except ValueError:
            continue
    return counts


def ripgrep_phrase_topk(query: str, k: int) -> list[str]:
    """Naive literal-phrase search — the documented first-attempt baseline."""
    return _rg(["-e", re.escape(query)])[:k]


def ripgrep_keyword_topk(query: str, k: int) -> list[str]:
    """Fair keyword baseline: rank files by (distinct query terms matched, total matches).

    This is a strong lexical proxy for an agent's grep-and-read loop: files that cover more
    of the query's content words, and mention them more often, rank first. Ties broken by
    path for determinism.
    """
    terms = [t for t in re.findall(r"[a-zA-Z_]{3,}", query.lower()) if t not in STOPWORDS]
    if not terms:
        return []
    distinct: Counter[str] = Counter()  # path -> # distinct query terms it matched
    total: Counter[str] = Counter()     # path -> total match count across terms
    for term in set(terms):
        for f, cnt in _rg_counts(term).items():
            if any(f.endswith(ext) for ext in (".py", ".sql", ".ts", ".js", ".sh", ".md")):
                distinct[f] += 1
                total[f] += cnt
    ranked = sorted(distinct, key=lambda f: (-distinct[f], -total[f], f))
    return ranked[:k]


def is_hit(topk: list[str], expected: list[str]) -> bool:
    top = set(topk)
    return any(e in top for e in expected)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semantic", type=Path, help="JSON of task_id -> ranked file list")
    ap.add_argument("--json", action="store_true", help="emit machine-readable summary")
    args = ap.parse_args()

    es = load_eval_set()
    k = es.get("k", 5)
    tasks = es["tasks"]

    semantic = {}
    if args.semantic and args.semantic.exists():
        semantic = json.loads(args.semantic.read_text())

    rows = []
    for t in tasks:
        exp = t["expected_files"]
        phrase = ripgrep_phrase_topk(t["query"], k)
        keyword = ripgrep_keyword_topk(t["query"], k)
        row = {
            "id": t["id"],
            "category": t["category"],
            "rg_phrase_hit": is_hit(phrase, exp),
            "rg_keyword_hit": is_hit(keyword, exp),
            "rg_keyword_topk": keyword,
        }
        if semantic:
            sem_topk = semantic.get(t["id"], [])[:k]
            row["semantic_hit"] = is_hit(sem_topk, exp)
            row["semantic_topk"] = sem_topk
        rows.append(row)

    n = len(rows)
    agg = {
        "n": n,
        "rg_phrase_hit_at_k": sum(r["rg_phrase_hit"] for r in rows),
        "rg_keyword_hit_at_k": sum(r["rg_keyword_hit"] for r in rows),
    }
    if semantic:
        agg["semantic_hit_at_k"] = sum(r.get("semantic_hit") for r in rows)
        # Semantic wins on tasks the fair keyword baseline missed:
        agg["semantic_wins_over_keyword"] = sum(
            1 for r in rows if r.get("semantic_hit") and not r["rg_keyword_hit"]
        )
        agg["gate_pass"] = (
            agg["semantic_hit_at_k"] >= 7 and agg["semantic_wins_over_keyword"] >= 2
        )

    if args.json:
        print(json.dumps({"k": k, "aggregate": agg, "rows": rows}, indent=2))
        return 0

    print(f"\nSpike eval — hit@{k} over {n} tasks (repo: {es['repo']})\n")
    hdr = f"{'id':<4} {'category':<13} {'rg-phrase':<10} {'rg-keyword':<11}"
    if semantic:
        hdr += f" {'semantic':<9}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        line = (
            f"{r['id']:<4} {r['category']:<13} "
            f"{'HIT' if r['rg_phrase_hit'] else 'miss':<10} "
            f"{'HIT' if r['rg_keyword_hit'] else 'miss':<11}"
        )
        if semantic:
            line += f" {'HIT' if r.get('semantic_hit') else 'miss':<9}"
        print(line)
    print("-" * len(hdr))
    print(f"\nripgrep-phrase  hit@{k}: {agg['rg_phrase_hit_at_k']}/{n}")
    print(f"ripgrep-keyword hit@{k}: {agg['rg_keyword_hit_at_k']}/{n}  (fair lexical baseline)")
    if semantic:
        print(f"semantic        hit@{k}: {agg['semantic_hit_at_k']}/{n}")
        print(f"semantic wins over keyword baseline: {agg['semantic_wins_over_keyword']}")
        print(f"\nGATE (>=7/10 semantic AND >=2 wins): {'PASS' if agg['gate_pass'] else 'FAIL'}")
    else:
        print("\n(semantic column absent — supply --semantic results.json to evaluate the gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
