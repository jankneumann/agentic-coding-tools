# Change Context: add-branch-local-context-checkpoints

Phase 3 (post-implementation). `Files Changed` and `Evidence` are populated; evidence is the
orchestrator's own verification run at `c052bccb` (403 tests across the three affected suites,
`ruff` clean, `openspec validate --strict` valid).

Capability prefixes: `pcro` = `project-context-refresh-orchestration`, `swf` = `skill-workflow`.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| pcro.1 | specs/project-context-refresh-orchestration/spec.md | Branch-local checkpoint mode reports the context a work package invalidated | contracts/context-checkpoint.schema.json | D3 | skills/project-context-refresh/scripts/checkpoint.py, skills/project-context-refresh/scripts/cli.py | test_checkpoint.py, test_checkpoint_cli.py | pass c052bccb |
| pcro.2 | specs/project-context-refresh-orchestration/spec.md | Checkpoint creates/modifies/finalizes no operation record and emits no manifest | --- | D1, D10 | skills/project-context-refresh/scripts/checkpoint.py | test_checkpoint_isolation.py | pass c052bccb |
| pcro.3 | specs/project-context-refresh-orchestration/spec.md | Checkpoint indexing targets a non-canonical namespace | contracts/context-checkpoint.schema.json#/properties/namespace | D4 | skills/project-context-refresh/scripts/semantic_adapter.py, openspec/schemas/context-checkpoint.schema.json | test_semantic_adapter_namespace.py, test_checkpoint_contract.py | pass c052bccb |
| pcro.4 | specs/project-context-refresh-orchestration/spec.md | Checkpoint execution restricted to read_allow minus deny, deny winning | contracts/context-checkpoint.schema.json#/properties/scope | D5 | skills/project-context-refresh/scripts/semantic_adapter.py, skills/project-context-refresh/scripts/checkpoint.py | test_semantic_adapter_namespace.py | pass c052bccb |
| pcro.5 | specs/project-context-refresh-orchestration/spec.md | Checkpoint modifies no tracked producer output; producers run in check mode | --- | D3 | skills/project-context-refresh/scripts/checkpoint.py | test_checkpoint.py | pass c052bccb |
| pcro.6 | specs/project-context-refresh-orchestration/spec.md | Report is change-local, version-controlled, byte-stable for a fixed revision | contracts/context-checkpoint.schema.json | D7 | skills/project-context-refresh/scripts/checkpoint.py, openspec/schemas/context-checkpoint.schema.json | test_checkpoint.py, test_checkpoint_contract.py | pass c052bccb |
| pcro.7 | specs/project-context-refresh-orchestration/spec.md | Architecture freshness and delta reported separately; stale delta labelled | contracts/context-checkpoint.schema.json#/properties/architecture | D6 | skills/project-context-refresh/scripts/checkpoint.py, openspec/schemas/context-checkpoint.schema.json | test_checkpoint_architecture.py | pass c052bccb |
| pcro.8 | specs/project-context-refresh-orchestration/spec.md | Semantic indexing degrades to a recorded fallback without failing | contracts/context-checkpoint.schema.json#/properties/semantic_index | D9 | skills/project-context-refresh/scripts/checkpoint.py, skills/project-context-refresh/scripts/semantic_adapter.py | test_checkpoint.py | pass c052bccb |
| pcro.9 | specs/project-context-refresh-orchestration/spec.md | Drift is reported as data; failure only when no valid report could be produced | contracts/context-checkpoint.schema.json#/properties/checkpoint_status | D8 | skills/project-context-refresh/scripts/checkpoint.py, skills/project-context-refresh/scripts/cli.py | test_checkpoint.py, test_checkpoint_cli.py | pass c052bccb |
| swf.1 | specs/skill-workflow/spec.md | Implementation dispatch triggers a checkpoint per context-invalidating package | --- | D2 | skills/implement-feature/SKILL.md, skills/project-context-refresh/scripts/checkpoint.py | test_context_checkpoint_trigger.py | pass c052bccb |
| swf.2 | specs/skill-workflow/spec.md | Missing context_impact block reported as unmigrated, not impact-free | --- | D2 | skills/implement-feature/SKILL.md, skills/project-context-refresh/scripts/checkpoint.py | test_context_checkpoint_trigger.py | pass c052bccb |
| swf.3 | specs/skill-workflow/spec.md | Workflow passes the package's resolved read scope to the checkpoint | --- | D5 | skills/implement-feature/SKILL.md, skills/project-context-refresh/scripts/checkpoint.py | test_context_checkpoint_trigger.py | pass c052bccb |

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
| D3 | The four landed check-mode producers have no write path into tracked outputs | registry.run_producer(..., "check", ...) only | Strongest available check; the registry does NOT structurally forbid a check-mode write, so ri-10 must assert rather than assume |
| D4 | Canonical promotion is already gated on kind=main and key=main | `work_package` namespace threaded through semantic_adapter.py | Reuses tested downstream enforcement |
| D5 | indexing_policy already enforces read_allow; ri-08 already computes it | index_scopes() output passed as --read-allow/--deny | Supply the policy, don't reimplement the check |
| D6 | architecture-provenance.schema.json pins mode to full\|quick | arch_utils.provenance.check_freshness plus diff_architecture.py against the merge base | Avoids a contract change for a slice mode; the CLI wrapper collapses stale and invalid, which the report needs kept apart |
| D7 | Reviewers read the PR diff | Tracked report under openspec/changes/<id>/context-checkpoints/ | Matches the stated purpose of the item |
| D8 | ri-10 owns drift gating | Exit 0 on drift; non-zero only when no report | Gives ri-10 a signal, not a gate to rework |
| D9 | ri-07 D4 already establishes degradable indexing | not-configured status with a fallback | One uniform posture toward the index |
| D10 | checkout_policy reasons about worktree path, not the clone-global common dir | Explicit regression test on the ledger directory | Widening checkout_policy would affect every mutating skill |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|
| F1 | wp-contracts | contract_gap | high | accepted | `delta_authoritative` invariant was prose-only; `{freshness: stale, delta_authoritative: true}` validated. Encoded as an `if/then`; verified failing before the fix (commit b2ac1a83) |
| F2 | wp-checkpoint | design_overclaim | medium | accepted | D3 claimed check-mode read-only-ness was "true by construction"; the registry provides no such guarantee. Wording corrected and ri-10 warned (commit 4ae98f15) |
| F3 | wp-checkpoint | design_ambiguity | medium | accepted | D6 did not name the "current" graph. Resolved to working-tree, since committed-vs-committed blinds the checkpoint during the uncommitted window it exists for |
| F4 | wp-checkpoint | design_gap | low | accepted | ri-08's `undeclared`/`spurious_rationale` have no representable form in the contract; mapped to "could not produce a valid report" (exit non-zero, no report) |
| F5 | wp-checkpoint | design_gap | low | accepted | A self-cancelling read scope degrades the index per D9 rather than failing the run; deterministic findings are retained |
| F6 | wp-checkpoint | deviation | low | accepted | Freshness read via `check_freshness` rather than the `run_architecture.py --check` wrapper, to keep `stale` and `invalid` distinct |
| F7 | wp-workflow | test_method | low | accepted | RED-before-GREEN was impossible (dependency already landed); tests mutation-checked instead — 3/3 failed under a mutation collapsing `unmigrated` into `declared` |

## Coverage Summary

- **Requirements traced**: 12/12
- **Tests mapped**: 12 requirements have at least one test
- **Evidence collected**: 12/12 requirements have pass evidence
- **Gaps identified**: none blocking. Six design ambiguities surfaced during implementation and were reconciled into `design.md` (D3 wording, D6 baseline side + freshness call boundary, and three edge cases the decisions had not resolved).
- **Deferred items**: `mypy` over `skills/` is not a CI gate (tracked separately); index-namespace retention/GC is left to ri-10/ri-11.
