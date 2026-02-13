## 1. Database Migrations

- [ ] 1.1 Add `delegated_from` nullable TEXT column to `agent_sessions` table
- [ ] 1.2 Create `approval_queue` table (id, agent_id, operation, resource, context, status, decided_by, decided_at, reason, expires_at, created_at)
- [ ] 1.3 Create `cedar_policies_history` table (id, policy_id, version, policy_text, changed_by, changed_at, change_type)
- [ ] 1.4 Add PostgreSQL trigger on `cedar_policies` to copy rows to history on UPDATE/DELETE
- [ ] 1.5 Add `policy_version` auto-incrementing column to `cedar_policies`
- [ ] 1.6 Create `session_permission_grants` table (id, session_id, agent_id, operation, justification, granted_at, expires_at, approved_by)
- [ ] 1.7 Add RLS policies for new tables (service_role full access, anon read where appropriate)

## 2. Delegated Identity

- [ ] 2.1 Update `AgentConfig` in `src/config.py` to include `delegated_from` from env var
- [ ] 2.2 Update Cedar schema (`cedar/schema.cedarschema`) to add `delegated_by` attribute on Agent entity and `DelegatingUser` entity type
- [ ] 2.3 Update `CedarPolicyEngine._build_entity()` in `src/policy_engine.py` to include `delegated_by` attribute
- [ ] 2.4 Update `NativePolicyEngine.check_operation()` to pass `delegated_from` through context
- [ ] 2.5 Update `AuditService.log_operation()` in `src/audit.py` to record `delegated_from`
- [ ] 2.6 Update MCP tools in `src/coordination_mcp.py` to accept and propagate `on_behalf_of`
- [ ] 2.7 Update HTTP API in `verification_gateway/coordination_api.py` to accept `delegated_from` in requests
- [ ] 2.8 Write unit tests for delegated identity propagation and Cedar evaluation

## 3. Human-in-the-Loop Approval Gates

- [ ] 3.1 Create `src/approval.py` with `ApprovalService` (submit_request, check_request, decide_request, expire_stale_requests)
- [ ] 3.2 Add `ApprovalConfig` dataclass to `src/config.py` (enabled, default_timeout, auto_deny)
- [ ] 3.3 Update `src/guardrails.py` to support `severity: approval_required` and route to ApprovalService
- [ ] 3.4 Add MCP tools: `request_approval`, `check_approval` in `src/coordination_mcp.py`
- [ ] 3.5 Add HTTP endpoints: `GET /approvals/pending`, `POST /approvals/{id}/decide` in coordination_api.py
- [ ] 3.6 Integrate approval check into work_queue.py guardrail flow (claim, complete, submit)
- [ ] 3.7 Add audit logging for approval decisions
- [ ] 3.8 Write unit tests for approval lifecycle (submit → approve, deny, expire)

## 4. Contextual Risk Scoring

- [ ] 4.1 Create `src/risk_scorer.py` with `RiskScorer` class (compute_score, get_violation_count)
- [ ] 4.2 Add `RiskScoringConfig` dataclass to `src/config.py` (enabled, low_threshold, high_threshold, violation_window)
- [ ] 4.3 Implement sliding-window violation counter using audit_log queries
- [ ] 4.4 Integrate risk score into `CedarPolicyEngine.check_operation()` as `context.risk_score`
- [ ] 4.5 Integrate risk score into `NativePolicyEngine.check_operation()` context
- [ ] 4.6 Update Cedar schema to include `risk_score` in context type
- [ ] 4.7 Add default Cedar policies with risk-based conditions
- [ ] 4.8 Write unit tests for risk scoring computation and Cedar integration

## 5. Real-Time Policy Synchronization

- [ ] 5.1 Create `src/policy_sync.py` with `PolicySyncService` interface and `SupabaseRealtimePolicySyncService` implementation
- [ ] 5.2 Add `PolicySyncConfig` dataclass to `src/config.py` (enabled, reconnect_max_retries, reconnect_backoff)
- [ ] 5.3 Implement Supabase Realtime channel subscription for `cedar_policies` table
- [ ] 5.4 Wire `on_policy_change` to `CedarPolicyEngine.invalidate_cache()`
- [ ] 5.5 Implement reconnection with exponential backoff on WebSocket disconnect
- [ ] 5.6 Add fallback to TTL-based polling when Realtime unavailable
- [ ] 5.7 Write unit tests for policy sync lifecycle (connect, receive, invalidate, reconnect)

## 6. Policy Version History

- [ ] 6.1 Add `list_policy_versions` method to `CedarPolicyEngine`
- [ ] 6.2 Add `rollback_policy` method to `CedarPolicyEngine`
- [ ] 6.3 Add MCP tool: `list_policy_versions` in `src/coordination_mcp.py`
- [ ] 6.4 Add HTTP endpoint: `POST /policies/{name}/rollback` in coordination_api.py
- [ ] 6.5 Add audit logging for policy mutations (create, update, delete, rollback)
- [ ] 6.6 Write unit tests for version history and rollback

## 7. Session-Scoped Permission Grants

- [ ] 7.1 Create `src/session_grants.py` with `SessionGrantService` (request_grant, revoke_grants, get_active_grants)
- [ ] 7.2 Update Cedar schema to add `session_grants` attribute on Agent entity (Set<String>)
- [ ] 7.3 Update `CedarPolicyEngine._build_entity()` to include active session grants
- [ ] 7.4 Integrate grant expiration into dead agent cleanup (`discovery.py`)
- [ ] 7.5 Add MCP tool: `request_permission` in `src/coordination_mcp.py`
- [ ] 7.6 Add audit logging for grant lifecycle (request, approve, expire)
- [ ] 7.7 Write unit tests for session grant lifecycle and Cedar evaluation

## 8. Integration and Documentation

- [ ] 8.1 Update `agent-coordinator/README.md` with new features, environment variables, and architecture
- [ ] 8.2 Update default Cedar policies (`cedar/default_policies.cedar`) with delegation, risk, and approval conditions
- [ ] 8.3 Run full test suite and fix any regressions
- [ ] 8.4 Verify backward compatibility: all existing tests pass with features disabled
