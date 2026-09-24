## ADDED Requirements

### Requirement: Fact-Check First-Stage Ground Screen

`fact_check.run` SHALL screen each non-protected finding with a calibrated judgment before deciding whether to send it to the existing economy-tier LLM prompt (stage two). The screen SHALL ask one `Noul` per finding for Ground A ("the code this finding describes is not in the subject file's diff") and one `Noul` per finding as a Ground-B screen ("a line in this diff directly contradicts the finding's central claim"), batched into a single calibrated-decision call per fact-check invocation. A finding whose Ground-A probability clears a config-held floor SHALL be removed directly, without a quoted evidence line, mirroring Ground A's existing no-evidence-required treatment. A finding whose Ground-B probability clears the floor SHALL be included in the batch sent to stage two, where the existing quoted-evidence-line check (`_evidence_line_in_subject_diff`) SHALL still gate any removal, unchanged. A finding clearing neither ground SHALL be kept without ever reaching stage two. Protected-subject findings (per the existing `protected_subject` veto) SHALL never be screened, since no ground's verdict can override that veto; they SHALL always reach stage two exactly as before this requirement. When the screen is unavailable (module missing or no usable answer), every finding SHALL fall through to stage two exactly as `fact_check.run` behaved before this requirement.

#### Scenario: A batch screening entirely below the Ground-B threshold makes no stage-two call

- **GIVEN** a batch of non-protected findings whose Ground-A and Ground-B probabilities are all below the configured floor
- **WHEN** the fact-check pass runs and the screen is available
- **THEN** the stage-two caller SHALL NOT be invoked
- **AND** every finding SHALL be kept

#### Scenario: A confident Ground-A screen removes a finding without stage two

- **GIVEN** a finding whose Ground-A probability clears the configured floor
- **WHEN** the fact-check pass runs
- **THEN** the finding SHALL be removed with ground `A_absent_from_subject_diff` and no evidence line
- **AND** the stage-two caller SHALL NOT be invoked for that finding

#### Scenario: A confident Ground-B screen still requires stage-two evidence to remove

- **GIVEN** a finding whose Ground-B probability clears the configured floor
- **WHEN** stage two's response does not include a diff line that literally appears in the finding's subject file
- **THEN** the finding SHALL be kept, not removed

#### Scenario: Protected-subject findings are never screened

- **GIVEN** a finding matching a protected-subject category
- **WHEN** the fact-check pass runs
- **THEN** the screen's calibrated-decision call SHALL NOT be invoked for that finding
- **AND** the finding SHALL still reach stage two exactly as before this requirement

#### Scenario: An unavailable screen falls back to unmodified stage-two behavior

- **GIVEN** the screen is unavailable (the calibrated-decision module is missing, or returns no usable answer)
- **WHEN** the fact-check pass runs
- **THEN** every non-protected finding SHALL be sent to stage two exactly as `fact_check.run` behaved before this requirement

#### Scenario: A stage-two call failure discards any tentative stage-one removal

- **GIVEN** a batch where the screen confidently resolved one finding via Ground A and flagged another for stage two
- **WHEN** the stage-two caller raises or returns an unparsable response
- **THEN** every finding in the batch SHALL be kept, including the one the screen resolved via Ground A
