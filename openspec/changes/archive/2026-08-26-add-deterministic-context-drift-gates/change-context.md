# Change Context: add-deterministic-context-drift-gates

Phase 1 (pre-implementation). `Files Changed` and `Evidence` are `---` and get populated in
Phase 2 and Phase 3 respectively.

Capability prefixes: `pcro` = `project-context-refresh-orchestration`,
`ar` = `architecture-refresh`.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| pcro.1 | specs/project-context-refresh-orchestration/spec.md | A single composed gate runs deterministic producers, architecture freshness, and context-impact validation, emitting one structured report | contracts/context-drift-gate.schema.json | D1 | --- | test_gate.py | --- |
| pcro.2 | specs/project-context-refresh-orchestration/spec.md | The report names every stale artifact by repository-relative path, not an aggregate count | contracts/context-drift-gate.schema.json#/$defs/ProducerFinding/properties/artifacts | D1 | --- | test_gate.py | --- |
| pcro.3 | specs/project-context-refresh-orchestration/spec.md | The gate writes nothing to the checkout and records no durable operation or manifest | --- | D1, D8 | --- | test_gate.py, test_check_mode_read_only.py | --- |
| pcro.4 | specs/project-context-refresh-orchestration/spec.md | Producer results are classified into four disjoint groups by a pure, IO-free function | contracts/context-drift-gate.schema.json | D2 | --- | test_classify_degradation.py | --- |
| pcro.5 | specs/project-context-refresh-orchestration/spec.md | Classification is additive: the terminal-outcome decision, OperationState, and the durable schemas are unchanged | --- | D2 | --- | test_classify_degradation.py, test_orchestrator.py | --- |
| pcro.6 | specs/project-context-refresh-orchestration/spec.md | OpenSpec projection drift is informational and never contributes to a failing exit code | contracts/context-drift-gate.schema.json#/properties/informational_drift | D3 | --- | test_classify_degradation.py, test_gate.py | --- |
| pcro.7 | specs/project-context-refresh-orchestration/spec.md | Architecture freshness compares committed provenance against recomputed digests, never a rebuild from the working tree | --- | D4 | --- | test_architecture_freshness.py | --- |
| pcro.8 | specs/project-context-refresh-orchestration/spec.md | Missing, malformed, or schema-invalid provenance is drift; a non-importable owner is an absent optional owner | contracts/context-drift-gate.schema.json#/properties/architecture | D4 | --- | test_architecture_freshness.py | --- |
| pcro.9 | specs/project-context-refresh-orchestration/spec.md | Gate exit codes derive from the classification: 1 failure, 2 blocking drift, 0 informational or absent-owner only | contracts/context-drift-gate.schema.json#/properties/exit_code | D5 | --- | test_gate.py | --- |
| pcro.10 | specs/project-context-refresh-orchestration/spec.md | The gate's exit-code mapping does not alter the existing per-producer or orchestrated check entry points | --- | D5 | --- | test_cli.py | --- |
| pcro.11 | specs/project-context-refresh-orchestration/spec.md | Semantic index is reported as not attempted with an explicit reason; no indexer is constructed | contracts/context-drift-gate.schema.json#/properties/semantic | D6 | --- | test_gate.py | --- |
| pcro.12 | specs/project-context-refresh-orchestration/spec.md | Every producer from the registry leaves tracked and untracked paths byte-identical in check mode | --- | D8 | --- | test_check_mode_read_only.py | --- |
| pcro.13 | specs/project-context-refresh-orchestration/spec.md | The registry receives no runtime filesystem guard; the assertion is the enforcement mechanism | --- | D8 | --- | test_check_mode_read_only.py | --- |
| pcro.14 | specs/project-context-refresh-orchestration/spec.md | The gate is the only CI check verifying decision index freshness; the previous job is removed | --- | D9 | --- | test_decision_index_orphan.py | --- |
| pcro.15 | specs/project-context-refresh-orchestration/spec.md | An orphaned capability file with unchanged content is detected as drift | --- | D9 | --- | test_decision_index_orphan.py | --- |
| pcro.16 | specs/project-context-refresh-orchestration/spec.md | Context-impact validation covers only work-package files in the diff under test, without strict legacy enforcement | --- | D7 | --- | test_gate.py | --- |
| pcro.17 | specs/project-context-refresh-orchestration/spec.md | A validator usage or configuration error is an apparatus failure, not drift | --- | D7 | --- | test_gate.py | --- |
| ar.1 | specs/architecture-refresh/spec.md | Architecture provenance is tracked in version control as a committed baseline | --- | D4, D10 | --- | test_architecture_freshness.py | --- |
| ar.2 | specs/architecture-refresh/spec.md | Regeneration updates the committed provenance in the same commit, so a clean checkout at the recorded revision has no diff | --- | D10 | --- | test_architecture_freshness.py | --- |

## Requirement-to-Package Assignment

| Req ID | Owning package |
|--------|----------------|
| pcro.2 (schema half), pcro.11 (schema half) | wp-contracts |
| pcro.4, pcro.5, pcro.6 (classifier half), pcro.7, pcro.8, pcro.12, pcro.13 | wp-lifecycle |
| pcro.1, pcro.2 (rendering half), pcro.3, pcro.6 (gate half), pcro.9, pcro.10, pcro.11, pcro.16, pcro.17 | wp-gate |
| pcro.14, pcro.15 | wp-ci |
| ar.1, ar.2 | wp-integration |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | "Precise artifact list" is a rendering requirement, and rendering assembled by shell over job output is untestable | gate.py owns composition; cli.py and the Makefile target are thin seams | Unit-testable list; one local command reproduces any CI failure; keeps a contended ci.yml delta short |
| D2 | OperationState is pinned by the durable operation and manifest schemas, and ri-07 D9 makes recorded operations immutable | New pure `classify_degradation` returning four disjoint groups, alongside an unchanged `decide_outcome` | Widening the enum would break durable records; additive costs nothing |
| D3 | Measured: 37 failed validations on unmodified main tracing to 31 active changes, with remediation "archive the active change(s)" | `INFORMATIONAL_PRODUCERS = {openspec.projection}`; its drift never affects the exit code | A repository always has active changes, so blocking on it blocks every PR forever; written as a requirement because the opposite reading looks like a reasonable future fix |
| D4 | `_default_architecture_producer` calls `build_provenance` then returns fresh unconditionally, reporting fresh where `make architecture-check` reports PROVENANCE_MISSING and exits 1 | `check_freshness` replaces `build_provenance`; unverifiable provenance maps to drift, not not-configured | Routing unverifiable evidence to not-configured would reintroduce fail-open through the classifier instead of the producer |
| D5 | Per-producer `_exit_code` maps NOT_CONFIGURED to 1 while `decide_outcome` folds it into DEGRADED/2 — neither is right for a gate | Exit codes derive from the breakdown; both existing entry points keep their current codes | Registry policy already rewrites a *required* not-configured to failed, so a survivor is always an optional owner, i.e. external degradation |
| D6 | ri-07 D4 and `orchestrator.check` deliberately never probe the index, so CI stays green without a database | Report `semantic.status = "not-attempted"` with a bounded reason; construct no indexer | not-configured would falsely assert a probe found no configuration; not-attempted makes no currency claim at all |
| D7 | Measured: 4 of 70 work-package files declare a context_impact block; 65 fail under `--strict-legacy` | Diff-scoped invocation, never `--strict-legacy`; validator exit 2 remapped to gate exit 1 | Enabling strict would make the gate red on arrival; the validator's usage-error code collides with the drift convention |
| D8 | ri-09 D3 states the registry does not structurally forbid a check-mode write and that ri-10 must assert rather than assume | Test enumerating `list_producers()`, digesting tracked *and* untracked paths against a dirty worktree | A runtime guard would change a seam both entry points depend on, for a property no adapter violates; strictly stronger than ri-09's tracked-tree assertion |
| D9 | The retired job and the producer delegate to the same emitter, so keeping both leaves two authorities that can disagree | Remove `validate-decision-index`; prove orphan detection via `tree_diff`'s `deleted` bucket first | An orphan's content is unchanged, so `git diff` structurally cannot see it — the replacement must be shown to cover the blind spot before the old job goes |
| D10 | 20 artifacts are stale on main, so a blocking gate cannot go green until they are regenerated | One commit containing only regenerated output, landing after the D4 producer fix | Acceptance outcome 4 is verifiable only if a commit exists where regeneration produces no diff; generated noise interleaved with logic hides real changes |
| D11 | Branch protection requires exactly six contexts and a PR cannot add a seventh | Ship the job plus the exact `gh api` call, and mark the promotion as a MANUAL task | Until applied the gate is "blocking job, not a required context" — precisely how docs/decisions/ drifted; recorded as a gap rather than described as done |

## Review Findings Summary

<!-- Populated in Phase C3 from artifacts/<package-id>/review-findings.json. -->

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 19/19
- **Tests mapped**: 19 requirements have at least one test
- **Evidence collected**: 0/19 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
