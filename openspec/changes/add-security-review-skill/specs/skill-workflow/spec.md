## ADDED Requirements

### Requirement: Cross-Project Security Review Skill

The system SHALL provide a `/security-review` skill that can run against any repository and produce a structured security assessment without requiring project-specific manual scripting.

#### Scenario: Run security review in auto mode
- **WHEN** a user invokes `/security-review` in a supported repository
- **THEN** the skill SHALL detect the project profile and select compatible scanners
- **AND** the skill SHALL execute configured scanners and produce normalized outputs

#### Scenario: Unsupported or ambiguous repository shape
- **WHEN** the repository does not match a known profile with high confidence
- **THEN** the skill SHALL fall back to a generic profile with explicitly documented skipped checks
- **AND** the output SHALL include follow-up instructions for manual configuration

### Requirement: Project Profile Detection and Scanner Matrix Selection

The `/security-review` skill SHALL auto-detect one or more project profiles from repository signals and map each profile to a scanner matrix.

#### Scenario: Mixed-stack profile detection
- **WHEN** a repository contains multiple ecosystem signals (for example `pyproject.toml` and `package.json`)
- **THEN** the skill SHALL classify the repository as mixed-stack
- **AND** the scanner plan SHALL include applicable checks from each detected profile

#### Scenario: Profile detection confidence is low
- **WHEN** profile detection cannot determine a reliable scanner matrix
- **THEN** the skill SHALL mark profile confidence as low in the report
- **AND** it SHALL require explicit profile override for strict gating mode

### Requirement: OWASP Dependency-Check Adapter

The `/security-review` skill SHALL support OWASP Dependency-Check execution through native CLI or Docker fallback and normalize the results.

#### Scenario: Dependency-Check executes successfully
- **WHEN** dependency scanning is enabled and at least one execution method is available
- **THEN** the skill SHALL run OWASP Dependency-Check for the target repository
- **AND** findings SHALL be normalized into the shared reporting schema with CVE and severity metadata

#### Scenario: Dependency-Check prerequisites missing
- **WHEN** both native and Docker execution paths are unavailable
- **THEN** the skill SHALL mark the dependency-check scanner status as unavailable with remediation guidance
- **AND** strict gate mode SHALL treat the run as failing or inconclusive according to configured policy

### Requirement: OWASP ZAP Docker Adapter

The `/security-review` skill SHALL support ZAP Docker scans for web/API targets and normalize findings into the shared reporting schema.

#### Scenario: ZAP baseline or API scan runs
- **WHEN** a reachable web/API target is configured for DAST
- **THEN** the skill SHALL run the configured ZAP Docker scan mode
- **AND** normalized findings SHALL include rule IDs, risk levels, and request/endpoint context

#### Scenario: DAST target is unavailable
- **WHEN** the configured target cannot be reached during preflight checks
- **THEN** the skill SHALL skip the ZAP scan with explicit diagnostic context
- **AND** strict gate mode SHALL not silently pass the overall review

#### Scenario: DAST profile detected without target configuration
- **WHEN** repository profiling indicates DAST coverage is expected and no `--zap-target` is provided
- **THEN** the skill SHALL mark ZAP execution status as unavailable with guidance to set `--zap-target`
- **AND** strict gate mode SHALL produce `INCONCLUSIVE` unless degraded passing is explicitly enabled

### Requirement: Skill Script Directory Convention

The `/security-review` skill SHALL keep all executable helper scripts under `skills/security-review/scripts/`.

#### Scenario: Add new helper script
- **WHEN** implementation adds a helper script used by `/security-review`
- **THEN** the script SHALL be created in `skills/security-review/scripts/`
- **AND** skill documentation SHALL reference the script using that path

#### Scenario: Planned script path outside scripts directory
- **WHEN** a planned script path is outside `skills/security-review/scripts/`
- **THEN** plan validation SHALL treat it as a proposal inconsistency
- **AND** the plan SHALL be updated before approval

### Requirement: Dependency Bootstrap and Install Guidance

The `/security-review` skill SHALL provide dependency bootstrap scripts and platform-specific install guidance for required scanner prerequisites.

#### Scenario: Missing prerequisites with bootstrap enabled
- **WHEN** required tooling (for example Java, Docker, or scanner binaries) is missing and bootstrap mode is enabled
- **THEN** the skill SHALL run dependency bootstrap helpers for the current platform
- **AND** the report SHALL record which dependencies were installed or attempted

#### Scenario: Bootstrap unavailable or disabled
- **WHEN** required tooling is missing and automated bootstrap cannot run
- **THEN** the skill SHALL emit explicit install instructions for the missing dependencies
- **AND** the gate outcome SHALL remain `FAIL` or `INCONCLUSIVE` until prerequisites are satisfied

### Requirement: Normalized Risk-Gated Reporting

The `/security-review` skill SHALL aggregate scanner outputs into a canonical report model and compute a deterministic gate decision from configured severity thresholds.

#### Scenario: Findings exceed configured risk threshold
- **WHEN** normalized findings include severities at or above the configured `--fail-on` threshold
- **THEN** the skill SHALL return a failing gate decision with non-zero exit behavior
- **AND** the report SHALL identify which findings triggered the gate

#### Scenario: Partial scanner execution
- **WHEN** one or more scanners are skipped, unavailable, or fail to execute
- **THEN** the report SHALL include per-scanner execution status and confidence annotations
- **AND** the overall decision SHALL be marked `INCONCLUSIVE` unless policy explicitly allows degraded passing

#### Scenario: Intermediate outputs stored in docs/security-review
- **WHEN** `/security-review` runs for a repository
- **THEN** aggregate, gate, and canonical report outputs SHALL be written under `docs/security-review/`
- **AND** workflow documentation SHALL use `docs/security-review/` as the default report location

### Requirement: Security Workflow Position

The skill workflow SHALL support `/security-review` as an optional security gate that can run before PR review or before `/cleanup-feature` without requiring workflow restructuring.

#### Scenario: Security review before PR review
- **WHEN** a feature branch is ready for review and the operator invokes `/security-review`
- **THEN** the skill SHALL produce a gate outcome and remediation summary suitable for PR discussion
- **AND** the existing `/implement-feature` and `/iterate-on-implementation` flow SHALL remain unchanged

#### Scenario: Security review omitted
- **WHEN** the user chooses not to run `/security-review` for a change
- **THEN** the existing workflow SHALL remain valid and executable
- **AND** the system SHALL not introduce hidden mandatory dependencies on `/security-review`

### Requirement: Security Review Artifact Dependency Flow

The workflow SHALL support an OpenSpec `security-review-report.md` artifact generated by `/security-review` and checked by `/validate-feature` before full validation phases execute.

#### Scenario: Security review writes artifact for a change
- **WHEN** `/security-review` is invoked with a change-id
- **THEN** it SHALL write `openspec/changes/<change-id>/security-review-report.md`
- **AND** the artifact SHALL contain scanner execution status, severity summary, and gate decision

#### Scenario: Validate feature checks security artifact before validation
- **WHEN** `/validate-feature <change-id>` starts
- **THEN** it SHALL check for `security-review-report.md` prior to deployment/spec checks
- **AND** if missing or stale relative to current HEAD, it SHALL fail fast or mark validation as blocked with remediation guidance
