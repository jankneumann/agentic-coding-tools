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
