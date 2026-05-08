# Plan Review — harden-multi-vendor-review-recovery

You are an independent reviewer evaluating an OpenSpec proposal that has just been refined via self-review (PLAN_ITERATE). Your job is to find issues another vendor would also flag, AND issues only your vendor would catch.

Read these artifacts in this directory:
- `proposal.md` — Why, What Changes, Selected Approach, Approaches Considered, Impact, Post-Merge Actions
- `design.md` — Architecture, Decision Log (D1-D7), Component Interactions, Data Shapes, Edge Cases, Test Strategy
- `tasks.md` — Phase 0-8 TDD-ordered tasks
- `specs/skill-workflow/spec.md` — 6 ADDED requirements with 24 scenarios
- `contracts/README.md`, `contracts/review-cache-layout.schema.json`, `contracts/finding.schema.json`
- `work-packages.yaml` — 5 packages forming a DAG

ALSO read these existing files (the proposal modifies them):
- `skills/autopilot/scripts/convergence_loop.py` — the in-process `converge()` API being modified
- `skills/parallel-infrastructure/scripts/consensus_synthesizer.py` — gaining `--findings-dir` mode
- `skills/parallel-infrastructure/scripts/review_dispatcher.py` — manifest write logic (lines ~1180-1208)

## Focus areas

1. **Architecture alignment** — Does the proposed checkpoint flow + subprocess fallback actually fix the durability gap, or does it just move the failure surface? Does the "manifest superset" pattern preserve all existing CLI consumer assumptions?
2. **Specification completeness** — Are there scenarios missing? Edge cases unconsidered? The 24 scenarios cover happy/failure paths — what failure modes are still uncovered?
3. **Contract consistency** — Does `review-cache-layout.schema.json` accept everything the existing `review_dispatcher.py:write_manifest()` writes? Are there fields the existing CLI consumers might trip on?
4. **Security** — Path safety (R6) covers vendor names and artifacts_dir, but are there other inputs that could be hostile? What about vendor-supplied `findings_path` strings the manifest references?
5. **Work package validity** — Are write_allow scopes correct? Are the LOC estimates plausible (1190 total across 5 packages)? Is the DAG actually parallelizable in places, or is everything serial?
6. **Testability** — Every `SHALL`/`MUST` should map to at least one task in tasks.md. Find scenarios that don't map to a test task.

## Output format

Output ONLY valid JSON conforming to `review-findings.schema.json`. Each finding has:
- `id` (vendor-scoped)
- `type` (architecture | security | spec_gap | correctness | contract_mismatch | testability | observability | performance | resilience | compatibility | style)
- `criticality` (low | medium | high | blocking)
- `description` (1-2 sentences, specific, with file:line where applicable)
- `disposition` (fix | regenerate | accept | escalate)
- `resolution` (1 sentence proposed fix)
- `file_path` (optional)
- `line_range` (optional, as `{"start": N, "end": M}` or null)
- `vendor` (your vendor identifier)

## Cross-cutting check

The proposal documents a `consensus_synthesizer.py:59` line_range bug as out-of-scope. Verify this matches reality by reading lines 50-65 of that file. If the bug is NOT what the proposal claims, file a finding.

