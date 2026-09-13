# Tasks: pack-and-parallelize-vendor-review

## 1. Contracts

- [x] 1.1 Write tests for review-packet document validation
  **Spec scenarios**: skill-workflow Review Packet As Default Input (diff+schema, missing ledger, overflow)
  **Contracts**: `contracts/review-packet.schema.json`
  **Design decisions**: D1
  **Dependencies**: None
  **Files**: `skills/tests/parallel-infrastructure/test_review_packet_schema.py`

- [x] 1.2 Add review-packet contract artifacts
  **Dependencies**: 1.1
  **Files**: `openspec/changes/pack-and-parallelize-vendor-review/contracts/**`

- [x] Checkpoint: run contract tests, review diff, verify scope

## 2. Packet builder

- [x] 2.1 Write tests for packet contents, checksum, overflow flag, ledger-optional build
  **Spec scenarios**: skill-workflow Review Packet As Default Input
  **Contracts**: `contracts/review-packet.schema.json`
  **Design decisions**: D1
  **Dependencies**: 1.2
  **Files**: `skills/tests/parallel-infrastructure/test_review_packet.py`

- [x] 2.2 Implement `review_packet.py`
  **Dependencies**: 2.1
  **Files**: `skills/parallel-infrastructure/scripts/review_packet.py`

- [x] 2.3 Pass the packet path from `converge()` into dispatch
  **Dependencies**: 2.2
  **Files**: `skills/autopilot/scripts/convergence_loop.py`

- [x] Checkpoint: run packet tests, review diff, verify scope

## 3. Concurrent dispatch

- [x] 3.1 Write overlap tests with two 2-second stub processes
  **Spec scenarios**: skill-workflow Parallel Review Dispatch (parallel, sequential is a bug)
  **Design decisions**: D2, D4
  **Dependencies**: 2.2
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`

- [x] 3.2 Implement concurrent `dispatch_and_wait` including async submit
  **Dependencies**: 3.1
  **Files**: `skills/parallel-infrastructure/scripts/review_dispatcher.py`

- [x] 3.3 Add detached snapshot fallback for concurrent git-access errors
  **Dependencies**: 3.2
  **Files**: `skills/parallel-infrastructure/scripts/review_dispatcher.py`

- [x] Checkpoint: run dispatcher concurrency tests, review diff, verify scope

## 4. Structured output probe

- [x] 4.1 Record empirical probe results for Codex, Claude, pi, Antigravity structured-output flags
  **Spec scenarios**: skill-workflow Verify-Then-Wire Structured Output
  **Contracts**: `contracts/vendor-structured-output.md`
  **Design decisions**: D3
  **Dependencies**: 1.2
  **Files**: `openspec/changes/pack-and-parallelize-vendor-review/contracts/vendor-structured-output.md`

- [x] 4.2 Wire `agents.yaml` review args only for rows marked `verified`
  **Dependencies**: 4.1
  **Files**: `agent-coordinator/agents.yaml`

- [x] Checkpoint: confirm Grok schema injection still passes existing tests, review diff, verify scope

## 5. Integration

- [x] 5.1 Add a packet-plus-concurrency fixture for ledger-optional builds
  **Spec scenarios**: skill-workflow Review Packet As Default Input (missing ledger); Parallel Review Dispatch
  **Design decisions**: D1, D2
  **Dependencies**: 3.3, 2.3
  **Files**: `skills/tests/parallel-infrastructure/test_review_packet_dispatch.py`

- [x] 5.2 Validate the change with `openspec validate --strict` then the parallel-infrastructure unit suite
  **Dependencies**: 5.1, 4.2
  **Files**: none
