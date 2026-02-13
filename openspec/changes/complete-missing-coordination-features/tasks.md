## 1. Documentation & Status Updates
- [ ] 1.1 Update `docs/agent-coordinator.md` implementation status table to reflect actual state
- [ ] 1.2 Update `openspec/specs/agent-coordinator/spec.md` implementation status and database tables sections

## 2. Schema Integration (Phase 2-3 Database)
- [ ] 2.1 Create migration `004_memory_tables.sql` from `verification_gateway/supabase_memory_schema.sql` (memory_episodic, memory_working, memory_procedural tables + functions)
- [ ] 2.2 Create migration `005_verification_tables.sql` from `verification_gateway/supabase_schema.sql` (changesets, verification_results, verification_policies, approval_queue tables + functions + views)
- [ ] 2.3 Add migration tests to verify schema compatibility with Phase 1 tables

## 3. Memory MCP Tools (Phase 2)
- [ ] 3.1 Add `remember` tool to `coordination_mcp.py` wrapping episodic memory storage
- [ ] 3.2 Add `recall` tool to `coordination_mcp.py` wrapping memory retrieval
- [ ] 3.3 Create `src/memory.py` service layer for memory operations (episodic, working, procedural)
- [ ] 3.4 Write unit tests for memory service

## 4. Guardrails Engine (Phase 3)
- [ ] 4.1 Create `src/guardrails.py` with destructive operation pattern registry
- [ ] 4.2 Implement pattern matching for git force operations, mass deletion, credential modification
- [ ] 4.3 Add pre-execution analysis function that scans task output for destructive patterns
- [ ] 4.4 Create migration `006_guardrails_tables.sql` (operation_guardrails, guardrail_violations)
- [ ] 4.5 Write unit tests for guardrails pattern matching

## 5. Agent Profiles (Phase 3)
- [ ] 5.1 Create `src/profiles.py` with Pydantic-based profile definitions
- [ ] 5.2 Implement trust level enforcement (0-4)
- [ ] 5.3 Implement resource limit tracking (max files, execution time, API calls)
- [ ] 5.4 Create migration `007_agent_profiles.sql` (agent_profiles, agent_profile_assignments)
- [ ] 5.5 Integrate profile checks into lock acquisition and work queue claiming
- [ ] 5.6 Write unit tests for profile enforcement

## 6. Audit Trail (Phase 3)
- [ ] 6.1 Create `src/audit.py` with append-only logging service
- [ ] 6.2 Create migration `008_audit_log.sql` (audit_log table with immutable constraint)
- [ ] 6.3 Add audit logging hooks to existing coordination operations (locks, work queue, handoffs)
- [ ] 6.4 Write unit tests for audit logging

## 7. Network Access Policies (Phase 3)
- [ ] 7.1 Create `src/network_policies.py` with domain allowlist/denylist enforcement
- [ ] 7.2 Create migration `009_network_policies.sql` (network_policies, network_access_log)
- [ ] 7.3 Integrate with agent profiles (per-profile network policies)
- [ ] 7.4 Write unit tests for policy evaluation

## 8. GitHub-Mediated Coordination (Phase 2)
- [ ] 8.1 Create `src/github_coordination.py` with issue label lock signaling
- [ ] 8.2 Implement branch naming convention parser (`agent/{agent_id}/{task_id}`)
- [ ] 8.3 Add webhook handler that syncs GitHub state to coordination database
- [ ] 8.4 Write unit tests for GitHub coordination

## 9. Verification Executor Completion (Phase 3)
- [ ] 9.1 Complete GitHub Actions trigger implementation in `gateway.py`
- [ ] 9.2 Complete NTM dispatch implementation in `gateway.py`
- [ ] 9.3 Complete E2B sandbox execution implementation in `gateway.py`
- [ ] 9.4 Write integration tests for each executor

## 10. Integration & Validation
- [ ] 10.1 Run full test suite (pytest) and fix any failures
- [ ] 10.2 Run type checking (mypy) and fix any issues
- [ ] 10.3 Run linting (ruff) and fix any issues
- [ ] 10.4 Verify all existing tests still pass after new migrations
