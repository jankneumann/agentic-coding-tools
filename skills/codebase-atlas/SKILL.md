---
name: codebase-atlas
description: Render the architecture graph as a single self-contained interactive HTML page — foldable structure tree, animated dependency graph, and cross-connection tracing
category: Architecture
tags: [architecture, visualization, documentation, html, navigation]
user_invocable: true
triggers:
  - "codebase atlas"
  - "visualize the codebase"
  - "visualise the codebase"
  - "code visualization"
  - "show me the architecture"
  - "dependency graph"
related:
  - refresh-architecture
  - project-context-refresh
  - documentation-and-adrs
---

# Codebase Atlas

Turn `docs/architecture-analysis/architecture.graph.json` into one interactive
HTML file you can open, read, and reason with. Built for the problem of losing
the shape of a codebase that agents are changing faster than anyone reads diffs.

This is a **rendering** skill. Every fact it displays comes from artifacts
`/refresh-architecture` already produces; it never parses source itself. If the
graph is wrong or narrow, the atlas says so rather than hiding it.

## Arguments

`$ARGUMENTS` — optional flags, forwarded to `scripts/build_atlas.py`:

| Flag | Effect |
|---|---|
| *(none)* | Write `docs/architecture-analysis/atlas/index.html` |
| `--check` | Read-only; exit `2` if the written page is stale |
| `--output PATH` | Write somewhere else |
| `--json-only` | Print the view-model as JSON; render nothing |
| `--no-coverage` | Skip the on-disk coverage scan (faster, drops the banner) |
| `--graph PATH` | Read a different graph artifact |

## Usage

```bash
make atlas          # build docs/architecture-analysis/atlas/index.html
make atlas-check    # read-only drift check (exit 0 fresh / 2 stale)
```

Then open the file. It needs no server, no build step, and makes **zero network
requests** — it works offline and under a strict CSP.

## What the page gives you

**Structure pane (left)** — foldable tree: language → file → symbol, with SQL
columns nested under their tables. Live filter across files and symbols;
expand/collapse all. Counts at every level.

**Dependency pane (centre)** — animated force-directed graph, one node per
source file, sized by symbol count and coloured by language. Scroll to zoom,
drag to pan, drag a node to pin it, double-click to re-frame. The simulation
pre-warms before the first paint so the page opens on a settled layout, then
stops once relaxed, so an open tab costs no CPU.

**Cross-connections pane (right)** — select anything and see what calls it and
what it calls. Callers render orange, dependencies teal, with arrowheads and hop
distance; everything else dims. The hop slider widens the neighbourhood to 4.
Every entry is clickable, so you can walk the call graph without leaving the
page. Selecting a symbol gives symbol-level precision; selecting a file gives
the aggregated module view.

Any view is a URL: selection, hop depth, filter text, and disabled
language/edge-type filters all round-trip through the location hash, so a view
can be pasted into a PR or an issue.

## Coverage honesty

The banner at the top is the most important thing on the page, and it cannot be
dismissed. The analyzer only examines the roots configured in the Makefile
(`PYTHON_SRC_DIR`, `TS_SRC_DIR`), so the graph can describe a small fraction of
the repository while looking authoritative. The banner reports, per language:

- how many on-disk files the graph actually covers, as a percentage;
- which top-level directories contain files the graph never saw;
- how many files the graph names that **no longer exist on disk** — a direct
  staleness signal, since it means the graph outlived its source.

Coverage is matched by **file name, not full path**, because the analyzer records
bare basenames. One graph name can match several on-disk files, so the reported
percentage is an optimistic upper bound. Treat it as a ceiling.

## Determinism

Output is byte-stable for a fixed input graph: collections are sorted, JSON is
serialised with sorted keys, and initial node positions are seeded from a hash of
each module key rather than from a random generator. Re-running without upstream
changes produces an identical file, which is what makes `--check` meaningful.

Selecting a node deliberately does **not** re-heat the simulation. A node must
not move because it was clicked, or the reader loses their mental map.

## Relationship to other skills

- `/refresh-architecture` produces the graph this reads. Run it first; if the
  atlas reports staleness, that is the fix.
- `project-context-refresh` owns deterministic *documentation* inventories
  (`documentation.inventory`, `api.contracts`). The atlas is the visual
  counterpart and shares its generate/check exit-code contract
  (`0` fresh · `1` error · `2` drift).
- The generated HTML is **gitignored**: it is derived, ~650 KB, and not
  meaningfully diffable. Regenerate it with `make atlas` instead of committing it.

## Scope

This skill renders what the graph contains: files, symbols, call edges, and
import edges. It does not add extraction, a graph database, a server, or an
LLM-backed query surface. Those are later phases of
`docs/proposals/codebase-visualization-tool.md`, deliberately not prerequisites
for the page existing.
