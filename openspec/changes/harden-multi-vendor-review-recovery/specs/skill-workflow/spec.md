# skill-workflow — Delta for harden-multi-vendor-review-recovery

## ADDED Requirements

### Requirement: Vendor Findings Checkpoint Layout

The system SHALL define a single canonical on-disk layout for per-vendor review findings, used by both the in-process `converge()` API and the CLI dispatcher. The layout SHALL be writable and readable by a shared helper module so neither caller hardcodes filenames or directory structure.

The canonical layout SHALL be:

- Directory: `<artifacts_dir>/.review-cache/`
- Per-vendor file: `<artifacts_dir>/.review-cache/findings-{vendor}-{review_type}.json`
- Manifest: `<artifacts_dir>/.review-cache/review-manifest.json`

The manifest SHALL include `change_id`, `review_type`, `vendors`, `created_at` (ISO-8601 UTC), `schema_version`, and per-vendor `findings_path` entries.

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
- **AND** an operator SHALL be able to manually invoke `consensus_synthesizer.py` against the checkpoint directory and obtain a consensus report

#### Scenario: Empty review round still produces a manifest
- **WHEN** all vendors return zero findings (or no vendors are reachable)
- **THEN** the checkpoint helper SHALL still write `review-manifest.json`
- **AND** the manifest's `vendors` array MAY be empty
- **AND** no per-vendor finding files SHALL be written for vendors that produced no output

### Requirement: CLI Subprocess Fallback on Synthesis Failure

When `synthesizer.synthesize()` raises an exception during the in-process `converge()` flow, the system SHALL automatically invoke `consensus_synthesizer.py` as a subprocess against the checkpoint directory. If the subprocess succeeds, `converge()` SHALL return its result with the recovery marked observable. If the subprocess also fails, `converge()` SHALL raise the **original** synthesis exception, with the subprocess stderr tail attached to a structured diagnostics field.

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
- **THEN** the subprocess SHALL be passed the checkpoint directory path and `--review-type <type>` so it can locate the per-vendor finding files
- **AND** no path translation or finding-file copying SHALL be required between the in-process write and the subprocess read

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

Each event SHALL include `change_id`, `review_type`, `original_exception_class`, `original_exception_message`, and `timestamp` (ISO-8601 UTC).

#### Scenario: Successful fallback emits exactly one audit event
- **WHEN** fallback recovery succeeds
- **THEN** exactly one `convergence.fallback_recovered` event SHALL be emitted for the invocation
- **AND** no `convergence.fallback_failed` event SHALL be emitted

#### Scenario: Double-failure emits exactly one audit event
- **WHEN** both in-process synthesis and CLI subprocess fail
- **THEN** exactly one `convergence.fallback_failed` event SHALL be emitted for the invocation
- **AND** no `convergence.fallback_recovered` event SHALL be emitted

#### Scenario: Audit emission failure does not mask result
- **WHEN** the audit emission itself fails (coordinator unreachable, etc.)
- **THEN** `converge()` SHALL still return the recovered result (or re-raise the original exception, as appropriate)
- **AND** the audit failure SHALL be logged as a warning but SHALL NOT change the recovery outcome
