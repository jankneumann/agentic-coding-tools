# Design: pack-and-parallelize-vendor-review

## Context

`dispatch_and_wait` loops vendors one-by-one. Each CLI is a tool-using coding
agent. `converge()`'s prompt truncates proposal/design to 4k chars and does
not attach the diff, so the agent tool-walks. Grok is the only vendor with
`--json-schema`. Parallel Review Dispatch is already a SHALL.

Issue #349 serialized PR vendor review because of a shared working tree and
a detached-HEAD guard. That is a write-conflict problem. Review dispatch is
read-only.

Phase 1 gives honest per-vendor timeouts and parse repair. Phase 2 gives a
delta (last-fix diff + open ledger). Phase 3 makes the job small enough and
overlapped enough that those timeouts are rarely hit.

## Goals / Non-Goals

**Goals**

- Review input is a packed packet, not a repo walk.
- Vendor subprocesses overlap.
- Structured-output flags are on for every vendor where they are empirically
  real.

**Non-goals**

- Replacing async `task_id_pattern` / `success_pattern` (dg-02).
- Turning on semantic context injection.
- Changing blocking policy or the ledger (phase 2).
- Guessing CLI flags.

## Decisions

### D1: Packet contents and budget

A review packet is a single markdown (or JSON envelope with a markdown body)
written to the round directory before dispatch:

1. Schema-derived prompt contract (phase 1 helper).
2. Unified diff: `git diff <base>...<head>` on round 1; last-fix diff on
   round N>1 when phase 2 is present; otherwise the same full diff.
3. Traced spec excerpts: `specs/**/spec.md` for the change, truncated per
   file to a cap.
4. Open ledger items if `.review-ledger/ledger.json` exists; omitted if not.
5. Packet checksum (sha256 of the body) in sidecar metadata.

Size budget: 80k tokens-equivalent ≈ 320k characters. If over budget, drop
spec excerpts first (keep paths), then truncate the diff with a note, then
set `tools_overflow=true` so the reviewer may Read/Grep. Under budget,
review mode SHOULD still pass the vendor's existing tool flags (read-only)
because some CLIs cannot disable tools, but the prompt says "the packet is
complete; do not explore."

Packet builder lives in
`skills/parallel-infrastructure/scripts/review_packet.py` so both converge
and CLI dispatcher share it. It MAY call context-engineering helpers if they
exist; it MUST work without `SEMANTIC_CONTEXT_INJECTION`.

### D2: Concurrent dispatch, read-only cwd

`dispatch_and_wait` uses a thread pool (or `concurrent.futures`) sized to
the number of available vendors. Each vendor gets the same `cwd` (the
worktree) because review is read-only. If a vendor CLI errors on concurrent
git index access, fall back to a `git worktree add --detach` snapshot per
vendor under `.git-worktrees/.review-snapshots/<round>/<vendor>/` and
destroy after collect. First implementation: shared cwd + overlap; snapshot
fallback is a documented escape hatch with a test that injects the error.

Do not share writeable state. Do not hold file locks for review.

Async (cloud) vendors keep their existing submit+poll path; those already
overlap if we submit all then poll. This change SHALL submit async tasks
concurrently rather than submit-and-wait-one-by-one (today's loop does
submit+poll per vendor before the next).

### D3: Verify-then-wire structured output

A table in `contracts/vendor-structured-output.md` records, per vendor:

- Flag(s) probed
- Probe date
- Result: `verified` | `absent` | `unprobed`
- Wiring: only `verified` rows change `agents.yaml` review args

Grok is `verified` (already wired). Codex, Claude, pi, agy start `unprobed`.
Implementation task 2.x is the empirical checkpoint: run the probe; if a
flag works, wire it; if not, leave prompt-only (phase 1 repair still
applies). **Do not copy Grok's `--json-schema` onto another binary.**

### D4: Fake-CLI concurrency test is the performance gate

The 4-minute live p50 cannot be a unit test. The required test starts two
stub processes that sleep 2s each; concurrent dispatch finishes in <3s,
sequential would take ≥4s. Live p50 is an evidence-phase measurement
recorded in the validation report, not a CI fail.

### D5: No new regex on the result path

Packet metadata and concurrent collect MUST use the existing
`ReviewResult` object and schema validation. Do not parse completion from
stdout with new regex. Async poll regex stays as it is until dg-02.

### Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| p50 < 4 min live | Validation-report measurement; not CI | deferred (safe: stub overlap test is CI) |
| Subprocess overlap | Fake-CLI start/end timestamps overlap | new |
| Packet over budget enables overflow | Unit test | new |
| Ledger-absent packet still builds | Unit test | new |
| Grok json-schema unchanged | Existing dispatcher tests | existing |
| Packet checksum written | Unit test | new |

## Alternatives Considered

See proposal. Design-level reject: multiprocessing vs threads — threads are
enough because work is subprocess I/O. Reject process-per-vendor worktree
as the default (expensive); keep as fallback (D2).

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Concurrent git status from two CLIs corrupts index | Read-only; snapshot fallback on detected error |
| Packet truncation hides the defect | Overflow tools; phase 2 delta keeps packets small |
| Empirical probe finds no flags | Phase 1 repair remains; change still ships parallel + packet |
| Live p50 still > 4 min | Packet should cut repo-walk; if not, file a follow-up rather than raising timeouts again |
| Thread pool vs signal handling on timeout | Keep per-future timeout; don't share one subprocess.run timeout across vendors |

## Migration Plan

Behavior change is internal to the dispatcher. Callers of `dispatch_and_wait`
keep the same signature plus an optional `packet_path`. Rollback: revert;
sequential dispatch returns. `agents.yaml` structured-output flags are
additive and vendor-local.
