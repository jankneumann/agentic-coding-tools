# Design: Script-to-Skill Migration (Full Elimination)

## Architecture Overview

```
skills/
├── pyproject.toml               # Shared Python deps (moved from scripts/)
├── uv.lock                      # Lock file (moved from scripts/)
├── install.sh                   # Updated: --deps reads skills/pyproject.toml
│
├── worktree/                    # NEW infrastructure skill
│   ├── SKILL.md                 # API docs for worktree.py, merge_worktrees.py
│   └── scripts/
│       ├── worktree.py          # MOVED from scripts/worktree.py
│       ├── merge_worktrees.py   # MOVED from scripts/merge_worktrees.py
│       ├── git-parallel-setup.sh
│       └── tests/
│           ├── test_worktree.py
│           └── test_merge_worktrees.py
│
├── coordination-bridge/         # NEW infrastructure skill
│   ├── SKILL.md
│   └── scripts/
│       ├── coordination_bridge.py
│       └── tests/
│           └── test_coordination_bridge.py
│
├── validate-packages/           # NEW infrastructure skill
│   ├── SKILL.md
│   └── scripts/
│       ├── validate_work_packages.py
│       ├── parallel_zones.py
│       ├── validate_work_result.py
│       ├── validate_schema.py
│       ├── architecture_schema.json
│       └── tests/
│           ├── test_validate_work_packages.py
│           ├── test_parallel_zones_packages.py
│           └── test_validate_work_result.py
│
├── validate-flows/              # NEW infrastructure skill
│   ├── SKILL.md
│   └── scripts/
│       ├── validate_flows.py
│       └── tests/
│           └── test_flow_tracer.py
│
├── refresh-architecture/        # EXISTING skill — absorbs analysis scripts
│   ├── SKILL.md                 # Updated with full script inventory
│   └── scripts/
│       ├── analyze_python.py
│       ├── analyze_postgres.py
│       ├── analyze_sql_treesitter.py
│       ├── analyze_typescript.ts
│       ├── compile_architecture_graph.py
│       ├── diff_architecture.py
│       ├── enrich_with_treesitter.py
│       ├── generate_views.py
│       ├── run_architecture.py
│       ├── refresh_architecture.sh
│       ├── treesitter_queries/
│       │   ├── python.scm
│       │   ├── security.scm
│       │   └── typescript.scm
│       ├── insights/
│       │   ├── comment_linker.py
│       │   ├── cross_layer_linker.py
│       │   ├── db_linker.py
│       │   ├── flow_tracer.py
│       │   ├── flow_validator.py
│       │   ├── graph_builder.py
│       │   ├── impact_ranker.py
│       │   ├── parallel_zones.py
│       │   ├── pattern_reporter.py
│       │   └── summary_builder.py
│       ├── reports/
│       │   ├── architecture_report.py
│       │   └── config_schema.py
│       └── tests/
│           ├── conftest.py
│           ├── fixtures/
│           ├── test_analyze_sql_treesitter.py
│           ├── test_comment_linker.py
│           ├── test_cross_layer_linker.py
│           ├── test_enrich_with_treesitter.py
│           ├── test_flow_tracer.py
│           ├── test_graph_builder.py
│           ├── test_impact_ranker.py
│           ├── test_pattern_reporter.py
│           ├── test_pipeline_integration.py
│           ├── test_run_architecture.py
│           └── test_summary_builder.py
│
├── bao-vault/                   # NEW infrastructure skill
│   ├── SKILL.md
│   └── scripts/
│       ├── bao_seed.py
│       └── tests/
│           └── test_bao_seed.py
│
├── linear-plan-feature/         # UPDATED — path refs change
│   └── SKILL.md
├── parallel-implement-feature/  # UPDATED — path refs + sys.path imports
│   ├── SKILL.md
│   └── scripts/
│       ├── dag_scheduler.py     # sys.path updated
│       └── scope_checker.py     # sys.path updated
...
```

## Design Decisions

### D1: Single Source of Truth in Skills

Scripts are **moved** into skill directories, not copied. The skill directory is the canonical location. `scripts/` is deleted entirely.

**Why**: Eliminates duplication and the sync mechanism. One place to edit, one place to test, one place to deploy.

### D2: Infrastructure Skills Are Not User-Invocable

Infrastructure skills exist to be synced as dependencies. Their `SKILL.md` documents the script API but they don't appear in the user-invocable skill list.

```yaml
# skills/worktree/SKILL.md frontmatter
---
name: worktree
description: Worktree lifecycle management scripts (infrastructure dependency)
category: Infrastructure
tags: [worktree, git, infrastructure]
user_invocable: false
---
```

### D3: Sibling-Relative Path Resolution

Skills resolve infrastructure scripts relative to their own location:

```bash
# In any SKILL.md:
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "<change-id>"
```

This works everywhere — source repo, `.claude/skills/`, `.codex/skills/`, `.gemini/skills/`.

### D4: Shared pyproject.toml at skills/ Level

`scripts/pyproject.toml` and `scripts/uv.lock` move to `skills/`:

```
skills/
├── pyproject.toml    # Python deps for all infrastructure skills
├── uv.lock
```

`install.sh --deps apply` reads `skills/pyproject.toml` and creates a shared `.skills-venv` at the target location. Infrastructure scripts run against this venv.

**Why**: Keeps dependency declaration co-located with the skills that need them. No separate `scripts/` venv to manage.

### D5: Test Placement

Tests live alongside the scripts they test:

```
skills/<skill>/scripts/tests/test_<module>.py
```

**Shared fixtures**: `conftest.py` and `fixtures/` live in `skills/refresh-architecture/scripts/tests/` (the largest test suite). Other skills that need shared fixtures use pytest's `confdir` or `rootdir` configuration.

**CI update**: `.github/workflows/ci.yml` changes test paths:
```yaml
# Before:
run: scripts/.venv/bin/python -m pytest scripts/tests/

# After — run all infra skill tests:
run: |
  for skill in worktree coordination-bridge validate-packages validate-flows refresh-architecture bao-vault; do
    skills/.venv/bin/python -m pytest skills/$skill/scripts/tests/ || exit 1
  done
```

### D6: sys.path Resolution for Cross-Skill Imports

```python
# Before (in parallel-implement-feature/scripts/dag_scheduler.py):
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"

# After:
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "validate-packages" / "scripts"
```

### D7: Architecture Scripts Absorbed by refresh-architecture

The `refresh-architecture` skill already exists but only has a SKILL.md. It absorbs all architecture analysis scripts, the `insights/` module, `reports/` module, and `treesitter_queries/`.

This is natural — `refresh-architecture` is the user-invocable skill that runs the analysis pipeline, and all these scripts are its implementation.

### D8: bao-vault as New Infrastructure Skill

`bao_seed.py` moves to a new `skills/bao-vault/` skill. This skill manages OpenBao/Vault credential seeding and could later absorb other Vault-related tooling.

## Verification Strategy

### Unit Tests (Tier A)
- All moved tests pass from their new locations
- Infrastructure skill SKILL.md files validate with `openspec validate`
- `install.sh` correctly creates venv from `skills/pyproject.toml`

### Integration Tests (Tier B)
- End-to-end: sync skills to a temp directory, invoke a skill that depends on `worktree.py`
- CI pipeline runs green with updated test paths

### Regression (Tier C)
- `scripts/` directory does not exist
- No SKILL.md references `scripts/` as a repo-root path
