## ADDED Requirements

### Requirement: GATEKEEPER Shadow Judgment

The autopilot loop's GATEKEEPER phase SHALL, on every run where `change_dir`
is known, compute a second candidate verdict from a calibrated `Score`-based
judgment and record it alongside the acting verdict without acting on it.

The shadow judgment SHALL derive its candidate verdict in code from two
`Score` distributions (`verifiability`, `risk`) against thresholds sourced
from configuration; a `Choice(verdict, ...)` answer SHALL be recorded only as
a cross-check and SHALL NOT itself determine the candidate verdict.

The acting verdict returned by GATEKEEPER, and every field of `LoopState`
that verdict affects (`gate_verdict`, `val_review_enabled`, any gate
evaluation), SHALL be unaffected by the shadow judgment, for every run,
whether or not the shadow judgment is available.

#### Scenario: A shadow record per gatekeeper run appends judged verdict, both score distributions and the acting verdict

- **GIVEN** a GATEKEEPER run with a known `change_dir` and an available
  shadow judgment
- **WHEN** `_phase_gatekeeper` completes
- **THEN** exactly one `"GATEKEEPER_SHADOW"` entry is appended to
  `state.phase_history` carrying the acting verdict, the code-computed
  candidate verdict, the `Choice` cross-check answer, and both `Score`
  distributions

#### Scenario: The acting verdict is byte-identical to today's for every run in the shadow period

- **GIVEN** a recorded `gate_signals` profile from a real prior autopilot run
- **WHEN** that run is replayed through `_phase_gatekeeper` with the shadow
  judgment enabled and configured to compute a candidate verdict that
  differs from the originally recorded acting verdict
- **THEN** the returned outcome and `state.gate_verdict` are byte-identical
  to the originally recorded acting verdict

#### Scenario: The code-computed verdict is derived from the two Score distributions with thresholds read from config

- **GIVEN** a `verifiability` and a `risk` `Score` answer from the shadow
  judgment
- **WHEN** the candidate verdict is computed
- **THEN** it is produced by a pure function of those two scores and
  threshold values loaded from `gatekeeper_shadow.load_shadow_thresholds()`,
  never from a bare literal in the computation itself, and the `Choice`
  answer plays no role in that computation

#### Scenario: The GATEKEEPER shadow judgment degrades silently on unavailability

- **GIVEN** `system_one_decisions` is not installed, `decide()` returns
  `None`, or the returned answer set is missing an expected key
- **WHEN** `_phase_gatekeeper` runs
- **THEN** no `"GATEKEEPER_SHADOW"` entry is appended to `state.phase_history`
  and the acting verdict is computed exactly as it would be with no shadow
  judgment at all

#### Scenario: A reporting script emits the GATEKEEPER disagreement rate over the shadow period's runs

- **GIVEN** one or more recorded `loop-state.json` files containing
  `"GATEKEEPER_SHADOW"` `phase_history` entries
- **WHEN** `gatekeeper_shadow_report.py` is run against those files
- **THEN** it prints the fraction of entries where the candidate verdict
  differs from the acting verdict, without making any model call itself

#### Scenario: --force and the scope-safety floor are untouched

- **GIVEN** `--force` is set, or the deterministic scope-safety floor in
  `_phase_init` fires
- **WHEN** the autopilot loop runs
- **THEN** GATEKEEPER (and therefore the shadow judgment) is skipped exactly
  as it is today, and every existing test covering `--force` and the
  scope-safety floor continues to pass unmodified
