# Skill Consolidation Spec Delta: unify-skill-tiers

## ADDED Requirements

### Requirement: Tier detection
The unified skill SHALL detect the execution tier at startup by running `check_coordinator.py --json` and analyzing feature complexity.
- Tier detection logic SHALL differ per skill phase (plan-feature uses scope analysis; implement-feature checks for existing work-packages.yaml)

#### Scenario: Tier detection selects coordinated mode when coordinator is available
- **WHEN** the coordinator is running and reachable
- **THEN** the unified skill SHALL select coordinated tier

#### Scenario: Tier detection selects local-parallel when coordinator is unavailable
- **WHEN** the coordinator is not reachable
- **AND** the feature has work-packages.yaml or crosses 2+ architectural boundaries
- **THEN** the unified skill SHALL select local-parallel tier

#### Scenario: Tier detection selects sequential for simple features
- **WHEN** the coordinator is unavailable
- **AND** the feature has no work-packages.yaml and crosses fewer than 2 architectural boundaries
- **THEN** the unified skill SHALL execute sequentially

---

### Requirement: Coordinated tier execution
When coordinator is available with all required capabilities, the skill SHALL execute in coordinated mode with full coordinator integration.

#### Scenario: Coordinated tier uses full coordinator integration
- **WHEN** the coordinator is available with all required capabilities
- **THEN** the skill SHALL use full coordinator integration for locks, work queue, and handoffs

---

### Requirement: Local parallel tier execution
When coordinator is unavailable but complexity is sufficient, the skill SHALL execute in local-parallel mode using built-in Agent tool parallelism.

#### Scenario: Local parallel tier dispatches concurrent agents
- **WHEN** the coordinator is unavailable
- **AND** the feature has work-packages.yaml with 3+ independent tasks
- **THEN** the skill SHALL dispatch concurrent Agent calls with `run_in_background=true`

---

### Requirement: Artifact preservation in local-parallel
When operating in local-parallel tier, the skill SHALL generate the same planning artifacts as the coordinated tier except for coordinator-dependent registration steps.

#### Scenario: Local-parallel tier generates contracts and work-packages
- **WHEN** the skill is operating in local-parallel tier
- **AND** it completes planning
- **THEN** it SHALL produce contracts and work-packages.yaml matching coordinated tier output

---

### Requirement: Tier notification
The unified skill SHALL emit a tier notification at startup indicating which tier was selected and why.

#### Scenario: Tier notification is emitted at startup
- **WHEN** the skill starts and selects a tier
- **THEN** it SHALL emit a notification indicating the tier name and reason for selection

---

### Requirement: Tier override via trigger
If the user invoked the skill via a parallel-prefixed trigger phrase, the skill SHALL select at least the local-parallel tier regardless of complexity analysis.

#### Scenario: Parallel prefix forces local-parallel tier minimum
- **WHEN** the user invokes with a parallel-prefixed trigger phrase
- **AND** the feature complexity would otherwise select sequential tier
- **THEN** the skill SHALL select at least the local-parallel tier

---

### Requirement: Deprecated skill removal
`install.sh` SHALL remove deprecated skill directories from agent config directories before installing current skills.
- `install.sh` SHALL NOT remove directories that do not contain a `SKILL.md` file
- `install.sh` SHALL maintain a `DEPRECATED_SKILLS` array listing skill names that have been superseded

#### Scenario: Deprecated skills are removed during install
- **WHEN** deprecated skills exist in an agent config directory
- **AND** `install.sh` runs
- **THEN** it SHALL remove those deprecated skill directories

#### Scenario: Non-managed directories are preserved
- **WHEN** a directory in the agent config does not contain a `SKILL.md` file
- **THEN** `install.sh` SHALL NOT remove that directory

---

### Requirement: Trigger backward compatibility
Each unified skill SHALL accept all trigger phrases from its former linear and parallel counterparts.
- The base skill names (without prefix) SHALL be the canonical names used in documentation and cross-references

#### Scenario: Linear and parallel trigger phrases are accepted
- **WHEN** a user invokes a skill with a linear-prefixed or parallel-prefixed name
- **THEN** the unified skill SHALL handle the invocation

---

### Requirement: Local parallel DAG execution
The implement-feature skill SHALL parse work-packages.yaml and compute topological execution order when operating in local-parallel tier.
- Independent packages SHALL be dispatched as concurrent Agent calls with `run_in_background=true`
- Each dispatched agent prompt SHALL include the package's `write_allow`, `read_allow`, and `deny` globs
- Each package SHALL run its declared verification steps before being considered complete
- Local-parallel tier SHALL use a single feature worktree with prompt-based scope constraints

#### Scenario: DAG is computed and packages dispatched concurrently
- **WHEN** the implement-feature skill operates in local-parallel tier
- **AND** work-packages.yaml has packages with no dependency between them
- **THEN** those packages SHALL be launched concurrently with scope constraints in their prompts

#### Scenario: Per-package verification runs before completion
- **WHEN** a package agent finishes implementation
- **THEN** it SHALL run declared verification steps and only report complete if they pass

---

### Requirement: Infrastructure script relocation
A new `parallel-infrastructure` non-user-invocable skill SHALL house all parallel execution scripts.
- `coordination-bridge` SHALL gain `check_coordinator.py` as the single canonical coordinator detection script
- All skills that import from `parallel-implement-feature/scripts/` SHALL update their import paths to reference `parallel-infrastructure/scripts/`

#### Scenario: parallel-infrastructure contains execution scripts
- **WHEN** the parallel-infrastructure skill directory is inspected
- **THEN** it SHALL contain dag_scheduler.py, review_dispatcher.py, consensus_synthesizer.py, and scope_checker.py

#### Scenario: Import paths reference parallel-infrastructure
- **WHEN** a skill previously imported from parallel-implement-feature/scripts/
- **THEN** its import paths SHALL reference parallel-infrastructure/scripts/

---

### Requirement: Downstream skill updates
Skills that depend on relocated scripts SHALL be updated.
- `auto-dev-loop` SHALL replace all `/parallel-*` and `/linear-*` skill invocations with unified skill names
- `fix-scrub` SHALL update import paths to `parallel-infrastructure/scripts/`
- `merge-pull-requests` SHALL update import paths to `parallel-infrastructure/scripts/`

#### Scenario: Downstream skills use updated paths
- **WHEN** auto-dev-loop, fix-scrub, or merge-pull-requests invoke parallel scripts
- **THEN** they SHALL reference parallel-infrastructure/scripts/
