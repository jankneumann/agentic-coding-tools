---
name: refresh-architecture
description: Refresh architecture analysis artifacts (docs/architecture-analysis/) from the codebase
category: Architecture
tags: [architecture, analysis, graph, validation, views]
triggers:
  - "refresh architecture"
  - "update architecture"
  - "regenerate architecture"
  - "architecture analysis"
  - "run architecture"
---

# Refresh Architecture

Regenerate, validate, or inspect the `docs/architecture-analysis/` artifacts that describe the codebase structure. These artifacts power planning, parallel-zone identification, and cross-layer flow tracing.

## Arguments

`$ARGUMENTS` - Optional mode selector and flags:

| Argument | Description |
|----------|-------------|
| *(empty)* | Full pipeline: analyze + compile + validate + views + report |
| `--validate` | Validate the existing graph (no regeneration) |
| `--views` | Regenerate views and parallel zones from existing graph |
| `--report` | Generate Markdown report from existing Layer 2 artifacts |
| `--diff <sha>` | Compare current graph to a baseline commit |
| `--feature <files>` | Extract a feature-slice subgraph for the given files |
| `--clean` | Remove all generated artifacts |

## Prerequisites

- Python 3.12+ available as `python3`
- For TypeScript analysis: `npm` with `ts-morph`, `typescript`, and `ts-node`
- A consumer project root. Defaults are `src/`, `web/`, and
  `database/migrations/`; override them with `--python-src-dir`,
  `--ts-src-dir`, and `--migrations-dir` for other layouts.

Resolve `<skill-base-dir>` to the directory containing this loaded `SKILL.md`.
Every command below invokes shipped tools from that directory and does not
require a repo-root Makefile, `agent-coordinator/`, or `skills/.venv`.

## Local CLI Mutation Boundary

Modes that regenerate, rewrite, or clean `docs/architecture-analysis/` artifacts
MUST run in a managed worktree in local CLI execution:

```bash
CHANGE_ID="refresh-architecture-<short-slug>"
eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "$CHANGE_ID")"
cd "$WORKTREE_PATH"
python3 "<skill-base-dir>/../shared/checkout_policy.py" require-mutation
```

Pure read-only inspection modes may run from the shared checkout when they do
not write files.

## Architecture Overview

The analysis pipeline has 3 layers:

```
Layer 1: Code Analysis (per-language)
  analyze_python.py    -> python_analysis.json
  analyze_postgres.py  -> postgres_analysis.json
  analyze_typescript.ts -> ts_analysis.json

Layer 2: Insight Synthesis (from Layer 1 outputs)
  graph_builder        -> architecture.graph.json
  cross_layer_linker   -> (updates graph with api_call edges)
  db_linker            -> (updates graph with db_access edges)
  flow_tracer          -> cross_layer_flows.json
  impact_ranker        -> high_impact_nodes.json
  summary_builder      -> architecture.summary.json
  validate_flows       -> architecture.diagnostics.json
  parallel_zones       -> parallel_zones.json

Layer 3: Report Aggregation
  generate_views       -> views/*.mmd (Mermaid diagrams)
  architecture_report  -> architecture.report.md
```

## Steps

### 1. Parse Arguments

```
ARGS="$ARGUMENTS"
```

Determine which mode to run based on the arguments.

### 2. Execute the Appropriate Mode

#### Full Pipeline (no args or explicit `--full`)

Run the complete 3-layer pipeline:

```bash
python3 "<skill-base-dir>/scripts/run_architecture.py" \
  --target-dir . \
  --python-src-dir "${PYTHON_SRC_DIR:-src}" \
  --ts-src-dir "${TS_SRC_DIR:-web}" \
  --migrations-dir "${MIGRATIONS_DIR:-database/migrations}"
```

The wrapper resolves `refresh_architecture.sh` from this installed skill and
runs all layers in the consumer project working directory. Expect output
showing each stage completing.

**When to use:** After significant code changes, before planning a new feature, or when artifacts are stale/missing.

#### Validate Only (`--validate`)

```bash
python3 "<skill-base-dir>/../validate-flows/scripts/validate_flows.py" \
  --graph docs/architecture-analysis/architecture.graph.json \
  --output docs/architecture-analysis/architecture.diagnostics.json
```

Runs schema validation and flow validation on the existing graph. Does NOT regenerate — just checks what's there.

**When to use:** After implementing changes to verify no cross-layer flows were broken. Good for CI checks.

#### Views Only (`--views`)

```bash
python3 "<skill-base-dir>/scripts/generate_views.py" \
  --graph docs/architecture-analysis/architecture.graph.json \
  --output-dir docs/architecture-analysis/views
python3 "<skill-base-dir>/scripts/parallel_zones.py" \
  --graph docs/architecture-analysis/architecture.graph.json \
  --output docs/architecture-analysis/parallel_zones.json
```

Regenerates Mermaid diagrams and parallel zones from the existing graph.

**When to use:** When you need updated diagrams but the graph itself hasn't changed.

#### Report Only (`--report`)

```bash
python3 "<skill-base-dir>/scripts/reports/architecture_report.py" \
  --input-dir docs/architecture-analysis \
  --output docs/architecture-analysis/architecture.report.md
```

Generates `architecture.report.md` from all Layer 2 JSON artifacts.

**When to use:** When you need a human-readable summary of the current architecture state.

#### Diff (`--diff <sha>`)

```bash
BASE_SHA=<sha>
mkdir -p docs/architecture-analysis/tmp
git show "${BASE_SHA}:docs/architecture-analysis/architecture.graph.json" \
  > docs/architecture-analysis/tmp/baseline_graph.json
python3 "<skill-base-dir>/scripts/diff_architecture.py" \
  --baseline docs/architecture-analysis/tmp/baseline_graph.json \
  --current docs/architecture-analysis/architecture.graph.json \
  --output docs/architecture-analysis/architecture.diff.json
```

Compares the current architecture graph to a baseline from the given commit SHA. Reports new cycles, new high-impact modules, untested routes, and structural changes.

**When to use:** Before merging a PR, to understand the architectural impact of the changes.

#### Feature Slice (`--feature <files>`)

```bash
python3 "<skill-base-dir>/scripts/generate_views.py" \
  --graph docs/architecture-analysis/architecture.graph.json \
  --output-dir docs/architecture-analysis/views \
  --feature-files "<comma-separated files or glob>"
```

Extracts a subgraph containing only the nodes and edges relevant to the specified files. Produces a Mermaid diagram and JSON in `docs/architecture-analysis/views/`.

**When to use:** To understand the blast radius of changing specific files, or to visualize a feature's dependency footprint.

#### Clean (`--clean`)

```bash
ARCH_DIR="docs/architecture-analysis"  # consumer-project-relative output
rm -f "$ARCH_DIR"/{python_analysis,ts_analysis,postgres_analysis,architecture.graph,architecture.summary,architecture.diagnostics,architecture.diff,cross_layer_flows,high_impact_nodes,parallel_zones}.json
rm -f "$ARCH_DIR/architecture.report.md"
rm -rf "$ARCH_DIR/views" "$ARCH_DIR/tmp"
```

Removes all generated artifacts. The committed README and schema files are preserved.

**When to use:** When artifacts are corrupted or you want a fresh start.

### 3. Report Results

After running, report to the user:

1. **Which artifacts were generated/updated** (list the files)
2. **Key stats** from `architecture.summary.json`:
   - Total nodes/edges by language
   - Number of cross-layer flows
   - Number of disconnected endpoints (potential issues)
   - Number of high-impact nodes
3. **Any validation findings** from `architecture.diagnostics.json`:
   - Errors (must fix)
   - Warnings (should investigate)
   - Info (awareness)
4. **Parallel zones** from `parallel_zones.json`:
   - Number of independent groups
   - Largest group size

### 4. Commit Artifacts (if requested)

If the user asks to commit, stage the `docs/architecture-analysis/` directory:

```bash
git add docs/architecture-analysis/
```

Architecture artifacts are designed to be committed to the repo so agents can consult them during planning.

## Key Files Reference

| File | Purpose |
|------|---------|
| `docs/architecture-analysis/architecture.graph.json` | Canonical graph (nodes, edges, entrypoints) |
| `docs/architecture-analysis/architecture.summary.json` | Compact summary with stats and flows |
| `docs/architecture-analysis/architecture.diagnostics.json` | Validation findings |
| `docs/architecture-analysis/parallel_zones.json` | Independent module groups for safe parallel work |
| `docs/architecture-analysis/cross_layer_flows.json` | Frontend-to-database flow traces |
| `docs/architecture-analysis/high_impact_nodes.json` | Nodes with many transitive dependents |
| `docs/architecture-analysis/architecture.report.md` | Human-readable Markdown report |
| `docs/architecture-analysis/views/*.mmd` | Mermaid diagrams at multiple zoom levels |

## Revision-Aware Provenance & Freshness

The architecture producer records `docs/architecture-analysis/architecture.provenance.json`
(analyzed Git SHA, dirty state, producer version, relevant input fingerprint,
mode, and owned-artifact SHA-256 digests). Freshness is **content-based and
mtime-independent** — decided by input/producer/artifact identity, never file age.

- `make architecture-refresh` — deterministic staged refresh (stage → validate →
  promote → write provenance). Byte-identical for the same revision/inputs; a
  failed run preserves the last known-good committed artifacts.
- `make architecture-check` — read-only freshness check; exits 0 only when
  `fresh` and prints precise drift reason codes + stale artifact paths.
- `carried_over` — promotion copies staged files into the output directory and
  never deletes, because the optional stages skip soft (a partial refresh must
  not destroy the last good copy) and `views/.gitkeep` is committed but never
  staged. So an artifact a stage failed to produce survives at the bytes an
  earlier revision wrote. Each recorded artifact therefore carries
  `carried_over`: `false` means this run produced it, `true` means it was left
  in place. Both are recorded — the digest still pins the committed bytes — and
  both refresh and check list the carried-over paths. Carrying an artifact over
  is **not** drift; it is a soft skip, and the flag is what keeps the record
  from claiming the revision generated it. An entry with no `carried_over` key
  was written outside a staged run: unknown, never "freshly generated".
- Durable cross-process status is owned by `project-context-runtime`
  (`add-durable-context-refresh-records`); this skill records one canonical
  `producer_id=architecture` result per `(repository, revision)` operation and
  projects it onto the refresh RPC. It never finalizes the whole operation.

## Integration with Workflow

- **Before `/plan-feature`**: Run full pipeline to ensure agents have current architecture context
- **During `/implement-feature`**: Run `--validate` after code changes to check for broken flows
- **Before `/validate-feature`**: Run `--diff` against the base branch to understand architectural impact
- **In CI**: Run `make architecture-check` (content-based) to catch stale committed artifacts
