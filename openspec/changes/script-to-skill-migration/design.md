# Design: Script-to-Skill Migration

## Architecture Overview

```
skills/
├── worktree/                    # NEW infrastructure skill
│   ├── SKILL.md                 # Documents worktree.py + merge_worktrees.py API
│   └── scripts/
│       ├── worktree.py          # Copy of scripts/worktree.py
│       └── merge_worktrees.py   # Copy of scripts/merge_worktrees.py
├── coordination-bridge/         # NEW infrastructure skill
│   ├── SKILL.md
│   └── scripts/
│       └── coordination_bridge.py
├── validate-packages/           # NEW infrastructure skill
│   ├── SKILL.md
│   └── scripts/
│       ├── validate_work_packages.py
│       ├── parallel_zones.py
│       └── validate_work_result.py
├── validate-flows/              # NEW infrastructure skill
│   ├── SKILL.md
│   └── scripts/
│       └── validate_flows.py
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

### D1: Infrastructure Skills Are Not User-Invocable

Infrastructure skills exist to be synced as dependencies. Their `SKILL.md` documents the script API (arguments, outputs, exit codes) but they don't appear in the skill trigger list.

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

**Why**: These aren't workflows — they're utilities. Exposing them as invocable skills would clutter the skill list and confuse users expecting a multi-step workflow.

### D2: Sibling-Relative Path Resolution

Skills resolve infrastructure scripts using a path relative to their own `SKILL.md` location:

```bash
# In any SKILL.md that needs worktree.py:
# <skill-base-dir> is provided by the skill runner
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "<change-id>"
```

**Why**: This pattern:
- Works in the source repo (skills/ is siblings)
- Works when synced to `.claude/skills/` (sibling relationship preserved by install.sh)
- Works when synced to `.codex/skills/` or `.gemini/skills/`
- Requires no environment variables or configuration

**Alternative considered**: Environment variable `$SKILLS_ROOT` pointing to the skills directory. Rejected because it requires the skill runner to set it, adding coupling between install.sh and every agent runtime.

### D3: Source Scripts Remain in scripts/

The `scripts/` directory continues to exist as the development home:
- CI runs tests from `scripts/tests/`
- Developers can run scripts directly during development
- `install.sh` creates copies in infrastructure skills during sync

**Why**: Moving scripts entirely into skills would break CI, developer workflows, and the existing test infrastructure. The duplication is managed by `install.sh --mode rsync` which already handles this pattern for skill-local scripts.

### D4: Script Grouping by Domain

Related scripts are bundled into a single infrastructure skill:

| Infrastructure Skill | Scripts | Rationale |
|---------------------|---------|-----------|
| `worktree` | `worktree.py`, `merge_worktrees.py` | Both manage git worktree lifecycle |
| `coordination-bridge` | `coordination_bridge.py` | Single-purpose HTTP bridge |
| `validate-packages` | `validate_work_packages.py`, `parallel_zones.py`, `validate_work_result.py` | All validate parallel workflow artifacts |
| `validate-flows` | `validate_flows.py` | Architecture flow validation |

**Why**: Minimizes the number of new skill directories while keeping dependencies logically grouped. A skill that needs work-package validation also needs zone validation — they're always used together.

### D5: install.sh Enhancement — Script Source Sync

Add a step to `install.sh` that copies scripts from `scripts/` into infrastructure skill directories before syncing to agents:

```bash
# In install.sh, before the main sync loop:
# Sync source scripts into infrastructure skill directories
for infra_skill in worktree coordination-bridge validate-packages validate-flows; do
    if [ -d "skills/$infra_skill/scripts" ]; then
        rsync -a --delete scripts/${mapping[$infra_skill]}/ skills/$infra_skill/scripts/
    fi
done
```

**Why**: Ensures infrastructure skills always have the latest script versions without requiring developers to manually copy files. The sync happens at install time, not at skill execution time.

**Mapping**:
```bash
declare -A mapping=(
    [worktree]="worktree.py merge_worktrees.py"
    [coordination-bridge]="coordination_bridge.py"
    [validate-packages]="validate_work_packages.py parallel_zones.py validate_work_result.py"
    [validate-flows]="validate_flows.py"
)
```

### D6: sys.path Resolution for Cross-Skill Imports

For Python scripts that import from other scripts (e.g., `dag_scheduler.py` imports from `validate_work_packages.py`), update the path resolution:

```python
# Before (in parallel-implement-feature/scripts/dag_scheduler.py):
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"

# After:
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "validate-packages" / "scripts"
```

**Why**: Follows the same sibling-relative pattern as SKILL.md path references. When synced, `validate-packages/scripts/` is a sibling of `parallel-implement-feature/scripts/`.

## Verification Strategy

### Unit Tests (Tier A)
- Infrastructure skill SKILL.md files validate with `openspec validate`
- Path resolution works from both source repo and synced location
- `install.sh` correctly syncs infrastructure skills

### Integration Tests (Tier B)
- End-to-end: sync skills to a temp directory, invoke a skill that depends on `worktree.py`
- Verify all 21 worktree-dependent skills can resolve the script

### Regression (Tier C)
- Existing `scripts/tests/` continue to pass
- CI pipeline unchanged
