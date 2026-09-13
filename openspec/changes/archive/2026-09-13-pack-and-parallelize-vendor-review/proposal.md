# Change: pack-and-parallelize-vendor-review

**Series**: multi-vendor review robustness (phase 3 of 3)
**Depends on**: `harden-review-dispatch-parse-and-timeouts`
**Prefers**: `ledger-driven-review-convergence` (open ledger items in the packet)
**Related, not blocked on**: `build-structured-vendor-result-channel` (dg-02)

## Why

Even after parse/timeout hardening (phase 1) and ledger-driven rounds (phase 2),
a review job is still a 10-minute repo walk by a coding agent, dispatched
**sequentially**. Successful Claude reviews in the archive have p50 = 410s and
p90 = 633s. Four vendors × that budget is 20–40 minutes per round *before*
fixes. Operators then shrink the timeout, which recreates phase 1 failures.

Two more facts:

- The spec already says `ReviewDispatcher SHALL execute vendor reviews in
  parallel (concurrent subprocess invocation)`. The implementation comment is
  `Currently dispatches sequentially.` Phase 3 implements an existing SHALL.
  Sequential dispatch was justified by a shared-worktree / detached-HEAD guard
  (#349). Review is read-only; that guard does not apply.
- Only Grok review mode uses `--json-schema`. Codex, Claude, Antigravity, and
  pi are prompt-only. Phase 1 derives the prompt and repairs once. Phase 3
  turns on each vendor's structured-output flag **where the CLI actually has
  one**, which is the review-scoped slice of dg-02. It does not replace regex
  async polling or cloud lock-release.

Timeouts are a symptom of asking a coding agent to explore a repo instead of
sending a packed review packet (diff + traced specs + schema + open ledger
items). Context-engineering already describes that pack; review dispatch does
not use it. Semantic context injection exists and is **off** by default — this
change does not turn it on; it packs the explicit artifacts.

## What Changes

- A **review packet** is the default review input: unified diff (or last-fix
  delta when phase 2 is present), traced spec excerpts, the schema-derived
  prompt contract, and open ledger items when `.review-ledger/` exists.
  Tools remain available as overflow when the packet exceeds a size budget;
  they are not the default way to obtain the artifact.
- `dispatch_and_wait` starts vendor subprocesses **concurrently** and collects
  as each completes. Wall clock becomes `max(vendor)` instead of `sum`.
  Read-only cwd: the existing worktree, or a throwaway snapshot if a vendor
  CLI refuses a dirty tree. No shared-write.
- For each vendor whose CLI has a verified structured-output / JSON-schema
  flag, review mode uses it (Grok already does; Codex/Claude/pi/agy are
  probed and wired only when the flag is real). Unverified flags are not
  guessed — that class of bug is what `add-agy-grok-pi-harnesses` spent a
  phase fixing.
- Acceptance target: p50 wall clock for a 4-vendor implementation review
  under 4 minutes on a fixture the size of a typical change; quorum_lost
  rate well below the 29% archive baseline when combined with phase 1.

Non-goals: dg-02 completion-ledger / regex-poll replacement / cloud
list-and-release-by-agent. Non-goals: enabling `SEMANTIC_CONTEXT_INJECTION`.
Non-goals: ambient post-commit review.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Performance | Wall clock of a 4-vendor impl review on a fixture | p50 < 4 minutes | Evidence: timed fake-CLI fixture (subprocess sleep stubs prove concurrency; live p50 is documented as a follow-up measurement) |
| Performance | Dispatch overlap | Two vendors' subprocesses overlap in time | Unit test with recorded start/end |
| Resilience | Packet over budget | Tools overflow is used; dispatch still returns | Unit test |
| Compatibility | Phase 2 ledger absent | Packet still builds from diff + specs + schema | Unit test |
| Compatibility | Existing Grok `--json-schema` | Unchanged | Existing dispatcher tests |
| Observability | Packet checksum | Written next to the prompt in the round directory | Unit test |

## Approaches Considered

### Approach 1: Packed packet, concurrent CLI, structured-output flags where verified

Pack the review input. Run CLIs concurrently. Turn on real JSON-schema flags
per vendor after an empirical probe recorded in this change.

- **Pros**: Implements an existing parallel SHALL; attacks the actual timeout
  cause (repo walk); keeps CLI reviewers; scoped so dg-02 can still replace
  async polling later without a second packet format.
- **Cons**: Live 4-minute p50 depends on vendors actually finishing faster
  once they stop walking; concurrency tests need fake CLIs; empirical probe
  of Codex/Claude/pi/agy flags is a planning/implementation checkpoint.
- **Effort**: M

### Approach 2: SDK-only one-shot reviews

Drop CLI review. Send the packet through SDK `response_format`.

- **Pros**: Structured output is native; easy concurrency.
- **Cons**: Abandons the CLI path autopilot uses; SDK adapters are incomplete
  (dg-02 already tracks this); Grok CLI structured output would be orphaned.
- **Effort**: L

### Approach 3: Wait for dg-02 then parallelize

Do not pack or parallelize until every adapter is structured-envelope +
completion-ledger.

- **Pros**: One cutover.
- **Cons**: dg-02 is skipped/re-homed and includes cloud lock-release;
  sequential 40-minute rounds continue until then; the spec's parallel SHALL
  stays unimplemented.
- **Effort**: L (wait) + M

### Recommended

**Approach 1.** The spec already requires concurrent dispatch. Packing is
what makes the per-vendor budget in phase 1 honest. SDK-only and dg-02-wait
are larger than the problem.

### Selected Approach

Approach 1. Selected by the operator on 2026-09-11 when requesting proposals
for all three phases. No modifications. Structured-output flags are
**verify-then-wire**, never guessed.

## Impact

- **Affected specs**: `skill-workflow` — MODIFIED Parallel Review Dispatch
  (already SHALL concurrent; add packet + snapshot cwd). ADDED review packet,
  optional tool overflow, verify-then-wire structured output.
- **Affected code**:
  - `skills/parallel-infrastructure/scripts/review_dispatcher.py`
    (`dispatch_and_wait` concurrency)
  - new packet builder (parallel-infrastructure or context-engineering
    consumer)
  - `agent-coordinator/agents.yaml` review-mode args for vendors whose flags
    are verified
  - `skills/autopilot/scripts/convergence_loop.py` (pass packet path)
- **Related**: dg-02 owns async regex polling; this change must not add new
  `task_id_pattern` / `success_pattern` regexes. Grok `--json-schema` stays
  the injection path from phase 1 / ri-14.
