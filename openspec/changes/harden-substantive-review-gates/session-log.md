# Session Log: harden-substantive-review-gates

## Summary

The supervisor-roadmap failure investigation identified three review-pipeline guardrails that must land before retrying failed items. The user authorized the proposed recovery order, including this incident-scoped implementation and subsequent roadmap retries.

## Key Decisions

1. **Decision**: Land the review guardrails before retrying `ri-12` and `ri-09`.
   - **Rationale**: Retrying first could reproduce lost work or false convergence.
2. **Decision**: Use the narrow fail-closed approach.
   - **Rationale**: It closes demonstrated defects without absorbing broader active proposals.
3. **Decision**: Use local-parallel fallback for orchestration.
   - **Rationale**: Coordinator health checks passed, but this harness exposes no callable coordinator lock or work-queue adapter.

## Alternatives Considered

### Decision 2: Guardrail scope

| Alternative | Why Rejected |
|-------------|-------------|
| Add quorum-eligibility metadata everywhere | Overlaps active atomic-harness work and expands migration scope |
| Require evidence attestation from all vendors | Breaking change to current vendor prompts and emitters |

## Trade-offs

- **Chose explicit placeholder-only detection over a new evidence protocol because**: recovery needs a compatible incident fix now; positive evidence remains future work.

## Open Questions

- [ ] Whether the later structured vendor result channel should supersede the callback with a versioned sink interface.

## Relevant Files

- `skills/parallel-infrastructure/scripts/review_dispatcher.py` — result ingestion and concurrent collection.
- `skills/autopilot/scripts/convergence_loop.py` — checkpoint and convergence policy.
- `skills/parallel-infrastructure/scripts/review_ledger.py` — blocking and adjudication classification.

## Session Metadata

| Field | Value |
|-------|-------|
| Agent Type | codex |
| Session ID(s) | current recovery session |
| Date Range | 2026-09-13 — 2026-09-13 |
| Interactions | 1 implementation directive plus status updates |
| Source | live conversation and canonical roadmap artifacts |
