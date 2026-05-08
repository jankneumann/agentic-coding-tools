# skill-workflow — Delta for harden-multi-vendor-review-recovery

## ADDED Requirements

### Requirement: Vendor Findings Checkpoint Layout

The system SHALL define a single canonical on-disk layout for per-vendor review findings, used by both the in-process `converge()` API and the CLI dispatcher. The layout SHALL be writable and readable by a shared helper module so neither caller hardcodes filenames or directory structure.

The shared helper SHALL live under `skills/parallel-infrastructure/scripts/checkpoint_findings.py` so that the dependency direction is one-way: `autopilot` imports from `parallel-infrastructure`, never the reverse.

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

### Requirement: ConvergenceResult Observability Fields

The `ConvergenceResult` dataclass returned by `converge()` SHALL include two new fields enabling callers to detect that synthesis failed and a manual recovery is needed.

The fields SHALL be:
- `checkpoint_dir: Path | None` (default `None`) — set to the absolute path of the `.review-cache/` directory when the checkpoint write succeeded, regardless of whether synthesis subsequently succeeded.
- `synthesis_failed: bool` (default `False`) — set to `True` when checkpoint write succeeded but synthesis raised. Note: when synthesis raises, the exception propagates AND a `ConvergenceResult` is NOT returned in the typical path; this field exists for partial-result reconstruction in callers that catch the exception themselves.

#### Scenario: Existing callers see no behavior change
- **WHEN** an existing caller of `converge()` does not read the new fields
- **THEN** every previously-passing test SHALL continue to pass
- **AND** the result's other fields (findings, status, iterations, etc.) SHALL retain their prior semantics

#### Scenario: Recovery-aware callers can locate the checkpoint
- **WHEN** a caller checks `result.checkpoint_dir`
- **AND** the checkpoint write succeeded for this invocation
- **THEN** the value SHALL be a `Path` pointing at the absolute path of the checkpoint directory
- **AND** the path SHALL exist on disk

#### Scenario: synthesis_failed defaults to False on happy path
- **WHEN** synthesis completes without raising
- **THEN** `result.synthesis_failed` SHALL be `False`

### Requirement: Audit Logging of Synthesis Failures

The system SHALL emit an audit event when synthesis fails with a checkpoint present. This makes chronic synthesis failures observable in `query_audit` even if no human notices the immediate exception.

The event SHALL be `convergence.synthesis_failed_with_checkpoint` and SHALL include `change_id`, `review_type`, `original_exception_class`, `original_exception_message`, `checkpoint_dir` (absolute path, post-`Path.resolve()`), and `timestamp` (ISO-8601 UTC).

#### Scenario: Synthesis failure with checkpoint emits one audit event
- **WHEN** the checkpoint write succeeded AND synthesis raised
- **THEN** exactly one `convergence.synthesis_failed_with_checkpoint` event SHALL be emitted for the invocation
- **AND** the event SHALL contain all required fields

#### Scenario: Synthesis success emits no audit event
- **WHEN** synthesis completes without raising
- **THEN** NO `convergence.synthesis_failed_with_checkpoint` event SHALL be emitted
- **AND** the audit log SHALL contain zero events of this type for this invocation

#### Scenario: Audit emission failure does not mask result
- **WHEN** the audit emission itself fails for any reason (coordinator unreachable, network timeout, permission denied, or any `Exception` subclass)
- **THEN** `converge()` SHALL still re-raise the original synthesis exception (the audit failure is secondary to the synthesis failure that prompted the audit attempt)
- **AND** the audit failure SHALL be logged as a warning but SHALL NOT change the recovery outcome

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
