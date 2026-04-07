# skill-workflow Specification Delta

## ADDED Requirements

### Requirement: Rework Report Artifact

The workflow SHALL produce a machine-readable `rework-report.json` artifact during validation whenever scenario-based validation is executed.

The artifact SHALL include:
- failed scenario IDs
- scenario visibility (`public` or `holdout`)
- implicated requirement refs
- implicated interfaces or contracts
- likely owners or work packages
- recommended next action (`iterate`, `revise-spec`, `defer`, `block-cleanup`)

#### Scenario: Validation produces rework report
Given validation runs scenario-based checks and one or more scenarios fail
When validation completes
Then `rework-report.json` is written in the change directory with the failing scenarios and routing metadata

#### Scenario: Iterate consumes rework report
Given `rework-report.json` exists with recommended action `iterate`
When `/iterate-on-implementation` runs
Then it uses that artifact as the primary input for prioritizing fixes

#### Scenario: Holdout failure blocks cleanup
Given `rework-report.json` includes a failed holdout scenario with recommended action `block-cleanup`
When `/cleanup-feature` evaluates merge readiness
Then cleanup stops and reports the holdout failure as a blocking issue

### Requirement: Process Analysis Artifact

The workflow SHALL support optional `process-analysis.md` and `process-analysis.json` artifacts summarizing convergence behavior for a change.

The process-analysis artifact SHALL report at minimum:
- validation loops taken
- repeated findings or flaky scenarios
- time to first passing validation
- requirement or file churn
- deferred vs resolved finding counts

#### Scenario: Process analysis summarizes convergence
Given a change has gone through implementation, validation, and at least one rework loop
When process analysis is generated
Then it summarizes loops, churn, and outcome counts in machine-readable and markdown forms

#### Scenario: Process analysis tolerates missing optional artifacts
Given a change has validation-report and session-log but no impl-findings
When process analysis is generated
Then it still produces output and marks the missing artifact as absent rather than failing

#### Scenario: Archive mining can consume process analysis
Given `process-analysis.json` exists for an archived change
When archive mining runs
Then the process-analysis data is normalized into the archive index

### Requirement: Visibility-Aware Workflow Gates

The workflow SHALL enforce scenario visibility at phase boundaries.

`/implement-feature` and `/iterate-on-implementation` SHALL run public scenarios as soft gates when scenario packs exist. `/validate-feature`, `/cleanup-feature`, and merge-time validation SHALL be able to run holdout scenarios, with holdout failures treated as hard-gate evidence unless explicitly downgraded by policy.

#### Scenario: Implement feature runs public scenarios only
Given a change with public and holdout scenario packs
When `/implement-feature` executes validation-aware checks
Then only public scenarios are run in that phase

#### Scenario: Validate feature distinguishes public and holdout outcomes
Given both public and holdout scenarios are available
When `/validate-feature` runs
Then the validation artifacts report separate results for public and holdout scenarios

#### Scenario: Merge gate treats holdout failure as blocking
Given merge-time validation includes a failed holdout scenario
When `/merge-pull-requests` evaluates the PR
Then it blocks merge until the rework artifact no longer indicates a blocking holdout failure
