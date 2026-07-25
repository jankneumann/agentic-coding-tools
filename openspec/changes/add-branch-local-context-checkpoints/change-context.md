# Change Context: add-branch-local-context-checkpoints

Phase 1 (pre-implementation). `Files Changed` and `Evidence` are `---` until Phases 2 and 3.

Capability prefixes: `pcro` = `project-context-refresh-orchestration`, `swf` = `skill-workflow`.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| pcro.1 | specs/project-context-refresh-orchestration/spec.md | Branch-local checkpoint mode reports the context a work package invalidated | contracts/context-checkpoint.schema.json | D3 | --- | test_checkpoint.py, test_checkpoint_cli.py | --- |
| pcro.2 | specs/project-context-refresh-orchestration/spec.md | Checkpoint creates/modifies/finalizes no operation record and emits no manifest | --- | D1, D10 | --- | test_checkpoint_isolation.py | --- |
| pcro.3 | specs/project-context-refresh-orchestration/spec.md | Checkpoint indexing targets a non-canonical namespace | contracts/context-checkpoint.schema.json#/properties/namespace | D4 | --- | test_semantic_adapter_namespace.py, test_checkpoint_contract.py | --- |
| pcro.4 | specs/project-context-refresh-orchestration/spec.md | Checkpoint execution restricted to read_allow minus deny, deny winning | contracts/context-checkpoint.schema.json#/properties/scope | D5 | --- | test_semantic_adapter_namespace.py | --- |
| pcro.5 | specs/project-context-refresh-orchestration/spec.md | Checkpoint modifies no tracked producer output; producers run in check mode | --- | D3 | --- | test_checkpoint.py | --- |
| pcro.6 | specs/project-context-refresh-orchestration/spec.md | Report is change-local, version-controlled, byte-stable for a fixed revision | contracts/context-checkpoint.schema.json | D7 | --- | test_checkpoint.py, test_checkpoint_contract.py | --- |
| pcro.7 | specs/project-context-refresh-orchestration/spec.md | Architecture freshness and delta reported separately; stale delta labelled | contracts/context-checkpoint.schema.json#/properties/architecture | D6 | --- | test_checkpoint_architecture.py | --- |
| pcro.8 | specs/project-context-refresh-orchestration/spec.md | Semantic indexing degrades to a recorded fallback without failing | contracts/context-checkpoint.schema.json#/properties/semantic_index | D9 | --- | test_checkpoint.py | --- |
| pcro.9 | specs/project-context-refresh-orchestration/spec.md | Drift is reported as data; failure only when no valid report could be produced | contracts/context-checkpoint.schema.json#/properties/checkpoint_status | D8 | --- | test_checkpoint.py, test_checkpoint_cli.py | --- |
| swf.1 | specs/skill-workflow/spec.md | Implementation dispatch triggers a checkpoint per context-invalidating package | --- | D2 | --- | test_context_checkpoint_trigger.py | --- |
| swf.2 | specs/skill-workflow/spec.md | Missing context_impact block reported as unmigrated, not impact-free | --- | D2 | --- | test_context_checkpoint_trigger.py | --- |
| swf.3 | specs/skill-workflow/spec.md | Workflow passes the package's resolved read scope to the checkpoint | --- | D5 | --- | test_context_checkpoint_trigger.py | --- |

## Requirement-to-Package Assignment

| Req ID | Owning package |
|--------|----------------|
| pcro.3 (schema half), pcro.6 (schema half) | wp-contracts |
| pcro.3 (argv half), pcro.4 | wp-adapter |
| pcro.1, pcro.2, pcro.5, pcro.6, pcro.7, pcro.8, pcro.9 | wp-checkpoint |
| swf.1, swf.2, swf.3 | wp-workflow |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | A recorded producer result is immutable for its revision and reused verbatim, so a scope-restricted checkpoint result in the canonical ledger is unrecoverable | checkpoint.py constructs no OperationStore | Structural impossibility beats convention |
| D2 | `None` (missing block) and `frozenset()` (empty list) mean different things in the ri-08 detector | implement-feature reports `unmigrated` distinctly | Absence of evidence is not evidence of absence |
| D3 | A check-mode producer has no write path into tracked outputs | registry.run_producer(..., "check", ...) only | Makes acceptance outcome 3 true by construction |
| D4 | Canonical promotion is already gated on kind=main and key=main | `work_package` namespace threaded through semantic_adapter.py | Reuses tested downstream enforcement |
| D5 | indexing_policy already enforces read_allow; ri-08 already computes it | index_scopes() output passed as --read-allow/--deny | Supply the policy, don't reimplement the check |
| D6 | architecture-provenance.schema.json pins mode to full\|quick | run_architecture.py --check plus diff_architecture.py | Avoids a contract change for a slice mode |
| D7 | Reviewers read the PR diff | Tracked report under openspec/changes/<id>/context-checkpoints/ | Matches the stated purpose of the item |
| D8 | ri-10 owns drift gating | Exit 0 on drift; non-zero only when no report | Gives ri-10 a signal, not a gate to rework |
| D9 | ri-07 D4 already establishes degradable indexing | not-configured status with a fallback | One uniform posture toward the index |
| D10 | checkout_policy reasons about worktree path, not the clone-global common dir | Explicit regression test on the ledger directory | Widening checkout_policy would affect every mutating skill |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 0/12
- **Tests mapped**: 12 requirements have at least one test
- **Evidence collected**: 0/12 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
