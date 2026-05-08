# skill-workflow — Delta for harden-multi-vendor-review-recovery

## ADDED Requirements

### Requirement: Vendor Findings Checkpoint Layout

The system SHALL define a single canonical on-disk layout for per-vendor review findings, used by both the in-process `converge()` API and the CLI dispatcher. The layout SHALL be writable and readable by a shared helper module so neither caller hardcodes filenames or directory structure.

The shared helper SHALL live under `skills/parallel-infrastructure/scripts/checkpoint_findings.py` so that the dependency direction is one-way: `autopilot` imports from `parallel-infrastructure`, never the reverse.

The helper SHALL be responsible for constructing the per-vendor file's wrapper-object envelope (`review_type`, `target`, `reviewer_vendor`, `findings: [...]`). Callers pass in the raw `ReviewResult.findings` list and the wrapping metadata; the helper builds the wrapper object before writing. This keeps the wire-format contract centralized and prevents callers from accidentally writing raw arrays.

The canonical layout SHALL use:

- Per-vendor finding files at the existing dispatcher path (`<output_dir>/findings-{vendor}-{review_type}.json`) for CLI invocations, and at `<artifacts_dir>/.review-cache/findings-{vendor}-{review_type}.json` for in-process callers. The two locations SHALL NOT be unified by this proposal; each call site continues writing where it already writes (or, for in-process, where this proposal newly writes).
- Per-vendor finding file contents SHALL preserve the existing wrapper-object shape: `{review_type, target, reviewer_vendor, findings: [...]}`. This proposal does NOT change the per-vendor file format.
- Manifest at `<output_dir>/review-manifest.json` (CLI) or `<artifacts_dir>/.review-cache/review-manifest.json` (in-process). The manifest format SHALL be a strict superset of the format currently written by `review_dispatcher.py:write_manifest()`.

The manifest SHALL preserve all fields the existing dispatcher writes (`review_type`, `target`, `dispatches[]`, `quorum_requested`, `quorum_received`) AND SHALL add: `schema_version` (integer, currently `1`), `change_id` (string), `created_at` (ISO-8601 UTC string), and `vendors[]` (per-vendor index with `name`, `findings_path`, `finding_count`).

The shared helper SHALL write the manifest atomically (write-to-temp, fsync, rename, fsync parent directory) so a crash mid-write SHALL NOT leave a partially-written `review-manifest.json`. Per-vendor finding files SHALL be written via the same atomic-rename pattern.

#### Scenario: Round-trip preserves vendor findings
- **WHEN** the helper writes findings for vendor `claude` to a checkpoint directory
- **AND** the helper reads from the same directory
- **THEN** the returned dict (keyed by vendor name, values are lists of `ReviewFinding`) SHALL contain the same findings (id, type, criticality, description, disposition, file_path, line_range, vendor) as the original
- **AND** the read SHALL succeed even if other vendor files are absent

#### Scenario: Manifest is sufficient to enumerate vendors
- **WHEN** an operator reads `review-manifest.json`
- **THEN** the manifest SHALL list every vendor that produced findings in this review round
- **AND** each entry SHALL point at a `findings_path` that exists on disk
- **AND** the manifest SHALL NOT reference vendors whose finding files are missing

#### Scenario: Manifest preserves existing dispatcher fields
- **WHEN** the helper writes a manifest in a context where dispatch metadata is available (the CLI dispatcher's call site)
- **THEN** the resulting `review-manifest.json` SHALL contain ALL of `review_type`, `target`, `dispatches[]`, `quorum_requested`, `quorum_received` (existing CLI fields)
- **AND** SHALL ALSO contain `schema_version`, `change_id`, `created_at`, `vendors[]` (new fields)
- **AND** existing CLI consumers reading the manifest SHALL continue to function without modification

#### Scenario: In-process callers without dispatch metadata
- **WHEN** the in-process `converge()` API writes a manifest
- **AND** dispatch metadata (`model_used`, `elapsed_seconds`, etc.) is available from `ReviewResult` objects
- **THEN** the helper SHALL pass that metadata through into the `dispatches[]` field
- **AND** if dispatch metadata is absent (e.g., test fixtures), the helper SHALL write `dispatches: []` and the schema SHALL accept that shape

#### Scenario: quorum_received reflects actual successful vendors
- **WHEN** the helper writes a manifest
- **THEN** `quorum_received` SHALL equal the count of vendors with non-empty `findings` (or, when dispatch metadata is provided, the count of `dispatches[].success == true`)
- **AND** `quorum_received` SHALL NOT be silently set equal to `quorum_requested` (the count of vendors dispatched) — operators reading the manifest need to see the actual successful count, not the requested count

#### Scenario: change_id is optional for CLI dispatcher
- **WHEN** the CLI dispatcher (`review_dispatcher.py`) writes a manifest
- **AND** the dispatcher has no `change_id` source (its existing `target` argument is used for generic feature/package identifiers like `cli-dispatch`)
- **THEN** the helper SHALL accept `change_id=None` and the manifest's `change_id` field SHALL be `null`
- **AND** the schema SHALL validate the manifest with `change_id: null`
- **AND** in-process callers (`converge()`) SHALL populate `change_id` since they always have it

#### Scenario: Manifest write is atomic
- **WHEN** the helper writes `review-manifest.json`
- **THEN** the bytes SHALL be written to a temporary path, fsync'd, atomically renamed to the final path, and the parent directory SHALL be fsync'd to persist the directory entry
- **AND** an interrupt or crash mid-write SHALL leave EITHER the previous manifest intact OR a complete new manifest, never a partial file

#### Scenario: Concurrent converge calls use distinct cache directories
- **WHEN** two `converge()` invocations run with different `artifacts_dir` arguments
- **THEN** each invocation SHALL write to its own checkpoint area under its own `artifacts_dir`
- **AND** neither invocation SHALL read or modify the other's checkpoint files

### Requirement: In-Process Converge Checkpoints Before Synthesis

The `converge()` API in `skills/autopilot/scripts/convergence_loop.py` SHALL persist per-vendor findings to disk BEFORE invoking `synthesizer.synthesize()`. The checkpoint SHALL be written for every successful dispatch, regardless of whether synthesis subsequently succeeds. If synthesis raises, the exception SHALL propagate to the caller; this proposal does NOT introduce automatic recovery.

#### Scenario: Successful synthesis path also writes checkpoints
- **WHEN** `converge()` completes a review round successfully
- **THEN** `<artifacts_dir>/.review-cache/findings-{vendor}-{review_type}.json` SHALL exist for every vendor that returned findings
- **AND** `<artifacts_dir>/.review-cache/review-manifest.json` SHALL exist
- **AND** the returned `ConvergenceResult` SHALL have `synthesis_failed=False` and `checkpoint_dir` set to the checkpoint directory path

#### Scenario: Synthesis failure leaves checkpoint intact and exception propagates
- **WHEN** `synthesizer.synthesize()` raises an exception
- **THEN** the per-vendor finding files SHALL remain on disk
- **AND** `review-manifest.json` SHALL remain on disk
- **AND** `converge()` SHALL re-raise the original synthesis exception (no fallback, no recovery)
- **AND** an operator SHALL be able to manually invoke `consensus_synthesizer.py` against the checkpoint after diagnosing the underlying issue

#### Scenario: Empty review round still produces a manifest
- **WHEN** all vendors return zero findings (or no vendors are reachable)
- **THEN** the checkpoint helper SHALL still write `review-manifest.json`
- **AND** the manifest's `vendors[]` array MAY be empty
- **AND** no per-vendor finding files SHALL be written for vendors that produced no output

#### Scenario: Checkpoint write permission error
- **WHEN** writing checkpoint files fails with `OSError`/`PermissionError` (filesystem full, directory not writable, etc.)
- **THEN** `converge()` SHALL surface the error as a hard failure
- **AND** synthesis SHALL NOT be attempted (the prerequisite for downstream recovery — readable on-disk findings — is impossible)
- **AND** any partially-written per-vendor finding files SHALL be left in place for manual inspection

### Requirement: ConvergenceResult Observability Field

The `ConvergenceResult` dataclass returned by `converge()` SHALL include one new field: `checkpoint_dir: Path | None` (default `None`). The field SHALL be set to the absolute path of the checkpoint directory when the checkpoint write succeeded.

**Why a single field, not two:** an earlier draft proposed a second `synthesis_failed: bool` field, but multi-vendor review caught that the field is unreachable: when synthesis raises, the exception propagates from `converge()` and no `ConvergenceResult` is returned. A boolean flag never set on the success path and never observed on the failure path is dead code. The exception itself is a perfectly observable signal that synthesis failed; callers that need recovery context can read `checkpoint_dir` from a `ConvergenceResult` they constructed themselves before the exception, or simply locate `<artifacts_dir>/.review-cache/` from caller-known state.

#### Scenario: Existing callers see no behavior change
- **WHEN** an existing caller of `converge()` does not read the new field
- **THEN** every previously-passing test SHALL continue to pass
- **AND** the result's other fields (findings, status, iterations, etc.) SHALL retain their prior semantics

#### Scenario: Recovery-aware callers can locate the checkpoint
- **WHEN** a caller checks `result.checkpoint_dir`
- **AND** the checkpoint write succeeded for this invocation
- **THEN** the value SHALL be a `Path` pointing at the absolute path of the checkpoint directory
- **AND** the path SHALL exist on disk

### Requirement: Structured Logging of Synthesis Failures

The system SHALL emit a structured log entry when synthesis fails with a checkpoint present. This makes chronic synthesis failures observable to operators monitoring logs (or downstream log-aggregation systems like the journal) even if no human notices the immediate exception.

The log emission SHALL use Python's standard `logging` module with a structured payload (e.g., `extra={...}` dict) at level `ERROR`. The event "name" is conveyed via a stable string in the message text — `convergence.synthesis_failed_with_checkpoint` — so log consumers can filter by it. This proposal does NOT introduce a new HTTP audit endpoint or a new `coordination_bridge` helper; it uses the logging primitive that already exists.

The structured payload SHALL include `change_id` (or `null` if not applicable), `review_type`, `original_exception_class`, `original_exception_message`, `checkpoint_dir` (absolute path, post-`Path.resolve()`), and `timestamp` (ISO-8601 UTC).

A separate log entry — `convergence.checkpoint_write_failed` — SHALL be emitted when the checkpoint write itself fails (OSError/PermissionError before synthesis). Same structured-payload pattern. Uses `artifacts_dir` instead of `checkpoint_dir` (since no checkpoint dir exists in this case).

#### Scenario: Synthesis failure with checkpoint emits structured log entry
- **WHEN** the checkpoint write succeeded AND synthesis raised
- **THEN** exactly one `ERROR`-level log entry SHALL be emitted whose message contains the literal `convergence.synthesis_failed_with_checkpoint`
- **AND** the log entry's structured payload SHALL contain all required fields
- **AND** the original synthesis exception SHALL still propagate to the caller

#### Scenario: Synthesis success emits no log entry
- **WHEN** synthesis completes without raising
- **THEN** NO `convergence.synthesis_failed_with_checkpoint` log entry SHALL be emitted

#### Scenario: Checkpoint write failure emits a different log entry
- **WHEN** the checkpoint write itself raises (filesystem full, permission denied, etc.) before synthesis is attempted
- **THEN** exactly one `ERROR`-level log entry SHALL be emitted whose message contains the literal `convergence.checkpoint_write_failed`
- **AND** the log entry's structured payload SHALL contain `change_id`, `review_type`, `original_exception_class`, `original_exception_message`, `artifacts_dir`, `timestamp`
- **AND** the OSError/PermissionError SHALL still propagate to the caller

#### Scenario: Logging failure does not mask result
- **WHEN** the logging emission itself fails (e.g., a misconfigured handler raises in `logger.error()`)
- **THEN** `converge()` SHALL still re-raise the original synthesis exception (the logging failure is secondary)
- **AND** the logging implementation SHALL absorb its own failure (Python's `logging` module already does this by default; no special handling needed)

### Requirement: Checkpoint Path Safety

The shared checkpoint helper SHALL guard against unsafe path inputs reaching the filesystem. The two attack surfaces are: (a) the caller-supplied `artifacts_dir` argument, and (b) vendor-supplied `vendor` names that interpolate into per-vendor filenames. Both SHALL be validated before any disk operation.

#### Scenario: artifacts_dir is normalized
- **WHEN** the helper is invoked with an `artifacts_dir` that contains symlinks, `..` segments, or unusual separators
- **THEN** the helper SHALL resolve the path with `Path.resolve(strict=False)` to its canonical absolute form before any read/write
- **AND** the resolved path SHALL be used for all subsequent operations (no string concatenation against the original)

#### Scenario: vendor name with path separators is rejected
- **WHEN** a finding's `vendor` field contains `/`, `\`, `..`, NUL, or any character outside `[A-Za-z0-9_-]`
- **THEN** the helper SHALL reject the finding before any disk write
- **AND** SHALL raise a structured validation error naming the vendor field and the offending characters

#### Scenario: review_type is constrained
- **WHEN** the helper is invoked with a `review_type` value outside `{"plan", "implementation"}`
- **THEN** the helper SHALL reject the invocation before any disk write
- **AND** SHALL raise a structured validation error

#### Scenario: Manifest-referenced paths stay within manifest's directory
- **WHEN** a reader follows `vendors[].findings_path` entries from a manifest
- **THEN** each `findings_path` SHALL be a simple filename (no directory components, no `..`)
- **AND** each resolved file SHALL have a parent directory equal to the manifest's directory (no escape via symlinks)
- **AND** any `findings_path` failing these checks SHALL cause the reader to refuse with a structured error
