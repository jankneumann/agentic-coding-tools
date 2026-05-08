# Tasks — Harden Multi-Vendor Review Recovery

Tasks are ordered TDD test-first within each phase. Implementation tasks declare a `Dependencies:` line referencing the test task they are paired with. Spec scenario IDs reference `specs/skill-workflow/spec.md` — Requirement N, Scenario M is encoded as `skill-workflow.RN.SM` for brevity.

## Phase 0: Contracts and Shared Helper

- [ ] 0.1 Write tests for `checkpoint_findings.py` — round-trip, empty manifest, missing files, concurrent writes, schema validation rejects malformed findings before write, atomic-rename behavior, path-safety rejection of unsafe vendor names and `artifacts_dir` values
  - **Spec scenarios**: skill-workflow.R1.S1 (round-trip), skill-workflow.R1.S2 (manifest sufficient), skill-workflow.R1.S3 (concurrent), skill-workflow.R1.S4 (manifest superset), skill-workflow.R1.S5 (in-process callers), skill-workflow.R1.S6 (findings rejected on schema violation), skill-workflow.R1.S7 (manifest atomic write), skill-workflow.R2.S3 (empty round), skill-workflow.R6.S1 (artifacts_dir normalized), skill-workflow.R6.S2 (vendor name rejected), skill-workflow.R6.S3 (review_type constrained)
  - **Contracts**: `contracts/review-cache-layout.schema.json` (manifest superset), `contracts/finding.schema.json` (per-vendor file)
  - **Design decisions**: D2 (reuse CLI layout), D6 (manifest is superset), D7 (--findings-dir CLI mode)
  - **Dependencies**: None — test file lives at `skills/tests/autopilot/test_checkpoint_findings.py`
- [ ] 0.2 Implement `skills/autopilot/scripts/checkpoint_findings.py` with `write_vendor_findings` (validates against finding.schema.json before write), `read_vendor_findings`, `write_manifest` (writes superset shape; in-process callers omit dispatches; atomic-rename), `read_manifest`, `_validate_path_safety`
  - **Dependencies**: 0.1
- [ ] 0.3 Author `contracts/review-cache-layout.schema.json` (superset schema preserving review_dispatcher.py fields + new fields) and `contracts/finding.schema.json` (per-vendor finding schema) — JSON Schemas validating the on-disk format. Verify the schema accepts the existing `review_dispatcher.py:write_manifest()` output shape (so existing CLI consumers stay valid against the new schema).
  - **Spec scenarios**: skill-workflow.R1.S4 (manifest superset), skill-workflow.R1.S5 (in-process callers)
  - **Dependencies**: None (can run parallel with 0.1)
- [ ] 0.4 Author `contracts/README.md` documenting which contract sub-types were evaluated and which apply (no OpenAPI, no DB schema, no events — just JSON schemas for the on-disk layout).
  - **Dependencies**: 0.3

## Phase 1: Migrate `review_dispatcher.py` to the shared helper (manifest superset)

This phase routes the CLI dispatcher through the new shared module. Per-vendor finding files remain byte-identical; the manifest gains new fields (schema_version, change_id, created_at, vendors[]) while preserving all existing fields (review_type, target, dispatches[], quorum_requested, quorum_received). NOT a "byte-identical" refactor — it is a SUPERSET migration. Existing CLI consumers continue working because every field they read is still present.

- [ ] 1.1 Write tests asserting (a) per-vendor `findings-{vendor}-{review_type}.json` files remain byte-identical to the prior dispatcher output, (b) the new manifest contains every field the old manifest contained with the same values, AND additionally contains the new fields, (c) existing CLI consumer fixtures (any caller that parses `dispatches[]`, `quorum_requested`, `quorum_received`) continue to parse the new manifest successfully.
  - **Spec scenarios**: skill-workflow.R1.S1, skill-workflow.R1.S2, skill-workflow.R1.S4 (manifest preserves existing fields)
  - **Design decisions**: D6 (manifest superset)
  - **Dependencies**: 0.2
- [ ] 1.2 Replace inlined finding-writes (lines ~1360-1362) and the `write_manifest()` method (lines ~1180-1208) in `review_dispatcher.py` with calls to `checkpoint_findings.write_vendor_findings()` and `checkpoint_findings.write_manifest()`. Pass through the dispatch metadata (model_used, elapsed_seconds, error_class) as the `dispatches=` argument.
  - **Dependencies**: 1.1, 0.2
- [ ] 1.3 Run the existing `parallel-infrastructure` test suite end-to-end; assert no regressions. Additionally grep for any caller that reads the manifest and verify each accessed field still resolves: `grep -rn "review-manifest" skills/ tests/`
  - **Dependencies**: 1.2

## Phase 2: Extract `load_findings_from_dir()` and add `--findings-dir` CLI mode

Decouples the in-memory loader from the CLI argparse plumbing AND adds a directory-input mode to the synthesizer CLI so the fallback path can pass a single directory instead of enumerated files.

- [ ] 2.1 Write tests for `load_findings_from_dir()` — parse manifest + per-vendor files, return `dict[str, list[ReviewFinding]]` (vendor-keyed dict, not flat list). Round-trip assertion: writing via `checkpoint_findings.write_vendor_findings()` and reading back via `load_findings_from_dir()` produces equal data. Verify path-safety enforcement (R6.S4): manifest entries with `..`/symlinked findings_paths are refused.
  - **Spec scenarios**: skill-workflow.R1.S1, skill-workflow.R6.S4 (manifest-referenced paths stay within checkpoint dir)
  - **Design decisions**: D7 (--findings-dir CLI mode)
  - **Dependencies**: 0.2
- [ ] 2.2 Extract `load_findings_from_dir(path: Path) -> dict[str, list[ReviewFinding]]` from `consensus_synthesizer.py`'s existing CLI loading logic. The function reads the manifest's `vendors[].findings_path` entries (not glob); enforces path safety; returns a dict keyed by vendor name (not a flat list).
  - **Dependencies**: 2.1
- [ ] 2.3 Add `--findings-dir <path>` argument to `consensus_synthesizer.py main()` argparse. Place `--findings` and `--findings-dir` in a mutually exclusive argparse group; the parser rejects passing both. When `--findings-dir` is used, call `load_findings_from_dir()`; preserve existing `--findings <file1>...` behavior unchanged.
  - **Spec scenarios**: skill-workflow.R3.S4 (subprocess uses canonical layout)
  - **Design decisions**: D7
  - **Dependencies**: 2.2
- [ ] 2.4 Verify the CLI entrypoint (`main()`) produces identical `consensus-report.json` outputs for fixture inputs in BOTH input modes (`--findings <files>` and `--findings-dir <path>` reading the same data). Asserts the two modes are semantically equivalent.
  - **Dependencies**: 2.3

## Phase 3: ConvergenceResult observability fields

Lands the dataclass change first, before adding the recovery logic that sets the fields. This way every later test can assert on the fields without race conditions.

- [ ] 3.1 Write tests for `ConvergenceResult` shape — defaults are `recovered_via_fallback=False`, `fallback_diagnostics=None`
  - **Spec scenarios**: skill-workflow.R4.S1 (existing callers), skill-workflow.R4.S2 (recovery-aware), skill-workflow.R4.S3 (diagnostics only on fallback)
  - **Design decisions**: D3 (observable fields, not side-channel)
  - **Dependencies**: None
- [ ] 3.2 Add `recovered_via_fallback: bool = False` and `fallback_diagnostics: dict[str, Any] | None = None` to `ConvergenceResult`
  - **Dependencies**: 3.1
- [ ] 3.3 Run all existing `converge()` callers' tests; assert no regressions (backwards compatibility check). Discover callers explicitly: `grep -rn "from convergence_loop import\|import convergence_loop\|convergence_loop\.converge" skills/ tests/` and ensure every test module covering a discovered caller is in the test command. Document the caller list in the test docstring so future contributors don't drop coverage on rename.
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

- [ ] 5.1 Write tests for the success-recovery path — mock `synthesizer.synthesize` to raise, mock `subprocess.run` to return exit 0 with a fixture `consensus-report.json`; assert `recovered_via_fallback=True`, `fallback_diagnostics` populated with all three documented keys, and audit event emitted.
  - **Spec scenarios**: skill-workflow.R3.S1 (recover via fallback)
  - **Design decisions**: D1 (subprocess over native)
  - **Dependencies**: 4.2, 3.2
- [ ] 5.1.5 Write a dedicated test isolating R3.S4 — assert the subprocess is invoked with exactly four arguments: `--findings-dir`, `--review-type`, `--target`, `--output`. Assert no path translation or finding-file copying occurs between the in-process write and the subprocess read. Use `unittest.mock.patch('subprocess.run')` and inspect the `args` argv.
  - **Spec scenarios**: skill-workflow.R3.S4 (subprocess uses canonical layout)
  - **Design decisions**: D7 (--findings-dir CLI mode)
  - **Dependencies**: 4.2, 3.2, 2.3
- [ ] 5.2 Write tests for the double-failure path — both raise; assert ORIGINAL exception bubbles (not the subprocess error) with subprocess stderr tail attached via `__notes__`. Cover sub-cases: subprocess exit 1, subprocess timeout, subprocess executable not found (FileNotFoundError), subprocess output unparseable JSON. Each sub-case asserts the corresponding audit event payload.
  - **Spec scenarios**: skill-workflow.R3.S2 (both fail), skill-workflow.R3.S3 (subprocess timeout), skill-workflow.R3.S5 (subprocess executable not found), skill-workflow.R3.S6 (subprocess output unparseable)
  - **Design decisions**: D4 (re-raise original)
  - **Dependencies**: 4.2, 3.2
- [ ] 5.2.5 Write tests for sanitization of `subprocess_stderr_tail` and `original_exception_message` — feed strings containing `sk-1234567890abcdef` (Anthropic-style key) and `AIzaSy...` (Google-style key) and bearer tokens. Assert each is replaced with `[REDACTED:api_key]` placeholder in BOTH `fallback_diagnostics` and the audit event payload. Verify sanitization is best-effort: high-entropy strings without known prefixes pass through unchanged.
  - **Spec scenarios**: skill-workflow.R3.S7 (sanitization)
  - **Dependencies**: 4.2, 3.2
- [ ] 5.3 Implement `_invoke_synthesizer_cli(cache_dir: Path, review_type: str, change_id: str, output_path: Path, timeout: int = 300) -> ConsensusReport` helper in `convergence_loop.py`. The helper invokes `consensus_synthesizer.py --findings-dir <cache_dir> --review-type <type> --target <change_id> --output <output_path>`, captures stderr (tail to last 4KB), parses the output JSON with schema validation, and returns a `ConsensusReport`. Maps subprocess outcomes to: success, exit-1 failure, timeout, FileNotFoundError, parse error.
  - **Dependencies**: 5.1, 5.1.5, 5.2
- [ ] 5.4 Wrap `synthesizer.synthesize()` call in `try/except Exception:` in `converge()`. On exception: invoke `_invoke_synthesizer_cli`, populate `recovered_via_fallback=True` + `fallback_diagnostics` (with sanitization). On both-failure: attach sanitized stderr tail to original exception via `__notes__` (Python 3.11+) and re-raise the ORIGINAL exception (not the subprocess error). Skip fallback if the in-process exception is `OSError`/`PermissionError` from the checkpoint write itself (fallback prerequisite — readable on-disk findings — is impossible).
  - **Spec scenarios**: skill-workflow.R2.S4 (manifest write permission error skips fallback)
  - **Dependencies**: 5.3, 5.2.5

## Phase 6: Audit log emission

Closes the observability loop — chronic primary failures surface in `query_audit`.

- [ ] 6.1 Write tests for audit emission — `convergence.fallback_recovered` on success-recovery, `convergence.fallback_failed` on double-failure, NO event on happy path, audit-emission failure does not mask result. Verify the audit payload includes `change_id`, `review_type`, `original_exception_class`, sanitized `original_exception_message`, `checkpoint_dir`, and `timestamp` fields per R5.
  - **Spec scenarios**: skill-workflow.R5.S1 (success emits one event), skill-workflow.R5.S2 (double-failure emits one event), skill-workflow.R5.S3 (audit failure does not mask), skill-workflow.R5.S4 (happy path no events)
  - **Design decisions**: D5 (audit failures do not mask)
  - **Dependencies**: 5.4
- [ ] 6.2 Implement audit event emission in `converge()` recovery branches. Use `coordination_bridge.try_emit_audit_event(...)` so coordinator unavailability is non-fatal. Wrap call in `try/except Exception:` with `logger.warning()` per D5. Include `checkpoint_dir` (absolute path) in payload.
  - **Dependencies**: 6.1

## Phase 7: Integration test reproducing the original failure

End-to-end test that pipes the latent `line_range` shape mismatch through the real (non-mocked) in-process synthesizer to confirm the fallback recovers it.

- [ ] 7.1 Author integration test — feed vendor findings with `line_range: "10-20"` (string) to `converge()`; in-process synthesizer raises (current bug); fallback CLI subprocess receives the same input and recovers (CLI also has the bug, but test fixture stubs the CLI to return a known-good consensus report). The test verifies the *plumbing* — not the bug fix.
  - **Spec scenarios**: skill-workflow.R3.S1, skill-workflow.R2.S2, skill-workflow.R5.S1
  - **Note**: The bug at `consensus_synthesizer.py:59` is fixed in a separate proposal; this test does NOT depend on that fix.
  - **Dependencies**: 6.2

## Phase 8: Documentation

- [ ] 8.1 Update `docs/parallel-agentic-development.md` Section 8.C with one paragraph documenting the recovery contract — readers debugging convergence failures need to know the fallback exists and how to read `recovered_via_fallback`. Mention the `--findings-dir` CLI mode and the manifest superset shape.
  - **Dependencies**: 5.4
- [ ] 8.2 Update `skills/autopilot/SKILL.md` to mention the recovery semantics in the convergence-loop section.
  - **Dependencies**: 5.4

(The follow-up `consensus_synthesizer.py:59` bug fix is a Post-Merge Action documented in `proposal.md`, NOT a task of this proposal. After this change merges, the operator files a new narrow OpenSpec proposal that references this one as motivation.)

## Out of Scope

The following are explicitly NOT part of this change. Listed here so reviewers can confirm the boundary:

- Fix for `consensus_synthesizer.py:59` `line_range` type bug — separate proposal filed as a Post-Merge Action (see `proposal.md`).
- Automatic re-dispatch of vendors when synthesis fails. The recovery is "make synthesis work with what we have," not "ask vendors again."
- Cross-process locking on `.review-cache/`. Single converge() call owns its checkpoint directory; the atomic-rename requirement on the manifest is intra-process safety, not multi-process locking.
- Migration of fix-application loop (after consensus) to use checkpointing. Out of scope; the durability gap was at synthesis, not at fix application.
- Adaptive subprocess timeout. 300s default matches existing vendor convention.
- Fallback latency metrics (Langfuse/StatsD style). The audit events specified in R5 are sufficient for this change; richer observability is a follow-up.
