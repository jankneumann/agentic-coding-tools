# Change: Add Architecture CLI Wrapper for External Target Directories

## Why

`make architecture` currently assumes invocation from this repository root, which is inconvenient when analyzing a different project directory. While source directories can be overridden via environment variables, users still need repo-relative script paths and root-specific execution context.

## What Changes

1. Keep `make architecture` as the primary workflow for local repository usage.
2. Add a Python CLI wrapper (`scripts/run_architecture.py`) that can be invoked from any location and target another code directory.
3. The wrapper will:
   - accept `--target-dir` and execute analysis as if run from that directory
   - accept `--python-src-dir`, `--ts-src-dir`, `--migrations-dir`, `--arch-dir`, and `--quick`
   - resolve `SCRIPTS_DIR` to this repository's absolute `scripts/` path
   - run `scripts/refresh_architecture.sh` with the correct environment variables
4. Document usage for user-level and project-level invocation.

## Impact

- Affected specs: `codebase-analysis`
- Affected code:
  - `scripts/run_architecture.py` (new)
  - `Makefile` (optional wrapper integration/backward-compatible invocation path)
  - `docs/architecture-analysis/README.md` (usage documentation)
- Breaking changes: None. Existing `make architecture` behavior remains supported.
