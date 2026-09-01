## ADDED Requirements

### Requirement: Supervised Background Dispatch Boundary

The skill workflow SHALL treat a supervised background Autopilot agent as an isolated write-capable worker whose public result is the supervised-dispatch result contract rather than its conversation transcript.

#### Scenario: Background agent completes normally
- **WHEN** a supervised Autopilot agent finishes in its verified managed worktree
- **THEN** the host returns a schema-valid outcome and handoff identifier through `dispatch_fn`
- **AND** the parent supervisor does not copy the child transcript into its session or durable state

#### Scenario: Background agent fails without a handoff
- **WHEN** a supervised Autopilot agent exits unsuccessfully and produces no valid handoff
- **THEN** the host returns a correlated failed outcome with a bounded reason
- **AND** the roadmap failure policy handles the failure without treating transcript text as executable context

#### Scenario: Inspect the parent session after two child runs
- **WHEN** a fake host-event capture adapter drives two background child sessions whose transcripts contain unique sentinels and whose public results are schema-valid
- **THEN** the adapter-captured parent-session event stream contains only requests, task handles, lease events, and the two structured outcomes, with no transcript sentinel
- **AND** checkpoint, learning, handoff, and supervisor-record outputs contain no transcript sentinel
