# Proposal: Migrate Shared Scripts to Infrastructure Skills

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

Convert shared scripts into **infrastructure skills** — lightweight skill directories that bundle the scripts and are synced alongside SDLC skills by `install.sh`.

### Key Design Decisions

1. **Infrastructure skills** have a minimal `SKILL.md` that documents the script's API but are not user-invocable — they serve as dependency packages for other skills
2. **Sibling-relative paths** — consuming skills reference scripts via `<skill-base-dir>/../<infra-skill>/scripts/<script>.py` instead of `scripts/<script>.py`
3. **install.sh requires no changes** — it already syncs all directories under `skills/` that contain a `SKILL.md`
4. **Existing tests remain** in `scripts/tests/` and continue to run against `scripts/` during CI — the infrastructure skills contain copies synced by `install.sh`
5. **Grouping by domain** — related scripts are bundled together (e.g., `worktree.py` + `merge_worktrees.py` → `skills/worktree/`)

### Migration Plan

| Priority | New Skill | Bundled Scripts | Dependent Skills |
|----------|-----------|----------------|-----------------|
| P0 | `worktree` | `worktree.py`, `merge_worktrees.py` | 21 skills |
| P0 | `coordination-bridge` | `coordination_bridge.py` | 12 skills |
| P1 | `validate-packages` | `validate_work_packages.py`, `parallel_zones.py`, `validate_work_result.py` | 4 skills |
| P1 | `validate-flows` | `validate_flows.py` | 2 skills |
| P2 | `refresh-architecture` | _(already a skill — just bundle `refresh_architecture.sh`)_ | 1 skill |

### What Changes

- **New skill directories**: `skills/worktree/`, `skills/coordination-bridge/`, `skills/validate-packages/`, `skills/validate-flows/`
- **Updated SKILL.md in 21+ skills**: Path references change from `scripts/X.py` to sibling-relative `<skill-base-dir>/../worktree/scripts/X.py`
- **Updated sys.path imports**: `parallel-implement-feature/scripts/dag_scheduler.py` and `scope_checker.py` use sibling-relative imports
- **New documentation**: `docs/script-skill-dependencies.md` (dependency report with Mermaid graph)

### What Doesn't Change

- `scripts/` directory stays in the source repo — it's the development home and CI test target
- `install.sh` logic is unchanged
- Test suites remain in `scripts/tests/`
- Existing skill-local scripts (bug-scrub, fix-scrub, security-review, etc.) are unaffected

## Risks

| Risk | Mitigation |
|------|-----------|
| Path resolution complexity | Use `<skill-base-dir>` variable already available in SKILL.md prompts |
| Script duplication (source vs skill copy) | `install.sh --mode rsync` keeps copies in sync; CI tests against `scripts/` source |
| Breaking existing workflows | Backward-compatible — old paths still work in source repo; new paths work everywhere |
| Large number of SKILL.md edits | Well-scoped find-and-replace; each skill has at most 2-3 path references to update |

## Success Criteria

1. All skills work when synced to a fresh repo with no `scripts/` directory
2. `install.sh` syncs infrastructure skills alongside SDLC skills
3. CI tests continue to pass against `scripts/` source
4. No functional changes to skill behavior
