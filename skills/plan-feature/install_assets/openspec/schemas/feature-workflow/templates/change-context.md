# Change Context: <change-id>

<!-- 3-phase incremental artifact:
     Phase 1 (pre-implementation): Req ID, Spec Source, Description, Contract Ref, Design Decision,
       Test(s) planned. Files Changed = "---". Evidence = "---".
     Phase 2 (implementation): Files Changed populated. Tests pass (GREEN).
     Phase 3 (validation): Evidence filled with "pass <SHA>", "fail <SHA>", or "deferred <reason>". -->

## Requirement Traceability Matrix

<!-- One row per SHALL/MUST requirement from specs/<capability>/spec.md.
     Req ID format: <capability>.<N> (sequential per capability).
     Phase 1: Fill Req ID, Spec Source, Description, Design Decision, Test(s).
       Contract Ref SHALL NOT be populated by hand when the capability has any traced
         contract document (a document declaring a `traceability`/`x-traceability` block,
         per trace-requirements-to-contracts design D8): run
         `packages/gen-eval/scripts/generate_contract_refs.py --change <change-id>` instead,
         which joins each row to the contract documents whose operations cite that
         requirement's derived identifier, by parse position — never by name similarity —
         and writes "---" where no operation cites it. Populate the column by hand only
         when `packages/gen-eval/scripts/generate_contract_refs.py` is absent (a repository
         without gen-eval): use the path to the contract file the requirement maps to
         (e.g., contracts/openapi/v1.yaml#/paths/~1users), or "---" if no contract applies.
       Design Decision: D# from design.md that this requirement validates (e.g., D3), or "---" if none.
       Files Changed and Evidence = "---".
     Phase 2: Fill Files Changed after implementation. Evidence still "---". Re-run
       generate_contract_refs.py if traceability citations changed during implementation.
     Phase 3: Fill Evidence with "pass <SHA>", "fail <SHA>", or "deferred <reason>". -->

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|

## Design Decision Trace

<!-- One row per decision from design.md. Omit section entirely if no design.md exists. -->

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|

## Review Findings Summary

<!-- Parallel workflow only. Synthesized from artifacts/<package-id>/review-findings.json.
     Omit section for linear workflow. -->

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

<!-- Populated during validation. Use exact counts. -->

- **Requirements traced**: 0/0
- **Tests mapped**: 0 requirements have at least one test
- **Evidence collected**: 0/0 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
