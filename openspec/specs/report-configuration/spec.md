# report-configuration Specification

## Purpose
TBD - created by archiving change add-report-config. Update Purpose after archive.
## Requirements
### Requirement: Architecture Report Configuration File

The system SHALL support an optional YAML configuration file (`architecture.config.yaml`) that parameterizes the architecture report generator. All configuration fields SHALL have sensible defaults so the file is never required.

- The config file SHALL be loaded from a path specified by `--config` CLI flag, falling back to `architecture.config.yaml` in the current working directory, falling back to built-in defaults.
- The config SHALL support a `project` section with `name` (string), `description` (string), `primary_language` (string, overrides auto-detection), and `protocol` (string: "mcp" | "http" | "grpc" | "cli" | "auto", overrides entrypoint-based detection).
- The config SHALL support a `paths` section with `input_dir` (string) and `output_report` (string) that serve as defaults when CLI flags are not provided.
- The config SHALL support a `report.sections` list that controls which sections appear in the report and in what order.
- The config SHALL support a `health` section with `expected_categories` (list of strings), `category_explanations` (map of category to explanation string), and `severity_thresholds` (map of category to minimum severity).
- The config SHALL support a `best_practices` section listing files (with optional section headings) whose content is included as reference context in the report.
- Unknown configuration keys SHALL produce a logged warning, not an error, to maintain forward compatibility.

#### Scenario: Report generation with config file
- **WHEN** `architecture.config.yaml` exists with `project.primary_language: "python"` and `health.expected_categories: ["disconnected_flow"]`
- **THEN** the report SHALL use "Python" as the primary language without auto-detection
- **AND** the "Disconnected Flow" health section SHALL be marked "(expected)"

#### Scenario: Report generation without config file
- **WHEN** no `architecture.config.yaml` exists and no `--config` flag is provided
- **THEN** the report generator SHALL use built-in defaults
- **AND** produce identical output to the current behavior

#### Scenario: CLI flags override config file
- **WHEN** the config file sets `paths.input_dir: "docs/architecture-analysis"` but `--input-dir .architecture` is passed on the command line
- **THEN** the report generator SHALL read artifacts from `.architecture`

#### Scenario: Section toggling via config
- **WHEN** the config file sets `report.sections` to `["system_overview", "entry_points", "health"]`
- **THEN** the report SHALL contain only those three sections in that order
- **AND** other sections (module_map, dependency_layers, etc.) SHALL be omitted

#### Scenario: Custom health category explanation
- **WHEN** the config file sets `health.category_explanations.orphan` to a custom string
- **THEN** the "Orphan" health section SHALL use the custom explanation instead of the built-in default

#### Scenario: Best practices reference inclusion
- **WHEN** the config file lists `best_practices: [{path: "CLAUDE.md", sections: ["Architecture Patterns"]}]`
- **AND** `CLAUDE.md` contains a section headed `## Architecture Patterns`
- **THEN** the report SHALL include the content of that section as reference context

#### Scenario: Unknown config keys
- **WHEN** the config file contains a key `experimental.foo: "bar"` that is not part of the schema
- **THEN** the report generator SHALL log a warning about the unknown key
- **AND** proceed with report generation using known fields

#### Scenario: Severity threshold filtering
- **WHEN** the config file sets `health.severity_thresholds.orphan: "warning"`
- **THEN** the "Orphan" health section SHALL only show findings with severity "warning" or higher
- **AND** "info"-level orphan findings SHALL be excluded from the count and examples

