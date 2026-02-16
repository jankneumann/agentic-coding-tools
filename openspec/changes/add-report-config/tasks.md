# Tasks: Add Architecture Report Configuration File

## Task 1: Define config dataclass and YAML loader
**File**: `scripts/reports/config_schema.py` (new)
**Depends on**: nothing
**Verification**: Unit test with sample YAML, test defaults when no file exists

- Create `ReportConfig` dataclass with fields matching the YAML schema
- Create `load_config(path: Path | None) -> ReportConfig` that loads YAML and falls back to defaults
- Validate section names against a known set, warn on unknowns
- Validate category names are strings, paths exist (with warnings, not errors)

## Task 2: Thread config through report generator
**File**: `scripts/reports/architecture_report.py`
**Depends on**: Task 1
**Verification**: Existing tests still pass (backwards-compatible)

- Add `--config` CLI argument to `parse_args()`
- Call `load_config()` in `main()` and pass to `generate_report()`
- Use `config.paths.input_dir` as fallback default for `--input-dir` (CLI flag still overrides)
- Use `config.paths.output_report` as fallback default for `--output` (CLI flag still overrides)
- Pass config to each section function

## Task 3: Implement section toggling
**File**: `scripts/reports/architecture_report.py`
**Depends on**: Task 2
**Verification**: Test that omitting a section from config.report.sections skips it

- In `generate_report()`, filter section functions against `config.report.sections`
- Map section names to functions (e.g., `"system_overview"` → `_section_system_overview`)

## Task 4: Implement health customization
**File**: `scripts/reports/architecture_report.py`
**Depends on**: Task 2
**Verification**: Test with custom expected_categories and category_explanations

- Replace hardcoded `_EXPECTED_CATEGORIES` with `config.health.expected_categories`
- Replace hardcoded `_CATEGORY_EXPLANATIONS` with `config.health.category_explanations` (merged with defaults)
- Implement `severity_thresholds` filtering

## Task 5: Implement best practices references
**File**: `scripts/reports/architecture_report.py`
**Depends on**: Task 2
**Verification**: Test that referenced files appear in report header
**Parallelizable with**: Tasks 3, 4

- Add `_section_best_practices_context()` that reads referenced files
- Extract specified sections from each file (by markdown heading)
- Include as a collapsible reference section in the report

## Task 6: Implement project identity overrides
**File**: `scripts/reports/architecture_report.py`
**Depends on**: Task 2
**Verification**: Test that config.project.primary_language overrides auto-detection
**Parallelizable with**: Tasks 3, 4, 5

- Use `config.project.primary_language` when set (skip auto-detection)
- Use `config.project.protocol` when set (skip entrypoint-based detection)
- Include `config.project.name` and `config.project.description` in report header

## Task 7: Create default config for this project
**File**: `architecture.config.yaml` (new, project root)
**Depends on**: Task 1
**Parallelizable with**: Tasks 2-6

- Write the config file with values matching current hardcoded behavior
- Document each field with YAML comments

## Task 8: Update tests
**File**: `scripts/tests/test_pipeline_integration.py`
**Depends on**: Tasks 2-6
**Verification**: `pytest scripts/tests/ -v` all pass

- Test report generation with explicit config file
- Test report generation with no config file (backwards-compatible defaults)
- Test section toggling (omit a section, verify it's absent)
- Test custom expected_categories

## Task 9: Update documentation
**File**: `docs/architecture-analysis/README.md`
**Depends on**: Task 7
**Verification**: Manual review

- Add "Configuration" section explaining the config file
- Document all config fields with examples
