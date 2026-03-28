# Spec: Skill Consolidation

## Capability: Tiered Execution

### TIER-1: Tier detection
The unified skill SHALL detect the execution tier at startup by running `check_coordinator.py --json` and analyzing feature complexity. Tier detection logic SHALL differ per skill phase (plan-feature uses scope analysis; implement-feature checks for existing work-packages.yaml).

### TIER-2: Coordinated tier
When coordinator is available with all required capabilities, the skill SHALL execute in coordinated mode with full coordinator integration.

### TIER-3: Local parallel tier
When coordinator is unavailable but the feature has work-packages.yaml or sufficient complexity (2+ architectural boundaries for planning, 3+ independent tasks for implementation), the skill SHALL execute in local-parallel mode using built-in Agent tool parallelism.

### TIER-4: Sequential tier
When neither coordinator nor work-packages are available and the feature is simple, the skill SHALL execute sequentially.

### TIER-5: Artifact preservation
When operating in local-parallel tier, the skill SHALL generate the same planning artifacts as the coordinated tier (contracts, work-packages.yaml) except for coordinator-dependent registration steps.

### TIER-6: Tier notification
The unified skill SHALL emit a tier notification at startup indicating which tier was selected and why (e.g., "Tier: local-parallel — coordinator unavailable, generating contracts and work-packages for local DAG execution").

### TIER-7: Tier override via trigger
If the user invoked the skill via a parallel-prefixed trigger phrase (e.g., "parallel plan feature"), the skill SHALL select at least the local-parallel tier regardless of complexity analysis.

## Capability: Skill Directory Cleanup

### CLEAN-1: Deprecated skill removal
`install.sh` SHALL remove deprecated skill directories from agent config directories before installing current skills.

### CLEAN-2: User skill preservation
`install.sh` SHALL NOT remove directories that do not contain a `SKILL.md` file (indicating they are not managed by the installer).

### CLEAN-3: Deprecated list maintenance
`install.sh` SHALL maintain a `DEPRECATED_SKILLS` array listing skill names that have been superseded.

## Capability: Trigger Consolidation

### TRIG-1: Backward compatibility
Each unified skill SHALL accept all trigger phrases from its former linear and parallel counterparts.

### TRIG-2: Canonical naming
The base skill names (without prefix) SHALL be the canonical names used in documentation and cross-references.

## Capability: Local Parallel Execution

### LPAR-1: DAG parsing
The implement-feature skill SHALL parse work-packages.yaml and compute topological execution order when operating in local-parallel tier.

### LPAR-2: Agent dispatch
Independent packages SHALL be dispatched as concurrent Agent calls with `run_in_background=true`, each receiving a context slice.

### LPAR-3: Scope enforcement
Each dispatched agent prompt SHALL include the package's `write_allow`, `read_allow`, and `deny` globs to enforce scope boundaries.

### LPAR-4: Per-package verification
Each package SHALL run its declared verification steps before being considered complete.

### LPAR-5: Single worktree
Local-parallel tier SHALL use a single feature worktree with prompt-based scope constraints. Per-package worktrees are coordinated-tier only.

## Capability: Infrastructure Script Relocation

### INFRA-1: Coordination bridge expansion
`coordination-bridge` SHALL gain `check_coordinator.py` as the single canonical coordinator detection script.

### INFRA-2: Parallel infrastructure skill
A new `parallel-infrastructure` non-user-invocable skill SHALL house all parallel execution scripts (DAG scheduler, review dispatcher, consensus synthesizer, scope checker, etc.).

### INFRA-3: Import path migration
All skills that import from `parallel-implement-feature/scripts/` (auto-dev-loop, fix-scrub, merge-pull-requests) SHALL update their import paths to reference `parallel-infrastructure/scripts/`.

## Capability: Downstream Skill Updates

### DOWN-1: auto-dev-loop update
`auto-dev-loop` SHALL replace all `/parallel-*` and `/linear-*` skill invocations with unified skill names and update script import paths.

### DOWN-2: fix-scrub update
`fix-scrub` SHALL update import paths from `parallel-implement-feature/scripts/` to `parallel-infrastructure/scripts/`.

### DOWN-3: merge-pull-requests update
`merge-pull-requests` SHALL update import paths from `parallel-implement-feature/scripts/` to `parallel-infrastructure/scripts/`.
