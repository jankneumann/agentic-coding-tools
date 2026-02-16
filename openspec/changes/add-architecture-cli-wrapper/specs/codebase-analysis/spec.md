## ADDED Requirements

### Requirement: Standalone Architecture Runner for Arbitrary Target Directories

The system SHALL provide a Python entrypoint that runs the architecture refresh pipeline against a specified target directory without requiring invocation from this repository root.

- The system SHALL provide `scripts/run_architecture.py` as a wrapper around `scripts/refresh_architecture.sh`.
- The wrapper SHALL accept `--target-dir` and execute the refresh pipeline with that directory as working directory.
- The wrapper SHALL accept `--python-src-dir`, `--ts-src-dir`, `--migrations-dir`, and `--arch-dir` and map them to `PYTHON_SRC_DIR`, `TS_SRC_DIR`, `MIGRATIONS_DIR`, and `ARCH_DIR` for the refresh script.
- The wrapper SHALL support `--quick` and pass it through to the refresh script.
- The wrapper SHALL set `SCRIPTS_DIR` to this repository's absolute `scripts/` path so tool resolution does not depend on the target directory layout.
- The existing `make architecture` workflow SHALL remain supported for local repository usage.

#### Scenario: Analyze an external project directory
- **WHEN** a user runs `python scripts/run_architecture.py --target-dir /path/to/project`
- **THEN** the wrapper SHALL run the architecture refresh pipeline with working directory `/path/to/project`
- **AND** artifacts SHALL be produced under that target directory's configured `ARCH_DIR`

#### Scenario: Override source and output paths
- **WHEN** a user runs `python scripts/run_architecture.py --target-dir /path/to/project --python-src-dir app --ts-src-dir frontend --migrations-dir db/migrations --arch-dir docs/architecture-analysis`
- **THEN** the wrapper SHALL pass the corresponding environment variables to `refresh_architecture.sh`
- **AND** analyzers SHALL read from the overridden source directories

#### Scenario: Quick mode passthrough
- **WHEN** a user runs `python scripts/run_architecture.py --target-dir /path/to/project --quick`
- **THEN** the wrapper SHALL invoke `refresh_architecture.sh --quick`
- **AND** Layer 3 report/view generation SHALL be skipped

#### Scenario: Backward-compatible local workflow
- **WHEN** a user runs `make architecture` from this repository root
- **THEN** the architecture pipeline SHALL still execute successfully without requiring `--target-dir`
