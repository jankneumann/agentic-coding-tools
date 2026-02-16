# Proposal: Add Architecture Report Configuration File

## Summary

Add a YAML configuration file (`architecture.config.yaml`) that lets projects declaratively configure the architecture report generator. Currently, report behavior (expected diagnostic categories, section toggles, language classification, best practices references) is hardcoded in `architecture_report.py`. A config file makes the tooling portable across projects without code changes.

## Motivation

The architecture analysis tooling was built for the agent-coordinator project specifically. Several behaviors are hardcoded assumptions:

1. **Expected diagnostics**: `disconnected_flow` is marked "(expected)" because this is an MCP server — a web app would want those flagged as warnings.
2. **Language classification**: SQL is excluded from "primary language" detection because the codebase is a Python service with a Postgres schema. A SQL-heavy project would want different logic.
3. **Section selection**: All 10 report sections are always emitted. Some projects may want to skip irrelevant sections (e.g., no "Parallel Modification Zones" for solo-dev projects).
4. **Best practices context**: The report can't currently reference project-specific coding standards, ADRs, or style guides to contextualize its findings.
5. **Path defaults**: Input/output paths are hardcoded as CLI defaults — a config file provides a single source of truth.

## Approach

### Config file: `architecture.config.yaml`

A single YAML file at the project root (path overridable via `--config` CLI flag). The report generator loads it at startup and uses it to parameterize all sections. Missing keys fall back to sensible defaults so the config file is always optional.

### Config schema

```yaml
# architecture.config.yaml
project:
  name: "agent-coordinator"
  description: "Multi-agent coordination MCP server"
  primary_language: "python"          # Override auto-detection
  protocol: "mcp"                     # Override: "mcp", "http", "grpc", "cli", "auto"

paths:
  input_dir: "docs/architecture-analysis"
  output_report: "docs/architecture-analysis/architecture.report.md"

report:
  sections:                           # List of sections to include (order matters)
    - system_overview
    - module_map
    - dependency_layers
    - entry_points
    - health
    - impact_analysis
    - code_health
    - parallel_zones
    - cross_layer_flows               # Omitted if no flows exist regardless
    - diagrams

health:
  expected_categories:                # Diagnostic categories to mark "(expected)"
    - disconnected_flow
  category_explanations:              # Override/extend explanations per category
    disconnected_flow: "MCP routes have no frontend callers — expected (clients are AI agents)"
  severity_thresholds:                # Minimum severity to display per category
    orphan: "warning"                 # Skip info-level orphan findings

best_practices:                       # Files whose content contextualizes findings
  - path: "CLAUDE.md"
    sections: ["Architecture Patterns", "Code Style"]
  - path: "docs/agent-coordinator.md"
    sections: ["Design Principles"]
```

### Key design decisions

1. **YAML over JSON/TOML**: YAML supports comments (important for documenting why categories are expected), is widely used for config in this ecosystem, and the project already depends on PyYAML.
2. **Optional by design**: Every field has a default. Projects that don't create the file get identical behavior to today.
3. **No Makefile changes**: The config file is consumed by `architecture_report.py` only. The Makefile and `refresh_architecture.sh` continue to use `ARCH_DIR` env var for paths — the config file's `paths` section is an alternative default that the CLI falls back to.
4. **Best practices as context, not rules**: The `best_practices` section points to documents that are read and included as reference context in the report header — they don't drive automated checks.

## Scope

- **In scope**: Config file schema, config loading in `architecture_report.py`, section toggling, health customization, best practices reference, tests.
- **Out of scope**: Changing the analysis pipeline itself, adding new report sections, modifying the Makefile or shell scripts.

## Files to modify

| File | Change |
|------|--------|
| `scripts/reports/architecture_report.py` | Add `_load_config()`, thread config through `generate_report()` and section functions |
| `scripts/tests/test_pipeline_integration.py` | Add test for report generation with config file |
| `docs/architecture-analysis/README.md` | Document the config file |

## Files to create

| File | Purpose |
|------|---------|
| `architecture.config.yaml` | Default config for this project |
| `scripts/reports/config_schema.py` | Config dataclass + YAML loader + defaults |

## Risks

- **Schema drift**: If report sections are renamed/added, the config section names must stay in sync. Mitigated by validating config section names against known sections at load time and warning on unknowns.
- **Over-configuration**: Too many knobs makes the config hard to understand. Mitigated by keeping defaults sensible and the schema flat.
