# Design: Harden Multi-Vendor Review Recovery

## Architectural Position

The change sits at the seam between two existing components:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           skills/autopilot/                              │
│                                                                          │
│   convergence_loop.py                                                    │
│   ├── converge(...)              ← MODIFIED: checkpoint + fallback       │
│   ├── ConvergenceResult          ← MODIFIED: + 2 observability fields    │
│   └── _invoke_synthesizer_cli()  ← NEW: subprocess wrapper               │
│                                                                          │
│   checkpoint_findings.py         ← NEW: shared write/read helpers        │
│   ├── write_vendor_findings(artifacts_dir, vendor_findings, review_type) │
│   │       — validates against finding.schema.json BEFORE write           │
│   ├── read_vendor_findings(cache_dir) -> dict[str, list[ReviewFinding]]  │
│   ├── write_manifest(cache_dir, change_id, review_type, vendors,         │
│   │                  dispatches=None, quorum_requested=None,             │
│   │                  quorum_received=None, target=None)                  │
│   │       — writes superset shape; in-process callers omit dispatches    │
│   │       — atomic-rename: write to .tmp, fsync, rename                  │
│   └── _validate_path_safety(artifacts_dir, vendor, review_type)          │
│           — Path.resolve(); rejects ../, vendor with non-[A-Za-z0-9_-]   │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │ imports
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│              skills/parallel-infrastructure/scripts/                     │
│                                                                          │
│   review_dispatcher.py                                                   │
│   └── (lines ~1360-1362)         ← MODIFIED: call shared helper instead  │
│                                                                          │
│   consensus_synthesizer.py                                               │
│   ├── load_findings_from_dir()   ← NEW: extracted helper, no behavior Δ  │
│   └── main()                     ← UNCHANGED                             │
└──────────────────────────────────────────────────────────────────────────┘
```

The shared `checkpoint_findings` module lives under `skills/autopilot/scripts/` because that is the closer caller (the new code path), and `parallel-infrastructure/scripts/review_dispatcher.py` is happy to import upstream from there. The alternative — putting it under `parallel-infrastructure/` and importing into `autopilot/` — was considered and rejected because `autopilot` already imports from `parallel-infrastructure` (via `ReviewOrchestrator`), and adding a reverse edge complicates the dependency graph. Keeping the shared module on the caller side (autopilot) makes both directions one-way.

## Decision Log

### D1: Subprocess fallback over native checkpoint-then-synthesize

**Context.** Two paths give us the same end-state durability: (a) checkpoint-then-fallback-CLI-on-failure (Approach 1), (b) checkpoint-then-synthesize-natively (Approach 2). The user selected (a) at Gate 1.

**Decision.** Approach 1. The fallback path uses the existing `consensus_synthesizer.py` CLI binary verbatim — no parallel synthesizer implementation.

**Why.** Reuses a working code path instead of forking it. If a future bug in the synthesizer is fixed in the CLI, the fallback path inherits the fix automatically. If we re-implemented synthesis natively in `converge()`, both paths would need the fix.

**How to apply.** When extending recovery in the future, prefer "checkpoint more upstream + invoke the same CLI" over "add a second native code path."

### D2: Reuse `<artifacts_dir>/.review-cache/` (CLI's existing layout)

**Context.** Three options for the checkpoint location were considered: shared with the CLI's existing layout, dedicated `converge-checkpoints/` subdir, or tmpfile-only.

**Decision.** Shared. Same directory, same filename pattern, same manifest format.

**Why.** The CLI is the fallback path. Any layout other than the CLI's layout requires either a path-translation step at fallback time or a second loader. Both add complexity for zero functional benefit. The `.review-cache/` name is also semantically right — these are *cached* per-vendor findings, durable across the dispatch → synthesize boundary.

**How to apply.** All future writers of vendor findings (in-process, CLI, third party) MUST go through `checkpoint_findings.write_vendor_findings()`. Do not introduce a parallel layout.

### D3: Observable recovery via two fields, not a side-channel

**Context.** The user selected "Log + structured warning, but report success." We need callers to be able to tell recovery happened without breaking the success path of existing callers.

**Decision.** Add two fields directly to `ConvergenceResult` — `recovered_via_fallback: bool` (default `False`) and `fallback_diagnostics: dict | None` (default `None`).

**Why.** A side-channel (env var, thread-local, audit log only) hides the recovery from callers that legitimately need to know. The dataclass is the natural carrier — existing consumers ignore the new fields, recovery-aware consumers read them. Keeping the diagnostics as a structured dict (not a free-form string) gives us forwards compatibility for new diagnostic keys.

**How to apply.** Recovery-aware callers should treat `recovered_via_fallback=True` as a SUCCESS but emit their own monitoring signal (e.g., a Langfuse score, a Slack ping) — chronic recovery means primary-path issues, not failures.

### D4: Re-raise the **original** synthesis exception when fallback also fails

**Context.** When both primary synthesis and fallback CLI fail, we have two errors. Which one bubbles?

**Decision.** Re-raise the **original** synthesis exception (E1). The subprocess stderr tail attaches to E1 as forensic data. The subprocess error itself does not become the surface exception.

**Why.** E1 is the diagnostically interesting one — it's the failure we wanted to recover from. The subprocess failure is secondary (likely the same underlying cause manifesting again). If we surfaced the subprocess error, callers would see a confusing trace pointing at a Python subprocess wrapper instead of at the actual synthesizer bug.

**How to apply.** Test fixture for the double-failure case must assert `assert isinstance(exc, OriginalSynthesizerError)`, not the subprocess wrapper.

### D5: Audit emission failures do not mask the recovery result

**Context.** What if the coordinator audit endpoint is unreachable when we try to emit `convergence.fallback_recovered`?

**Decision.** Audit emission is best-effort. A failed audit emission emits a warning to the local log but does not change the `converge()` return value or raise an exception.

**Why.** Recovery has succeeded by the time we try to audit. Punishing the caller for an unrelated infra failure (audit endpoint down) would un-recover the recovery. This matches the convention of `coordination-bridge` where the bridge logs warnings on coordinator unavailability but never blocks the primary work.

**How to apply.** Wrap the audit call in a `try/except Exception:` with a `logger.warning()` in the except block. Never let audit failures propagate.

### D6: Manifest is a superset, not a replacement

**Context.** The original proposal assumed we'd replace the existing `review_dispatcher.py:write_manifest()` shape with our new one. PLAN_ITERATE caught that the existing manifest carries dispatch metadata (`model_used`, `elapsed_seconds`, `error_class`) that consumers (and operators reading audit logs) currently rely on.

**Decision.** The new schema is a **superset**. All existing fields (`review_type`, `target`, `dispatches[]`, `quorum_requested`, `quorum_received`) are preserved. New fields (`schema_version`, `change_id`, `created_at`, `vendors[]`) are added. In-process callers that lack dispatch metadata write `dispatches: []`.

**Why.** Replacing breaks downstream consumers and loses operationally valuable data. Adding is additive and backward-compatible. The schema is a single document with `additionalProperties: false`, so any future drift requires an explicit schema bump (D7 — version 1 → 2 with reader rejection of unknown versions).

**How to apply.** Future writers MUST go through `checkpoint_findings.write_manifest()`. Direct `json.dump(...)` of manifest data is prohibited. Future fields must be additive within `schema_version=1` or trigger a version bump.

### D7: New `--findings-dir` argument on `consensus_synthesizer.py`

**Context.** The existing CLI requires `--findings <file1> <file2>...` (`nargs="+"`). The fallback path needs the CLI to accept a directory and discover files itself, otherwise `converge()` has to glob and pass file lists across a process boundary.

**Decision.** Add `--findings-dir <path>` as an alternative input mode to `consensus_synthesizer.py main()`. The directory mode reads `<dir>/review-manifest.json` and follows `vendors[].findings_path`. The existing `--findings <file1>...` mode is preserved unchanged for backward compatibility.

**Why.** Symmetric with `checkpoint_findings.read_vendor_findings()`: both accept a directory and use the manifest for enumeration. Consistent input shape for the in-process loader and the CLI loader. Avoids ad-hoc glob logic in `converge()`.

**How to apply.** The two modes SHALL be mutually exclusive at the argparse level. `--findings` and `--findings-dir` SHALL be in a mutually exclusive group; the parser rejects passing both. Tests cover both modes.

## Component Interactions

### Happy path (no fallback fires)

```
caller → converge()
        ├─→ orchestrator.dispatch_and_wait()      → list[VendorResult]
        ├─→ checkpoint_findings.write_vendor_findings(...)
        │   └─→ writes findings-{vendor}-{type}.json + review-manifest.json
        ├─→ synthesizer.synthesize(vendor_results) → ConsensusReport
        └─→ return ConvergenceResult(
              ...,
              recovered_via_fallback=False,
              fallback_diagnostics=None,
            )
```

### Recovery path (synthesis fails, CLI succeeds)

```
caller → converge()
        ├─→ orchestrator.dispatch_and_wait()      → list[VendorResult]
        ├─→ checkpoint_findings.write_vendor_findings(...)  ← already on disk
        ├─→ synthesizer.synthesize(...)           → raises SynthesisError(E1)
        ├─→ _invoke_synthesizer_cli(cache_dir, review_type, change_id, output_path)
        │   └─→ subprocess: consensus_synthesizer.py
        │         --findings-dir <cache_dir>
        │         --review-type <type>
        │         --target <change_id>
        │         --output <output_path>
        │       → exit 0, writes consensus-report.json to <output_path>
        ├─→ parse consensus-report.json (with schema validation)
        ├─→ sanitize stderr tail and exception message (R3)
        ├─→ emit_audit_event("convergence.fallback_recovered", {
        │      change_id, review_type, original_exception_class,
        │      original_exception_message_sanitized, checkpoint_dir, timestamp
        │    })
        └─→ return ConvergenceResult(
              ...,
              recovered_via_fallback=True,
              fallback_diagnostics={
                "original_exception_class": "SynthesisError",
                "original_exception_message": "<sanitized>",
                "subprocess_stderr_tail": "<sanitized, last 4KB>",
              },
            )
```

NOTE: `--findings-dir` is a NEW argument added to `consensus_synthesizer.py main()` as part of this proposal. The existing `--findings <file1> <file2>...` mode remains for backward compatibility. The directory mode reads `.review-cache/review-manifest.json` to enumerate per-vendor finding files via `vendors[].findings_path` entries (no glob).

### Double-failure path

```
caller → converge()
        ├─→ orchestrator.dispatch_and_wait()      → list[VendorResult]
        ├─→ checkpoint_findings.write_vendor_findings(...)  ← already on disk
        ├─→ synthesizer.synthesize(...)           → raises SynthesisError(E1)
        ├─→ _invoke_synthesizer_cli(...)          → exit 1
        ├─→ emit_audit_event("convergence.fallback_failed", {...})
        ├─→ E1.__notes__.append(stderr_tail)
        └─→ raise E1
```

### Subprocess timeout path

Identical to double-failure path but with `subprocess.TimeoutExpired` triggering the fallback-failed branch instead of non-zero exit code.

## Data Shapes

### `review-manifest.json` (canonical — SUPERSET of existing CLI manifest)

The shared manifest preserves all fields the existing `review_dispatcher.py:write_manifest()` writes (so existing CLI consumers continue working unchanged) AND adds new fields that the in-process flow and the fallback CLI both need.

```json
{
  "schema_version": 1,
  "change_id": "harden-multi-vendor-review-recovery",
  "review_type": "implementation",
  "created_at": "2026-05-07T14:30:00Z",

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
    },
    {
      "vendor": "codex",
      "success": true,
      "model_used": "gpt-5.4",
      "models_attempted": ["gpt-5.4"],
      "elapsed_seconds": 11.8,
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
    },
    {
      "name": "codex",
      "findings_path": "findings-codex-implementation.json",
      "finding_count": 8
    }
  ]
}
```

**Field origin**:
- `schema_version`, `change_id`, `created_at`, `vendors[]` — NEW in this proposal.
- `target`, `dispatches[]`, `quorum_requested`, `quorum_received` — preserved from the existing `review_dispatcher.py:write_manifest()` shape so downstream readers don't break.

**In-process callers** (the `converge()` flow) do not have `model_used`/`elapsed_seconds`/etc, so they write `dispatches: []` and populate `quorum_requested`/`quorum_received` from vendor counts. The schema permits `dispatches: []` so both call sites validate.

### `findings-{vendor}-{review_type}.json` (canonical, unchanged from CLI)

```json
[
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
```

### `ConvergenceResult` (delta)

```python
@dataclass
class ConvergenceResult:
    # ... all existing fields unchanged ...

    # NEW — observability of recovery
    recovered_via_fallback: bool = False
    fallback_diagnostics: dict[str, Any] | None = None
```

## Edge Cases

- **Empty review round** (zero vendors returned findings): write an empty manifest with `vendors: []`. Synthesis is a no-op — the consensus report is empty. Fallback never fires. Tested explicitly.
- **One vendor returned, one timed out**: write checkpoint for the vendor that returned. Manifest lists only that vendor. If synthesis fails, fallback CLI sees the same one-vendor input and either succeeds or fails consistently.
- **Synthesis succeeds but raises a warning**: not a failure. Warnings do not trigger fallback. Only `Exception` (not `Warning`) subclasses do.
- **`artifacts_dir` does not yet exist**: `checkpoint_findings.write_vendor_findings()` SHALL create it (`Path.mkdir(parents=True, exist_ok=True)`). Symmetric with how the CLI creates output dirs today.
- **Permissions error writing checkpoint**: surface as a hard failure of `converge()` — we cannot recover from a write failure to a path we own. The audit log captures it.
- **Subprocess CLI version mismatch** (e.g., `.review-cache/` schema_version=1 but installed CLI expects schema_version=2): the CLI SHALL detect and refuse with a clear error. Audit log records `convergence.fallback_failed` with the version mismatch in the stderr tail. Caller sees the original synthesis exception.

## Test Strategy

- **Round-trip unit tests** (`test_checkpoint_findings.py`) — write/read pairs for full vendor finding shapes; assert byte-equivalence of JSON after a write/read/write cycle.
- **Manifest correctness** — empty vendor list, single vendor, multiple vendors, missing finding file.
- **Fallback success** (`test_convergence_fallback.py`) — mock `synthesizer.synthesize` to raise `SynthesisError`, mock `subprocess.run` to return exit 0 with a fixture `consensus-report.json`. Assert `recovered_via_fallback=True` and audit event emitted.
- **Fallback failure** — mock `synthesizer.synthesize` to raise; mock `subprocess.run` to return exit 1. Assert original exception bubbles, stderr tail attached, audit event emitted.
- **Subprocess timeout** — mock `subprocess.run` to raise `TimeoutExpired`. Assert original exception bubbles.
- **Audit emission failure** — mock the audit emitter to raise. Assert `converge()` still returns the recovered result.
- **Integration test** — end-to-end with a controlled synthesis-time exception (e.g., feed a `line_range: "10-20"` string into the in-process synthesizer to reproduce the latent bug); assert recovery via real subprocess CLI invocation succeeds.
