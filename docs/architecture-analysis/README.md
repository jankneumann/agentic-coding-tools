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

## Schema

The canonical graph follows the JSON schema defined in `scripts/architecture_schema.json`. Key concepts:

- **Nodes**: Functions, classes, components, tables — identified by `{prefix}:{qualified_name}` (py, ts, pg)
- **Edges**: Relationships with type, confidence (high/medium/low), and evidence
- **Entrypoints**: Routes, CLI commands, event handlers, jobs
- **Snapshots**: Generation metadata (timestamp, git SHA, tool versions)
