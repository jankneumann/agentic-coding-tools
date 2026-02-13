# Change: Complete Missing Coordination Features (Phases 2-4)

## Why

The agent-coordinator documentation (`docs/agent-coordinator.md`) and spec (`openspec/specs/agent-coordinator/spec.md`) both state that Phases 2-4 are only "Specified" (not implemented). However, a code audit reveals that significant Phase 2-3 work already exists in the `verification_gateway/` directory — including an HTTP API, memory endpoints, verification gateway, and SQL schemas — but this code is not integrated into the main migration pipeline and several key safety/governance features remain unbuilt. The documentation is outdated, and the gap between what exists and what's specified creates confusion and risk.

## Gap Analysis

### Already Implemented (undocumented)

| Feature | Phase | Location |
|---------|-------|----------|
| HTTP API (15+ endpoints, API key auth) | 2 | `verification_gateway/coordination_api.py` |
| Memory API (episodic, working, procedural) | 2 | `verification_gateway/coordination_api.py` |
| Memory DB schema (3 tables, 3 functions) | 2 | `verification_gateway/supabase_memory_schema.sql` |
| Verification gateway (4 tiers, 5 executors) | 3 | `verification_gateway/gateway.py` |
| Verification DB schema (4 tables, 3 views, 2 functions) | 3 | `verification_gateway/supabase_schema.sql` |
| GitHub/Agent webhooks | 3 | `verification_gateway/gateway.py` |
| Inline static analysis (ruff, mypy, tsc) | 3 | `verification_gateway/gateway.py` |
| Evaluation framework | 4 | `agent-coordinator/evaluation/` |
| Session continuity (handoff documents) | 1+ | `src/handoffs.py`, migration `002_handoff_documents.sql` |
| Agent discovery & heartbeat | 1+ | `src/discovery.py`, migration `003_agent_discovery.sql` |
| Declarative team composition | 1+ | `src/teams.py`, `teams.yaml` |

### Genuinely Missing

| Feature | Phase | Spec Requirements |
|---------|-------|-------------------|
| Guardrails engine | 3 | Req: Destructive Operation Guardrails |
| Agent profiles with trust levels | 3 | Req: Agent Profiles |
| Network access policies | 3 | Req: Network Access Policies |
| Audit trail | 3 | Req: Audit Trail |
| GitHub-mediated coordination | 2 | Req: GitHub-Mediated Coordination |
| Strands SDK orchestration | 4 | Req: Agent Orchestration |
| AgentCore integration | 4 | Req: Agent Orchestration |
| Memory MCP tools (remember/recall) | 2 | Req: MCP Server Interface (Phase 2 note) |
| Schema integration into main migrations | 2-3 | Req: Database Persistence |

### Integration Gaps

The `verification_gateway/` directory contains standalone SQL schemas (`supabase_schema.sql`, `supabase_memory_schema.sql`) that are **not** part of the main migration pipeline (`supabase/migrations/`). This means:
- Schemas are defined but not deployable via standard migration workflow
- No migration ordering or dependency management with Phase 1 tables
- Verification and memory features cannot be enabled without manual SQL execution

## What Changes

### Phase 2 Completion
- Integrate memory database schema into main migrations (`004_memory_tables.sql`)
- Add `remember` and `recall` MCP tools to `coordination_mcp.py`
- Implement GitHub-mediated coordination fallback (issue labels, branch naming)
- Integrate verification_gateway coordination_api.py with main project structure

### Phase 3 Completion
- Implement guardrails engine (`src/guardrails.py`) with destructive operation pattern registry
- Implement agent profiles (`src/profiles.py`) with trust levels 0-4
- Implement network access policies with domain allowlists/denylists
- Implement audit trail (`src/audit.py`) with append-only logging
- Integrate verification schema into main migrations (`005_verification_tables.sql`)
- Complete verification executor implementations (GitHub Actions, NTM, E2B — currently skeleton)

### Phase 4 (Deferred — Design Only)
- Strands SDK orchestration and AgentCore integration are deferred to a future proposal
- Current evaluation framework is sufficient for Phase 4's measurement goals
- Design document captures integration architecture for when Strands/AgentCore are adopted

### Documentation Updates
- Update `docs/agent-coordinator.md` implementation status table
- Update `openspec/specs/agent-coordinator/spec.md` implementation status and database tables sections

## Impact

- Affected specs: `agent-coordinator`
- Affected code:
  - `agent-coordinator/src/` (new modules: guardrails.py, profiles.py, audit.py, github_coordination.py)
  - `agent-coordinator/src/coordination_mcp.py` (add memory tools)
  - `agent-coordinator/supabase/migrations/` (new migrations 004, 005)
  - `agent-coordinator/verification_gateway/` (integrate into main structure)
  - `docs/agent-coordinator.md` (update status)
  - `openspec/specs/agent-coordinator/spec.md` (update status metadata)
- **BREAKING**: None. All changes are additive.
