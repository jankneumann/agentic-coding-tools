# Harden Multi-Vendor Review Recovery

## Why

The multi-vendor review/converge loop has two divergent execution paths:

1. **In-process API** — `converge()` in `skills/autopilot/scripts/convergence_loop.py:177` orchestrates dispatch, synthesis, and iterative fix application all within a single Python process. Per-vendor findings live only in memory across the dispatch → synthesize boundary.
2. **CLI dispatcher** — `skills/parallel-infrastructure/scripts/review_dispatcher.py` writes each vendor's findings to disk (`<output_dir>/findings-{vendor}-{review_type}.json`) **before** `consensus_synthesizer.py` reads them. The two stages are decoupled by a serialization boundary.

This asymmetry causes a real failure mode: when synthesis crashes on a malformed input from one vendor (e.g., the latent `consensus_synthesizer.py:59` `line_range` shape bug — string instead of dict), the **CLI loses nothing** because every vendor's output is already on disk. The synthesis failure becomes a recoverable state — operators can manually re-run synthesis after fixing the underlying bug, swap synthesizers, or hand-edit one vendor's file. The **in-process API loses everything** — minutes of multi-vendor review work vanish with the exception, because the in-memory findings are never materialized.

The pattern observed during the original incident: when `converge()` failed, the recovery was to re-run the same logic via the CLI of the dispatcher. That worked because the CLI's per-vendor checkpointing happened to land the data on disk before the same crash recurred — and a human operator stepped in to drive the re-run.

We should make the **durable checkpoint** first-class instead of accidental. We will NOT attempt automatic recovery in this proposal because the bugs that cause synthesis failure (like the `line_range` shape mismatch) live in `Finding.from_dict()` — a parser that runs in BOTH the in-process synthesizer AND any CLI subprocess invoking the same module. An auto-fallback to the CLI would re-execute the same buggy code from a subprocess and fail identically. Multi-vendor review of an earlier draft of this proposal converged on this point unanimously.

What this proposal DOES deliver:

- The in-process API checkpoints vendor findings to disk **before** synthesis runs, using the same on-disk layout the CLI dispatcher already uses.
- When synthesis crashes, the checkpoint survives. An operator can manually re-run `consensus_synthesizer.py` against the checkpoint after diagnosing or fixing the underlying issue.
- `ConvergenceResult` gains observability fields so callers can detect that synthesis failed and a manual recovery is needed.
- Structured ERROR-level log entries fire when synthesis crashes with checkpoints in place (or when the checkpoint write itself fails), so chronic synthesis failures surface in log aggregation tools even if no human notices the immediate exception. Logs use Python's standard `logging` module — no new HTTP audit endpoint, no new coordinator bridge function (round 2 review caught that those didn't exist; building them is out of scope for this proposal).
- Path-safety guards on caller-supplied `artifacts_dir` and vendor names prevent symlink injection and path traversal.

What this proposal explicitly does NOT deliver (Non-goals, deferred to follow-up proposals):

- **Automatic recovery from synthesis failures.** A separate, narrower proposal will fix `consensus_synthesizer.py:59` `line_range` parsing. Once the deterministic bugs are gone, a third proposal MAY layer automatic recovery on top of the durable checkpoint this proposal provides.
- **Subprocess fallback to the synthesizer CLI.** Same reason — it doesn't escape the shared parser.
- **Schema tightening on `finding.schema.json`.** We document the wire format as it is today (permissive on `line_range`); the bug-fix proposal will tighten it.

## What Changes

- **NEW**: `skills/parallel-infrastructure/scripts/checkpoint_findings.py` — small module with `write_vendor_findings()`, `read_vendor_findings()`, `write_manifest()`, `read_manifest()`, `_validate_path_safety()`. Single source of truth for the on-disk checkpoint format. Located under `parallel-infrastructure/` so the dependency direction is one-way (`autopilot` imports from `parallel-infrastructure`, not the reverse).
- **MODIFIED**: `skills/autopilot/scripts/convergence_loop.py` — `converge()` checkpoints per-vendor findings to `<artifacts_dir>/.review-cache/` BEFORE invoking `synthesizer.synthesize()`. The checkpoint write happens unconditionally on successful dispatch. If synthesis raises, the exception propagates to the caller (no fallback) but the checkpoint files survive on disk for manual recovery.
- **MODIFIED**: `ConvergenceResult` dataclass — gains `checkpoint_dir: Path | None` (set when checkpoint was written successfully). Defaults preserve backward compatibility for existing consumers. (An earlier draft also added `synthesis_failed: bool`; round 2 review pruned it as unreachable — the Python exception is already an observable signal that synthesis failed.)
- **MODIFIED**: `skills/parallel-infrastructure/scripts/review_dispatcher.py` — `write_manifest()` calls the shared helper. Per-vendor finding-file writes also route through the helper. **Behavior change**: the manifest gains new fields (`schema_version`, `change_id`, `created_at`, `vendors[]`) while preserving all existing fields (`review_type`, `target`, `dispatches[]`, `quorum_requested`, `quorum_received`). Per-vendor files preserve their existing wrapper shape (`{review_type, target, reviewer_vendor, findings: [...]}`). **No artifact relocation** — files stay where the dispatcher already writes them; the manifest format becomes a strict superset.
- **NEW SPEC**: `skill-workflow` capability gains 4 ADDED requirements: checkpoint layout, in-process checkpointing, observability fields, and path safety. Plus 1 requirement for audit emission of synthesis-failure-with-checkpoint events.
- **NEW TESTS**: Round-trip tests for `checkpoint_findings.py`, integration test that injects a synthesis-time exception and asserts the checkpoint files survive on disk and `ConvergenceResult.synthesis_failed=True`.

### Selected Approach

**Approach 1 (revised): Durable checkpoint, manual recovery** — selected at Gate 1 originally as "auto-fallback to CLI subprocess"; revised after multi-vendor PLAN_REVIEW caught that auto-fallback can't escape shared parser bugs.

The durability part of the original approach is preserved. The "automatic recovery" part is dropped because both the in-process synthesizer and any subprocess invocation share `Finding.from_dict()` — bugs in that parser cause both paths to fail identically. The honest recovery story is "checkpoint survives → human or follow-up tooling drives the recovery." That's a meaningful improvement over the current state (where findings vanish entirely on synthesis failure) without overstating what this proposal achieves.

This proposal pairs naturally with two follow-up proposals tracked as Post-Merge Actions: one to fix `consensus_synthesizer.py:59`, and one to optionally layer automatic recovery on top once the parser is reliable. Sequencing those as separate small proposals (rather than bundled here) is cleaner and lower-risk.

### Approaches Considered (revised)

**Approach 1 (revised): Durable checkpoint + manual recovery** — **SELECTED**
- **Description**: `converge()` checkpoints vendor findings to disk before synthesis. On synthesis exception, the checkpoint survives; the exception propagates. Human operators run the synthesizer manually after diagnosing the issue.
- **Pros**: Honest framing of what's actually achievable. Eliminates subprocess fallback complexity. Eliminates `--findings-dir` CLI extension. Eliminates secret-sanitization requirements (no diagnostics to sanitize). Significantly reduced LOC. No false promises about automatic recovery.
- **Cons**: Doesn't actually recover automatically — humans need to step in. Less impressive on paper than "automatic recovery" would have been.
- **Effort**: S

**Approach 2: Bundle the `line_range` parser fix into this proposal**
- **Description**: Fix `consensus_synthesizer.py:59` parser as part of this proposal so synthesis stops crashing on malformed input. With the parser reliable, eventually layer automatic recovery on top.
- **Pros**: One change covers the durability AND the underlying bug, so the recovery story actually works.
- **Cons**: Violates the "narrow proposals" principle. Mixes a systemic-durability change with a specific bug fix; if either part stalls in review, the other is also blocked. The user explicitly requested separate filing.
- **Effort**: M

**Approach 3: Reject this proposal entirely**
- **Description**: The durable checkpoint + observability + audit fields aren't worth the engineering cost; the right move is to fix the parser bug and stop there.
- **Pros**: Smallest possible change.
- **Cons**: Leaves the in-process flow vulnerable to *future* synthesizer bugs (not just the current `line_range` one). The durability primitive has independent value beyond the specific motivating bug — every future synthesis-time exception loses findings without it.
- **Effort**: trivial (file the bug fix only)

**Recommended (and selected): Approach 1 (revised).** Closes the *systemic* durability gap. The recovery automation is layerable later, on a known-reliable parser, in a separate small proposal. The user's preference for narrow proposals is preserved.

### Earlier approach (NOW REJECTED)

The original Approach 1 was "auto-fallback to CLI subprocess." Multi-vendor PLAN_REVIEW (claude + codex + gemini) converged on rejecting this: the CLI subprocess loads findings via the same `Finding.from_dict()` parser, so deterministic synthesizer bugs fail both paths identically. The fallback would log audit events about a recovery that didn't actually happen. The current Approach 1 is the corrected version after that review.

## Impact

- **Affected specs**: `skill-workflow` (5 ADDED requirements covering checkpoint layout, in-process checkpointing, observability fields, audit logging, path safety).
- **Affected code**:
  - **NEW**: `skills/parallel-infrastructure/scripts/checkpoint_findings.py` — shared write/read helpers + path-safety validation.
  - **MODIFIED**: `skills/autopilot/scripts/convergence_loop.py` — pre-synthesis checkpoint, `ConvergenceResult` shape changes.
  - **MODIFIED**: `skills/parallel-infrastructure/scripts/review_dispatcher.py` — call `checkpoint_findings.write_*()` for both per-vendor files and manifest.
  - **NEW TESTS**: under `skills/tests/parallel-infrastructure/` (helper) and `skills/tests/autopilot/` (integration).
- **Coordination claims**: planning-time lock keys (TTL=0) on `convergence_loop.py` and `consensus_synthesizer.py` — though `consensus_synthesizer.py` is now untouched by this proposal (the `--findings-dir` CLI extension is dropped).
- **Operational defaults**:
  - Checkpoint location: `<artifacts_dir>/.review-cache/` for in-process callers; CLI dispatcher continues writing directly under `--output-dir` (no relocation, just routing through the shared helper for the manifest format).
  - Manifest format: superset of existing; old fields preserved.
  - Per-vendor finding files: existing wrapper-object shape (`{review_type, target, reviewer_vendor, findings: [...]}`) preserved.
  - On synthesis failure with checkpoint present: original exception propagates to caller; `ConvergenceResult.synthesis_failed=True` if any partial result is constructed; audit event records the failure with checkpoint path.
- **Backwards compatibility**: existing `ConvergenceResult` consumers continue to work (new fields default to `None`/`False`). Existing CLI consumers reading the manifest continue to work (every existing field is preserved). No artifact paths move.
- **Non-goals** (out of scope for this change):
  - Fix for `consensus_synthesizer.py:59` `line_range` type bug — separate Post-Merge Action proposal.
  - Automatic recovery from synthesis failure — DEFERRED. Layerable in a future proposal once the parser is reliable.
  - CLI subprocess fallback — DROPPED after multi-vendor review caught the architectural flaw.
  - Adding `--findings-dir` mode to `consensus_synthesizer.py` — DROPPED with the subprocess fallback. Not needed if no one is invoking the CLI from converge().
  - Secret sanitization on diagnostics — DROPPED with the subprocess fallback (no stderr to capture, no subprocess exception messages to sanitize).
  - Cross-process locking on `.review-cache/`. Single converge() call owns its checkpoint directory; concurrent calls use distinct artifacts_dir paths by construction.
  - Adaptive timeouts. No subprocess; no timeout to tune.
  - Fallback latency metrics (Langfuse / StatsD).

## Post-Merge Actions

These are not tasks of this proposal:

- **Bug fix proposal**: file a narrow proposal fixing `consensus_synthesizer.py:59` `Finding.from_dict()` to handle `line_range: "10-20"` (string form) by parsing it into `{start, end}`. The new proposal SHALL reference this proposal as motivation and SHALL tighten `contracts/finding.schema.json` to reject only the malformed string shape (this proposal accepts both shapes for backward compatibility).
- **Optional automatic-recovery proposal**: after the parser bug is fixed, file a follow-up that layers automatic recovery on top of this proposal's durable checkpoint. With the parser reliable, "auto-fallback to CLI subprocess" becomes a meaningful improvement instead of a paper-thin one. Whether this is worth doing depends on observed audit-event frequency (R5 events) — if synthesis failures with checkpoints are rare in practice, manual recovery is sufficient and we skip the third proposal.
- **Audit observation**: monitor production audit logs for `convergence.synthesis_failed_with_checkpoint` events. A sustained stream over multiple weeks SHOULD prompt prioritizing the parser fix.

## Open Questions

- **Q1**: Should the checkpoint directory survive `/cleanup-feature` for forensic value, or be deleted along with other artifacts? Default plan: delete (matches existing review artifact lifecycle). This proposal does NOT add a SHALL requirement for cleanup deletion (such a requirement would have no implementation owner here — `/cleanup-feature` would need its own task). If retention is desired, file a follow-up.
- **Q2**: Will the dormant `harness-engineering-features` proposal's planned `ConvergenceResult` shape changes conflict with our `checkpoint_dir` / `synthesis_failed` additions when it resumes? Mitigation: planning-time lock keys make contention visible. Merge order resolves.
