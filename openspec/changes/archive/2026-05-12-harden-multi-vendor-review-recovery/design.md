# Design: Harden Multi-Vendor Review Recovery (revised)

## Architectural Position

```
┌──────────────────────────────────────────────────────────────────────────┐
│              skills/parallel-infrastructure/scripts/                     │
│                                                                          │
│   checkpoint_findings.py         ← NEW: shared write/read helpers        │
│   ├── _atomic_write_json(path, payload)                                  │
│   │       — write to temp → fsync(file) → os.replace → fsync(parent_dir) │
│   │       — Used by both write_vendor_findings and write_manifest        │
│   ├── write_vendor_findings(out_dir, *, vendor, review_type, target,     │
│   │                          findings, reviewer_vendor=None)             │
│   │       — keyword-only after out_dir to prevent positional confusion   │
│   │       — wraps raw findings list into the per-vendor envelope         │
│   │       — validates `vendor` against [A-Za-z0-9_-]+ before any disk op │
│   │       — uses _atomic_write_json (file fsync + parent-dir fsync)      │
│   ├── read_vendor_findings(out_dir) -> dict[str, list[dict[str, Any]]]   │
│   │       — values are raw finding dicts (NOT a Finding class type)      │
│   ├── write_manifest(out_dir, *, review_type, target, vendors,           │
│   │                  change_id=None, dispatches=None,                    │
│   │                  quorum_requested=None, quorum_received=None)        │
│   │       — keyword-only after out_dir; change_id optional (None for CLI)│
│   │       — uses _atomic_write_json (file fsync + parent-dir fsync)      │
│   │       — defaults: dispatches=[], quorum_*=computed from vendors[]    │
│   ├── read_manifest(out_dir) -> dict[str, Any]                           │
│   │       — returns parsed manifest as raw dict                          │
│   ├── _validate_path_safety(artifacts_dir, vendor, review_type)          │
│   └── _safe_log_error(event, **payload)                                  │
│           — wraps logger.error in try/except; never raises                │
│           — used by converge() for the two log events                    │
│                                                                          │
│   review_dispatcher.py                                                   │
│   └── (lines ~1180-1208 + ~1360-1362)  ← MODIFIED: route via helper      │
│                                                                          │
│   consensus_synthesizer.py                                               │
│   └── (UNCHANGED — no --findings-dir extension; no behavior change)      │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │ imports (one-way)
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           skills/autopilot/                              │
│                                                                          │
│   convergence_loop.py                                                    │
│   ├── converge(...)              ← MODIFIED: pre-synthesis checkpoint    │
│   │       + audit on synthesis failure                                   │
│   └── ConvergenceResult          ← MODIFIED: + 1 observability field     │
│           (checkpoint_dir)                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

The shared `checkpoint_findings` module lives under `skills/parallel-infrastructure/scripts/` (not `autopilot/`) so the dependency direction is one-way: `autopilot` imports from `parallel-infrastructure`, never the reverse. Multi-vendor review of an earlier draft caught that placing the helper under `autopilot/` while having `review_dispatcher.py` import it would create a bidirectional cycle.

## Decision Log

### D1: Durable checkpoint, manual recovery (NOT automatic)

**Context.** The original Approach 1 was "auto-fallback to CLI subprocess on synthesis failure." Multi-vendor PLAN_REVIEW (claude + codex + gemini) converged on a fundamental flaw: the in-process synthesizer and the CLI subprocess BOTH call `Finding.from_dict()` to deserialize per-vendor findings. Bugs in that parser (like the `consensus_synthesizer.py:59` `line_range` shape mismatch that motivated this proposal) cause both paths to fail identically. The fallback would log audit events about a recovery that didn't actually happen.

**Decision.** Drop automatic recovery from this proposal. Deliver only durability — the checkpoint exists on disk, the synthesis exception propagates to the caller. Recovery is manual: an operator diagnoses the issue (or fixes the underlying bug in a separate proposal) and re-runs the synthesizer against the checkpoint.

**Why.** Honest framing of what's actually achievable. The durability primitive has independent value beyond automatic recovery — every future synthesis-time exception preserves findings instead of losing them. Layering automatic recovery on top is a follow-up proposal that depends on the parser fix landing first.

**How to apply.** Resist the temptation to add subprocess fallback "just in case." Future automatic-recovery proposals SHALL depend explicitly on a known-reliable synthesizer parser, not just on this proposal's checkpoint primitive.

### D2: Same on-disk path as the CLI dispatcher (no relocation)

**Context.** An earlier draft proposed routing the CLI dispatcher's per-vendor finding writes into `<output_dir>/.review-cache/`. Multi-vendor review caught that this would silently move artifacts that other code globs for at `<output_dir>/findings-*-{review_type}.json`.

**Decision.** Per-vendor finding files stay where the dispatcher writes them today (`<output_dir>/findings-{vendor}-{review_type}.json`). The in-process flow uses `<artifacts_dir>/.review-cache/findings-{vendor}-{review_type}.json` because in-process callers don't have an `output_dir` analogous to the CLI's. The two paths are NOT unified — each call site continues writing where it already writes.

**Why.** Compatibility with existing globs in other code. The relocation was a non-essential change for cosmetic uniformity; the cost (broken globs) outweighed the benefit (one less code path).

**How to apply.** Future writers SHALL go through `checkpoint_findings.write_vendor_findings()` for the format, but pass their preferred `out_dir`. The helper does not impose a single canonical directory.

### D3: Manifest is a superset, not a replacement

**Context.** The existing `review_dispatcher.py:write_manifest()` writes `{review_type, target, dispatches[], quorum_requested, quorum_received}`. Replacing this would lose forensically valuable dispatch metadata that operators read today.

**Decision.** New schema is a superset. All existing fields preserved. New fields added: `schema_version`, `change_id`, `created_at`, `vendors[]`. In-process callers that lack dispatch metadata write `dispatches: []` and `quorum_*: 0`.

**Why.** Adding is additive and backward-compatible. Replacing breaks downstream consumers.

**How to apply.** Future writers MUST go through `checkpoint_findings.write_manifest()`. Direct `json.dump(...)` of manifest data is prohibited. New fields must be additive within `schema_version=1` or trigger a version bump.

### D4: Per-vendor finding-file shape is preserved (wrapper object, not raw array)

**Context.** An earlier draft of `contracts/finding.schema.json` defined the per-vendor file as a top-level array `[{...}, {...}]`. Multi-vendor review caught (and the synthesizer's literal crash demonstrated) that the actual wire format is a wrapper object: `{review_type, target, reviewer_vendor, findings: [...]}`.

**Decision.** The contracted schema mirrors the actual wire format — wrapper object with `findings: [...]` inside. This proposal does NOT change the per-vendor file shape; it documents what's already there.

**Why.** The synthesizer literally crashes (`AttributeError: 'list' object has no attribute 'get'`) when fed a raw array, because it does `data.get("findings", [])`. Conforming to the existing wire format avoids breaking the synthesizer.

**How to apply.** Future writers SHALL use the wrapper object shape. Tightening or restructuring the per-vendor file is a separate proposal.

### D5: Use Python's standard `logging` module, not coordinator audit events

**Context.** Round 2 review caught that the proposal referenced a `coordination_bridge.try_emit_audit_event()` helper that doesn't exist, plus a `POST /audit/log` HTTP endpoint that doesn't exist either. The agent-coordinator's audit infrastructure is read-only via `GET /audit` plus an internal `audit_service.log_operation()` not exposed publicly. Adding both endpoint + bridge function would substantially expand scope.

**Decision.** Emit observability events via Python's standard `logging` module at level `ERROR` with structured payload (`extra={...}`). Use stable string identifiers in the log message (`convergence.synthesis_failed_with_checkpoint`, `convergence.checkpoint_write_failed`) so log-aggregation tools can filter by them. Do NOT introduce a new HTTP audit endpoint or a new bridge helper.

**Why.** Logging primitive already exists. Operators monitoring `journalctl`, `loki`, or any log-aggregation system can filter by the stable strings and detect chronic failures. The trade-off is that events live in logs not in the coordinator's audit table — but the coordinator's audit table isn't actually queryable for these events without adding endpoints, so the trade-off is "what we can deliver in this proposal" vs "what we'd ship in a separate audit-infrastructure proposal."

**How to apply.** Use `logger.error("convergence.synthesis_failed_with_checkpoint", extra={...})`. Don't wrap in try/except — Python's `logging` already absorbs handler failures. The narrow `try/except Exception:` is only around `synthesizer.synthesize()`, for the purpose of logging the structured payload before re-raising.

### D6: Path safety is enforced at write-time, not just read-time

**Context.** `artifacts_dir` is caller-supplied; vendor names interpolate into filenames. Without explicit guards, a malicious or malformed vendor name with `/`, `..`, or NUL characters could escape the checkpoint directory or corrupt unrelated files.

**Decision.** Validate path inputs (artifacts_dir, vendor, review_type) BEFORE any disk operation. `Path.resolve()` for artifacts_dir; regex `[A-Za-z0-9_-]+` for vendor; enum constraint for review_type.

**Why.** Vendor names come from external sources (vendor adapters, config files). Trusting them without validation is exactly the kind of input-validation gap that gets flagged in security review. Cheap to add now; expensive to retrofit.

**How to apply.** Both `write_vendor_findings()` and `read_vendor_findings()` (via the manifest's `vendors[]` index) call `_validate_path_safety()` before disk access. The contract schema also enforces the vendor pattern so manifests with bad vendor names fail validation.

## Component Interactions

### Happy path (synthesis succeeds)

```
caller → converge()
        ├─→ orchestrator.dispatch_and_wait()      → list[ReviewResult]
        ├─→ checkpoint_findings.write_vendor_findings(...)
        │   └─→ writes findings-{vendor}-{type}.json (atomic rename)
        ├─→ checkpoint_findings.write_manifest(...)
        │   └─→ writes review-manifest.json (atomic rename + parent fsync)
        ├─→ synthesizer.synthesize(vendor_results) → ConsensusReport
        └─→ return ConvergenceResult(
              ...,
              checkpoint_dir=<artifacts_dir>/.review-cache/,
            )
```

### Failure path (synthesis raises with checkpoint present)

```
caller → converge()
        ├─→ orchestrator.dispatch_and_wait()      → list[ReviewResult]
        ├─→ checkpoint_findings.write_vendor_findings(...)
        ├─→ checkpoint_findings.write_manifest(...)
        ├─→ synthesizer.synthesize(...)           → raises SynthesisError(E1)
        ├─→ logger.error("convergence.synthesis_failed_with_checkpoint", extra={
        │     "change_id": ..., "review_type": ...,
        │     "original_exception_class": "SynthesisError",
        │     "original_exception_message": "...", "checkpoint_dir": "...",
        │     "timestamp": "..."
        │   })
        │   └─→ Python's logging absorbs handler failures by default
        └─→ raise SynthesisError(E1)  ← ORIGINAL exception propagates
```

The caller sees the original exception. The checkpoint files are on disk. An operator who notices the failure can manually run:

```bash
consensus_synthesizer.py \
  --findings <artifacts_dir>/.review-cache/findings-*-<review_type>.json \
  --target <change_id> \
  --review-type <review_type> \
  --output <output_path>
```

If the synthesizer still fails (because the underlying parser bug is unfixed), the operator knows it's a parser bug and either fixes it (separate proposal) or hand-edits the malformed vendor file.

### Checkpoint write failure path

```
caller → converge()
        ├─→ orchestrator.dispatch_and_wait()      → list[ReviewResult]
        ├─→ checkpoint_findings.write_vendor_findings(...)
        │   └─→ raises OSError (filesystem full) / PermissionError
        └─→ raise OSError  ← propagates; synthesis is never attempted
```

No audit event in this case — the audit primitive is layered on synthesis failure, not on checkpoint failure. Caller sees the OSError directly.

## Data Shapes

### `review-manifest.json` (canonical — SUPERSET of existing CLI manifest)

```json
{
  "schema_version": 1,
  "change_id": "harden-multi-vendor-review-recovery",
  "review_type": "implementation",
  "created_at": "2026-05-08T14:30:00Z",

  "target": "harden-multi-vendor-review-recovery",
  "dispatches": [
    {
      "vendor": "claude",
      "success": true,
      "model_used": "claude-opus-4.7",
      "models_attempted": ["claude-opus-4.7"],
      "elapsed_seconds": 14.2,
      "error": null,
      "error_class": null
    }
  ],
  "quorum_requested": 2,
  "quorum_received": 2,

  "vendors": [
    {
      "name": "claude",
      "findings_path": "findings-claude-implementation.json",
      "finding_count": 12
    }
  ]
}
```

**Field origin**:
- `schema_version`, `change_id`, `created_at`, `vendors[]` — NEW.
- `target`, `dispatches[]`, `quorum_requested`, `quorum_received` — preserved from existing dispatcher.

In-process callers without dispatch metadata write `dispatches: []`, `quorum_requested: <N vendors>`, `quorum_received: <N vendors>` (they don't track per-vendor success/failure since synthesis runs over `ReviewResult` objects passed in directly).

### `findings-{vendor}-{review_type}.json` (canonical — wrapper object, UNCHANGED)

```json
{
  "review_type": "implementation",
  "target": "harden-multi-vendor-review-recovery",
  "reviewer_vendor": "claude",
  "findings": [
    {
      "id": "claude-001",
      "type": "logic-error",
      "criticality": "high",
      "description": "...",
      "disposition": "fix",
      "file_path": "skills/foo/bar.py",
      "line_range": {"start": 10, "end": 20},
      "vendor": "claude"
    }
  ]
}
```

This is the EXISTING wire format the dispatcher writes today and the synthesizer reads via `data.get("findings", [])`. Documenting it as a contract; not changing it.

### `ConvergenceResult` (delta)

```python
@dataclass
class ConvergenceResult:
    # ... all existing fields unchanged ...

    # NEW — observability of durability
    checkpoint_dir: Path | None = None
```

`checkpoint_dir` is set on successful checkpoint write, regardless of whether synthesis subsequently succeeds. Round 2 review pruned a second `synthesis_failed: bool` field as unreachable — when synthesis raises, the exception propagates and no `ConvergenceResult` is returned, so a flag for "synthesis failed" has no observable code path. The Python exception itself is the signal that synthesis failed; callers needing recovery context locate `<artifacts_dir>/.review-cache/` from caller-known state (the `artifacts_dir` they passed in).

## Edge Cases

- **Empty review round**: write empty manifest with `vendors: []`. Synthesis is a no-op. Success path; checkpoint exists.
- **One vendor returned, one timed out**: write checkpoint for the vendor that returned. Manifest's `dispatches[]` records both vendors with success/failure metadata; `vendors[]` only includes the successful vendor.
- **`artifacts_dir` does not yet exist**: `checkpoint_findings.write_vendor_findings()` SHALL create it (`Path.mkdir(parents=True, exist_ok=True)`).
- **Checkpoint write permission denied**: surface as hard failure of `converge()`. Caller sees the OSError. Synthesis never attempted.
- **Synthesis raises a Warning (not Exception)**: NOT a failure. Warnings do not flag `synthesis_failed`.
- **Audit emission fails**: warning logged; original synthesis exception propagates unchanged.
- **Multiple converge() calls with the same artifacts_dir**: undefined behavior; the proposal does not cross-process lock. Distinct artifacts_dir per call is the intended invariant.

## Test Strategy

- **Round-trip unit tests** (`test_checkpoint_findings.py`) — write/read pairs; manifest superset preserves existing fields; in-process callers may write empty `dispatches`; atomic-rename behavior verified by interrupting via signal in test harness.
- **Path safety** — vendor names with separators/NUL/`..` are rejected; artifacts_dir with symlinks is normalized; review_type outside `{plan, implementation}` is rejected.
- **Manifest correctness** — schema validation passes for both CLI-style writes (with dispatches) and in-process-style writes (empty dispatches).
- **Convergence failure path** (`test_convergence_checkpoint.py`) — mock `synthesizer.synthesize` to raise; assert original exception propagates AND checkpoint files exist on disk AND audit event is emitted with correct fields.
- **Convergence success path** — assert checkpoint files exist AND `result.checkpoint_dir` is set AND `synthesis_failed=False` AND no audit event emitted.
- **Audit emission failure** — mock the audit emitter to raise; assert `converge()` still re-raises the synthesis exception (audit failure is secondary).
- **Integration test** (`test_convergence_durability_integration.py`) — feed real `line_range: "10-20"` malformed input; assert exception propagates, checkpoint exists, manual subprocess invocation of `consensus_synthesizer.py` against the checkpoint STILL fails (parser bug unfixed). Verifies the proposal's actual claim — durability — without falsely claiming recovery.
