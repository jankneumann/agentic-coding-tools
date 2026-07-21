## ADDED Requirements

### Requirement: Portable GitHub Classifier Ownership

GitHub PR classification SHALL have one canonical implementation inside the installable skills boundary. The coordinator SHALL import or load that portable implementation; installed skills MUST NOT import from `agent-coordinator/src`.

#### Scenario: Coordinator and installed skill share classification behavior
- **WHEN** the coordinator adapts a GitHub REST PR and the installed merge skill classifies the equivalent `gh` payload
- **THEN** both paths SHALL use the same canonical classification implementation
- **AND** return equivalent raw origin and change-id values before PR-card folding

#### Scenario: Installed skill runs without coordinator source
- **WHEN** the merge skill is installed in a consumer with no `agent-coordinator/src/github_classifier.py`
- **THEN** its classifier SHALL remain importable and preserve all OpenSpec, Jules, Codex, Dependabot, Renovate, and manual classification rules
- **AND** coordinator-specific REST adaptation SHALL remain available to the coordinator without reversing the dependency direction
