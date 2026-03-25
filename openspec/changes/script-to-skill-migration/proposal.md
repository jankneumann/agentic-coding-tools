# Proposal: Migrate All Scripts to Skills — Eliminate scripts/ Directory

## Change ID
`script-to-skill-migration`

## Problem

Skills reference Python scripts at repo-root paths (e.g., `python3 scripts/worktree.py setup ...`) that only exist in the source repository. When skills are synced to other repos via `install.sh`, the `scripts/` directory is absent — these scripts simply don't exist at the target location.

This means **21 skills fail** when invoked outside the source repo because `scripts/worktree.py` cannot be found, and **12 skills fail** because `scripts/coordination_bridge.py` is missing.

### Root Cause

The skill packaging model treats skills as self-contained directories but allows SKILL.md instructions to reference paths outside the skill boundary. `install.sh` syncs `skills/<name>/` directories but has no mechanism to also sync `scripts/`.

### Impact

- Skills are **not portable** — they only work in the source repo
- Worktree-based execution (the launcher invariant) breaks in deployed contexts
- Coordinator bridge fallback is unavailable, removing graceful degradation
- Parallel workflow validation scripts are missing

## Solution

**Move all scripts into their relevant skill directories and delete `scripts/` entirely.** Each script becomes the single source of truth inside its skill — no duplication, no sync step.

### Key Design Decisions

1. **Single source of truth** — scripts live in skill directories, not copied from elsewhere
2. **`scripts/` is fully eliminated** — no residual directory, no two-place maintenance
3. **`pyproject.toml` moves to `skills/`** — becomes the shared Python dependency manifest for infrastructure skills, referenced by `install.sh` during `--deps` step
4. **Tests move with their scripts** — each infra skill gets `scripts/tests/` with the relevant test files
5. **CI updates** — points at `skills/*/scripts/tests/` instead of `scripts/tests/`
6. **Sibling-relative paths** — consuming skills reference scripts via `<skill-base-dir>/../<infra-skill>/scripts/<script>.py`

### Complete Migration Map

| Destination Skill | Scripts Moved | Tests Moved |
|-------------------|--------------|-------------|
| `skills/worktree/` (new) | `worktree.py`, `merge_worktrees.py`, `git-parallel-setup.sh` | `test_worktree.py`, `test_merge_worktrees.py` |
| `skills/coordination-bridge/` (new) | `coordination_bridge.py` | `test_coordination_bridge.py` |
| `skills/validate-packages/` (new) | `validate_work_packages.py`, `parallel_zones.py`, `validate_work_result.py`, `validate_schema.py`, `architecture_schema.json` | `test_validate_work_packages.py`, `test_parallel_zones_packages.py`, `test_validate_work_result.py` |
| `skills/validate-flows/` (new) | `validate_flows.py` | `test_flow_tracer.py` |
| `skills/refresh-architecture/` (exists) | `analyze_python.py`, `analyze_postgres.py`, `analyze_sql_treesitter.py`, `analyze_typescript.ts`, `compile_architecture_graph.py`, `diff_architecture.py`, `enrich_with_treesitter.py`, `generate_views.py`, `run_architecture.py`, `refresh_architecture.sh`, `treesitter_queries/`, `insights/`, `reports/` | `test_analyze_sql_treesitter.py`, `test_comment_linker.py`, `test_cross_layer_linker.py`, `test_enrich_with_treesitter.py`, `test_flow_tracer.py`, `test_graph_builder.py`, `test_impact_ranker.py`, `test_pattern_reporter.py`, `test_pipeline_integration.py`, `test_run_architecture.py`, `test_summary_builder.py`, `conftest.py`, `fixtures/` |
| `skills/bao-vault/` (new) | `bao_seed.py` | `test_bao_seed.py` |

### Shared Test Infrastructure

- `scripts/tests/conftest.py` and `scripts/tests/fixtures/` move to `skills/refresh-architecture/scripts/tests/` (largest consumer) and are referenced via conftest path configuration where needed by other skills
- `scripts/tests/__init__.py` is recreated in each skill's test directory

### What Changes

- **6 skill directories** created or updated with scripts as source of truth
- **`scripts/` deleted entirely** — including `.venv`, `.pytest_cache`, `__pycache__`
- **`skills/pyproject.toml`** — shared dependency manifest (tree-sitter, jsonschema, pyyaml, hvac)
- **21+ SKILL.md files** — path references updated to sibling-relative
- **CI workflow** — test paths updated from `scripts/tests/` to `skills/*/scripts/tests/`
- **CLAUDE.md** — worktree commands, Python environment section updated

## Risks

| Risk | Mitigation |
|------|-----------|
| Large number of file moves | Git tracks renames; atomic commit per work package |
| CI breakage | Update CI in same PR; test paths are straightforward |
| Shared test fixtures | conftest.py path configuration handles cross-skill test deps |
| Breaking developer muscle memory | CLAUDE.md updated; old paths produce clear "not found" errors |

## Success Criteria

1. `scripts/` directory no longer exists
2. All skills work when synced to a fresh repo with no `scripts/` directory
3. All existing tests pass from their new locations
4. CI is green
5. `install.sh` installs Python dependencies from `skills/pyproject.toml`
