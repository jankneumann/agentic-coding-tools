# Migrate discovery generators to emit candidate-work stubs

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `migrate-discovery-generators-to-emit-candidate-work-stubs`
> Roadmap item: `ri-12`
> Effort: M
> Priority: 2

## Why

ri-11 established `openspec/schemas/candidate-work.schema.json` as the one shape
that discovery producers and proposal/roadmap consumers share, but the system still
has three disconnected producer shapes. Bug-scrub writes findings, improve-harness
writes a markdown proposal stub, and explore-feature writes a rich shortlist. The
consumer validates canonical stubs if they are supplied, but does not rank them or
turn an approved stub into roadmap work. The discovery back-edge therefore still
requires a human to translate fields and edit intermediate artifacts.

## What Changes

1. Add deterministic adapters for bug-scrub, improve-harness, and explore-feature
   that emit canonical candidate-work sidecars without replacing their existing
   rich reports.
2. Validate every sidecar through one shared ri-11 validation/serialization seam
   before atomic persistence. Invalid input fails closed and preserves the prior batch.
3. Add a distinct mixed candidate-work ranking lane to `/prioritize-proposals`, preserving
   provenance and producing a stable order across stubs from all three generators.
4. Add a reusable `/plan-roadmap` candidate intake seam that maps one validated,
   approved stub to one roadmap item and then delegates mutation to the existing
   new-roadmap or refine-roadmap transaction.
5. Document output paths, compatibility behavior, and the boundary with ri-13's
   supervisor digest/approval conversation.

## Approaches Considered

### Approach 1: Additive sidecars plus shared consumer seams (Recommended)

Keep each producer's current human/rich artifact and emit a canonical JSON sidecar.
Consumers validate at their input boundary and use small deterministic mapping
helpers.

- **Pros**
  - Backward compatible with current reports and prompts.
  - One schema remains authoritative; no producer-specific consumer branches.
  - Deterministic adapters and mapping are directly testable.
  - ri-13 can call the same roadmap intake instead of duplicating field mapping.
- **Cons**
  - Adds sidecar files beside existing artifacts.
  - Requires explicit defaults for effort, priority, and slug construction.
- **Effort**: M

### Approach 2: Replace all producer artifacts with candidate-work arrays

Make candidate-work the only output of the three generators.

- **Pros**
  - Fewer files and shapes at first glance.
- **Cons**
  - The closed schema cannot carry bug-scrub diagnostics or explore-feature HMW,
    lens, and rejected-alternative evidence.
  - Breaks existing readers and tests.
- **Effort**: L

### Approach 3: Normalize stubs conversationally in the supervisor

Leave producers unchanged and ask the host model to translate outputs during every
digest or planning run.

- **Pros**
  - Smallest code change.
- **Cons**
  - Non-deterministic and not independently testable.
  - Repeats field mapping in each session and preserves the human-courier problem.
- **Effort**: S

### Selected Approach

**Approach 1**, approved at roadmap altitude through ri-12. It keeps the canonical
schema as the contract, preserves existing artifact consumers, and places validation
at the producer-write and consumer-read boundaries.

## Non-Functional Requirements

| Attribute | Metric | Target | Verifying phase |
|---|---|---|---|
| Compatibility | Existing rich outputs | Existing report/opportunity fields and legacy improve-harness flag remain usable | VALIDATE |
| Determinism | Same input bytes and repository state | Byte-identical candidate batch and stable mixed ranking | VALIDATE |
| Safety | Invalid candidate input | No partial sidecar or roadmap mutation | VALIDATE |
| Traceability | Stub provenance | 100% of emitted stubs include source artifact, finding IDs, and generator | VALIDATE |
| Isolation | Roadmap writes | Existing new/refine transaction remains the sole mutation boundary | VALIDATE |

## Impact

- `skills/bug-scrub/`, `skills/improve-harness/`, `skills/explore-feature/`
- `skills/prioritize-proposals/`, `skills/plan-roadmap/`
- Focused tests under each skill and cross-skill tests under `skills/tests/`
- OpenSpec deltas for `skill-workflow` and `roadmap-orchestration`

## Out of Scope

- Changing the canonical candidate-work schema introduced by ri-11.
- Replacing producer-specific rich reports with the canonical stub.
- Implementing ri-13's digest, scoring rubric, decision ledger, or supervisor UI.
- Writing directly to an existing `roadmap.yaml` outside refine-roadmap preview/apply.

## Dependencies

- ri-11 / `define-canonical-candidate-work-schema` — completed in commit `4c04f159`.
- ri-13 / `add-supervisor-candidate-work-digest` — active downstream consumer; its
  approval routing should call the reusable seam created here.

## Acceptance Outcomes

- All three generators emit stubs that validate against the canonical schema,
  covered by tests per generator.
- An approved stub becomes a roadmap item via `/plan-roadmap` without hand-editing
  intermediate artifacts.
- `/prioritize-proposals` successfully ranks a mixed batch of stubs from all three
  generators.
