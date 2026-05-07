# Tasks — Harden Multi-Vendor Review Recovery

Tasks are ordered TDD test-first within each phase. Implementation tasks declare a `Dependencies:` line referencing the test task they are paired with. Spec scenario IDs reference `specs/skill-workflow/spec.md` — Requirement N, Scenario M is encoded as `skill-workflow.RN.SM` for brevity.

## Phase 0: Contracts and Shared Helper

- [ ] 0.1 Write tests for `checkpoint_findings.py` — round-trip, empty manifest, missing files, concurrent writes
  - **Spec scenarios**: skill-workflow.R1.S1 (round-trip), skill-workflow.R1.S2 (manifest sufficient), skill-workflow.R1.S3 (concurrent), skill-workflow.R2.S3 (empty round)
  - **Contracts**: `contracts/review-cache-layout.schema.json` (manifest), `contracts/finding.schema.json` (per-vendor file)
  - **Design decisions**: D2 (reuse CLI layout)
  - **Dependencies**: None — test file lives at `skills/tests/autopilot/test_checkpoint_findings.py`
- [ ] 0.2 Implement `skills/autopilot/scripts/checkpoint_findings.py` with `write_vendor_findings`, `read_vendor_findings`, `write_manifest`, `read_manifest`
  - **Dependencies**: 0.1
- [ ] 0.3 Author `contracts/review-cache-layout.schema.json` (manifest schema) and `contracts/finding.schema.json` (per-vendor finding schema) — JSON Schemas validating the on-disk format.
  - **Spec scenarios**: skill-workflow.R1.S1, skill-workflow.R1.S2
  - **Dependencies**: None (can run parallel with 0.1)
- [ ] 0.4 Author `contracts/README.md` documenting which contract sub-types were evaluated and which apply (no OpenAPI, no DB schema, no events — just JSON schemas for the on-disk layout).
  - **Dependencies**: 0.3

## Phase 1: Refactor `review_dispatcher.py` to use shared helper

This phase keeps CLI behavior unchanged while routing through the new shared module. Validates that `checkpoint_findings.py` is correct in production conditions before we add the in-process caller.

- [ ] 1.1 Write tests asserting `review_dispatcher.py` continues to produce byte-identical on-disk artifacts after refactor
  - **Spec scenarios**: skill-workflow.R1.S1, skill-workflow.R1.S2
  - **Dependencies**: 0.2
- [ ] 1.2 Replace inlined finding-writes (lines ~1360-1362) and manifest-writes (~1180-1208) in `review_dispatcher.py` with calls to `checkpoint_findings.write_vendor_findings()` and `write_manifest()`
  - **Dependencies**: 1.1, 0.2
- [ ] 1.3 Run the existing `parallel-infrastructure` test suite end-to-end; assert no regressions
  - **Dependencies**: 1.2

## Phase 2: Extract `load_findings_from_dir()` in `consensus_synthesizer.py`

Decouples the in-memory loader from the CLI argparse plumbing so converge() can call it directly when subprocess invocation is overkill (e.g., test fixtures, future native callers).

- [ ] 2.1 Write tests for `load_findings_from_dir()` — parse manifest + per-vendor files, return `dict[str, list[ReviewFinding]]`
  - **Spec scenarios**: skill-workflow.R1.S1
  - **Dependencies**: 0.2
- [ ] 2.2 Extract `load_findings_from_dir(path: Path) -> dict[str, list[ReviewFinding]]` from `consensus_synthesizer.py`'s existing CLI loading logic
  - **Dependencies**: 2.1
- [ ] 2.3 Verify the CLI entrypoint (`main()`) still produces identical `consensus-report.json` outputs for fixture inputs
  - **Dependencies**: 2.2

## Phase 3: ConvergenceResult observability fields

Lands the dataclass change first, before adding the recovery logic that sets the fields. This way every later test can assert on the fields without race conditions.

- [ ] 3.1 Write tests for `ConvergenceResult` shape — defaults are `recovered_via_fallback=False`, `fallback_diagnostics=None`
  - **Spec scenarios**: skill-workflow.R4.S1 (existing callers), skill-workflow.R4.S2 (recovery-aware), skill-workflow.R4.S3 (diagnostics only on fallback)
  - **Design decisions**: D3 (observable fields, not side-channel)
  - **Dependencies**: None
- [ ] 3.2 Add `recovered_via_fallback: bool = False` and `fallback_diagnostics: dict[str, Any] | None = None` to `ConvergenceResult`
  - **Dependencies**: 3.1
- [ ] 3.3 Run all existing converge() callers' tests; assert no regressions (backwards compatibility check)
  - **Dependencies**: 3.2

## Phase 4: In-process checkpointing in `converge()`

Adds the durability primitive. Synthesis still runs in-process; fallback comes in Phase 5.

- [ ] 4.1 Write tests for in-process checkpointing — successful path writes manifest+findings, synthesis-failure path leaves them intact
  - **Spec scenarios**: skill-workflow.R2.S1 (success path), skill-workflow.R2.S2 (failure path), skill-workflow.R2.S3 (empty round)
  - **Design decisions**: D2 (reuse CLI layout)
  - **Dependencies**: 0.2, 3.2
- [ ] 4.2 Modify `converge()` to call `checkpoint_findings.write_vendor_findings()` and `write_manifest()` after `orchestrator.dispatch_and_wait()` returns and before `synthesizer.synthesize()` runs
  - **Dependencies**: 4.1
- [ ] 4.3 Verify checkpoint files survive a synthesis exception (manual integration test in addition to unit tests)
  - **Dependencies**: 4.2

## Phase 5: CLI subprocess fallback

Adds the automatic recovery. Builds on Phase 4's checkpoint primitive.

- [ ] 5.1 Write tests for the success-recovery path — mock `synthesizer.synthesize` to raise, mock `subprocess.run` to return exit 0; assert `recovered_via_fallback=True` and `fallback_diagnostics` populated
  - **Spec scenarios**: skill-workflow.R3.S1 (recover via fallback), skill-workflow.R3.S4 (subprocess reuses canonical layout)
  - **Design decisions**: D1 (subprocess over native), D4 (re-raise original)
  - **Dependencies**: 4.2, 3.2
- [ ] 5.2 Write tests for the double-failure path — both raise; assert original exception bubbles with subprocess stderr tail attached
  - **Spec scenarios**: skill-workflow.R3.S2 (both fail), skill-workflow.R3.S3 (subprocess timeout)
  - **Design decisions**: D4 (re-raise original)
  - **Dependencies**: 4.2, 3.2
- [ ] 5.3 Implement `_invoke_synthesizer_cli(cache_dir, review_type, timeout=300) -> ConsensusReport` helper in `convergence_loop.py`
  - **Dependencies**: 5.1, 5.2
- [ ] 5.4 Wrap `synthesizer.synthesize()` call in `try/except Exception:` in `converge()`. On exception: invoke `_invoke_synthesizer_cli`, populate `recovered_via_fallback` + `fallback_diagnostics`. On both-failure: attach stderr tail to original exception via `__notes__` (Python 3.11+) and re-raise.
  - **Dependencies**: 5.3

## Phase 6: Audit log emission

Closes the observability loop — chronic primary failures surface in `query_audit`.

- [ ] 6.1 Write tests for audit emission — `convergence.fallback_recovered` on success-recovery, `convergence.fallback_failed` on double-failure, no event on happy path. Audit-emission failure does not mask result.
  - **Spec scenarios**: skill-workflow.R5.S1 (success emits one event), skill-workflow.R5.S2 (double-failure emits one event), skill-workflow.R5.S3 (audit failure does not mask)
  - **Design decisions**: D5 (audit failures do not mask)
  - **Dependencies**: 5.4
- [ ] 6.2 Implement audit event emission in `converge()` recovery branches. Use `coordination_bridge.try_emit_audit_event(...)` so coordinator unavailability is non-fatal. Wrap call in `try/except Exception:` with `logger.warning()` per D5.
  - **Dependencies**: 6.1

## Phase 7: Integration test reproducing the original failure

End-to-end test that pipes the latent `line_range` shape mismatch through the real (non-mocked) in-process synthesizer to confirm the fallback recovers it.

- [ ] 7.1 Author integration test — feed vendor findings with `line_range: "10-20"` (string) to `converge()`; in-process synthesizer raises (current bug); fallback CLI subprocess receives the same input and recovers (CLI also has the bug, but test fixture stubs the CLI to return a known-good consensus report). The test verifies the *plumbing* — not the bug fix.
  - **Spec scenarios**: skill-workflow.R3.S1, skill-workflow.R2.S2, skill-workflow.R5.S1
  - **Note**: The bug at `consensus_synthesizer.py:59` is fixed in a separate proposal; this test does NOT depend on that fix.
  - **Dependencies**: 6.2

## Phase 8: Documentation and cross-skill updates

- [ ] 8.1 Update `docs/parallel-agentic-development.md` Section 8.C with one paragraph documenting the recovery contract — readers debugging convergence failures need to know the fallback exists and how to read `recovered_via_fallback`.
  - **Dependencies**: 5.4
- [ ] 8.2 Update `skills/autopilot/SKILL.md` to mention the recovery semantics in the convergence-loop section.
  - **Dependencies**: 5.4
- [ ] 8.3 File the follow-up bug fix proposal for `consensus_synthesizer.py:59` `line_range` type handling (out of scope for this change, but noted in Open Questions). One-line tasks.md, single test, single fix.
  - **Note**: This task creates a *new* OpenSpec change, not part of this one. Performed during `/cleanup-feature` so the new proposal references this proposal as its motivation.
  - **Dependencies**: All prior phases (this proposal must land first)

## Out of Scope

The following are explicitly NOT part of this change. Listed here so reviewers can confirm the boundary:

- Fix for `consensus_synthesizer.py:59` `line_range` type bug — separate proposal (Phase 8.3 files it).
- Automatic re-dispatch of vendors when synthesis fails. The recovery is "make synthesis work with what we have," not "ask vendors again."
- Cross-process locking on `.review-cache/`. Single converge() call owns its checkpoint directory.
- Migration of fix-application loop (after consensus) to use checkpointing. Out of scope; the durability gap was at synthesis, not at fix application.
