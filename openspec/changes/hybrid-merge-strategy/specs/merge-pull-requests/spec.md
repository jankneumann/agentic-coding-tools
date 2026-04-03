# Delta: merge-pull-requests

## MODIFIED Requirements

### Requirement: Merge Strategy Selection

The merge skill SHALL select a merge strategy based on PR origin classification rather than using a single hardcoded default.

Agent-authored PRs (`openspec`, `codex` origins) SHALL default to rebase-merge to preserve granular commit history. Automation and dependency PRs (`sentinel`, `bolt`, `palette`, `dependabot`, `renovate` origins) and manual PRs (`other` origin) SHALL default to squash-merge.

The operator SHALL be able to override the default strategy for any individual PR during the interactive review step.

#### Scenario: Agent PR uses rebase-merge by default

WHEN a PR with origin `openspec` is merged
THEN the merge strategy SHALL be `rebase`
AND the individual commits from the PR branch SHALL appear on main

#### Scenario: Dependency PR uses squash-merge by default

WHEN a PR with origin `dependabot` is merged
THEN the merge strategy SHALL be `squash`
AND a single squash commit SHALL appear on main

#### Scenario: Operator overrides default strategy

WHEN the operator selects a merge strategy different from the origin default
THEN the selected strategy SHALL be used regardless of origin classification
