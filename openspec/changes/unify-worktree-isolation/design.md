# Design: Unify Worktree Isolation for Parallel Agents

## Architecture Decision: Two-Layer Isolation

### Decision

Use our `scripts/worktree.py` as the coordination layer (registry, lifecycle, merge) and vendor agent isolation as an optional safety layer. The orchestrator always calls `worktree.py setup` before dispatching agents.

### Rationale

Our worktree system provides capabilities no vendor isolation can:
- **Registry**: Who owns which worktree, when it was created, last heartbeat
- **Named branches**: Deterministic `openspec/<change-id>/<package-id>` naming for merge
- **Bootstrap**: `uv sync`, `.env` copy, skills sync — environment-ready worktrees
- **GC**: Automatic cleanup with pin/heartbeat protection
- **Cross-vendor**: Works the same regardless of agent vendor

Vendor isolation (when available) provides defense-in-depth — even if an agent ignores the `cd` instruction, it can't corrupt the main checkout.

## Key Design Changes

### 1. Orchestrator Worktree Lifecycle

The orchestrator (running `/parallel-implement-feature`) manages worktree lifecycle:

```
BEFORE dispatch:
  worktree.py setup <change-id> --agent-id <package-id> --no-bootstrap
  # --no-bootstrap for speed; agent does its own env setup in worktree

DURING execution:
  Agent heartbeats via worktree.py heartbeat
  Orchestrator monitors via worktree.py status

AFTER completion:
  Integration agent merges branches
  worktree.py teardown <change-id> --agent-id <package-id>
```

### 2. Agent Dispatch Protocol

The orchestrator builds a dispatch prompt for each agent that includes:

```
WORKTREE_PATH=/abs/path/to/.git-worktrees/<change-id>/<package-id>
BRANCH=openspec/<change-id>/<package-id>
CHANGE_ID=<change-id>
PACKAGE_ID=<package-id>
```

**For Claude Code (local)**: Use `Agent(prompt=..., isolation="worktree")` — the agent gets a vendor-managed worktree, but we also have our registered worktree as the merge source. The agent's prompt tells it to work on the our worktree's branch.

**For vendors without isolation**: Agent prompt starts with `cd $WORKTREE_PATH` and all subsequent work happens there.

### 3. Shared Checkout is Read-Only (Launcher Invariant)

The shared checkout is **never modified** by any orchestrator or agent. It serves only as a launcher — a place to invoke skills and read configuration. This prevents conflicts when multiple orchestrators run from the same checkout in different terminals.

Every package — including root packages — gets its own worktree:

```
main ──── openspec/<change-id> (feature branch, created but not checked out in shared dir)
              ├── openspec/<change-id>/wp-contracts (root, in own worktree)
              ├── openspec/<change-id>/wp-backend (parallel, in own worktree)
              ├── openspec/<change-id>/wp-frontend (parallel, in own worktree)
              └── openspec/<change-id>/wp-tests (parallel, in own worktree)
```

### 4. Root-First, Parallel-Second Pattern

Root packages (no dependencies) are implemented **sequentially in their own worktrees**, then merged into the feature branch before parallel packages begin. This ensures:
- Parallel agents can read root package outputs (new modules, contracts) via the feature branch
- Multiple orchestrators on the same checkout don't conflict
- Feature branch has a stable base for parallel branches

```
Phase 1 (sequential):
  worktree.py setup <change-id> --agent-id wp-contracts
  → implement in worktree → commit → merge into feature branch → teardown

Phase 2 (parallel):
  worktree.py setup <change-id> --agent-id wp-backend
  worktree.py setup <change-id> --agent-id wp-frontend
  → dispatch agents → wait for completion

Phase 3 (integration):
  worktree.py setup <change-id> --agent-id integrator
  → merge all branches → verify → teardown all
```

### 5. Integration Merge Strategy

After all parallel packages complete:

```bash
# Integrator works on the feature branch
git checkout openspec/<change-id>

# Merge each package branch
for pkg in wp-backend wp-frontend wp-tests; do
  git merge --no-ff openspec/<change-id>/$pkg \
    -m "merge: $pkg into feature branch"
done

# Run full test suite
pytest tests/ -m "not e2e and not integration"
mypy --strict src/
ruff check src/
```

Conflicts during merge indicate scope overlap violations — these should have been caught by `parallel_zones.py --validate-packages`.

### 6. Skill Prompt Updates (All Skills in `skills/`)

The launcher invariant applies to every skill that modifies the checkout. Source files live in `skills/`, not `.claude/skills/`.

#### 6a. `skills/parallel-plan-feature/SKILL.md`

Planning creates artifacts and registers resource claims. Currently works on the shared checkout.

**Change**: Use a feature-level worktree for the entire planning session.

```
Step 1 (new): Setup planning worktree
    - worktree.py setup <change-id>
    - cd into worktree
    - All subsequent steps (context gathering, artifact creation, openspec new change)
      happen inside the worktree

Step 8 (updated): Commit and push
    - Commit planning artifacts on branch openspec/<change-id>
    - Push branch
    - Pin worktree (reused by /parallel-implement-feature)
```

The worktree persists after planning — implementation reuses it or creates sub-worktrees from it.

#### 6b. `skills/linear-plan-feature/SKILL.md`

Same change as 6a. Single-agent planning also uses a feature-level worktree.

```
Step 1 (new): Setup planning worktree
    - worktree.py setup <change-id>
    - cd into worktree
    - Pin worktree (reused by /linear-implement-feature)
```

#### 6c. `skills/parallel-implement-feature/SKILL.md`

**Phase A (Preflight)** — add steps A3.5–A3.7:
```
A3.5. Create feature branch (from shared checkout, no checkout)
    - git branch openspec/<change-id> main (if not exists)
    - OR: reuse branch from planning phase

A3.6. Implement root packages (sequentially, each in own worktree)
    - For each root package (depends_on == []):
      - worktree.py setup <change-id> --agent-id <package-id>
      - Implement in worktree
      - Commit + push root branch
      - Merge root branch into feature branch (git merge --no-ff)
      - worktree.py teardown <change-id> --agent-id <package-id>

A3.7. Setup worktrees for parallel packages
    - For each non-root package: worktree.py setup <change-id> --agent-id <package-id>
    - Worktrees branch from feature branch (includes root package work)
    - Record worktree paths in dispatch context
    - Pin all worktrees (prevent GC during execution)
```

**Phase B (Worker)** — update B1:
```
B1. Verify worktree
    - Agent confirms it is running in the correct worktree path
    - OR: cd into worktree path if not already there
```

**Phase C (Integration)** — update C5:
```
C5. Integration merge
    - Setup integrator worktree
    - Checkout feature branch
    - Merge each package branch with --no-ff
    - Resolve any conflicts (should be none with proper scope enforcement)
    - Run full verification suite
    - Push feature branch
```

**Teardown** — add step:
```
Teardown. Cleanup worktrees
    - Unpin all worktrees
    - worktree.py teardown for each package + integrator
    - worktree.py gc (optional, for stale cleanup)
```

#### 6d. `skills/linear-implement-feature/SKILL.md`

Already uses a single worktree — **no change needed**. This skill is already compliant with the launcher invariant.

#### 6e. `skills/parallel-cleanup-feature/SKILL.md`

Cleanup performs merge, archive, and branch deletion. Currently operates on the shared checkout.

**Change**: Use a worktree for merge/archive operations.

```
Step 1 (new): Setup cleanup worktree
    - worktree.py setup <change-id> --agent-id cleanup
    - cd into worktree

Step 3–8 (updated): All merge, archive, and branch operations
    happen inside the cleanup worktree

Step 12 (updated): Teardown
    - worktree.py teardown <change-id> --agent-id cleanup
    - worktree.py gc (cleanup stale worktrees from implementation)
```

#### 6f. `skills/linear-cleanup-feature/SKILL.md`

Same pattern as 6e — use a worktree for merge/archive.

#### 6g. Read-only skills — NO CHANGES

These skills never modify the checkout and don't need worktrees:
- `skills/parallel-explore-feature/` — read-only codebase analysis
- `skills/linear-explore-feature/` — read-only codebase analysis
- `skills/parallel-review-plan/` — read-only plan review
- `skills/parallel-review-implementation/` — read-only code review
- `skills/parallel-validate-feature/` — read-only evidence audit
- `skills/linear-validate-feature/` — read-only verification (uses `worktree.py detect` already)

### 7. `work-packages.yaml` Schema — No Changes Needed

The existing `worktree` field already captures what's needed:

```yaml
worktree:
  name: add-otel-observability.wp-lock-metrics  # Used as agent-id
  mode: isolated
```

The orchestrator maps `worktree.name` → `--agent-id` when calling `worktree.py setup`.

## Alternatives Considered

### 1. Rely solely on vendor `isolation: "worktree"`

**Rejected**: Vendor-specific, no registry, no merge coordination, no heartbeat/GC, no bootstrap. Claude Code's worktree is opaque — we can't predict the branch name or path.

### 2. Rely solely on our worktree system + `cd`

**Rejected for Claude Code**: The Agent tool's prompt can say `cd /path` but there's no guarantee the agent respects it. `isolation: "worktree"` enforces isolation at the tool level.

### 3. Replace worktree.py with vendor isolation entirely

**Rejected**: Loses cross-vendor compatibility, registry, lifecycle management, and merge coordination. Different vendors have different isolation models (or none).

### 4. Implement root packages directly on shared checkout

**Rejected**: Breaks when multiple orchestrators run from the same checkout (e.g., two terminals working on different features). Only one `git checkout` can be active at a time, so orchestrators would race on the shared directory. The launcher-invariant (shared checkout is read-only) eliminates this entire class of conflicts.

## Risks

| Risk | Mitigation |
|------|------------|
| Bootstrap adds latency per worktree (now includes root packages) | Use `--no-bootstrap` for parallel packages; agent does `uv sync` lazily. Root packages bootstrap once. |
| Multiple orchestrators create overlapping feature branches | Feature branch names include change-id, which is unique per feature |
| Disk space from many worktrees | GC with 24h threshold; teardown after integration |
| Merge conflicts in integration | Scope validation in preflight (already exists); fail fast on conflict |
| Agent ignores worktree path | `isolation: "worktree"` as safety net for Claude Code; scope check in B7 catches drift |
| `worktree.py setup` fails | Retry once; fall back to direct implementation with warning |
