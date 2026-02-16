# Change: Refactor Analysis into Clean 3-Layer Architecture

## Why

The current codebase analysis pipeline works but has grown organically into a set of tightly coupled scripts. The graph compiler (`compile_architecture_graph.py`, 1376 lines) mixes three distinct responsibilities: raw code analysis ingestion, cross-layer insight derivation, and output formatting. This makes it difficult to add new analyzers, create new insight types, or change output formats without modifying a single monolithic file. The current design also lacks a clean separation between "what the code looks like" (structural facts) and "what the code means" (architectural insights), making it hard for consumers to choose the right level of abstraction.

Refactoring into a clean 3-layer architecture — (1) code-analysis, (2) insight synthesis, (3) report aggregation — will make the pipeline extensible, testable, and composable. Each layer has a single responsibility and a well-defined interface (JSON schemas for layers 1-2, Markdown for layer 3).

## What Changes

- **Layer 1 — Code Analysis**: The existing per-language analyzers (`analyze_python.py`, `analyze_typescript.ts`, `analyze_postgres.py`) remain as the foundation, but their outputs are standardized into a common JSON schema with consistent keys, node ID conventions, and metadata fields. Each module analyzes a specific aspect of the codebase and produces a self-contained JSON artifact.

- **Layer 2 — Insight Synthesis**: New modules that consume Layer 1 JSON outputs and produce higher-level insights. The current graph compiler's cross-language linking, flow inference, cycle detection, disconnected endpoint analysis, and impact ranking are decomposed into independent insight modules. Each module reads one or more Layer 1 artifacts and produces either JSON (for machine consumption) or Markdown (for human consumption) insights.

- **Layer 3 — Report Aggregation**: A single report aggregator that collects all Layer 1 and Layer 2 outputs and composes them into a unified human-readable Markdown report. This replaces the scattered summary generation currently embedded across the compiler, validator, and view generator.

- **Orchestrator update**: `refresh_architecture.sh` updated to run the 3 layers in sequence with clear stage boundaries.

- **Backward compatibility**: The canonical `architecture.graph.json` and `architecture.summary.json` formats are preserved — the internal refactoring does not change the output schema.

## Impact

- Affected specs: `codebase-analysis` (MODIFIED — adds layer separation requirements)
- Affected code:
  - `scripts/compile_architecture_graph.py` — decomposed into Layer 2 insight modules
  - `scripts/validate_flows.py` — becomes a Layer 2 insight module
  - `scripts/generate_views.py` — becomes a Layer 3 report contributor
  - `scripts/parallel_zones.py` — becomes a Layer 2 insight module
  - `scripts/refresh_architecture.sh` — updated orchestration
  - New: `scripts/insights/` directory for Layer 2 modules
  - New: `scripts/reports/` directory for Layer 3 aggregator
- **BREAKING**: None — output artifacts remain the same
