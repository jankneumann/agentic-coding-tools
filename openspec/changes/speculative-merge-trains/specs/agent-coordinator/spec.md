# Spec Delta: Agent Coordinator — Speculative Merge Trains

**Change ID**: `speculative-merge-trains`
**Capability**: `agent-coordinator`

## ADDED Requirements

### Requirement: Speculative Merge Train Composition

The merge queue service SHALL compose merge trains from queued entries by grouping them into partitions based on lock key prefix overlap and assigning speculative positions within each partition.

#### Scenario: Compose train from independent entries

WHEN three features are queued with non-overlapping lock keys (feature-A claims `api:GET /v1/users`, feature-B claims `db:schema:billing`, feature-C claims `api:POST /v1/orders`)
THEN compose_train SHALL create two partitions: one containing feature-A and feature-C (both `api:` prefix), and one containing feature-B (`db:` prefix)
AND each entry SHALL have a `train_id`, `partition_id`, and `train_position` in its metadata
AND entries in different partitions SHALL be assigned to independent sub-trains

#### Scenario: Compose train with cross-partition entries

WHEN a feature claims both `api:GET /v1/users` AND `db:schema:users`
THEN compose_train SHALL assign it to a cross-partition sub-train
AND entries behind it in any overlapping partition SHALL speculate against a base that includes this entry

#### Scenario: Empty queue produces no train

WHEN no features are queued
THEN compose_train SHALL return an empty train with no partitions

### Requirement: Speculative Branch Management

The merge queue service SHALL create speculative git references for each train position, representing the state of main with all preceding entries merged.

#### Scenario: Create speculative ref for first position

WHEN a train entry is at position 1 in its partition
THEN the git adapter SHALL create a speculative ref by merging the entry's branch onto current main
AND the ref SHALL be stored as `speculative_ref` in the entry's metadata

#### Scenario: Create speculative ref for subsequent positions

WHEN a train entry is at position N > 1
THEN the git adapter SHALL create a speculative ref by merging the entry's branch onto the speculative ref of position N-1
AND if the merge fails (conflict), the entry SHALL be marked BLOCKED

#### Scenario: Cleanup speculative refs after train completion

WHEN a train completes (all entries MERGED or EJECTED)
THEN the git adapter SHALL delete all speculative refs for that train
AND no orphaned refs SHALL remain under `refs/speculative/`

### Requirement: Train Entry State Machine

The merge queue service SHALL track each train entry through the states: QUEUED, SPECULATING, SPEC_PASSED, MERGING, MERGED, EJECTED, BLOCKED.

#### Scenario: Successful train entry lifecycle

WHEN an entry transitions through QUEUED → SPECULATING → SPEC_PASSED → MERGING → MERGED
THEN each transition SHALL be recorded in the audit log with timestamps
AND the entry's metadata SHALL reflect the current state at each step

#### Scenario: Failed entry ejection

WHEN a train entry in SPECULATING state fails CI
THEN the entry SHALL transition to EJECTED
AND its `merge_priority` SHALL be decremented by 10
AND entries behind it with zero lock key overlap SHALL remain in their current state
AND entries behind it with non-zero lock key overlap SHALL re-speculate (transition back to QUEUED for next train composition)

### Requirement: Priority Eject Recovery

The merge queue service SHALL support ejecting a failed entry from the train and continuing the train for independent entries.

#### Scenario: Eject with independent successors

WHEN entry at position 2 of 5 is ejected
AND entries at positions 3, 4, 5 have no overlapping lock keys with entry 2
THEN entries 3, 4, 5 SHALL continue with their existing speculative refs (no re-speculation)
AND the train SHALL complete when all remaining entries reach SPEC_PASSED

#### Scenario: Eject with dependent successors

WHEN entry at position 2 of 5 is ejected
AND entry at position 3 has overlapping lock keys with entry 2
THEN entry 3 SHALL transition to QUEUED
AND entry 3 SHALL be re-speculated in the next train composition
AND entries 4 and 5 SHALL be evaluated for overlap with entry 2 independently

### Requirement: Partition-Aware Merge

The merge queue service SHALL merge partitions independently, allowing true parallel merge execution for non-overlapping partitions.

#### Scenario: Parallel partition merge

WHEN partition A has 2 SPEC_PASSED entries and partition B has 3 SPEC_PASSED entries
THEN both partitions SHALL be eligible to merge simultaneously
AND the merge executor SHALL fast-forward main to the final speculative ref of each partition
AND partition merge order SHALL not affect the other partition

#### Scenario: Cross-partition ordering

WHEN a cross-partition entry exists that spans partitions A and B
THEN partitions A and B MUST serialize their merges around the cross-partition entry
AND the cross-partition entry SHALL merge only after all entries before it in both partitions have merged

### Requirement: Train Operation Authorization

All merge train operations SHALL require authenticated sessions with appropriate trust levels, preventing unauthorized agents from manipulating train ordering or ejecting entries.

#### Scenario: compose_train requires coordinator-level trust

WHEN an agent calls compose_train
THEN the agent MUST have trust level >= 3 (operator) or be the coordinator service itself
AND if trust level is insufficient, the operation SHALL be rejected with a 403 error
AND the rejection SHALL be logged to the audit trail

#### Scenario: eject_from_train requires ownership or operator trust

WHEN an agent calls eject_from_train(feature_id)
THEN the agent MUST be either the feature owner (registered_by) or have trust level >= 3
AND if the agent is neither the owner nor an operator, the operation SHALL be rejected
AND the rejection SHALL be logged to the audit trail

#### Scenario: HTTP train endpoints require API key authentication

WHEN train operations are exposed via HTTP API
THEN all endpoints SHALL require a valid `X-API-Key` header
AND the API key identity SHALL be resolved to an agent profile for trust level checks

### Requirement: Speculative Ref Security and Cleanup

Speculative git references SHALL be protected against leakage, cleaned up on failure, and garbage-collected if the coordinator crashes.

#### Scenario: Speculative ref naming validation

WHEN the git adapter creates a speculative ref
THEN the ref name MUST match the pattern `^refs/speculative/train-[a-f0-9]{8,32}/pos-\d{1,4}$`
AND branch names provided by agents MUST be validated against `^[a-zA-Z0-9/_.-]{1,200}$`
AND any name failing validation SHALL be rejected before subprocess execution
AND the git adapter MUST use `subprocess.run(args_list, shell=False)` exclusively — never shell=True

#### Scenario: Cleanup on coordinator crash

WHEN the coordinator restarts after an unexpected shutdown
THEN a startup cleanup routine SHALL enumerate all refs under `refs/speculative/`
AND for each ref, if the corresponding train_id has no active entries in the merge queue, the ref SHALL be deleted
AND cleanup actions SHALL be logged to the audit trail

#### Scenario: TTL-based garbage collection

WHEN a speculative ref has existed for longer than 6 hours
AND no active train entry references it
THEN the ref SHALL be eligible for garbage collection
AND the watchdog service SHALL delete it during its periodic sweep

### Requirement: Post-Speculation Claim Validation

After a speculative ref is created, the merge queue service SHALL validate that the entry's actual file changes match its declared resource claims, preventing partition misassignment.

#### Scenario: Claim matches actual changes

WHEN a speculative ref is created for an entry claiming `api:GET /v1/users`
AND the git diff of the entry shows changes only to `src/api/users.py`
THEN the claim validation SHALL pass
AND the entry SHALL proceed to CI

#### Scenario: Claim does not match actual changes

WHEN a speculative ref is created for an entry claiming `api:GET /v1/users`
AND the git diff shows changes to `src/db/schema.py` (which would map to `db:schema:*` partition)
THEN the claim validation SHALL fail
AND the entry SHALL transition to BLOCKED with reason "claim mismatch: actual changes span partitions not declared in resource_claims"
AND the entry owner SHALL be notified to update claims and re-enqueue

### Requirement: BLOCKED Entry Recovery

Entries that transition to BLOCKED SHALL have a defined recovery path.

#### Scenario: Manual re-enqueue of BLOCKED entry

WHEN an entry is in BLOCKED state
AND the entry owner calls enqueue with updated resource claims or branch
THEN the entry SHALL transition back to QUEUED
AND the entry SHALL be included in the next train composition with its original merge_priority

#### Scenario: Automatic re-evaluation on next train composition

WHEN compose_train runs and there are BLOCKED entries older than 1 hour
THEN compose_train SHALL re-evaluate BLOCKED entries by attempting speculative merge
AND if the merge succeeds (conflict resolved), the entry SHALL transition to SPECULATING
AND if the merge still fails, the entry SHALL remain BLOCKED with updated `checked_at` timestamp

### Requirement: Partition Detection Performance

The partition detection algorithm SHALL complete in bounded time proportional to the number of entries and their claim count.

#### Scenario: Partition detection within time bound

WHEN compose_train is called with N entries, each having at most P resource claims
THEN compute_partitions SHALL complete in O(N·P) time
AND for N=1000 and P=10, compose_train SHALL complete partition detection in under 5 seconds

#### Scenario: Cross-partition cycle detection

WHEN cross-partition entries exist such that entry A spans partitions {P1, P2} and entry B spans partitions {P2, P3} and entry C spans partitions {P3, P1}
THEN compose_train SHALL detect the circular dependency
AND all entries in the cycle SHALL be placed in a single serialized cross-partition sub-train
AND the cycle detection SHALL be logged as a warning

### Requirement: Speculative Ref Creation Performance

Speculative ref creation SHALL use efficient git operations that do not require working directory I/O.

#### Scenario: Merge-tree based speculation

WHEN the git adapter creates a speculative ref
THEN it SHALL use `git merge-tree` (or equivalent in-memory merge) rather than `git merge` with a working directory
AND tree objects SHALL be cached per train_id to avoid redundant computation
AND speculative ref creation for independent partitions SHALL be parallelizable (no global lock)

#### Scenario: Large train performance bound

WHEN a train has 100 entries across 5 partitions
THEN all speculative refs SHALL be created in under 30 seconds on a repository with 10,000 files

## MODIFIED Requirements

### Requirement: Merge Queue Enqueue (Extended)

The existing `enqueue` method SHALL accept an optional `decomposition` parameter indicating whether the entry represents a stacked-diff work package or a traditional feature branch.

#### Scenario: Enqueue stacked-diff entry

WHEN enqueue is called with `decomposition="stacked"` and a `stack_position` integer
THEN the entry's metadata SHALL include `decomposition: "stacked"` and `stack_position`
AND the entry SHALL be treated as an independently-mergeable unit

#### Scenario: Enqueue traditional feature branch (backward compatible)

WHEN enqueue is called without a `decomposition` parameter
THEN the entry SHALL default to `decomposition: "branch"`
AND existing behavior SHALL be preserved exactly
