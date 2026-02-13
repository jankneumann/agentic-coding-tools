## ADDED Requirements

### Requirement: Delegated Agent Identity

The system SHALL support binding agent identity to the human user or parent agent that authorized the session, enabling permission inheritance and full audit attribution.

- Agent sessions SHALL accept an optional `delegated_from` field identifying the authorizing principal
- When `delegated_from` is set, Cedar policies SHALL have access to the delegating principal's attributes for authorization decisions
- The audit trail SHALL record both `agent_id` and `delegated_from` for every operation
- MCP tools SHALL accept an optional `on_behalf_of` parameter, validated against session credentials
- HTTP API requests SHALL accept `delegated_from` in the request body, validated against the API key's ownership scope
- If `delegated_from` is not provided, the agent SHALL be treated as self-authorized (backward-compatible default)

#### Scenario: Agent session with delegated identity
- **WHEN** agent registers session with `delegated_from: "user:jane@example.com"`
- **THEN** system stores the delegation binding in `agent_sessions`
- **AND** Cedar entity for the agent includes `delegated_by: "user:jane@example.com"` attribute
- **AND** all subsequent operations by this agent are attributed to both agent and delegating user

#### Scenario: Cedar policy restricts based on delegating user
- **WHEN** Cedar policy contains `when { principal.delegated_by == "user:intern@example.com" && principal.trust_level > 2 }`
- **AND** agent with `delegated_from: "user:intern@example.com"` attempts trust-level-3 operation
- **THEN** system denies the operation because the delegating user's policy restricts elevation

#### Scenario: Agent without delegated identity (backward compatible)
- **WHEN** agent registers session without `delegated_from`
- **THEN** system treats the agent as self-authorized
- **AND** Cedar entity has `delegated_by: ""` (empty string)
- **AND** existing policies that do not reference `delegated_by` continue to function unchanged

#### Scenario: Delegated identity in audit trail
- **WHEN** agent with `delegated_from: "user:jane@example.com"` acquires a file lock
- **THEN** audit log entry contains both `agent_id` and `delegated_from` fields
- **AND** audit queries support filtering by `delegated_from`

---

### Requirement: Human-in-the-Loop Approval Gates

The system SHALL support blocking approval gates that suspend high-risk operations until a human reviewer approves or denies them.

- Guardrail rules SHALL support `severity: approval_required` in addition to `block` and `warn`
- When an operation triggers an `approval_required` guardrail, the operation SHALL be suspended and an approval request inserted into `approval_queue`
- Approval requests SHALL include: operation details, agent identity, risk context, and requesting reason
- Reviewers SHALL be able to approve or deny requests via HTTP API
- Approved operations SHALL resume execution; denied operations SHALL return an error to the agent
- Unanswered requests SHALL auto-deny after a configurable timeout (default: 1 hour)
- All approval decisions SHALL be logged immutably in the audit trail

#### Scenario: Destructive operation triggers approval gate
- **WHEN** agent submits work containing `git push --force` and guardrail rule has `severity: approval_required`
- **THEN** system suspends the operation
- **AND** inserts approval request into `approval_queue` with status `pending`
- **AND** returns `{success: false, status: "approval_pending", request_id: uuid, message: "Human approval required"}`

#### Scenario: Reviewer approves pending operation
- **WHEN** reviewer calls `POST /approvals/{request_id}/decide` with `{decision: "approved", reason: "Verified safe"}`
- **THEN** system updates approval request status to `approved`
- **AND** the agent can re-attempt the operation, which now proceeds
- **AND** audit trail records the approval with reviewer identity and reason

#### Scenario: Reviewer denies pending operation
- **WHEN** reviewer calls `POST /approvals/{request_id}/decide` with `{decision: "denied", reason: "Too risky"}`
- **THEN** system updates approval request status to `denied`
- **AND** agent receives `{success: false, error: "approval_denied", reason: "Too risky"}` on next check
- **AND** audit trail records the denial

#### Scenario: Approval request auto-expires
- **WHEN** approval request remains in `pending` status beyond the configured timeout
- **THEN** system automatically sets status to `expired`
- **AND** agent receives `{success: false, error: "approval_expired"}`
- **AND** audit trail records the expiration

#### Scenario: Agent checks approval status
- **WHEN** agent calls `check_approval(request_id)`
- **THEN** system returns `{request_id, status: "pending"|"approved"|"denied"|"expired", decided_by?, decided_at?, reason?}`

---

### Requirement: Contextual Risk Scoring

The system SHALL compute dynamic risk scores for operations based on contextual factors, enabling graduated authorization responses instead of binary allow/deny decisions.

- Risk scores SHALL be computed on a 0.0 to 1.0 scale
- Risk factors SHALL include: agent trust level, operation severity, resource sensitivity, recent violation count, session age, and time-of-day
- Risk scores SHALL be passed to Cedar as `context.risk_score` for policy-based threshold evaluation
- Risk thresholds SHALL be configurable: low (auto-allow), medium (log + allow), high (require approval)
- Recent violation counts SHALL be tracked per-agent in a configurable sliding window (default: 1 hour)
- The risk scorer SHALL be disabled by default (`RISK_SCORING_ENABLED=false`), returning 0.0 as pass-through

#### Scenario: Low-risk operation auto-allowed
- **WHEN** agent with trust_level 3, zero recent violations, performs a read operation
- **THEN** risk scorer computes score below low threshold (e.g., 0.1)
- **AND** operation proceeds without additional checks

#### Scenario: Medium-risk operation logged
- **WHEN** agent with trust_level 2, two recent violations, performs a write operation on a non-sensitive file
- **THEN** risk scorer computes score in medium range (e.g., 0.4)
- **AND** operation proceeds
- **AND** audit trail records the elevated risk score

#### Scenario: High-risk operation requires approval
- **WHEN** agent with trust_level 2, five recent violations, performs an admin operation
- **THEN** risk scorer computes score above high threshold (e.g., 0.8)
- **AND** system routes to approval gate (if approval gates enabled)
- **OR** blocks the operation (if approval gates disabled)

#### Scenario: Risk scoring disabled (default)
- **WHEN** `RISK_SCORING_ENABLED=false`
- **THEN** risk scorer returns 0.0 for all operations
- **AND** authorization proceeds based on trust levels and guardrails only (existing behavior)

#### Scenario: Cedar policy uses risk score
- **WHEN** Cedar policy contains `when { context.risk_score > 0.7 }` in a forbid rule
- **AND** operation has computed risk score of 0.8
- **THEN** Cedar evaluation denies the operation based on the risk threshold

---

### Requirement: Real-Time Policy Synchronization

The system SHALL support push-based policy cache invalidation to reduce policy propagation latency from TTL-based polling to sub-second updates.

- The system SHALL subscribe to Supabase Realtime channel on the `cedar_policies` table
- On INSERT, UPDATE, or DELETE events, the system SHALL immediately invalidate the Cedar policy cache
- If Realtime connection is unavailable or drops, the system SHALL fall back to TTL-based polling (existing behavior)
- The `PolicySyncService` SHALL implement a pluggable interface (`start`, `stop`, `on_policy_change`) to allow future replacement with OPAL
- Real-time sync SHALL be opt-in via `POLICY_SYNC_ENABLED` environment variable (default: false)

#### Scenario: Policy updated with Realtime enabled
- **WHEN** operator updates a row in `cedar_policies` table
- **AND** `POLICY_SYNC_ENABLED=true`
- **THEN** Supabase Realtime delivers change event to `PolicySyncService`
- **AND** `CedarPolicyEngine.invalidate_cache()` is called within 1 second
- **AND** next authorization check loads the updated policy

#### Scenario: Policy updated with Realtime disabled
- **WHEN** operator updates a row in `cedar_policies` table
- **AND** `POLICY_SYNC_ENABLED=false`
- **THEN** policy cache expires after TTL (default 300 seconds)
- **AND** next authorization check after TTL expiry loads the updated policy

#### Scenario: Realtime connection drops
- **WHEN** Supabase Realtime WebSocket connection is lost
- **THEN** `PolicySyncService` attempts reconnection with exponential backoff
- **AND** falls back to TTL-based polling until connection is restored
- **AND** logs connection state changes for operational visibility

#### Scenario: OPAL replacement path
- **WHEN** system scales to multiple coordination API instances
- **THEN** operator can implement `OpalPolicySyncService` with the same interface
- **AND** swap it in via configuration without changing policy engine or Cedar policies

---

### Requirement: Policy Version History

The system SHALL maintain a complete version history of all Cedar policy changes, enabling audit, rollback, and change tracking.

- Every INSERT, UPDATE, and DELETE on `cedar_policies` SHALL be captured in `cedar_policies_history`
- History records SHALL include: policy_id, version number, policy_text, changed_by, changed_at, change_type
- Policy version numbers SHALL auto-increment on each update
- Operators SHALL be able to rollback a policy to a previous version
- Policy mutations SHALL be logged in the audit trail with before/after content

#### Scenario: Policy update creates history entry
- **WHEN** operator updates the `write-operations` policy in `cedar_policies`
- **THEN** a trigger copies the previous version to `cedar_policies_history`
- **AND** the `policy_version` column on `cedar_policies` increments

#### Scenario: Policy rollback to previous version
- **WHEN** operator calls `POST /policies/write-operations/rollback?version=3`
- **THEN** system retrieves version 3 from `cedar_policies_history`
- **AND** updates `cedar_policies` with the historical policy_text
- **AND** creates a new history entry recording the rollback
- **AND** logs the rollback in audit trail

#### Scenario: Policy deletion preserves history
- **WHEN** operator deletes a policy from `cedar_policies`
- **THEN** a trigger copies the final version to `cedar_policies_history` with `change_type: "delete"`
- **AND** full history remains queryable

#### Scenario: List policy versions
- **WHEN** agent or operator calls `list_policy_versions(policy_name, limit?)`
- **THEN** system returns array of `{version, policy_text, changed_by, changed_at, change_type}` ordered by version descending

---

### Requirement: Session-Scoped Permission Grants

The system SHALL support per-session permission grants that expire when the session ends, enabling a zero-standing-permissions model where agents request and justify access rather than inheriting permanent trust levels.

- Agents SHALL be able to request elevated permissions for the current session via `request_permission(operation, justification)`
- Permission grants SHALL be scoped to the requesting agent's session and expire when the session ends
- Grant requests MAY require human approval (routed through approval gates) based on the operation's risk level
- Cedar policies SHALL support `session_grants` as a principal attribute for conditional evaluation
- The system SHALL log all permission grants and their justifications in the audit trail
- Default behavior (no session grants) SHALL match existing trust-level-based authorization

#### Scenario: Agent requests session-scoped write permission
- **WHEN** agent with trust_level 1 calls `request_permission("acquire_lock", "Need to fix critical bug in auth.py")`
- **AND** policy allows self-service grants for `acquire_lock` at trust_level 1
- **THEN** system adds `acquire_lock` to agent's `session_grants`
- **AND** agent can perform `acquire_lock` for the remainder of the session
- **AND** grant is logged with justification in audit trail

#### Scenario: Permission grant requires approval
- **WHEN** agent requests `force_push` permission
- **AND** policy requires approval for `force_push` grants
- **THEN** system routes to approval gate
- **AND** agent must wait for human approval before grant is active

#### Scenario: Session ends and grants expire
- **WHEN** agent session terminates (normal exit or stale heartbeat cleanup)
- **THEN** all session-scoped permission grants are automatically revoked
- **AND** audit trail records grant expiration

#### Scenario: Cedar policy evaluates session grants
- **WHEN** Cedar policy contains `when { principal.session_grants.contains(action) }`
- **AND** agent has been granted the requested operation for this session
- **THEN** Cedar evaluation permits the operation
