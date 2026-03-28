# Spec: Skill Consolidation

## Capability: Tiered Execution

### TIER-1: Tier detection
The unified skill SHALL detect the execution tier at startup by running `check_coordinator.py --json` and analyzing feature complexity.

### TIER-2: Coordinated tier
When coordinator is available with all required capabilities, the skill SHALL execute in coordinated mode with full coordinator integration.

### TIER-3: Local parallel tier
When coordinator is unavailable but the feature has work-packages.yaml or 3+ independent tasks, the skill SHALL execute in local-parallel mode using built-in Agent tool parallelism.

### TIER-4: Sequential tier
When neither coordinator nor work-packages are available and the feature is simple, the skill SHALL execute sequentially.

### TIER-5: Artifact preservation
When operating in local-parallel tier, the skill SHALL generate the same planning artifacts as the coordinated tier (contracts, work-packages.yaml) except for coordinator-dependent registration steps.

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
