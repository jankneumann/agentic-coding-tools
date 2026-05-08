# Tasks — Harden Multi-Vendor Review Recovery (revised)

Re-scoped after multi-vendor PLAN_REVIEW caught that automatic CLI-subprocess fallback can't escape shared parser bugs in `Finding.from_dict()`. The proposal now delivers durable checkpoint + observability + audit + path safety; automatic recovery is deferred to a follow-up proposal that depends on a separate parser fix.

Tasks are TDD-ordered within each phase. Each test task lists the spec scenarios it encodes.

## Phase 0: Contracts and Shared Helper

- [ ] 0.1 Write tests for `checkpoint_findings.py` — round-trip, manifest preserves existing dispatcher fields, in-process callers may write empty `dispatches[]`, atomic-rename behavior, path-safety rejection of unsafe vendor names and artifacts_dir values, empty-round still produces manifest, missing per-vendor file caught.
  - **Spec scenarios**: skill-workflow.R1.S1 (round-trip), skill-workflow.R1.S2 (manifest sufficient), skill-workflow.R1.S3 (manifest preserves existing fields), skill-workflow.R1.S4 (in-process callers without dispatch metadata), skill-workflow.R1.S5 (atomic write), skill-workflow.R1.S6 (concurrent dirs), skill-workflow.R5.S1 (artifacts_dir normalized), skill-workflow.R5.S2 (vendor name rejected), skill-workflow.R5.S3 (review_type constrained), skill-workflow.R5.S4 (manifest-referenced paths stay within dir)
  - **Contracts**: `contracts/review-cache-layout.schema.json` (manifest superset), `contracts/finding.schema.json` (per-vendor wrapper-object shape)
  - **Dependencies**: None — test file lives at `skills/tests/parallel-infrastructure/test_checkpoint_findings.py`
- [ ] 0.2 Implement `skills/parallel-infrastructure/scripts/checkpoint_findings.py` with `write_vendor_findings` (atomic-rename), `read_vendor_findings`, `write_manifest` (atomic-rename + parent-dir fsync; accepts optional `dispatches`/`quorum_*` for CLI callers), `read_manifest`, `_validate_path_safety`. Place under `parallel-infrastructure/` to keep dependency direction one-way (autopilot imports from parallel-infrastructure).
  - **Dependencies**: 0.1
- [ ] 0.3 Author `contracts/review-cache-layout.schema.json` (superset schema preserving review_dispatcher.py fields + new fields) and `contracts/finding.schema.json` (per-vendor finding-FILE shape — wrapper object with `findings: [...]`, NOT raw array). Verify the schema accepts the existing `review_dispatcher.py:write_manifest()` output shape (so existing CLI consumers stay valid).
  - **Spec scenarios**: skill-workflow.R1.S3, skill-workflow.R1.S4
  - **Dependencies**: None (can run parallel with 0.1)
- [ ] 0.4 Author `contracts/README.md` documenting which contract sub-types were evaluated and which apply.
  - **Dependencies**: 0.3

## Phase 1: Migrate `review_dispatcher.py` to the shared helper

The CLI dispatcher routes through `checkpoint_findings.write_manifest()` and `write_vendor_findings()`. Per-vendor file contents and paths remain UNCHANGED (no relocation to `.review-cache/`). The manifest gains new fields while preserving all existing fields.

- [ ] 1.1 Write tests asserting (a) per-vendor `findings-{vendor}-{review_type}.json` files remain byte-identical (same wrapper-object shape, same path under `--output-dir`), (b) the new manifest contains every field the old manifest contained AND the new fields, (c) any caller fixture that parses `dispatches[]`, `quorum_requested`, `quorum_received` continues to parse the new manifest successfully, (d) any caller that globs `<output_dir>/findings-*-{review_type}.json` continues to find files.
  - **Spec scenarios**: skill-workflow.R1.S3
  - **Dependencies**: 0.2
- [ ] 1.2 Replace inlined finding-writes (~lines 1360-1362) and the `write_manifest()` method (~lines 1180-1208) in `review_dispatcher.py` with calls to `checkpoint_findings.write_vendor_findings()` and `checkpoint_findings.write_manifest()`. Pass through the dispatch metadata (`model_used`, `elapsed_seconds`, `error_class`) as the `dispatches=` argument.
  - **Dependencies**: 1.1, 0.2
- [ ] 1.3 Run the existing `parallel-infrastructure` test suite end-to-end; assert no regressions. Grep for any caller that reads the manifest or globs the output dir: `grep -rn "review-manifest\|findings-.*-plan\.json\|findings-.*-implementation\.json" skills/ tests/` and verify each accessed field/path still resolves.
  - **Dependencies**: 1.2

## Phase 2: ConvergenceResult observability fields

- [ ] 2.1 Write tests for `ConvergenceResult` shape — defaults are `checkpoint_dir=None` and `synthesis_failed=False`. Existing-caller backward-compat: every test that constructed a `ConvergenceResult` before this change continues to pass without modification.
  - **Spec scenarios**: skill-workflow.R3.S1 (existing callers), skill-workflow.R3.S2 (recovery-aware callers), skill-workflow.R3.S3 (synthesis_failed default)
  - **Dependencies**: None
- [ ] 2.2 Add `checkpoint_dir: Path | None = None` and `synthesis_failed: bool = False` to `ConvergenceResult`.
  - **Dependencies**: 2.1
- [ ] 2.3 Run all existing `converge()` callers' tests; assert no regressions. Discover callers explicitly: `grep -rn "from convergence_loop import\|import convergence_loop\|convergence_loop\.converge" skills/ tests/` and ensure every test module covering a discovered caller is in the test command.
  - **Dependencies**: 2.2

## Phase 3: In-process checkpointing in `converge()`

- [ ] 3.1 Write tests for in-process checkpointing — successful path writes manifest+findings AND populates `result.checkpoint_dir`; synthesis-failure path leaves manifest+findings on disk AND propagates the original exception (no fallback); empty review round still produces manifest.
  - **Spec scenarios**: skill-workflow.R2.S1 (success path), skill-workflow.R2.S2 (synthesis failure preserves checkpoint and propagates), skill-workflow.R2.S3 (empty round), skill-workflow.R2.S4 (checkpoint write permission error)
  - **Dependencies**: 0.2, 2.2
- [ ] 3.2 Modify `converge()` to call `checkpoint_findings.write_vendor_findings()` and `write_manifest()` after `orchestrator.dispatch_and_wait()` returns and BEFORE `synthesizer.synthesize()` runs. Pass `model_used`/`elapsed_seconds`/`error_class` from `ReviewResult` objects through to the manifest's `dispatches[]`. On synthesis exception, propagate the original exception (no try/except wrapper around synthesis); the exception propagates through the caller's normal path with the checkpoint already on disk.
  - **Dependencies**: 3.1
- [ ] 3.3 Verify checkpoint files survive a synthesis exception (manual integration test in addition to unit tests). Run a controlled synthesis-time exception and assert the checkpoint files exist and are parseable by an out-of-band synthesizer invocation.
  - **Dependencies**: 3.2

## Phase 4: Audit log emission for synthesis failures

- [ ] 4.1 Write tests for audit emission — `convergence.synthesis_failed_with_checkpoint` on synthesis failure with checkpoint, NO event on happy path, audit-emission failure does not mask the original synthesis exception.
  - **Spec scenarios**: skill-workflow.R4.S1 (failure emits one event), skill-workflow.R4.S2 (success emits no event), skill-workflow.R4.S3 (audit failure does not mask)
  - **Dependencies**: 3.2
- [ ] 4.2 Implement audit event emission in `converge()` synthesis-failure path. Use `coordination_bridge.try_emit_audit_event(...)` so coordinator unavailability is non-fatal. Wrap the audit call in `try/except Exception:` with `logger.warning()`. Emit event BEFORE re-raising the original synthesis exception. Include `checkpoint_dir` (absolute path post-`Path.resolve()`) in payload.
  - **Dependencies**: 4.1

## Phase 5: Integration test reproducing the original failure mode

- [ ] 5.1 Author integration test — feed vendor findings with `line_range: "10-20"` (the malformed string shape that motivated this proposal) to `converge()`; the in-process synthesizer raises (current bug). Assert: (a) the original exception propagates to the caller, (b) the checkpoint files exist on disk and contain the original findings, (c) running `consensus_synthesizer.py` manually against the checkpoint via subprocess STILL fails (because the parser bug is unfixed — that's a separate proposal), (d) the audit event was emitted with the correct fields. The test verifies durability and observability, NOT recovery.
  - **Spec scenarios**: skill-workflow.R2.S2 (synthesis failure preserves checkpoint), skill-workflow.R4.S1 (audit emitted)
  - **Note**: The bug at `consensus_synthesizer.py:59` is fixed in a separate proposal (see Post-Merge Actions in proposal.md); this test does NOT depend on that fix.
  - **Dependencies**: 4.2

## Phase 6: Documentation

- [ ] 6.1 Update `docs/parallel-agentic-development.md` Section 8.C with one paragraph documenting: (a) the durable-checkpoint contract, (b) how to manually invoke `consensus_synthesizer.py` against `.review-cache/` after a synthesis failure, (c) what `ConvergenceResult.synthesis_failed` and `checkpoint_dir` mean for callers, (d) explicit non-claim: this proposal does NOT introduce automatic recovery.
  - **Dependencies**: 4.2
- [ ] 6.2 Update `skills/autopilot/SKILL.md` to mention the checkpoint semantics in the convergence-loop section. Note that synthesis failures will continue to surface to the caller; the value of this proposal is durability for postmortem and manual recovery, not automatic recovery.
  - **Dependencies**: 4.2

## Out of Scope

- Fix for `consensus_synthesizer.py:59` `line_range` type bug — separate proposal filed as a Post-Merge Action (see `proposal.md`).
- Automatic recovery from synthesis failure — DEFERRED to a follow-up proposal that depends on the parser fix landing first.
- CLI subprocess fallback — DROPPED after multi-vendor review caught the architectural flaw (both paths share `Finding.from_dict()`).
- Adding `--findings-dir` mode to `consensus_synthesizer.py` — DROPPED with the subprocess fallback.
- Secret sanitization on diagnostics — DROPPED with the subprocess fallback (no diagnostics to sanitize).
- Cross-process locking on `.review-cache/`. Single converge() call owns its checkpoint directory; the atomic-rename requirement is intra-process safety.
- Migration of fix-application loop (after consensus) to use checkpointing.
- Adaptive subprocess timeout, fallback latency metrics, etc. (all moot without subprocess fallback).
- Relocating the CLI dispatcher's per-vendor finding files into `.review-cache/` (would break existing globs in other code).
- Tightening `finding.schema.json` to reject the malformed `line_range: "10-20"` string shape (intentionally permissive in this proposal; the bug-fix proposal will tighten it).
- Adding a SHALL requirement for `/cleanup-feature` to delete `.review-cache/`. No work package in this proposal modifies `/cleanup-feature`; an unowned SHALL would be a spec gap.
