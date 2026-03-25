# Delta Spec: skill-workflow

## MODIFIED Requirements

### Requirement: Parallel Cleanup Feature Coordinator Integration

The `parallel-cleanup-feature` skill SHALL reference actual coordinator MCP tools and HTTP endpoints instead of pseudo-code for merge queue and feature registry operations.

#### Scenario: Merge queue enqueue in skill
- WHEN the skill enqueues a feature for merge
- THEN it SHALL call MCP tool `enqueue_merge` or HTTP `POST /merge-queue/enqueue`
- AND NOT reference `merge_queue.enqueue()` pseudo-code

#### Scenario: Pre-merge checks in skill
- WHEN the skill runs pre-merge checks
- THEN it SHALL call MCP tool `run_pre_merge_checks` or HTTP `POST /merge-queue/check/{feature_id}`

#### Scenario: Mark merged in skill
- WHEN the skill marks a feature as merged
- THEN it SHALL call MCP tool `mark_merged` or HTTP `POST /merge-queue/merged/{feature_id}`

#### Scenario: Coordinator unavailable fallback
- WHEN the coordinator is unavailable
- THEN the skill SHALL degrade to `linear-cleanup-feature` behavior without error
