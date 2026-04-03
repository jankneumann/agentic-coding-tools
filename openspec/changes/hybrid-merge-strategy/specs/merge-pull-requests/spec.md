# Delta: merge-pull-requests

## MODIFIED Requirements

### Requirement: Merge Strategy Selection

The merge skill SHALL select a merge strategy based on PR origin classification rather than using a single hardcoded default.

Agent-authored PRs (`openspec`, `codex` origins) SHALL default to rebase-merge to preserve granular commit history. Automation and dependency PRs (`sentinel`, `bolt`, `palette`, `dependabot`, `renovate` origins) and manual PRs (`other` origin) SHALL default to squash-merge.

The operator SHALL be able to override the default strategy for any individual PR during the interactive review step.

#### Scenario: Agent-authored PR uses rebase-merge by default

WHEN a PR with origin `openspec` or `codex` is merged without an explicit strategy override
THEN the merge strategy SHALL be `rebase`
AND the individual commits from the PR branch SHALL appear on main

#### Scenario: Dependency PR uses squash-merge by default

WHEN a PR with origin `dependabot` or `renovate` is merged without an explicit strategy override
THEN the merge strategy SHALL be `squash`
AND a single squash commit SHALL appear on main

#### Scenario: Automation PR uses squash-merge by default

WHEN a PR with origin `sentinel`, `bolt`, or `palette` is merged without an explicit strategy override
THEN the merge strategy SHALL be `squash`

#### Scenario: Operator overrides default strategy via CLI flag

WHEN the operator passes `--strategy <value>` to `merge_pr.py`
THEN the specified strategy SHALL be used regardless of origin classification

#### Scenario: Rebase-merge fails due to merge conflicts

WHEN a rebase-merge is attempted and GitHub reports a conflict
THEN the merge skill SHALL surface the conflict status to the operator
AND SHALL NOT automatically fall back to squash-merge
