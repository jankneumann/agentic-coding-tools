# Tasks — Harden Multi-Vendor Review Recovery (revised)

Re-scoped after multi-vendor PLAN_REVIEW caught that automatic CLI-subprocess fallback can't escape shared parser bugs in `Finding.from_dict()`. The proposal now delivers durable checkpoint + observability + audit + path safety; automatic recovery is deferred to a follow-up proposal that depends on a separate parser fix.

Tasks are TDD-ordered within each phase. Each test task lists the spec scenarios it encodes.

## Phase 0: Contracts and Shared Helper

- [ ] 0.1 Write tests for `checkpoint_findings.py` — round-trip, manifest preserves existing dispatcher fields, in-process callers may write empty `dispatches[]`, atomic-rename behavior, path-safety rejection of unsafe vendor names and artifacts_dir values, empty-round still produces manifest, missing per-vendor file caught.
  - **Spec scenarios**: skill-workflow.R1.S1 (round-trip), skill-workflow.R1.S2 (manifest sufficient), skill-workflow.R1.S3 (manifest preserves existing fields), skill-workflow.R1.S4 (in-process callers without dispatch metadata), skill-workflow.R1.S5 (atomic write), skill-workflow.R1.S6 (concurrent dirs), skill-workflow.R5.S1 (artifacts_dir normalized), skill-workflow.R5.S2 (vendor name rejected), skill-workflow.R5.S3 (review_type constrained), skill-workflow.R5.S4 (manifest-referenced paths stay within dir)
  - **Contracts**: `contracts/review-cache-layout.schema.json` (manifest superset), `contracts/finding.schema.json` (per-vendor wrapper-object shape)
  - **Dependencies**: None — test file lives at `skills/tests/parallel-infrastructure/test_checkpoint_findings.py`
- [ ] 0.2 Implement `skills/parallel-infrastructure/scripts/checkpoint_findings.py` with:
  - `_atomic_write_json(path: Path, payload: dict | list)` — single primitive used by ALL JSON writes in this module. Writes to `<path>.tmp`, calls `f.flush()` then `os.fsync(f.fileno())`, calls `os.replace(tmp, path)`, then opens the parent directory and calls `os.fsync(dirfd)` to persist the directory entry. Returns nothing on success; propagates OSError/PermissionError.
  - `write_vendor_findings(out_dir: Path, *, vendor: str, review_type: str, target: str, findings: list[dict], reviewer_vendor: str | None = None)` — KEYWORD-ONLY parameters after `out_dir` to prevent positional-argument confusion. Wraps the raw `findings` list into the `{review_type, target, reviewer_vendor, findings}` envelope before writing. `reviewer_vendor` defaults to `vendor` if not specified. Calls `_atomic_write_json` for the actual write. Validates `vendor` against `[A-Za-z0-9_-]+` regex BEFORE any disk operation. Validates each finding against `contracts/finding.schema.json` BEFORE writing.
  - `read_vendor_findings(out_dir: Path) -> dict[str, list[dict[str, Any]]]` — reads via the manifest's `vendors[]` index, validates path safety on each `findings_path`, returns vendor-keyed dict whose values are raw finding dicts (NOT a `Finding` class type — to avoid pulling consensus_synthesizer's class hierarchy into the helper). Callers that need `Finding` objects construct them themselves via `Finding.from_dict()`.
  - `write_manifest(out_dir: Path, *, review_type: str, target: str, vendors: list[dict], change_id: str | None = None, dispatches: list[dict] | None = None, quorum_requested: int | None = None, quorum_received: int | None = None)` — KEYWORD-ONLY after `out_dir`. `change_id`, `dispatches`, `quorum_*` all optional (CLI callers omit `change_id`; in-process callers populate it). When `dispatches` is None, writes `[]`. When `quorum_received` is None, computes from `dispatches` if available (count of `success=true`), else from `vendors[]` length. When `quorum_requested` is None, computes from `vendors[]` length. Calls `_atomic_write_json` for the actual write.
  - `read_manifest(out_dir: Path) -> dict[str, Any]` — returns parsed manifest as raw dict.
  - `_validate_path_safety(artifacts_dir: Path, vendor: str, review_type: str) -> Path` — `Path.resolve(strict=False)` for artifacts_dir; regex check on vendor (`^[A-Za-z0-9_-]+$`); enum check on review_type (`{"plan", "implementation"}`). Returns the resolved artifacts_dir.
  - `_safe_log_error(event: str, **payload)` — wraps `logger.error(event, extra=payload)` in `try/except Exception:` so a misconfigured custom log handler that raises in `emit()` does NOT mask the original exception that prompted the log call. The bare `try/except` is acceptable here — logging is best-effort and the catch block does nothing (no re-raise, no further log).
  - Verify existing vendor names in the codebase (`agents.yaml`, vendor adapter configs) match the regex; expand the regex or document migration if any non-compliant names found.
  - **Dependencies**: 0.1
- [ ] 0.3 Author `contracts/review-cache-layout.schema.json` (superset schema preserving review_dispatcher.py fields + new fields) and `contracts/finding.schema.json` (per-vendor finding-FILE shape — wrapper object with `findings: [...]`, NOT raw array). Tests:
  - **(a) Forward compat**: manifests written through the new `checkpoint_findings.write_manifest()` helper (with all new fields populated) SHALL validate against the schema.
  - **(b) Existing-consumer compat**: assemble a manifest with ONLY the legacy fields (`review_type`, `target`, `dispatches`, `quorum_requested`, `quorum_received`) and verify that any caller code reading those fields continues to work when handed a NEW-format manifest (i.e., the new fields don't shadow or rename existing ones).
  - **(c) Optional change_id**: manifests with `change_id: null` (CLI dispatcher) and `change_id: "some-id"` (in-process) BOTH validate.
  - Do NOT require pre-change legacy manifest JSON (manifests written by older versions of `review_dispatcher.py` lacking `schema_version` etc.) to validate against the new schema. They predate the proposal and will be regenerated next time the dispatcher writes.
  - **Spec scenarios**: skill-workflow.R1.S3, skill-workflow.R1.S4, skill-workflow.R1.S7 (change_id optional)
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

## Phase 2: ConvergenceResult observability field

- [ ] 2.1 Write tests for `ConvergenceResult` shape — default is `checkpoint_dir=None`. Existing-caller backward-compat: every test that constructed a `ConvergenceResult` before this change continues to pass without modification.
  - **Spec scenarios**: skill-workflow.R3.S1 (existing callers), skill-workflow.R3.S2 (recovery-aware callers can locate checkpoint)
  - **Dependencies**: None
- [ ] 2.2 Add `checkpoint_dir: Path | None = None` to `ConvergenceResult`. Do NOT add a `synthesis_failed: bool` field — round 2 review showed it would be unreachable from `converge()` (the synthesis exception propagates without a result being constructed).
  - **Dependencies**: 2.1
- [ ] 2.3 Run all existing `converge()` callers' tests; assert no regressions. Discover callers explicitly: `grep -rn "from convergence_loop import\|import convergence_loop\|convergence_loop\.converge" skills/ tests/` and ensure every test module covering a discovered caller is in the test command.
  - **Dependencies**: 2.2

## Phase 3: In-process checkpointing in `converge()`

- [ ] 3.1 Write tests for in-process checkpointing — successful path writes manifest+findings AND populates `result.checkpoint_dir`; synthesis-failure path leaves manifest+findings on disk AND propagates the original exception (no fallback); empty review round still produces manifest.
  - **Spec scenarios**: skill-workflow.R2.S1 (success path), skill-workflow.R2.S2 (synthesis failure preserves checkpoint and propagates), skill-workflow.R2.S3 (empty round), skill-workflow.R2.S4 (checkpoint write permission error)
  - **Dependencies**: 0.2, 2.2
- [ ] 3.2 Modify `converge()` to call `checkpoint_findings.write_vendor_findings()` and `write_manifest()` after `orchestrator.dispatch_and_wait()` returns and BEFORE `synthesizer.synthesize()` runs. Pass `model_used`/`elapsed_seconds`/`error_class` from `ReviewResult` objects through to the manifest's `dispatches[]`. Wrap `synthesizer.synthesize()` in a NARROW `try/except Exception:` that emits the structured-log entry (Phase 4) and then re-raises the ORIGINAL exception unmodified. The narrow try/except is necessary to log; it does NOT swallow, fall back, or transform the exception.
  - **Dependencies**: 3.1
- [ ] 3.3 Verify checkpoint files survive a synthesis exception (manual integration test in addition to unit tests). Run a controlled synthesis-time exception and assert the checkpoint files exist and are parseable by an out-of-band synthesizer invocation.
  - **Dependencies**: 3.2

## Phase 4: Structured-log emission for synthesis failures and checkpoint-write failures

This phase uses Python's standard `logging` module — NOT the coordinator audit endpoint. Round 2 review caught that `coordination_bridge.try_emit_audit_event()` does not exist and the agent-coordinator HTTP API has no `POST /audit/log` endpoint. Adding both is out of scope for this proposal; structured logging at level ERROR is sufficient for chronic-failure detection by log-aggregation tools.

- [ ] 4.1 Write tests for log emission — `convergence.synthesis_failed_with_checkpoint` ERROR-level log entry on synthesis failure with checkpoint, `convergence.checkpoint_write_failed` ERROR-level log entry on checkpoint write failure, NO log entry on happy path, logging failure does not mask the original exception (Python's `logging` already absorbs handler failures by default; verify this).
  - **Spec scenarios**: skill-workflow.R4.S1 (synthesis failure emits log entry), skill-workflow.R4.S2 (success emits no log entry), skill-workflow.R4.S3 (checkpoint write failure emits different log entry), skill-workflow.R4.S4 (logging failure does not mask)
  - **Dependencies**: 3.2
- [ ] 4.2 Implement log emission in `converge()`:
  - Use `checkpoint_findings._safe_log_error("convergence.synthesis_failed_with_checkpoint", **payload)` in the narrow synthesis try/except (Phase 3.2). Structured payload contains `change_id`, `review_type`, `original_exception_class`, `original_exception_message`, `checkpoint_dir`, `timestamp`. The helper passes the event string as `LogRecord.msg` AND as `extra={"event": ...}` so tests can assert on the structured field rather than rendered message text. After logging, re-raise the original exception.
  - Use `_safe_log_error("convergence.checkpoint_write_failed", **payload)` in a separate narrow try/except around `checkpoint_findings.write_*()`. Structured payload contains `change_id`, `review_type`, `original_exception_class`, `original_exception_message`, `artifacts_dir`, `timestamp`. After logging, re-raise the original OSError/PermissionError.
  - The `_safe_log_error` helper (defined in `checkpoint_findings.py` per task 0.2) wraps the actual `logger.error()` call in a bare try/except so a misconfigured custom log handler raising from `emit()` does NOT mask the original exception. Tests for Phase 4.1 SHALL include a fixture that installs a handler whose `emit()` raises and verify the original synthesis exception still propagates.
  - No coordinator dependency. No new bridge function. No new HTTP endpoint.
  - **Dependencies**: 4.1

## Phase 5: Integration test reproducing the original failure mode

- [ ] 5.1 Author integration test — feed vendor findings with `line_range: "10-20"` (the malformed string shape that motivated this proposal) to `converge()`; the in-process synthesizer raises (current bug). Assert: (a) the original exception propagates to the caller, (b) the checkpoint files exist on disk and contain the original findings, (c) running `consensus_synthesizer.py` manually against the checkpoint via subprocess STILL fails (because the parser bug is unfixed — that's a separate proposal), (d) the structured `convergence.synthesis_failed_with_checkpoint` log entry was emitted with the correct fields (assert on `extra["event"]` and payload keys, not on rendered message text). The test verifies durability and observability, NOT recovery.
  - **Spec scenarios**: skill-workflow.R2.S2 (synthesis failure preserves checkpoint), skill-workflow.R4.S1 (synthesis failure log entry emitted)
  - **Note**: The bug at `consensus_synthesizer.py:59` is fixed in a separate proposal (see Post-Merge Actions in proposal.md); this test does NOT depend on that fix.
  - **Dependencies**: 4.2

## Phase 6: Documentation

- [ ] 6.1 Update `docs/parallel-agentic-development.md` Section 8.C with one paragraph documenting: (a) the durable-checkpoint contract, (b) how to manually invoke `consensus_synthesizer.py` against `.review-cache/` after a synthesis failure, (c) what `ConvergenceResult.checkpoint_dir` means for callers, (d) the `convergence.synthesis_failed_with_checkpoint` and `convergence.checkpoint_write_failed` log entries operators can monitor, (e) explicit non-claim: this proposal does NOT introduce automatic recovery.
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
