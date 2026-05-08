# skill-workflow — Delta for harden-multi-vendor-review-recovery

## ADDED Requirements

### Requirement: Vendor Findings Checkpoint Layout

The system SHALL define a single canonical on-disk layout for per-vendor review findings, used by both the in-process `converge()` API and the CLI dispatcher. The layout SHALL be writable and readable by a shared helper module so neither caller hardcodes filenames or directory structure.

The canonical layout SHALL be:

- Directory: `<artifacts_dir>/.review-cache/`
- Per-vendor file: `<artifacts_dir>/.review-cache/findings-{vendor}-{review_type}.json`
- Manifest: `<artifacts_dir>/.review-cache/review-manifest.json`

The manifest SHALL be a **superset** of the manifest format currently written by `review_dispatcher.py` (which contains `review_type`, `target`, `dispatches[]`, `quorum_requested`, `quorum_received`). The new schema SHALL preserve all of those fields so existing CLI consumers continue to work, AND SHALL add: `schema_version` (integer, currently `1`), `change_id` (string), `created_at` (ISO-8601 UTC string), and `vendors[]` (per-vendor index with `name`, `findings_path`, `finding_count`).

The shared checkpoint helper SHALL validate findings against the contracted JSON Schema (`contracts/finding.schema.json`) BEFORE writing per-vendor files. Findings that fail validation SHALL be rejected with a structured error; partial writes SHALL NOT occur (either all findings for a vendor are written or none are).

The shared checkpoint helper SHALL write the manifest atomically (write-to-temp, fsync, rename) so a crash mid-write SHALL NOT leave a partially-written `review-manifest.json`.

The checkpoint directory at `<artifacts_dir>/.review-cache/` SHALL be deleted when `/cleanup-feature` is invoked, matching the lifecycle of other review artifacts. Operators MAY override this for forensic retention via a flag on `/cleanup-feature` (out of scope for this change; tracked in proposal.md Q1).

#### Scenario: Round-trip preserves vendor findings
- **WHEN** the helper writes a list of `ReviewFinding` objects for vendor `claude` to a checkpoint directory
- **AND** the helper reads from the same directory
- **THEN** the returned list SHALL contain the same findings (id, type, criticality, description, disposition, file_path, line_range, vendor) as the original
- **AND** the read SHALL succeed even if other vendor files are absent

#### Scenario: Manifest is sufficient to enumerate vendors
- **WHEN** an operator reads `.review-cache/review-manifest.json`
- **THEN** the manifest SHALL list every vendor that produced findings in this review round
- **AND** each entry SHALL point at a `findings_path` that exists on disk
- **AND** the manifest SHALL NOT reference vendors whose finding files are missing

#### Scenario: Concurrent converge calls use distinct cache directories
- **WHEN** two `converge()` invocations run with different `artifacts_dir` arguments
- **THEN** each invocation SHALL write to its own `.review-cache/` under its own `artifacts_dir`
- **AND** neither invocation SHALL read or modify the other's checkpoint files

#### Scenario: Manifest preserves existing dispatcher fields
- **WHEN** the shared helper writes a manifest in a context where dispatch metadata is available (e.g., the CLI dispatcher's call site after subprocess dispatches complete)
- **THEN** the resulting `review-manifest.json` SHALL contain ALL of `review_type`, `target`, `dispatches[]`, `quorum_requested`, `quorum_received` (existing CLI fields)
- **AND** SHALL ALSO contain `schema_version`, `change_id`, `created_at`, `vendors[]` (new fields)
- **AND** existing CLI consumers reading the manifest SHALL continue to function without modification

#### Scenario: In-process callers without dispatch metadata
- **WHEN** the in-process `converge()` API writes a manifest (it does not have access to `model_used`, `elapsed_seconds`, etc. produced by the CLI dispatcher)
- **THEN** the helper SHALL write the manifest with `dispatches: []` (empty array) and `quorum_requested`/`quorum_received` populated from vendor counts
- **AND** the manifest SHALL still validate against the schema
- **AND** new fields (`schema_version`, `change_id`, `created_at`, `vendors[]`) SHALL be present

#### Scenario: Findings rejected on schema violation before write
- **WHEN** the helper receives a finding that fails `contracts/finding.schema.json` validation (e.g., missing `id`, malformed `criticality` value)
- **THEN** the helper SHALL raise a structured validation error before any disk write occurs
- **AND** no partially-written file SHALL exist on disk
- **AND** the error SHALL identify the vendor name, the finding index, and the schema violation

#### Scenario: Manifest write is atomic
- **WHEN** the helper writes `review-manifest.json`
- **THEN** the bytes SHALL be written to a temporary path (e.g., `review-manifest.json.tmp`), fsync'd, and atomically renamed to the final path
- **AND** an interrupt or crash mid-write SHALL leave EITHER the previous manifest intact OR a complete new manifest, never a partial file

### Requirement: In-Process Converge Checkpoints Before Synthesis

The `converge()` API in `skills/autopilot/scripts/convergence_loop.py` SHALL persist per-vendor findings to the canonical checkpoint layout BEFORE invoking `synthesizer.synthesize()`. The checkpoint SHALL be written for every successful dispatch, regardless of whether synthesis subsequently succeeds.

#### Scenario: Successful synthesis path also writes checkpoints
- **WHEN** `converge()` completes a review round successfully
- **THEN** `<artifacts_dir>/.review-cache/findings-{vendor}-{review_type}.json` SHALL exist for every vendor that returned findings
- **AND** `<artifacts_dir>/.review-cache/review-manifest.json` SHALL exist
- **AND** the returned `ConvergenceResult` SHALL have `recovered_via_fallback=False`

#### Scenario: Synthesis failure leaves checkpoint intact
- **WHEN** `synthesizer.synthesize()` raises an exception
- **THEN** the per-vendor finding files SHALL remain on disk
- **AND** `review-manifest.json` SHALL remain on disk
- **AND** an operator SHALL be able to manually invoke the synthesizer CLI as `consensus_synthesizer.py --findings-dir <artifacts_dir>/.review-cache/ --review-type <type> --target <change_id> --output <path>` and obtain a consensus report

#### Scenario: Manifest write permission error
- **WHEN** writing `review-manifest.json` fails with `OSError`/`PermissionError` (filesystem full, directory not writable, etc.)
- **THEN** `converge()` SHALL surface the error as a hard failure (NOT a recoverable synthesis exception)
- **AND** the failure SHALL NOT trigger CLI fallback (the prerequisite for fallback — readable on-disk findings — is impossible)
- **AND** any partially-written per-vendor finding files SHALL be left in place for manual inspection

#### Scenario: Empty review round still produces a manifest
- **WHEN** all vendors return zero findings (or no vendors are reachable)
- **THEN** the checkpoint helper SHALL still write `review-manifest.json`
- **AND** the manifest's `vendors` array MAY be empty
- **AND** no per-vendor finding files SHALL be written for vendors that produced no output

### Requirement: CLI Subprocess Fallback on Synthesis Failure

When `synthesizer.synthesize()` raises an exception during the in-process `converge()` flow, the system SHALL automatically invoke `consensus_synthesizer.py` as a subprocess against the checkpoint directory. If the subprocess succeeds, `converge()` SHALL return its result with the recovery marked observable. If the subprocess also fails, `converge()` SHALL raise the **original** synthesis exception, with the subprocess stderr tail attached to a structured diagnostics field.

The subprocess SHALL be invoked using a `--findings-dir <path>` argument (added to `consensus_synthesizer.py main()` as part of this change) so the fallback path enumerates per-vendor files via the same on-disk layout the helper writes. The CLI SHALL retain its existing `--findings <file1> <file2>...` mode for backward compatibility; `--findings-dir` is added as an alternative input mode.

The fallback path SHALL sanitize forensic data attached to diagnostics (the subprocess stderr tail and the original exception message) to remove obvious secret patterns (API keys matching common vendor formats, bearer tokens, password-like fields) before persisting to `ConvergenceResult.fallback_diagnostics` or audit events. Sanitization SHALL be best-effort; high-entropy strings or unknown secret formats MAY pass through unchanged.

#### Scenario: Synthesizer crash recovers via CLI fallback
- **WHEN** the in-process `synthesizer.synthesize()` raises any exception
- **AND** `consensus_synthesizer.py` invoked as a subprocess against `.review-cache/` returns exit code 0
- **THEN** `converge()` SHALL parse the subprocess's `consensus-report.json` output
- **AND** SHALL return a `ConvergenceResult` populated from that report
- **AND** the returned result's `recovered_via_fallback` SHALL be `True`
- **AND** the returned result's `fallback_diagnostics` SHALL include the original exception class name and message
- **AND** the audit log SHALL record one event of type `convergence.fallback_recovered`

#### Scenario: Both primary and fallback fail
- **WHEN** `synthesizer.synthesize()` raises exception E1
- **AND** the `consensus_synthesizer.py` subprocess exits with non-zero status (or times out, or its output cannot be parsed)
- **THEN** `converge()` SHALL re-raise E1 (the original synthesis exception, not the subprocess error)
- **AND** E1's `__notes__` (or equivalent) SHALL include the subprocess stderr tail (last 4 KB)
- **AND** the audit log SHALL record one event of type `convergence.fallback_failed`
- **AND** the checkpoint files SHALL remain on disk for manual recovery

#### Scenario: Fallback subprocess timeout
- **WHEN** the `consensus_synthesizer.py` subprocess does not exit within the fallback timeout (default 300s)
- **THEN** the subprocess SHALL be terminated
- **AND** the behavior SHALL match "Both primary and fallback fail" — original exception re-raised, audit event emitted

#### Scenario: Subprocess invocation reuses canonical layout
- **WHEN** `converge()` invokes the fallback subprocess
- **THEN** the subprocess SHALL be invoked with arguments `--findings-dir <artifacts_dir>/.review-cache/`, `--review-type <type>`, `--target <change_id>`, and `--output <consensus_report_path>`
- **AND** the subprocess SHALL discover per-vendor files via the manifest's `vendors[].findings_path` entries (no glob, no fnmatch)
- **AND** no path translation or finding-file copying SHALL be required between the in-process write and the subprocess read

#### Scenario: Subprocess executable not available
- **WHEN** the subprocess invocation fails with `FileNotFoundError` (the Python interpreter or `consensus_synthesizer.py` script is unreachable)
- **THEN** the behavior SHALL match "Both primary and fallback fail" — original synthesis exception re-raised
- **AND** the audit event SHALL record `fallback_unavailable_reason="executable_not_found"` (or equivalent) so chronic environment misconfigurations surface in `query_audit`

#### Scenario: Subprocess output cannot be parsed
- **WHEN** the subprocess exits 0 but the consensus-report.json file is missing or contains invalid JSON
- **THEN** the behavior SHALL match "Both primary and fallback fail" — original synthesis exception re-raised
- **AND** the parse error SHALL be included in `fallback_diagnostics.subprocess_parse_error`
- **AND** the audit event SHALL include the parse error class

#### Scenario: Sanitization removes obvious secrets from diagnostics
- **WHEN** the subprocess stderr contains an API key matching a known vendor format (e.g., `sk-...`, `AIza...`, bearer tokens)
- **AND** that stderr is captured into `fallback_diagnostics.subprocess_stderr_tail`
- **THEN** the matching substring SHALL be replaced with a placeholder (e.g., `[REDACTED:api_key]`) before being stored
- **AND** sanitization SHALL be applied identically to `original_exception_message` before storage and audit emission

### Requirement: ConvergenceResult Observability Fields

The `ConvergenceResult` dataclass returned by `converge()` SHALL include two new fields enabling callers to detect when fallback recovery fired without breaking existing consumers.

The fields SHALL be:
- `recovered_via_fallback: bool` (default `False`)
- `fallback_diagnostics: dict[str, Any] | None` (default `None`)

When `recovered_via_fallback` is `True`, `fallback_diagnostics` SHALL be a non-`None` dict containing at minimum:
- `original_exception_class: str`
- `original_exception_message: str`
- `subprocess_stderr_tail: str` (may be empty if subprocess succeeded silently)

#### Scenario: Existing callers see no behavior change
- **WHEN** an existing caller of `converge()` does not read the new fields
- **THEN** every previously-passing test SHALL continue to pass
- **AND** the result's other fields (findings, status, iterations, etc.) SHALL retain their prior semantics

#### Scenario: Recovery-aware callers can detect fallback
- **WHEN** a caller checks `result.recovered_via_fallback`
- **THEN** the value SHALL be `True` only if the CLI subprocess fallback fired and succeeded for this invocation
- **AND** SHALL be `False` for invocations where the in-process synthesizer succeeded

#### Scenario: Diagnostics populated only on fallback path
- **WHEN** `result.recovered_via_fallback` is `False`
- **THEN** `result.fallback_diagnostics` SHALL be `None`

### Requirement: Audit Logging of Recovery Events

The system SHALL emit audit events when fallback recovery fires, regardless of outcome, so chronic primary-path failures surface via `query_audit`.

The events SHALL be:
- `convergence.fallback_recovered` — emitted on successful recovery
- `convergence.fallback_failed` — emitted when both primary and fallback paths fail

Each event SHALL include `change_id`, `review_type`, `original_exception_class`, `original_exception_message` (sanitized per R3), `checkpoint_dir` (absolute path to `<artifacts_dir>/.review-cache/`), and `timestamp` (ISO-8601 UTC). The `checkpoint_dir` field is REQUIRED so operators reading audit logs can locate the on-disk forensic state without grepping additional sources.

#### Scenario: Successful fallback emits exactly one audit event
- **WHEN** fallback recovery succeeds
- **THEN** exactly one `convergence.fallback_recovered` event SHALL be emitted for the invocation
- **AND** no `convergence.fallback_failed` event SHALL be emitted

#### Scenario: Double-failure emits exactly one audit event
- **WHEN** both in-process synthesis and CLI subprocess fail
- **THEN** exactly one `convergence.fallback_failed` event SHALL be emitted for the invocation
- **AND** no `convergence.fallback_recovered` event SHALL be emitted

#### Scenario: Audit emission failure does not mask result
- **WHEN** the audit emission itself fails for any reason (coordinator unreachable, network timeout, permission denied, invalid coordinator state, or any other `Exception` subclass)
- **THEN** `converge()` SHALL still return the recovered result (or re-raise the original exception, as appropriate)
- **AND** the audit failure SHALL be logged as a warning but SHALL NOT change the recovery outcome

#### Scenario: Happy path emits no audit event
- **WHEN** `synthesizer.synthesize()` succeeds in-process and `converge()` returns with `recovered_via_fallback=False`
- **THEN** NO `convergence.fallback_recovered` event SHALL be emitted
- **AND** NO `convergence.fallback_failed` event SHALL be emitted
- **AND** the audit log SHALL contain zero events of either type for this `converge()` invocation

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

#### Scenario: Manifest-referenced paths stay within checkpoint dir
- **WHEN** the fallback CLI reads `review-manifest.json` and follows `vendors[].findings_path` entries
- **THEN** each `findings_path` SHALL be a simple filename (no directory components, no `..`)
- **AND** each resolved file SHALL have a parent directory equal to the checkpoint dir (no escape via symlinks)
- **AND** any `findings_path` failing these checks SHALL cause the CLI to refuse with a structured error
