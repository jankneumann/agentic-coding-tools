# Deep Exploration: Parallel Agent Workflow Infrastructure

## Executive Summary

This codebase implements a sophisticated **two-level parallel agentic development system** with git worktree isolation, coordinator-managed resource locking, and DAG-scheduled multi-agent execution. The system enables **cross-feature parallelism** (multiple features merging concurrently) and **intra-feature parallelism** (work packages executing in parallel within a feature), while maintaining safety through resource claim analysis and conflict detection.

---

## 1. Git Worktree Management Infrastructure

### 1.1 Worktree Lifecycle: `skills/worktree/scripts/worktree.py`

**Location:** `/Users/jankneumann/Coding/agentic-coding-tools/skills/worktree/scripts/worktree.py`

**Purpose:** Manages the complete lifecycle of git worktrees for isolated parallel feature development.

**Key Capabilities:**

- **`cmd_setup`** — Creates isolated worktrees at `.git-worktrees/<change-id>/`
  - Resolves main repo even when called from within a worktree
  - Creates git branch (default: `openspec/<change-id>`)
  - Outputs KEY=VALUE pairs for shell eval (WORKTREE_PATH, BRANCH_CREATED, etc.)
  - Supports optional `--prefix` for task-level organization

- **`cmd_teardown`** — Removes worktrees (backward compatible with legacy paths)
  - Checks both new (`.git-worktrees/`) and legacy (`../<repo>.worktrees/`) locations
  - Must run from main repo to remove worktree

- **`cmd_status`** — Lists active worktrees or checks specific change-id
  - Detects location (new vs legacy)
  - Integration with `git worktree list`

- **`cmd_detect`** — Outputs context variables for skill execution
  - `IN_WORKTREE={true|false}`
  - `MAIN_REPO=<path>`
  - `OPENSPEC_PATH=<path>` (openspec/ in main repo or main repo for worktrees)

**Key Design Decision:**
```
Worktree Location Strategy:
  New (preferred):  .git-worktrees/<change-id>/
  Legacy:          ../<repo>.worktrees/<change-id>/
  
Both are gitignored. New location keeps worktrees inside project boundary.
```

**Pain Points & Gaps:**

1. **Symlink Timing Issue** — Memory note warns against creating symlinks to `~/.claude/skills/` during worktree execution because:
   - The symlink targets the main repo path
   - File only exists in the worktree during implementation
   - Symlink breaks until PR merges
   - **Solution:** Create symlinks during `/cleanup-feature` instead

2. **Worktree Cleanup Race** — No built-in garbage collection for stale worktrees
   - Relies on skill explicitly calling teardown
   - Orphaned worktrees can accumulate if skills fail
   - No timeout-based automatic cleanup

3. **Branch Rebase Semantics Confusion** — Documented in CLAUDE.md:
   - During `git rebase`, `--ours` = branch being rebased ONTO (upstream)
   - `--theirs` = commit being replayed
   - This is **opposite** of `git merge` semantics
   - Easy source of manual conflict resolution errors

---

## 2. Merge Queue & Ordered Merging

### 2.1 Merge Queue Service: `agent-coordinator/src/merge_queue.py`

**Location:** `/Users/jankneumann/Coding/agentic-coding-tools/agent-coordinator/src/merge_queue.py`

**Purpose:** Coordinates ordered merging of multiple parallel features to avoid conflicts and ensure deterministic merge order.

**Merge Queue States:**
```
QUEUED → PRE_MERGE_CHECK → READY → MERGING → MERGED
                              ↓
                          BLOCKED (if checks fail)
```

**Key Methods:**

- **`enqueue(feature_id, pr_url)`** — Registers feature in merge queue
  - Sets initial status = QUEUED
  - Stores `queued_at` timestamp
  - Metadata stored in `feature_registry.metadata['merge_queue']` (JSONB)

- **`run_pre_merge_checks(feature_id)`** — Re-validates before merging
  - Check 1: Feature still active in registry
  - Check 2: **No new resource conflicts** with other active features
  - Check 3: Feature is properly queued
  - Updates status to READY or BLOCKED
  - Returns detailed PreMergeCheckResult with conflict details

- **`get_next_to_merge()`** — Returns highest-priority READY feature
  - Ordered by `feature_registry.merge_priority` (1=highest)
  - Then by `registered_at` (FIFO tiebreaker)

- **`mark_merged(feature_id)`** — Post-merge lifecycle
  - Deregisters feature from registry (status='completed')
  - Frees resource claims for waiting features
  - Removes from merge queue

- **`remove_from_queue(feature_id)`** — Removes without merging
  - Clears merge_queue metadata
  - Keeps feature active

**Critical Design Pattern:**
```python
# Merge queue is a LOGICAL LAYER on top of feature_registry
# No separate table; uses feature_registry.metadata JSONB field
# Avoids adding database schema complexity

METADATA_KEY = "merge_queue"
merge_meta = {
    "status": "queued" | "pre_merge_check" | "ready" | "blocked",
    "pr_url": str,
    "queued_at": ISO datetime,
    "checked_at": ISO datetime,
    "merged_at": ISO datetime
}
```

**Pain Points & Gaps:**

1. **Pre-Merge Check Timing** — Re-validates at merge time, but:
   - Window exists between check and actual merge
   - If another feature merges in between, conflicts possible
   - Mitigated by GitHub branch protection rules, but not guaranteed atomically

2. **Merge Priority Not Dynamic** — Priority set at registration, never changes
   - Can't reprioritize based on dependency changes
   - Features waiting on earlier features can't bump priority

3. **No Rollback Mechanism** — If merge fails after mark_merged():
   - Feature already deregistered
   - Resource claims freed
   - No way to revert and re-queue
   - Must manual recovery

4. **Conflict Detection Limited to Resource Claims** — Pre-merge checks validate:
   - Resource overlaps (from feature registry locks)
   - **Does NOT validate:** semantic conflicts in non-overlapping files
   - Mitigated by scope-aware work packages and wp-integration, but not enforced by merge queue

---

## 3. Feature Registry & Parallel Feasibility Analysis

### 3.1 Feature Registry Service: `agent-coordinator/src/feature_registry.py`

**Location:** `/Users/jankneumann/Coding/agentic-coding-tools/agent-coordinator/src/feature_registry.py`

**Purpose:** Tracks active features and their resource claims; performs conflict analysis for parallel feasibility.

**Core Entities:**

```python
@dataclass
class Feature:
    feature_id: str                    # Unique identifier (e.g., "add-auth")
    status: str                        # "active" | "completed" | "cancelled"
    resource_claims: list[str]         # Lock keys feature will use
    merge_priority: int                # 1 (highest) to 10 (lowest)
    branch_name: str | None            # Git branch name
    registered_by: str                 # Agent ID
    registered_at: datetime | None     # When registered
    metadata: dict[str, Any]           # Flexible storage (includes merge_queue info)

class Feasibility(Enum):
    FULL       # No overlaps — fully parallel safe
    PARTIAL    # Some overlaps — can parallelize with coordination
    SEQUENTIAL # Too many overlaps (>50% of claims) — must serialize
```

**Key Methods:**

- **`register(feature_id, resource_claims, ...)`**
  - Registers feature with declared lock keys
  - Calls DB RPC `register_feature` (PostgreSQL function)
  - Atomic registration with conflict check

- **`analyze_conflicts(candidate_feature_id, candidate_claims)`**
  - Compares candidate against all active features
  - Returns ConflictReport with feasibility assessment
  - **SEQUENTIAL_THRESHOLD = 0.5** — if >50% of claims overlap, mark SEQUENTIAL

- **`get_active_features()`**
  - Queries all features with status='active'
  - Ordered by merge_priority, then registered_at

**Lock Key Namespaces** (from parallel_zones.json and two-level doc):
```
api:          API endpoints or contracts
db:           Database tables/schemas
event:        Event stream or pub/sub topics
flag:         Feature flags
env:          Environment/config keys
contract:     OpenAPI/async contract resources
feature:      Feature-level pause locks
```

**Pain Points & Gaps:**

1. **Threshold is Hard-Coded (50%)** — SEQUENTIAL_THRESHOLD = 0.5 is not configurable
   - May be too aggressive for some projects (serializes on 50% overlap)
   - May be too lenient for others (allows 50% overlap)
   - No way to tune without code change

2. **Conflict Analysis is Lock-Key-Based Only** — Does NOT account for:
   - File-level read dependencies (accessing same config file)
   - Ordering dependencies (feature A must be active before B)
   - Transitive conflicts (A conflicts with B, B conflicts with C, but C doesn't overlap A)
   - Service-level conflicts (shared test database, shared services)

3. **No Dependency Tracking Between Features** — Resource claims don't capture:
   - "This feature must complete before that feature"
   - "This feature requires that feature's resource to be freed"
   - Only resource overlaps are analyzed

4. **Race in Feature Status Transitions** — Scenario:
   - Feature A registered with claims {db:users}
   - Feature B analyzes conflicts (sees A is active)
   - Feature A completes and deregisters (frees {db:users})
   - Feature B proceeds to implement (expecting conflict)
   - Timing-sensitive behavior in multi-agent environment

---

## 4. Parallel Development Workflow Architecture

### 4.1 Two-Level Parallel Agentic Development (1546 lines)

**Location:** `/Users/jankneumann/Coding/agentic-coding-tools/docs/two-level-parallel-agentic-development.md`

**Scope:** Complete specification of cross-feature and intra-feature parallelism, DAG-scheduled work packages, contract-driven development, and deployment patterns.

**Two Levels of Parallelism:**

**Level 1: Cross-Feature Parallelism**
```
Linear workflow (current):
  Feature A: explore → plan → implement → validate → cleanup
             ↓ (merge)
  Feature B: explore → plan → implement → validate → cleanup
             ↓ (merge)
  Feature C: ...

Parallel workflow (proposed):
  Feature A: explore ──→ plan ──→ implement ──→ validate ──→ cleanup (merge via queue)
             /           /          /           /            /
  Feature B: /           /          /           /            /
             /           /          /           /            /
  Feature C: ───────────────────────────────────────────────────
             All phases can overlap if resource claims don't conflict
```

**Level 2: Intra-Feature Parallelism (Work Packages)**

Each feature decomposes into work packages with explicit:
- Dependencies (DAG: package A must complete before B)
- Resource claims (logical locks: {db:users}, {api:auth})
- Scope enforcement (file glob: write to `src/auth/**`, not elsewhere)
- Verification tiers (A=unit, B=integration, C=E2E)

Example DAG:
```
wp-database ──┐
              ├─→ wp-api ──┐
wp-schema ────┤            ├─→ wp-integration ──→ (merge to main)
              └─→ wp-frontend
```

**Key Artifact Types (with schemas):**

1. **`work-packages.yaml`** — Declares packages, dependencies, lock claims
2. **`contracts/`** — OpenAPI specs, Pact contracts, Schemathesis fixtures
3. **`work-queue-result.schema.json`** — Validates each package's completion report
4. **`review-findings.schema.json`** — Vendor-agnostic review output
5. **`execution-summary.md`** — DAG timeline, compliance, risk assessment

**Execution Protocol (Worker Agent, 11 Steps):**

```
B1.  Session registration
B2.  Pause-lock check (coordinator feature pause)
B3.  Deadlock-safe lock acquisition (request + wait, with timeout)
B4.  Worktree setup (create, fetch base branch)
B5.  Code generation + verification steps
B6.  Scope validation (git diff matches write_allow \ deny globs)
B7.  Verification (run A/B/C tier steps, collect evidence)
B8.  Result assembly (schema validation)
B9.  Pause-lock release
B10. Result publication (post to work_queue.result JSONB)
B11. Task completion signal
```

**Critical Safety Pattern: Deadlock-Safe Lock Acquisition**
```python
# NOT: acquire_lock("db:users", reason="need it")  # Deadlock risk
# Instead:
for attempt in range(max_attempts):
    acquired = try_acquire_lock("db:users", timeout=30s)
    if acquired:
        break
    wait(backoff)
else:
    escalate("LOCK_UNAVAILABLE")  # Pause feature, notify orchestrator
```

**Escalation Protocol** (6.2 in two-level doc):
- Package emits escalation with type + severity
- Orchestrator pauses feature (acquires `feature:<change-id>` pause lock)
- Escalation handler runs (human or automatic)
- Feature resumed after handler completes

---

### 4.2 Parallel Skills Family

#### parallel-implement-feature

**Location:** `/Users/jankneumann/Coding/agentic-coding-tools/skills/parallel-implement-feature/SKILL.md`

**Purpose:** Orchestrate DAG-scheduled parallel package execution with result validation and integration.

**Three Phases:**

**Phase A: Feature-Level Preflight (Orchestrator)**
- A1: Parse and validate `work-packages.yaml` (schema validation)
- A2: Validate all contract files exist
- A3: Compute DAG order (topological sort, cycle detection)
- A4: Submit work queue tasks (with depends_on graph)
- A5: Monitor loop (poll `discover_agents` for health, `get_task` for status)

**Phase B: Package Execution Protocol (Every Worker)**
- Workers claim tasks via `get_work` (respects depends_on constraints)
- Execute 11-step protocol (as documented above)
- Publish result to `work_queue.result` JSONB

**Phase C: Review + Integration Sequencing**
- C1: Result validation (schema conformance)
- C2: Escalation processing
- C3: Per-package review (dispatch `parallel-review-implementation`)
- C4: Integration gate (wait for all COMPLETED)
- C5: Integration merge (`wp-integration` package merges all worktrees)
- C6: Execution summary generation (DAG timeline, compliance, risk)

**Coordinator Capabilities (with degradation):**

```yaml
REQUIRED (hard failure):
  - CAN_DISCOVER: discover_agents() for health monitoring
  - CAN_QUEUE_WORK: submit_work/get_work/complete_work
  - CAN_LOCK: acquire_lock/release_lock for resource claims

SAFETY (enforce):
  - CAN_GUARDRAILS: check_guardrails for destructive patterns

ENRICHING (degrade gracefully):
  - CAN_HANDOFF: write_handoff for resumability
  - CAN_MEMORY: remember/recall for procedural memories
  - CAN_POLICY: check_policy for authorization
  - CAN_AUDIT: query_audit for execution summaries
```

If required capabilities unavailable → fallback to `/linear-implement-feature`.

#### parallel-cleanup-feature

**Location:** `/Users/jankneumann/Coding/agentic-coding-tools/skills/parallel-cleanup-feature/SKILL.md`

**Purpose:** Merge via coordinator merge queue, handle cross-feature rebases, archive OpenSpec proposal.

**Key Steps:**

1. Detect coordinator, read handoff if available
2. Determine change-id
3. Verify PR approved and CI passing
4. **Enqueue in merge queue** (if coordinator available)
5. **Run pre-merge checks** (re-validate conflicts)
6. Check merge order (may need to wait for higher-priority features)
7. Cross-feature rebase (if other features merged)
8. Merge PR (squash recommended)
9. Mark merged in registry (deregister, free resource claims)
10. Update local repo
11. Migrate open tasks
12. Archive OpenSpec proposal
13. Cleanup (delete branches, worktrees, release locks)
14. Notify dependent features (feasibility may upgrade from PARTIAL→FULL)
15. Clear session state

**Design Notes vs Linear Cleanup:**
- **Merge queue integration** — ordered merging based on priority
- **Pre-merge conflict re-validation** — catches conflicts from concurrent features
- **Cross-feature rebase coordination** — handles conflicts from merged features
- **Resource claim lifecycle** — deregister to unblock others
- **Dependent feature notification** — update feasibility for waiting features

---

## 5. Coordination Infrastructure

### 5.1 Docker Manager: `agent-coordinator/src/docker_manager.py`

**Purpose:** Auto-start ParadeDB container (or Supabase) and wait for health checks.

**Capabilities:**

- **`detect_runtime(preferred)`** — Auto-detect docker or podman
  - Validates `docker info` / `podman info`
  - Preferred order: auto (try docker→podman), docker, podman

- **`start_container(docker_config, base_dir)`**
  - Reads docker block from deployment profile (profiles/*.yaml)
  - Runs `docker compose up -d`
  - Config keys: enabled, container_runtime, container_name, compose_file

- **`wait_for_healthy(runtime, container_name, timeout, poll_interval)`**
  - Polls container health status every 2s
  - Returns True if reaches "healthy" within timeout (default 60s)

**Profile Integration:**
```yaml
# profiles/local.yaml
docker:
  enabled: true
  container_runtime: auto         # auto | docker | podman
  container_name: paradedb
  compose_file: docker-compose.yml

# profiles/railway.yaml (cloud)
docker:
  enabled: false  # Railway manages container
```

**Pain Points:**

1. **Single Container Assumption** — Design assumes one database container
   - Modern deployments may use 3-5 services (ParadeDB, Redis, etc.)
   - Compose file becomes large and fragile
   - Note in memory mentions: "Old containers survive docker-compose.yml service removal"
   - Must manually `docker stop/rm` + `docker network prune` before `up`

2. **Health Check Coupling** — Hardcoded to "healthy" status
   - Doesn't work with services that don't report health
   - Timeout silently returns False (skill must handle)

3. **No Port Isolation** — Multiple worktrees can't spin up parallel containers
   - Mitigated by port allocator (`allocate_ports`), but docker manager doesn't use it
   - Workaround: prefix container names with session ID (manual)

---

### 5.2 Configuration & Environment: `agent-coordinator/src/config.py`

**Purpose:** Centralized configuration from environment variables and YAML profiles.

**Config Hierarchy (in order of precedence):**
1. **Environment variables** (direct `os.environ`)
2. **Profile YAML** (from `profiles/<COORDINATOR_PROFILE>.yaml`, interpolates from `.secrets.yaml`)
3. **Hardcoded defaults** (in dataclass fields)

**Key Components:**

```python
@dataclass
class SupabaseConfig:        # Legacy PostgREST backend
@dataclass
class AgentConfig:           # This agent's identity
@dataclass
class LockConfig:            # Lock TTL, max TTL
@dataclass
class PostgresConfig:        # Direct asyncpg (preferred)
@dataclass
class DatabaseConfig:        # Selects backend: "supabase" | "postgres"
@dataclass
class GuardrailsConfig:      # Pattern cache TTL, code fallback
@dataclass
class ProfilesConfig:        # Agent trust levels, resource limits
@dataclass
class AuditConfig:           # Retention, async logging
@dataclass
class NetworkPolicyConfig:   # Default policy: "deny" | "allow"
@dataclass
class PolicyEngineConfig:    # "native" | "cedar" policy engine
@dataclass
class PortAllocatorConfig:   # Base port, range, TTL, max sessions
@dataclass
class ApiConfig:             # HTTP API host/port, API keys, identities
```

**Profile Loader Integration:**
```python
# profiles/base.yaml — shared defaults
# profiles/local.yaml — dev (Docker ParadeDB, MCP transport)
# profiles/railway.yaml — prod (Railway PostgreSQL, HTTP transport)

# Environment interpolation:
POSTGRES_DSN: "postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:5432/coordinator"
# Values resolved from .secrets.yaml:
DB_PASSWORD: postgres
DB_USER: postgres
DB_HOST: localhost
```

**Required Files:**

| File | Purpose | Status |
|------|---------|--------|
| `.env.example` | Environment variable template | Present |
| `.secrets.yaml.example` | Interpolation values template | Present |
| `profiles/base.yaml` | Shared config defaults | Not read (in memory) |
| `profiles/local.yaml` | Dev profile | Not read (in memory) |
| `profiles/railway.yaml` | Railway cloud profile | Not read (in memory) |

**Contents of `.env.example`:**
```bash
DB_BACKEND=postgres                          # or "supabase"
POSTGRES_DSN=postgresql://postgres:postgres@localhost:54322/postgres
AGENT_ID=claude-code-1
AGENT_TYPE=claude_code
LOCK_TTL_MINUTES=120
GUARDRAILS_CACHE_TTL=300
PROFILES_DEFAULT_TRUST_LEVEL=1
AUDIT_RETENTION_DAYS=90
NETWORK_DEFAULT_POLICY=deny
POLICY_ENGINE=native                         # or "cedar"
API_HOST=0.0.0.0
API_PORT=8081
COORDINATION_API_KEYS=<generated-key>
```

**Contents of `.secrets.yaml.example`:**
```yaml
DB_PASSWORD: postgres
COORDINATION_API_KEYS: ""
CLAUDE_WEB_API_KEY: ""
CODEX_API_KEY: ""
GEMINI_API_KEY: ""
```

---

## 6. Work Queue & Task Dispatch

### 6.1 Work Queue Service (Inferred from Code)

**Location:** `agent-coordinator/src/work_queue.py` (not fully read, but referenced)

**From two-level doc and skills:**

- **`submit_work(task_type, description, priority, depends_on, input_data)`**
  - Creates task with dependency graph
  - Returns task_id for tracking

- **`get_work(task_type, agent_id, max_claim_time)`**
  - Claims next available task (respects depends_on ordering)
  - Returns task with input_data
  - Atomic claim operation

- **`complete_work(task_id, success, result)`**
  - Marks task completed or failed
  - Stores result as JSONB (validated against schema)
  - Triggers cascading dependent task availability

- **`get_task(task_id)` (NEW in Delta A)**
  - Fetch task state without claiming
  - Returns: status, input_data, result, error_message
  - Enables orchestrator monitoring

**Task State Machine:**
```
pending → claimed → completed | failed | cancelled

pending + depends_on unsatisfied → waiting
pending + all depends_on completed → claimable
```

---

## 7. Parallel Zones Analysis

### 7.1 Architecture Parallel Zones Report

**Location:** `/Users/jankneumann/Coding/agentic-coding-tools/docs/architecture-analysis/parallel_zones.json` (32KB, auto-generated)

**Purpose:** Auto-generated dependency graph showing which modules can run in parallel (independent groups).

**Structure:**
```json
{
  "generated_at": "2026-03-01T02:32:44...",
  "independent_groups": [
    {
      "id": 0,
      "modules": [
        "py:audit.AuditService.db",
        "py:config.get_config",
        "py:coordination_api.create_coordination_api",
        ...
      ]
    },
    { "id": 1, "modules": [...] }
  ]
}
```

**Key Insight:** Groups with different IDs can run in parallel. Same ID = dependency exists.

**Auto-generation Command:**
```bash
python3 skills/refresh-architecture/scripts/parallel_zones.py --analyze agent-coordinator/src > \
  docs/architecture-analysis/parallel_zones.json
```

---

## 8. Skills Installation & Distribution

### 8.1 Skills Install Script: `skills/install.sh`

**Location:** `/Users/jankneumann/Coding/agentic-coding-tools/skills/install.sh`

**Purpose:** Sync/copy/symlink skills to agent config directories (.claude/skills/, .codex/skills/, .gemini/skills/)

**Installation Modes:**

- **`--mode symlink`** — Create symlinks (default for symlink agent configs)
- **`--mode rsync`** — Copy via rsync with checksums (default, good for worktrees)
- **`--mode copy`** — Copy with cp (slower, good for immutable archives)

**Auto-Discovery:**
```bash
# Finds all directories under skills/ with SKILL.md
find skills/ -maxdepth 1 -type d -o -type l | while read dir; do
  if [[ -f "$dir/SKILL.md" ]]; then
    skills+=("$dir")
  fi
done
```

**Usage:**
```bash
./install.sh [--target <dir>] [--mode symlink|rsync|copy] \
             [--deps none|print|apply] [--python-tools none|print|apply] \
             [--force]

# Worktree-safe (uses rsync):
bash skills/install.sh --mode rsync --force --deps none --python-tools none
```

**Dependency Hooks:**
```bash
# Per-skill installation hook: <skill>/scripts/install_deps.sh
# Called with --apply flag if --deps apply specified
```

**Python Tools Bootstrap:**
```bash
# If pytest/mypy/ruff missing, can bootstrap local venv:
# python3 -m venv .skills-venv
# .skills-venv/bin/pip install pytest mypy ruff
```

**Key Design:**
- Avoids modifying skills during installation (safe for read-only FS)
- Target directory structure:
  ```
  target/
    .claude/skills/
      parallel-implement-feature/ (symlink or rsync'd)
      parallel-cleanup-feature/
      ...
    .codex/skills/
      parallel-implement-feature/
      ...
    .gemini/skills/
      ...
  ```

---

## 9. Known Pain Points, Limitations, and Gaps

### 9.1 Worktree Management

| Pain Point | Current State | Impact |
|-----------|---------------|--------|
| **Symlink timing** | Symlinks created during impl, break until merge | High — worktrees can't reliably reference `~/.claude/skills/` |
| **Orphaned worktrees** | No garbage collection, manual cleanup required | Medium — accumulates over time with failed skills |
| **Branch rebase semantics** | `--ours/--theirs` inverted vs `git merge` | High — manual conflict resolution error-prone |
| **Concurrent worktree startup** | Each skill creates own worktree independently | Low — mitigated by coordinator detection |

### 9.2 Merge Queue & Ordering

| Pain Point | Current State | Impact |
|-----------|---------------|--------|
| **Pre-merge check race** | Window between check and merge exists | Medium — mitigated by GitHub branch protection |
| **Non-dynamic priority** | Set at registration, never changes | Medium — can't reprioritize based on new info |
| **No rollback after merge** | Can't revert mark_merged if merge fails | High — requires manual recovery |
| **Resource claim only** | Semantic conflicts in non-overlapping files not detected | Medium — mitigated by scope-aware packages |
| **Merge order blocking** | If higher-priority feature stuck, all lower ones blocked | Medium — can manually override |

### 9.3 Feature Registry & Conflict Analysis

| Pain Point | Current State | Impact |
|-----------|---------------|--------|
| **Hard-coded threshold (50%)** | SEQUENTIAL_THRESHOLD not configurable | Low — reasonable default but inflexible |
| **Lock-key-based only** | File reads, ordering, transitive conflicts not captured | High — requires manual analysis for complex features |
| **No dependency tracking** | Resource overlaps yes; feature ordering no | High — can't express "A must complete before B" |
| **Race in transitions** | Feature status can change between analysis and execution | Medium — timing-sensitive in multi-agent environment |
| **Read-only dependencies** | Lock model assumes write conflicts; doesn't track reads | Medium — test database contention not detected |

### 9.4 Parallel Skill Implementation

| Pain Point | Current State | Impact |
|-----------|---------------|--------|
| **Complex DAG orchestration** | Orchestrator must manage 11-step protocol, escalations | High — error-prone, hard to debug distributed execution |
| **Scope enforcement loose** | Scope validated via deterministic diff, not per-package enforcement | Medium — can bypass via git tricks |
| **Contract drift** | Three-layer validation (static types + Schemathesis + Pact) | Medium — flaky tests, environmental dependencies |
| **No partial rollback** | If package 3 fails, packages 1-2 already committed | High — can leave repo in inconsistent state |
| **Escalation handler undefined** — For pause/resume of features | High — system provides mechanism, skill must implement handler |

### 9.5 Docker & Infrastructure

| Pain Point | Current State | Impact |
|-----------|---------------|--------|
| **Single container assumption** | Design assumes one DB container | Medium — doesn't scale to complex architectures |
| **Old containers survive** | `docker-compose.yml` changes don't remove old containers | High — can cause port conflicts, hidden state |
| **No port isolation per worktree** | Multiple parallel executions compete for ports | Medium — mitigated by port allocator, but separate systems |
| **Health check coupling** | Hardcoded to "healthy" status | Low — works for standard containers |

### 9.6 Configuration & Environment

| Pain Point | Current State | Impact |
|-----------|---------------|--------|
| **Profile fallback chain unclear** | Multiple layers (env → profile → defaults) can confuse | Medium — debugging config issues hard |
| **Secrets exposure risk** | `.secrets.yaml` must never be committed; easy to forget | High — security risk, CI/CD pain |
| **Profile directory optional** | Works without `profiles/` but undocumented behavior | Low — most projects have profiles |
| **Port allocator separate** | Docker manager doesn't integrate with port allocator | Medium — parallel worktrees need coordinated ports |

### 9.7 Missing Components (Feature Gaps)

| Feature | Status | Gap Description |
|---------|--------|-----------------|
| **Formal verification** | Proposed (not implemented) | TLA+ models, Lean proofs would ensure DAG correctness |
| **Retry logic** | Work queue has max_attempts but unused | No scheduler-level retry + backoff |
| **Flaky test quarantine** | Escalation type exists but handler undefined | FLAKY_TEST_QUARANTINE_REQUEST type in schema, no action |
| **Feature pause UI** | Mechanism exists (acquire_lock) but no interface | Users must manually manage pause locks |
| **Merge queue dashboard** | No visualization of queue state | Users flying blind on merge order, timing |
| **Incremental build cache** | No cross-worktree artifact sharing | Each package re-runs full build from scratch |

---

## 10. Integration Patterns & Best Practices

### 10.1 Skill Execution Model

**Linear Skills** (default, backward compatible):
```bash
/explore-feature [focus] → shortlist of features
/plan-feature <desc> → OpenSpec proposal (single-agent)
/implement-feature <id> → Single worktree, sequential
/validate-feature <id> → Integration checks
/cleanup-feature <id> → Merge, archive
```

**Parallel Skills** (coordinator-aware):
```bash
/parallel-explore-feature [focus] → shortlist + feasibility analysis
/parallel-plan-feature <desc> → Contracts + work-packages.yaml
/parallel-review-plan <id> → Independent vendor reviews
/parallel-implement-feature <id> → DAG-scheduled multi-worktree
/parallel-review-implementation <id> → Per-package vendor reviews
/parallel-validate-feature <id> → Evidence completeness check
/parallel-cleanup-feature <id> → Merge queue + cross-feature rebase
```

### 10.2 Worktree Lifecycle in Skills

```bash
# Orchestrator (main repo)
eval "$(python3 skills/worktree/scripts/worktree.py detect)"  # IN_WORKTREE, MAIN_REPO, OPENSPEC_PATH

# Setup
eval "$(python3 skills/worktree/scripts/worktree.py setup $CHANGE_ID --branch openspec/$CHANGE_ID)"
cd $WORKTREE_PATH

# Worker code (in worktree)
git checkout $BRANCH
# ... implementation work ...
python3 skills/worktree/scripts/worktree.py detect  # Output confirms IN_WORKTREE=true, MAIN_REPO=../..

# Cleanup (back in main repo)
git checkout main
python3 skills/worktree/scripts/worktree.py teardown $CHANGE_ID
```

### 10.3 Resource Claim Declaration Pattern

From work-packages.yaml:

```yaml
work-packages:
  - package_id: wp-database
    locks:
      files:
        - src/db/migrations/*.sql
      keys:
        - db:schema
        - db:migrations
    scope:
      write_allow:
        - src/db/**
        - tests/db/**
      read_allow:
        - docs/**
      deny:
        - src/api/**
        - src/frontend/**

  - package_id: wp-api
    depends_on: [wp-database]
    locks:
      files:
        - src/api/**
      keys:
        - api:routes
        - contract:openapi
    scope:
      write_allow:
        - src/api/**
      read_allow:
        - src/db/**
```

**Key Pattern:** Lock keys declare **logical** resource needs (schema, API contract). Scope globs enforce **file-level** isolation. Together they enable:
- Parallel detection (check for lock key overlaps)
- Deterministic verification (git diff ⊆ write_allow \ deny)

---

## 11. Conclusion & Recommendations

### What Works Well

1. **Worktree isolation** — Clean separation of concerns, easy to parallelize
2. **Resource claim model** — Logical locks + file scopes give good signal-to-noise
3. **Coordinator integration** — Optional but powerful; skills degrade gracefully
4. **Merge queue** — Simple, re-uses feature registry, prevents merge chaos
5. **Execution protocol** — 11-step worker protocol is detailed, implementable

### What Needs Attention

1. **Feature registry** — Add dependency tracking, make threshold configurable, fix race conditions
2. **Escalation handler** — Define concrete implementations for PAUSE, CONTRACT_BUMP, PLAN_BUMP
3. **Docker/infrastructure** — Integrate port allocator, handle multi-container environments
4. **Testing** — Formal verification tasks (FV-1, FV-2, FV-3 in two-level doc) not yet started
5. **Observability** — No merge queue dashboard, limited audit trail visibility in parallel execution
6. **Documentation** — Parallel workflow still under development; many moving pieces

### Critical Path

From two-level doc (§4, Implementation Sequence):

```
#1 (skill families) ──→ #4 (parallel-plan, parallel-explore)
                              │
#2 (contract artifacts) ──→ #3 (work-packages + coordinator deltas)
                              │
                          ↓
                    #6 (parallel-implement)
                              │
                    #8 (merge queue + parallel-cleanup)
```

**Next Priority:** Complete `parallel-implement-feature` skill and merge queue integration. Foundation (worktrees, coordinator, schemas) mostly in place.

