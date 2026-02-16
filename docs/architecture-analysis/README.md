# Architecture Artifacts

This directory contains auto-generated architecture analysis artifacts for the codebase. These artifacts provide a machine-readable structural map of the project, enabling AI agents and developers to understand cross-layer relationships, validate flow connectivity, and identify safe parallel modification zones.

## Artifacts

| File | Description |
|------|-------------|
| `architecture.graph.json` | Full canonical graph with all nodes, edges, entrypoints, and snapshots |
| `architecture.summary.json` | Compact summary with cross-layer flows, stats, and disconnected endpoints |
| `architecture.diagnostics.json` | Validation findings (errors, warnings, info) from flow analysis |
| `architecture.report.md` | Narrative architecture report with explanations and health indicators |
| `parallel_zones.json` | Independent module groups, leaf modules, and high-impact modules |
| `python_analysis.json` | Intermediate Python AST analysis output |
| `postgres_analysis.json` | Intermediate Postgres schema analysis output |
| `ts_analysis.json` | Intermediate TypeScript analysis output (when available) |
| `views/` | Auto-generated Mermaid diagrams at multiple zoom levels |

## Views

| File | Description |
|------|-------------|
| `views/containers.mmd` | High-level container view (frontend, backend, database) |
| `views/backend_components.mmd` | Backend packages/modules with dependency edges |
| `views/frontend_components.mmd` | Frontend modules with import edges |
| `views/db_erd.mmd` | Database entity-relationship diagram |
| `views/feature_*.mmd` | Feature-scoped subgraph views |

## How to Refresh

From the project root:

```bash
# Full refresh (all analyzers + compiler + validator + views)
make architecture

# Quick refresh (skip views and parallel zones)
./scripts/refresh_architecture.sh --quick

# Validate only (uses existing graph)
make architecture-validate

# Regenerate views only
make architecture-views

# Compare to a baseline
make architecture-diff BASE_SHA=<commit-sha>

# Extract feature slice for PR review
make architecture-feature FEATURE="path/to/file1.py,path/to/file2.py"
```

From any location, targeting another project directory:

```bash
# Analyze another repository/project using this repo's tooling
python /path/to/agentic-coding-tools/scripts/run_architecture.py --target-dir /path/to/project

# Override source/output locations in the target project
python /path/to/agentic-coding-tools/scripts/run_architecture.py \
  --target-dir /path/to/project \
  --python-src-dir app \
  --ts-src-dir frontend \
  --migrations-dir db/migrations \
  --arch-dir docs/architecture-analysis \
  --quick
```

## When to Refresh

- **Before major feature work**: Ensure artifacts reflect the current state
- **After significant refactoring**: Update the structural map
- **Before creating a PR**: Run validation to catch broken flows
- Artifacts include `git_sha` and `generated_at` timestamps — a stale warning appears when artifacts are more than 20 commits behind HEAD

## How Agents Should Use These Artifacts

### Planning (`/plan-feature`)
- Read `architecture.summary.json` to understand which components, services, and tables are involved in related flows
- Use `cross_layer_flows` to identify existing end-to-end paths that the feature will touch
- Check `parallel_zones.json` to identify safe parallel modification zones

### Implementation (`/implement-feature`)
- Consult `parallel_zones.json` to determine which modules can be modified by parallel Task() agents
- After implementation, run `make architecture-validate` to check for broken flows

### Validation (`/validate-feature`)
- Include `architecture.diagnostics.json` findings alongside test and lint results
- Check for disconnected endpoints, missing test coverage, and orphaned code

## Configuration

The report generator supports an optional `architecture.config.yaml` file at the project root. This file controls report behavior without code changes, making the tooling portable across projects.

```bash
# Generate report using config file
python scripts/reports/architecture_report.py --config architecture.config.yaml

# Config is auto-detected if present in the current directory
python scripts/reports/architecture_report.py
```

### Config Fields

| Field | Description | Default |
|-------|-------------|---------|
| `project.name` | Project name shown in report header | *(empty)* |
| `project.description` | Project description shown in report header | *(empty)* |
| `project.primary_language` | Override language auto-detection | *(auto-detect)* |
| `project.protocol` | Override protocol detection (`mcp`, `http`, `grpc`, `cli`, `auto`) | *(auto-detect)* |
| `paths.input_dir` | Default input directory for JSON artifacts | `docs/architecture-analysis` |
| `paths.output_report` | Default output path for the report | `docs/architecture-analysis/architecture.report.md` |
| `report.sections` | Ordered list of sections to include | *(all sections)* |
| `health.expected_categories` | Diagnostic categories to mark "(expected)" | `[disconnected_flow]` |
| `health.category_explanations` | Override/extend explanations per category | *(built-in defaults)* |
| `health.severity_thresholds` | Minimum severity to display per category | *(none)* |
| `best_practices` | List of files to reference as project standards | *(none)* |

### Available Sections

`system_overview`, `module_map`, `dependency_layers`, `entry_points`, `health`, `impact_analysis`, `code_health`, `parallel_zones`, `cross_layer_flows`, `diagrams`

### Example

See `architecture.config.yaml` at the project root for a complete example with comments.

## Schema

The canonical graph follows the JSON schema defined in `scripts/architecture_schema.json`. Key concepts:

- **Nodes**: Functions, classes, components, tables — identified by `{prefix}:{qualified_name}` (py, ts, pg)
- **Edges**: Relationships with type, confidence (high/medium/low), and evidence
- **Entrypoints**: Routes, CLI commands, event handlers, jobs
- **Snapshots**: Generation metadata (timestamp, git SHA, tool versions)
