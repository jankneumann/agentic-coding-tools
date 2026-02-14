---
name: refresh-architecture
description: Refresh architecture analysis artifacts (.architecture/) from the codebase
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

Regenerate, validate, or inspect the `.architecture/` artifacts that describe the codebase structure. These artifacts power planning, parallel-zone identification, and cross-layer flow tracing.

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

- Python 3.12+ available (or activate the venv: `source agent-coordinator/.venv/bin/activate`)
- For TypeScript analysis: `npm` with `ts-morph` installed (`make architecture-setup`)
- For full pipeline: the source directories (`agent-coordinator/src`, `web/`, `agent-coordinator/supabase/migrations`) should exist

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
make architecture
```

This calls `scripts/refresh_architecture.sh` which runs all layers in sequence. Expect output showing each stage completing.

**When to use:** After significant code changes, before planning a new feature, or when artifacts are stale/missing.

#### Validate Only (`--validate`)

```bash
make architecture-validate
```

Runs schema validation and flow validation on the existing graph. Does NOT regenerate — just checks what's there.

**When to use:** After implementing changes to verify no cross-layer flows were broken. Good for CI checks.

#### Views Only (`--views`)

```bash
make architecture-views
```

Regenerates Mermaid diagrams and parallel zones from the existing graph.

**When to use:** When you need updated diagrams but the graph itself hasn't changed.

#### Report Only (`--report`)

```bash
make architecture-report
```

Generates `architecture.report.md` from all Layer 2 JSON artifacts.

**When to use:** When you need a human-readable summary of the current architecture state.

#### Diff (`--diff <sha>`)

```bash
make architecture-diff BASE_SHA=<sha>
```

Compares the current architecture graph to a baseline from the given commit SHA. Reports new cycles, new high-impact modules, untested routes, and structural changes.

**When to use:** Before merging a PR, to understand the architectural impact of the changes.

#### Feature Slice (`--feature <files>`)

```bash
make architecture-feature FEATURE="<comma-separated files or glob>"
```

Extracts a subgraph containing only the nodes and edges relevant to the specified files. Produces a Mermaid diagram and JSON in `.architecture/views/`.

**When to use:** To understand the blast radius of changing specific files, or to visualize a feature's dependency footprint.

#### Clean (`--clean`)

```bash
make architecture-clean
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

If the user asks to commit, stage the `.architecture/` directory:

```bash
git add .architecture/
```

Architecture artifacts are designed to be committed to the repo so agents can consult them during planning.

## Key Files Reference

| File | Purpose |
|------|---------|
| `.architecture/architecture.graph.json` | Canonical graph (nodes, edges, entrypoints) |
| `.architecture/architecture.summary.json` | Compact summary with stats and flows |
| `.architecture/architecture.diagnostics.json` | Validation findings |
| `.architecture/parallel_zones.json` | Independent module groups for safe parallel work |
| `.architecture/cross_layer_flows.json` | Frontend-to-database flow traces |
| `.architecture/high_impact_nodes.json` | Nodes with many transitive dependents |
| `.architecture/architecture.report.md` | Human-readable Markdown report |
| `.architecture/views/*.mmd` | Mermaid diagrams at multiple zoom levels |

## Integration with Workflow

- **Before `/plan-feature`**: Run full pipeline to ensure agents have current architecture context
- **During `/implement-feature`**: Run `--validate` after code changes to check for broken flows
- **Before `/validate-feature`**: Run `--diff` against the base branch to understand architectural impact
- **In CI**: Run `make architecture-validate` to catch regressions
