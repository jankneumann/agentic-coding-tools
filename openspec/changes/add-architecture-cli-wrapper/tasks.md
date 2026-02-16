## 1. CLI Wrapper

- [x] 1.1 Create `scripts/run_architecture.py` with argparse support for `--target-dir`, `--python-src-dir`, `--ts-src-dir`, `--migrations-dir`, `--arch-dir`, and `--quick`.
- [x] 1.2 Resolve this repository's `scripts/` directory to an absolute path and pass it as `SCRIPTS_DIR`.
- [x] 1.3 Execute `scripts/refresh_architecture.sh` from the target directory with environment variable overrides (`PYTHON_SRC_DIR`, `TS_SRC_DIR`, `MIGRATIONS_DIR`, `ARCH_DIR`, `PYTHON`, optional quick mode).
- [x] 1.4 Return the underlying script exit code and propagate stderr/stdout for operator visibility.

## 2. Local Workflow Compatibility

- [x] 2.1 Keep `make architecture` as a supported local workflow.
- [x] 2.2 Optionally route `make architecture` through the wrapper in a backward-compatible way (no required behavior changes for existing users).

## 3. Documentation and Validation

- [x] 3.1 Update `docs/architecture-analysis/README.md` with examples for analyzing an external target directory.
- [x] 3.2 Add or update tests validating argument mapping and environment propagation for the wrapper.
- [x] 3.3 Run relevant validation (`openspec validate add-architecture-cli-wrapper --strict`, and project tests covering the wrapper) before merge.
