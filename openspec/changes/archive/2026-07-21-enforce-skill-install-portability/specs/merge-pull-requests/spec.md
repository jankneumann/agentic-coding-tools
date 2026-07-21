## MODIFIED Requirements

### Requirement: PR Discovery and Classification

The skill SHALL discover all open pull requests in the current repository and classify each by origin: OpenSpec, Jules/Sentinel, Jules/Bolt, Jules/Palette, Codex, Dependabot, Renovate, or other. Its discovery entry point and classifier SHALL be runnable from the installed consumer payload without importing coordinator source code.

#### Scenario: Discover open PRs
- **WHEN** the skill is invoked in a consumer repository with open PRs
- **THEN** it SHALL list all open PRs with their number, title, author, origin classification, branch name, creation date, and labels
- **AND** discovery SHALL not require `agent-coordinator/src`

#### Scenario: Import discovery without coordinator checkout
- **WHEN** `discover_prs.py --help` is executed from an rsynced `.claude/skills/merge-pull-requests` or `.agents/skills/merge-pull-requests` directory
- **AND** the consumer contains no `agent-coordinator` package
- **THEN** the command SHALL exit successfully
- **AND** classification helpers SHALL resolve from the installed payload

#### Scenario: No open PRs
- **WHEN** the skill is invoked in a repository with no open PRs
- **THEN** it SHALL report that no open PRs were found and exit gracefully
- **AND** SHALL preserve the same classification result schema as the coordinator PR-card adapter
