## 1. Database Migrations

- [x]1.1 Add `delegated_from` nullable TEXT column to `agent_sessions` table
- [x]1.2 Create `approval_queue` table (id, agent_id, operation, resource, context, status, decided_by, decided_at, reason, expires_at, created_at)
- [x]1.3 Create `cedar_policies_history` table (id, policy_id, version, policy_text, changed_by, changed_at, change_type)
- [x]1.4 Add PostgreSQL trigger on `cedar_policies` to copy rows to history on UPDATE/DELETE
- [x]1.5 Add `policy_version` auto-incrementing column to `cedar_policies`
- [x]1.6 Create `session_permission_grants` table (id, session_id, agent_id, operation, justification, granted_at, expires_at, approved_by)
- [x]1.7 Add RLS policies for new tables (service_role full access, anon read where appropriate)

## 2. Delegated Identity

- [x]2.1 Update `AgentConfig` in `src/config.py` to include `delegated_from` from env var
- [x]2.2 Update Cedar schema (`cedar/schema.cedarschema`) to add `delegated_by` attribute on Agent entity and `DelegatingUser` entity type
- [x]2.3 Update `CedarPolicyEngine._build_entity()` in `src/policy_engine.py` to include `delegated_by` attribute
- [x]2.4 Update `NativePolicyEngine.check_operation()` to pass `delegated_from` through context
- [x]2.5 Update `AuditService.log_operation()` in `src/audit.py` to record `delegated_from`
- [x]2.6 Update MCP tools in `src/coordination_mcp.py` to accept and propagate `on_behalf_of`
- [x]2.7 Update HTTP API in `verification_gateway/coordination_api.py` to accept `delegated_from` in requests
- [x]2.8 Write unit tests for delegated identity propagation and Cedar evaluation

## 3. Human-in-the-Loop Approval Gates

- [x]3.1 Create `src/approval.py` with `ApprovalService` (submit_request, check_request, decide_request, expire_stale_requests)
- [x]3.2 Add `ApprovalConfig` dataclass to `src/config.py` (enabled, default_timeout, auto_deny)
- [x]3.3 Update `src/guardrails.py` to support `severity: approval_required` and route to ApprovalService
- [x]3.4 Add MCP tools: `request_approval`, `check_approval` in `src/coordination_mcp.py`
- [x]3.5 Add HTTP endpoints: `GET /approvals/pending`, `POST /approvals/{id}/decide` in coordination_api.py
- [x]3.6 Integrate approval check into work_queue.py guardrail flow (claim, complete, submit)
- [x]3.7 Add audit logging for approval decisions
- [x]3.8 Write unit tests for approval lifecycle (submit → approve, deny, expire)

## 4. Contextual Risk Scoring

- [x]4.1 Create `src/risk_scorer.py` with `RiskScorer` class (compute_score, get_violation_count)
- [x]4.2 Add `RiskScoringConfig` dataclass to `src/config.py` (enabled, low_threshold, high_threshold, violation_window)
- [x]4.3 Implement sliding-window violation counter using audit_log queries
- [x]4.4 Integrate risk score into `CedarPolicyEngine.check_operation()` as `context.risk_score`
- [x]4.5 Integrate risk score into `NativePolicyEngine.check_operation()` context
- [x]4.6 Update Cedar schema to include `risk_score` in context type
- [x]4.7 Add default Cedar policies with risk-based conditions
- [x]4.8 Write unit tests for risk scoring computation and Cedar integration

## 5. Real-Time Policy Synchronization

- [x]5.1 Create `src/policy_sync.py` with `PolicySyncService` interface and `PgListenNotifyPolicySyncService` implementation
- [x]5.2 Add `PolicySyncConfig` dataclass to `src/config.py` (enabled, reconnect_max_retries, reconnect_backoff)
- [x]5.3 Implement asyncpg LISTEN on `policy_changed` channel using a dedicated connection from the pool
- [x]5.4 Wire `on_policy_change` to `CedarPolicyEngine.invalidate_cache()`
- [x]5.5 Implement reconnection with exponential backoff on connection loss
- [x]5.6 Add fallback to TTL-based polling when LISTEN/NOTIFY unavailable
- [x]5.7 Add PostgreSQL trigger function `notify_policy_changed()` that sends `NOTIFY policy_changed, '<policy_name>'` on cedar_policies INSERT/UPDATE/DELETE (migration)
- [x]5.8 Write unit tests for policy sync lifecycle (connect, receive, invalidate, reconnect)

## 6. Policy Version History

- [x]6.1 Add `list_policy_versions` method to `CedarPolicyEngine`
- [x]6.2 Add `rollback_policy` method to `CedarPolicyEngine`
- [x]6.3 Add MCP tool: `list_policy_versions` in `src/coordination_mcp.py`
- [x]6.4 Add HTTP endpoint: `POST /policies/{name}/rollback` in coordination_api.py
- [x]6.5 Add audit logging for policy mutations (create, update, delete, rollback)
- [x]6.6 Write unit tests for version history and rollback

## 7. Session-Scoped Permission Grants

- [x]7.1 Create `src/session_grants.py` with `SessionGrantService` (request_grant, revoke_grants, get_active_grants)
- [x]7.2 Update Cedar schema to add `session_grants` attribute on Agent entity (Set<String>)
- [x]7.3 Update `CedarPolicyEngine._build_entity()` to include active session grants
- [x]7.4 Integrate grant expiration into dead agent cleanup (`discovery.py`)
- [x]7.5 Add MCP tool: `request_permission` in `src/coordination_mcp.py`
- [x]7.6 Add audit logging for grant lifecycle (request, approve, expire)
- [x]7.7 Write unit tests for session grant lifecycle and Cedar evaluation

## 8. Integration and Documentation

- [x]8.1 Update `agent-coordinator/README.md` with new features, environment variables, and architecture
- [x]8.2 Update default Cedar policies (`cedar/default_policies.cedar`) with delegation, risk, and approval conditions
- [x]8.3 Run full test suite and fix any regressions
- [x]8.4 Verify backward compatibility: all existing tests pass with features disabled
