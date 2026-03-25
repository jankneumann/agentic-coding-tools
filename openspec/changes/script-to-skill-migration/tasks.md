# Tasks: script-to-skill-migration

## T1: Create Infrastructure Skills and Move Scripts (P0)

### T1.1: Create `skills/worktree/` and move scripts
- [ ] Create `skills/worktree/SKILL.md` (user_invocable: false, API docs)
- [ ] Create `skills/worktree/scripts/`
- [ ] Move `scripts/worktree.py` → `skills/worktree/scripts/worktree.py`
- [ ] Move `scripts/merge_worktrees.py` → `skills/worktree/scripts/merge_worktrees.py`
- [ ] Move `scripts/git-parallel-setup.sh` → `skills/worktree/scripts/git-parallel-setup.sh`
- [ ] Move `scripts/tests/test_worktree.py` → `skills/worktree/scripts/tests/test_worktree.py`
- [ ] Move `scripts/tests/test_merge_worktrees.py` → `skills/worktree/scripts/tests/test_merge_worktrees.py`
- [ ] Verify tests pass from new location

### T1.2: Create `skills/coordination-bridge/` and move scripts
- [ ] Create `skills/coordination-bridge/SKILL.md` (user_invocable: false)
- [ ] Move `scripts/coordination_bridge.py` → `skills/coordination-bridge/scripts/coordination_bridge.py`
- [ ] Move `scripts/tests/test_coordination_bridge.py` → `skills/coordination-bridge/scripts/tests/test_coordination_bridge.py`
- [ ] Verify tests pass

### T1.3: Create `skills/validate-packages/` and move scripts
- [ ] Create `skills/validate-packages/SKILL.md` (user_invocable: false)
- [ ] Move `scripts/validate_work_packages.py` → `skills/validate-packages/scripts/`
- [ ] Move `scripts/parallel_zones.py` → `skills/validate-packages/scripts/`
- [ ] Move `scripts/validate_work_result.py` → `skills/validate-packages/scripts/`
- [ ] Move `scripts/validate_schema.py` → `skills/validate-packages/scripts/`
- [ ] Move `scripts/architecture_schema.json` → `skills/validate-packages/scripts/`
- [ ] Move relevant tests
- [ ] Verify tests pass

### T1.4: Create `skills/validate-flows/` and move scripts
- [ ] Create `skills/validate-flows/SKILL.md` (user_invocable: false)
- [ ] Move `scripts/validate_flows.py` → `skills/validate-flows/scripts/validate_flows.py`
- [ ] Move `scripts/tests/test_flow_tracer.py` → `skills/validate-flows/scripts/tests/`
- [ ] Verify tests pass

### T1.5: Move architecture scripts to `skills/refresh-architecture/`
- [ ] Create `skills/refresh-architecture/scripts/` (skill already exists)
- [ ] Move `scripts/analyze_python.py`, `analyze_postgres.py`, `analyze_sql_treesitter.py`, `analyze_typescript.ts`
- [ ] Move `scripts/compile_architecture_graph.py`, `diff_architecture.py`, `enrich_with_treesitter.py`
- [ ] Move `scripts/generate_views.py`, `run_architecture.py`, `refresh_architecture.sh`
- [ ] Move `scripts/treesitter_queries/` → `skills/refresh-architecture/scripts/treesitter_queries/`
- [ ] Move `scripts/insights/` → `skills/refresh-architecture/scripts/insights/`
- [ ] Move `scripts/reports/` → `skills/refresh-architecture/scripts/reports/`
- [ ] Move all architecture tests + `conftest.py` + `fixtures/`
- [ ] Update internal imports if needed (insights/ modules reference each other)
- [ ] Update `skills/refresh-architecture/SKILL.md` with full script inventory
- [ ] Verify tests pass

### T1.6: Create `skills/bao-vault/` and move scripts
- [ ] Create `skills/bao-vault/SKILL.md` (user_invocable: false)
- [ ] Move `scripts/bao_seed.py` → `skills/bao-vault/scripts/bao_seed.py`
- [ ] Move `scripts/tests/test_bao_seed.py` → `skills/bao-vault/scripts/tests/`
- [ ] Verify tests pass

### T1.7: Move pyproject.toml and uv.lock
- [ ] Move `scripts/pyproject.toml` → `skills/pyproject.toml`
- [ ] Move `scripts/uv.lock` → `skills/uv.lock`
- [ ] Update pytest paths in pyproject.toml
- [ ] Create venv at `skills/.venv` and verify all deps install

### T1.8: Delete scripts/ directory
- [ ] Verify no remaining references to `scripts/` in any skill
- [ ] Remove `scripts/` directory entirely (including `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`)

## T2: Update SKILL.md Path References (P0)

### T2.1: Update worktree path references (21 skills)
- [ ] All skills referencing `scripts/worktree.py` → `<skill-base-dir>/../worktree/scripts/worktree.py`
- [ ] All skills referencing `scripts/merge_worktrees.py` → `<skill-base-dir>/../worktree/scripts/merge_worktrees.py`

### T2.2: Update coordination_bridge path references (12 skills)
- [ ] All skills referencing `scripts/coordination_bridge.py` → `<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py`

### T2.3: Update validation script path references (4 skills)
- [ ] `scripts/validate_work_packages.py` → `<skill-base-dir>/../validate-packages/scripts/validate_work_packages.py`
- [ ] `scripts/parallel_zones.py` → `<skill-base-dir>/../validate-packages/scripts/parallel_zones.py`
- [ ] `scripts/validate_work_result.py` → `<skill-base-dir>/../validate-packages/scripts/validate_work_result.py`

### T2.4: Update validate_flows path references (2 skills)
- [ ] `scripts/validate_flows.py` → `<skill-base-dir>/../validate-flows/scripts/validate_flows.py`

### T2.5: Update refresh_architecture references (1 skill)
- [ ] `scripts/refresh_architecture.sh` → `<skill-base-dir>/scripts/refresh_architecture.sh` (already in same skill)

## T3: Update Python sys.path Imports (P1)

### T3.1: Update parallel-implement-feature/scripts/dag_scheduler.py
- [ ] `_SCRIPTS_DIR` → `parent.parent.parent / "validate-packages" / "scripts"`

### T3.2: Update parallel-implement-feature/scripts/scope_checker.py
- [ ] Same sibling-relative path update

### T3.3: Update insights/ internal imports
- [ ] Verify `insights/*.py` modules can find each other from new location
- [ ] Update any `sys.path` or relative import adjustments

## T4: Update install.sh (P1)

### T4.1: Add skills/pyproject.toml dependency support
- [ ] `--deps apply` reads `skills/pyproject.toml` and creates `skills/.venv` (or `.skills-venv` at target)
- [ ] Remove any references to `scripts/` venv

## T5: Update CI and Documentation (P1)

### T5.1: Update CI workflow
- [ ] `.github/workflows/ci.yml` — test paths from `scripts/tests/` to `skills/*/scripts/tests/`
- [ ] Verify CI runs green

### T5.2: Update CLAUDE.md
- [ ] Remove `scripts` Python environment section
- [ ] Add `skills` Python environment section
- [ ] Update worktree commands to use skill-relative paths
- [ ] Update documentation references

### T5.3: Update other docs
- [ ] `docs/script-skill-dependencies.md` — mark as completed migration
- [ ] `docs/skills-workflow.md` — add infrastructure skill section
- [ ] `docs/architecture-artifacts.md` — update refresh commands
- [ ] `docs/lessons-learned.md` — update cross-skill Python patterns
