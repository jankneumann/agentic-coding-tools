# Tasks: Add Architecture Report Configuration File

## Task 1: Define config dataclass and YAML loader
**File**: `scripts/reports/config_schema.py` (new)
**Depends on**: nothing
**Verification**: Unit test with sample YAML, test defaults when no file exists

- [x] Create `ReportConfig` dataclass with fields matching the YAML schema
- [x] Create `load_config(path: Path | None) -> ReportConfig` that loads YAML and falls back to defaults
- [x] Validate section names against a known set, warn on unknowns
- [x] Validate category names are strings, paths exist (with warnings, not errors)

## Task 2: Thread config through report generator
**File**: `scripts/reports/architecture_report.py`
**Depends on**: Task 1
**Verification**: Existing tests still pass (backwards-compatible)

- [x] Add `--config` CLI argument to `parse_args()`
- [x] Call `load_config()` in `main()` and pass to `generate_report()`
- [x] Use `config.paths.input_dir` as fallback default for `--input-dir` (CLI flag still overrides)
- [x] Use `config.paths.output_report` as fallback default for `--output` (CLI flag still overrides)
- [x] Pass config to each section function

## Task 3: Implement section toggling
**File**: `scripts/reports/architecture_report.py`
**Depends on**: Task 2
**Verification**: Test that omitting a section from config.report.sections skips it

- [x] In `generate_report()`, filter section functions against `config.report.sections`
- [x] Map section names to functions (e.g., `"system_overview"` → `_section_system_overview`)

## Task 4: Implement health customization
**File**: `scripts/reports/architecture_report.py`
**Depends on**: Task 2
**Verification**: Test with custom expected_categories and category_explanations

- [x] Replace hardcoded `_EXPECTED_CATEGORIES` with `config.health.expected_categories`
- [x] Replace hardcoded `_CATEGORY_EXPLANATIONS` with `config.health.category_explanations` (merged with defaults)
- [x] Implement `severity_thresholds` filtering

## Task 5: Implement best practices references
**File**: `scripts/reports/architecture_report.py`
**Depends on**: Task 2
**Verification**: Test that referenced files appear in report header
**Parallelizable with**: Tasks 3, 4

- [x] Add `_section_best_practices_context()` that reads referenced files
- [x] Extract specified sections from each file (by markdown heading)
- [x] Include as a collapsible reference section in the report

## Task 6: Implement project identity overrides
**File**: `scripts/reports/architecture_report.py`
**Depends on**: Task 2
**Verification**: Test that config.project.primary_language overrides auto-detection
**Parallelizable with**: Tasks 3, 4, 5

- [x] Use `config.project.primary_language` when set (skip auto-detection)
- [x] Use `config.project.protocol` when set (skip entrypoint-based detection)
- [x] Include `config.project.name` and `config.project.description` in report header

## Task 7: Create default config for this project
**File**: `architecture.config.yaml` (new, project root)
**Depends on**: Task 1
**Parallelizable with**: Tasks 2-6

- [x] Write the config file with values matching current hardcoded behavior
- [x] Document each field with YAML comments

## Task 8: Update tests
**File**: `scripts/tests/test_pipeline_integration.py`
**Depends on**: Tasks 2-6
**Verification**: `pytest scripts/tests/ -v` all pass

- [x] Test report generation with explicit config file
- [x] Test report generation with no config file (backwards-compatible defaults)
- [x] Test section toggling (omit a section, verify it's absent)
- [x] Test custom expected_categories

## Task 9: Update documentation
**File**: `docs/architecture-analysis/README.md`
**Depends on**: Task 7
**Verification**: Manual review

- [x] Add "Configuration" section explaining the config file
- [x] Document all config fields with examples
