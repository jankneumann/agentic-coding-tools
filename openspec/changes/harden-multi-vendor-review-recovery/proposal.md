# Harden Multi-Vendor Review Recovery

## Why

The multi-vendor review/converge loop has two divergent execution paths:

1. **In-process API** — `converge()` in `skills/autopilot/scripts/convergence_loop.py:177` orchestrates dispatch, synthesis, and iterative fix application all within a single Python process. Per-vendor findings live only in memory across the dispatch → synthesize boundary.
2. **CLI dispatcher** — `skills/parallel-infrastructure/scripts/review_dispatcher.py` writes each vendor's findings to disk (`<output_dir>/findings-{vendor}-{review_type}.json`) **before** `consensus_synthesizer.py` reads them. The two stages are decoupled by a serialization boundary.

This asymmetry causes a real failure mode: when synthesis crashes on a malformed input from one vendor (e.g., the latent `consensus_synthesizer.py:59` `line_range` type bug — string instead of dict), the **CLI loses nothing** because every vendor's output is already on disk. The synthesis failure becomes a recoverable state — operators can manually re-run synthesis, swap synthesizers, or hand-edit one vendor's file. The **in-process API loses everything** — minutes of multi-vendor review work vanish with the exception, because the in-memory findings are never materialized.

The pattern observed during the original incident: when `converge()` failed, the recovery was to re-run the same logic via the CLI of the dispatcher. That worked because the CLI's own per-vendor checkpointing happened to land the data on disk before the same crash recurred.

We should make this recovery first-class instead of accidental:

- The in-process API should checkpoint vendor findings to the same on-disk layout the CLI uses, so a synthesis failure leaves a forensically useful state.
- On synthesis failure, `converge()` should automatically fall back to invoking the synthesizer CLI as a subprocess against those checkpointed files. The CLI is the more conservative, file-based path; using it as recovery converts a hard crash into a degraded-but-successful path.
- The recovery SHALL be observable — callers must be able to tell whether the fallback fired so chronic primary-path failures don't go undetected.

This is structurally identical to the `coordination-bridge` pattern already used in this codebase: primary path (MCP transport) → fallback path (HTTP) → uniform result envelope. We mirror that convention here.

The latent `line_range` type bug at `consensus_synthesizer.py:59` triggered our investigation but is **out of scope for this proposal**. It will be filed as a separate narrow bug fix once this systemic recovery proposal lands. The recovery mechanism here protects against that bug *and* future bugs of the same shape.

## What Changes

- **MODIFIED**: `skills/autopilot/scripts/convergence_loop.py` — `converge()` gains:
  - **Checkpointing step**: After `orchestrator.dispatch_and_wait()` returns and before `synthesizer.synthesize()` runs, materialize per-vendor findings to `<artifacts_dir>/.review-cache/findings-{vendor}-{review_type}.json` and write a `review-manifest.json`. Reuses the exact filename pattern and manifest format produced by `review_dispatcher.py` so the CLI can read the cache without translation.
  - **CLI fallback**: Wrap `synthesizer.synthesize()` in a try/except. On any synthesis exception, invoke `consensus_synthesizer.py` as a subprocess pointed at the checkpoint directory, parse its consensus report, and return that. If the CLI also fails, raise the original synthesis exception (preserving the primary diagnosis).
  - **Observable result**: `ConvergenceResult` gains two fields — `recovered_via_fallback: bool` (default `False`) and `fallback_diagnostics: dict | None` (containing the original exception class/message and the CLI subprocess stderr tail when fallback fired). Audit log entries are emitted when fallback succeeds AND when it fails.
- **MODIFIED**: `skills/parallel-infrastructure/scripts/consensus_synthesizer.py` — extract a small `load_findings_from_dir(path: Path) -> list[ReviewFinding]` helper that converge() can call instead of subprocess-invoking the CLI when running in-process is acceptable. The CLI fallback uses the subprocess path; the helper is reused by tests and by future native callers. **No behavior change** to the CLI entrypoint.
- **MODIFIED**: `skills/autopilot/scripts/convergence_loop.py` and the `ConvergenceResult` dataclass — add result-shape changes described above.
- **NEW**: `skills/autopilot/scripts/checkpoint_findings.py` — small module with `write_vendor_findings(artifacts_dir, vendor_findings, review_type) -> Path` and `read_vendor_findings(cache_dir) -> dict[str, list[ReviewFinding]]` helpers. Single-source-of-truth for the on-disk layout, importable by both `convergence_loop.py` and the CLI dispatcher (which currently has the layout inlined).
- **MODIFIED**: `skills/parallel-infrastructure/scripts/review_dispatcher.py` — replace the inlined `findings-{vendor}-{review_type}.json` writes (lines ~1360-1362) with calls to `checkpoint_findings.write_vendor_findings()`. Pure refactor; same on-disk artifacts.
- **NEW SPEC**: `skill-workflow` capability gains ADDED requirements for the recovery contract, the on-disk checkpoint format, and the result-shape changes.
- **NEW TESTS**: Unit tests for checkpointing (round-trip), the CLI-fallback path (mocked subprocess), and observability fields. Integration test that injects a synthesis-time exception and asserts recovery succeeds with `recovered_via_fallback=True`.

### Selected Approach

**Approach 1: Auto-fallback to CLI subprocess** (user-selected at Gate 1).

Combined with:
- **Output location**: Reuse the CLI's existing `<change-id>/.review-cache/` layout — same directory, same filename pattern, same manifest. Maximum reuse; the synthesis CLI reads checkpoint files without translation.
- **Failure visibility**: Log + structured warning, but report success. `ConvergenceResult.recovered_via_fallback: bool` plus `fallback_diagnostics: dict | None` capture the recovery for postmortem without breaking existing callers' success paths.
- **Coordination with dormant `harness-engineering-features` proposal**: declare planning-time lock keys with `ttl_minutes=0` on `convergence_loop.py` and `consensus_synthesizer.py` so anyone resuming that proposal sees the contention.

Rationale: this is the smallest change that closes the durability gap. The CLI is already the more-robust path because it serializes vendor findings to disk before synthesis runs; making the in-process flow checkpoint to the same location and fall back to the same CLI on failure converts the existing accidental recovery pattern into a designed one. No two-path divergence risk because the fallback **literally invokes the same CLI binary**, not a parallel re-implementation.

### Approaches Considered

**Approach 1: Auto-fallback to CLI subprocess** — **SELECTED**
- **Description**: `converge()` checkpoints vendor findings to the CLI's on-disk layout before synthesis. On synthesis exception, subprocess-invokes `consensus_synthesizer.py` against the checkpoint and returns its result. Recovery is transparent except for an observability flag.
- **Pros**:
  - Smallest delta: the CLI already exists and works; we add a checkpoint step + a try/except.
  - No duplicate logic: the fallback path is the existing CLI binary, not a parallel re-implementation.
  - Forensic-friendly: failed synthesis leaves a usable on-disk state for manual recovery even if the fallback also fails.
  - Mirrors the `coordination-bridge` pattern already used in this codebase.
- **Cons**:
  - Subprocess overhead on the recovery path (not the hot path; only fires on synthesis failure).
  - Two code paths exist (in-process synthesizer + subprocess), but only on the failure branch. Same source-of-truth synthesizer logic in both.
- **Effort**: S

**Approach 2: Rebuild converge() to checkpoint-then-synthesize natively**
- **Description**: Refactor the in-process API so the dispatch → checkpoint → synthesize sequence is the only path, mirroring the CLI architecturally. No subprocess; no fallback. If synthesis fails, the on-disk state is still preserved and a manual rerun is possible.
- **Pros**:
  - Single architectural pattern; eliminates the subprocess-in-recovery flavor.
  - In-process and CLI paths fully converge in shape.
- **Cons**:
  - Larger refactor for the same end-state durability (checkpoint pre-synthesis is the load-bearing step).
  - Doesn't itself produce automatic recovery — synthesis failure still surfaces as an exception unless we also add fallback logic.
  - Higher chance of regressing existing callers during the refactor.
- **Effort**: M

**Approach 3: Both — CLI fallback now, native checkpointing later**
- **Description**: Ship Approach 1 as the immediate safety net, then file a follow-up proposal that converts the subprocess fallback into native checkpoint-then-synthesize.
- **Pros**:
  - Two-step risk reduction: durability first, architectural cleanup second.
- **Cons**:
  - Two proposals where one would do. Approach 1 already gives us the durability and observability we need.
  - Speculative future work — the subprocess-fallback shape may turn out fine in practice and never need refactoring. Pre-committing to a follow-up creates phantom roadmap.
- **Effort**: S + M (across two proposals)

**Recommended (and selected): Approach 1.** It closes the observed failure mode at minimum cost, reuses an existing CLI rather than a parallel implementation, and aligns with the `coordination-bridge` precedent for fallback-path patterns. Approach 2 can be revisited if the subprocess flavor proves operationally noisy, but we defer it on the principle of fixing only what's broken.

## Impact

- **Affected specs**: `skill-workflow` (new ADDED requirements for review-recovery contract, checkpoint format, and observability fields)
- **Affected code**:
  - **NEW**: `skills/autopilot/scripts/checkpoint_findings.py` — shared write/read helpers for the on-disk checkpoint layout.
  - **MODIFIED**: `skills/autopilot/scripts/convergence_loop.py` — checkpoint step, CLI fallback, ConvergenceResult shape.
  - **MODIFIED**: `skills/parallel-infrastructure/scripts/consensus_synthesizer.py` — extract `load_findings_from_dir()` helper; no CLI behavior change.
  - **MODIFIED**: `skills/parallel-infrastructure/scripts/review_dispatcher.py` — call `checkpoint_findings.write_vendor_findings()` instead of inlined writes.
  - **NEW TESTS**: under `skills/tests/autopilot/` and `skills/tests/parallel-infrastructure/` for round-trip, fallback, and observability.
- **Coordination claims**: planning-time lock keys (TTL=0) on `convergence_loop.py` and `consensus_synthesizer.py` so the dormant `harness-engineering-features` proposal sees contention if revived.
- **Operational defaults**:
  - Checkpoint location: `<artifacts_dir>/.review-cache/` — co-located with other review artifacts; deleted on `/cleanup-feature`.
  - Subprocess timeout for fallback CLI: 300s (matches vendor adapter default).
  - On fallback CLI failure: re-raise the **original** synthesis exception, attach CLI subprocess stderr tail to `fallback_diagnostics` for forensic pairing.
  - Audit log: emit on every fallback firing — both successful recovery and double-failure — so chronic primary-path issues surface in `query_audit`.
- **Backwards compatibility**: existing `ConvergenceResult` consumers continue to work — the two new fields default to `False` / `None`. Callers that want recovery semantics opt in by reading `recovered_via_fallback`.
- **Non-goals** (out of scope for this change):
  - Fix for `consensus_synthesizer.py:59` `line_range` type bug. Filed as separate narrow proposal once this lands. The recovery mechanism here protects against that bug *and* its analogues, so we don't need to bundle them.
  - Automatic re-dispatch of vendors when synthesis fails. The recovery is "make synthesis work with what we have," not "ask the vendors again."
  - Cross-process locking on `.review-cache/`. Single converge() call owns its checkpoint directory; concurrent calls use distinct artifacts_dir paths by construction.

## Open Questions

- **Q1**: Should the checkpoint directory survive `/cleanup-feature` for forensic value, or be deleted along with other artifacts? Default plan: delete (matches existing review artifact lifecycle), but flag for review at Gate 2.
- **Q2**: When the dormant `harness-engineering-features` proposal touches `convergence_loop.py` for the autonomous-author-response work, will its planned `ConvergenceResult` shape changes conflict with our `recovered_via_fallback` / `fallback_diagnostics` additions? Mitigation: the planning-time lock keys make the contention visible; merge order will determine which proposal does the rebase.
