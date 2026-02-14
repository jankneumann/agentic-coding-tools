## Context

The codebase analysis pipeline currently consists of 3 per-language analyzers feeding into a monolithic graph compiler (1376 lines) that handles ingestion, cross-language linking, flow inference, deduplication, and summary generation. Downstream consumers (validator, view generator, parallel zones) each read the compiler's output and produce their own artifacts independently.

This works but creates problems:
- Adding a new insight (e.g., "API surface area report") requires modifying the compiler
- The compiler mixes structural graph construction with analytical reasoning
- Testing insight logic requires running the full compilation pipeline
- The summary format is hardcoded into the compiler rather than being composable

## Goals / Non-Goals

- **Goals:**
  - Clean separation of structural analysis (Layer 1), insight synthesis (Layer 2), and report generation (Layer 3)
  - Each layer module is independently testable with fixture JSON inputs
  - New analyzers and insight modules can be added without modifying existing code
  - Consistent JSON schema contracts between layers
  - Preserve existing output artifact formats for backward compatibility

- **Non-Goals:**
  - Rewriting the per-language analyzers (Layer 1 modules are already well-structured)
  - Changing the canonical graph schema (nodes/edges/entrypoints)
  - Adding new analysis capabilities (this is purely a structural refactor)
  - Building a plugin/registry system (simple module imports are sufficient)

## Decisions

### Layer 1: Code Analysis Modules

**Decision:** Keep existing analyzers as-is but standardize output key naming.

The 3 existing analyzers (`analyze_python.py`, `analyze_typescript.ts`, `analyze_postgres.py`) already produce well-structured JSON. The only changes needed are fixing key mismatches identified in PR #14 review (e.g., `api_call_sites` vs `api_calls`, `stored_functions` vs `functions`).

Each Layer 1 module:
- Takes a source directory as input
- Produces a single JSON file as output
- Has no dependency on other Layer 1 modules
- Follows the naming convention: `<language>_analysis.json`

### Layer 2: Insight Synthesis Modules

**Decision:** Decompose the graph compiler into focused insight modules under `scripts/insights/`.

Current compiler responsibilities mapped to new modules:

| Current location | New module | Input | Output |
|---|---|---|---|
| `compile_architecture_graph.py:92-519` | `insights/graph_builder.py` | All Layer 1 JSON files | `architecture.graph.json` (canonical graph) |
| `compile_architecture_graph.py:558-723` | `insights/cross_layer_linker.py` | `architecture.graph.json` + Layer 1 TS data | Cross-language edges appended to graph |
| `compile_architecture_graph.py:731-797` | `insights/db_linker.py` | `architecture.graph.json` + Layer 1 Python/PG data | Backend→DB edges appended to graph |
| `compile_architecture_graph.py:805-882` | `insights/flow_tracer.py` | `architecture.graph.json` | `cross_layer_flows.json` |
| `compile_architecture_graph.py:890-990` | `insights/impact_ranker.py` | `architecture.graph.json` | `high_impact_nodes.json` |
| `validate_flows.py` | `insights/flow_validator.py` | `architecture.graph.json` | `architecture.diagnostics.json` |
| `parallel_zones.py` | `insights/parallel_zones.py` | `architecture.graph.json` | `parallel_zones.json` |

Each Layer 2 module:
- Reads one or more Layer 1 JSON artifacts (or the canonical graph)
- Produces a single JSON or Markdown output
- Is independently testable with fixture inputs
- Declares its input dependencies explicitly

**Alternatives considered:**
- Plugin registry with dynamic discovery → Rejected: over-engineering for ~7 modules
- Single file with classes per insight → Rejected: still couples everything in one file

### Layer 3: Report Aggregator

**Decision:** Single `scripts/reports/architecture_report.py` that reads all Layer 1 and Layer 2 outputs and produces a unified Markdown report.

The report aggregator:
- Reads `architecture.graph.json`, `architecture.summary.json`, `architecture.diagnostics.json`, `parallel_zones.json`, `cross_layer_flows.json`
- Produces `architecture.report.md` — a human-readable summary with sections for each analysis dimension
- Can optionally embed Mermaid diagrams inline (from `generate_views.py` output)
- Uses a simple template approach (string formatting, not a template engine)

The existing `generate_views.py` becomes a Layer 3 contributor that produces Mermaid diagram fragments consumed by the report aggregator.

### Shared Utilities

**Decision:** Keep `scripts/arch_utils/` as the shared utility layer (already exists with `node_id.py`, `constants.py`, `traversal.py`, `graph_io.py`).

### Orchestration

**Decision:** Update `refresh_architecture.sh` to run layers in explicit stages:

```
Stage 1: Code Analysis (parallel)
  → analyze_python.py
  → analyze_postgres.py
  → analyze_typescript.ts

Stage 2: Insight Synthesis (sequential, dependency-ordered)
  → graph_builder.py          (depends on: Layer 1 outputs)
  → cross_layer_linker.py     (depends on: graph_builder output + TS data)
  → db_linker.py              (depends on: graph_builder output + Python/PG data)
  → flow_tracer.py            (depends on: linked graph)
  → impact_ranker.py          (depends on: linked graph)
  → flow_validator.py         (depends on: linked graph)
  → parallel_zones.py         (depends on: linked graph)

Stage 3: Report Aggregation
  → generate_views.py         (depends on: linked graph)
  → architecture_report.py    (depends on: all Layer 2 outputs + views)
```

## Risks / Trade-offs

- **Risk:** Decomposition creates more files to navigate → **Mitigation:** Clear naming convention, shared utilities, single orchestrator entry point
- **Risk:** Intermediate JSON files increase disk usage → **Mitigation:** Files are small (KB range), and the intermediate artifacts are useful for debugging
- **Risk:** Sequential insight modules may be slower than monolithic compiler → **Mitigation:** Individual modules are fast; the overhead of JSON serialization/deserialization is negligible compared to analysis time. Layer 1 already runs in parallel.

## Migration Plan

1. Fix PR #14 bugs first (key mismatches, missing arguments) — done in this branch
2. Extract graph builder from compiler (preserves `architecture.graph.json` output)
3. Extract cross-language linker and DB linker
4. Extract flow tracer and impact ranker
5. Refactor validator and parallel zones into insight module interface
6. Create report aggregator
7. Update orchestrator
8. Verify output artifact compatibility (diff against baseline)

## Open Questions

- Should Layer 2 modules share a common base class / protocol, or is duck typing with consistent CLI interfaces sufficient?
- Should the report aggregator produce multiple report formats (Markdown, HTML, JSON summary) or just Markdown?
