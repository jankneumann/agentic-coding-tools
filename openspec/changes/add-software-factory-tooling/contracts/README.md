# Contracts: Software Factory Tooling

This change does not introduce a public HTTP, database, or event interface contract in the planning phase.

Contract sub-types evaluated:

- **OpenAPI**: not applicable for the initial proposal; no new public API surface is required
- **Database**: not applicable for the initial proposal; archive intelligence and workflow artifacts are file-based
- **Events**: not applicable for the initial proposal; no new event bus contract is required

Internal machine-readable artifacts planned by this change:

- `scenario-pack manifest`
- `rework-report.json`
- `process-analysis.json`
- `archive-intelligence index`
- `DTU fidelity report`

These artifact schemas will be defined during implementation and treated as internal workflow contracts.
