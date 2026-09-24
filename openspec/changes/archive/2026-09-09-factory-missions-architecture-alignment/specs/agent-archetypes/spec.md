# agent-archetypes Spec Delta — Factory Missions Architecture Alignment

## ADDED Requirements

### Requirement: Worker-Validator Vendor Diversity

When dispatching a worker (implementer) and a validator (reviewer or behavioral validator) to the same OpenSpec change, the dispatcher SHALL select agents from different vendors. This applies to both `review_dispatcher.py` (validator selection) and the worker-side selection logic in `implement-feature` (worker selection).

The dispatcher MUST track the vendor of each agent dispatched within a change's session and exclude already-used vendors from subsequent selections of the opposite role (worker vs validator) for that same change.

When only one vendor is available (e.g., the agents.yaml registry contains only one configured vendor, or rate limits exhausted all alternatives), the dispatcher MUST log a clear warning naming the policy violation and continue with the single available vendor. The dispatcher MUST NOT block dispatch.

The policy MUST be configurable in `agents.yaml` under a top-level `policies.vendor_diversity` key with at least the fields `enforce_for: [worker_vs_validator]` and `fallback: warn_and_continue`. The default for new installations MUST be enforcement enabled.

#### Scenario: Worker and validator dispatch to different vendors

- **GIVEN** an `agents.yaml` registry with vendors `claude`, `codex`, `gemini`
- **AND** a worker has been dispatched to change `example-feature` using vendor `claude`
- **WHEN** the dispatcher selects a validator for the same change-id
- **THEN** the dispatcher MUST exclude `claude` from candidate selection
- **AND** the dispatcher MUST select from `codex` or `gemini`
- **AND** the dispatcher MUST log "vendor_diversity: excluded claude (worker), selected codex (validator) for example-feature"

#### Scenario: Single-vendor environment falls back gracefully

- **GIVEN** an `agents.yaml` registry with only vendor `claude` available
- **AND** a worker has been dispatched using `claude`
- **WHEN** the dispatcher selects a validator for the same change
- **THEN** the dispatcher MUST log a warning: "vendor_diversity: only 1 vendor available (claude), violating policy but continuing"
- **AND** the dispatcher MUST select `claude` for the validator role
- **AND** the dispatcher MUST NOT exit with an error

#### Scenario: Policy disabled allows same-vendor dispatch

- **GIVEN** an `agents.yaml` with `policies.vendor_diversity.enforce_for: []`
- **AND** a worker dispatched with `claude`
- **WHEN** the dispatcher selects a validator
- **THEN** the dispatcher MAY select `claude` without warning
- **AND** the dispatcher MUST log "vendor_diversity: policy disabled by config"

#### Scenario: Vendor exhaustion within a session is tracked

- **GIVEN** an `agents.yaml` with vendors `claude`, `codex`
- **AND** for change `example-feature`, a worker dispatched with `claude` and a validator dispatched with `codex`
- **WHEN** a second validator is requested for the same change
- **THEN** the dispatcher MAY select either `claude` or `codex` (the worker-validator constraint applies once per role pair, not transitively)
- **AND** the dispatcher MUST log the role constraint that was checked

#### Scenario: Vendor-tracking session state is change-scoped and tamper-resistant

- **GIVEN** the dispatcher tracks worker/validator vendor history
- **WHEN** session state is persisted between dispatcher invocations within one OpenSpec change
- **THEN** session state MUST be stored at `openspec/changes/<change-id>/.dispatch-state.json` (change-scoped, not global)
- **AND** the file MUST be written with mode `0644` (owner-writable, world-readable for transparency, but not world-writable)
- **AND** the dispatcher MUST refuse to read state if the file's permissions include world-write (`0002` bit set), logging an error and falling back to no-history mode
- **AND** the file MUST be removed by `/cleanup-feature` when the change is archived (no orphan state files persist)
- **AND** state MUST be JSON conforming to `{worker_vendors: [string], validator_vendors: [string], change_id: string}` (other fields ignored)

#### Scenario: Session-state storage is tamper-resistant and change-scoped

- **GIVEN** the dispatcher has tracked vendor selections for change `example-feature` (worker=claude, validator=codex)
- **WHEN** a second invocation of the dispatcher runs for the same change-id within the same session
- **THEN** the dispatcher MUST persist its selection state under `openspec/changes/<change-id>/.dispatch-state/vendor-history.json` (or an equivalent change-scoped path resolved from `agents.yaml.policies.vendor_diversity.state_dir`)
- **AND** the state file MUST be created with mode `0600` (owner read/write only)
- **AND** when `/cleanup-feature <change-id>` runs, the `.dispatch-state/` directory MUST be removed alongside other change artifacts
- **AND** state from a different change-id MUST NOT influence vendor selection for the active change (no cross-change contamination)
