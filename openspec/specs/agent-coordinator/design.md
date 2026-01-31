# Agent Coordinator - Design

## Context

This system coordinates multiple AI coding agents working on shared codebases. The architecture must handle:
- Local agents (Claude Code CLI, Codex CLI, Aider) connecting via MCP
- Cloud-managed agents (Claude Code Web, Codex Cloud) connecting via HTTP with network restrictions
- Orchestrated agent swarms (Strands Agents) running on AgentCore Runtime
- Real-time coordination without conflicts
- Persistent memory across sessions
- Automated verification routing
- Guardrails preventing destructive autonomous operations

## Goals / Non-Goals

### Goals
- Prevent file conflicts between concurrent agents
- Enable agents to learn from past sessions
- Provide task orchestration across agent types
- Route changes to appropriate verification tier
- Enforce guardrails on destructive operations
- Support cloud agents with restricted network access
- Integrate with AWS Strands Agents and Bedrock AgentCore

### Non-Goals
- Replace version control (Git remains source of truth)
- Provide IDE integration (agents handle their own interfaces)
- Implement the verification execution (delegates to GitHub Actions, AgentCore Runtime)
- Replace Anthropic/OpenAI's cloud agent infrastructure

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AGENT LAYER                                     │
├─────────────────┬─────────────────┬─────────────────┬───────────────────────┤
│  LOCAL AGENTS   │  CLOUD-MANAGED  │  ORCHESTRATED   │   PRECONFIGURED       │
│                 │     AGENTS      │     AGENTS      │   AGENT PROFILES      │
│ • Claude Code   │ • Claude Code   │ • Strands       │                       │
│   CLI           │   Web           │   Swarms        │ • claude-code-cli     │
│ • Codex CLI     │ • Codex Cloud   │ • Strands       │ • claude-web-reviewer │
│ • Aider         │                 │   Graphs        │ • claude-web-impl     │
│                 │                 │                 │ • codex-cloud-worker  │
│ MCP (stdio)     │ HTTP (restrict) │ Strands SDK     │ • strands-orchestrator│
└────────┬────────┴────────┬────────┴────────┬────────┴───────────────────────┘
         │                 │                 │
         │                 │                 │
         ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          COORDINATION LAYER                                  │
├─────────────────┬─────────────────┬─────────────────┬───────────────────────┤
│  MCP SERVER     │  HTTP API       │  AGENTCORE      │   GUARDRAIL           │
│  (FastMCP)      │  (FastAPI)      │  GATEWAY        │   ENGINE              │
│                 │                 │                 │                       │
│ For local       │ For cloud       │ For Strands     │ • Pre-exec analysis   │
│ agents          │ agents          │ agents + MCP    │ • Pattern matching    │
│                 │                 │ connectivity    │ • Policy enforcement  │
└────────┬────────┴────────┬────────┴────────┬────────┴───────────┬───────────┘
         │                 │                 │                   │
         └─────────────────┴────────┬────────┴───────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            STATE LAYER                                       │
├───────────────────────────────┬─────────────────────────────────────────────┤
│        SUPABASE               │           AGENTCORE MEMORY                   │
│   (Coordination State)        │        (Session + Long-term)                 │
│                               │                                              │
│ • file_locks                  │ • Session context                            │
│ • work_queue                  │ • Cross-session learning                     │
│ • agent_profiles              │ • Semantic retrieval                         │
│ • network_policies            │                                              │
│ • guardrail_violations        │  ┌─────────────────────────────┐             │
│ • audit_log                   │  │ Alternative: Custom memory  │             │
│                               │  │ tables if not using         │             │
│                               │  │ AgentCore                   │             │
│                               │  └─────────────────────────────┘             │
└───────────────────────────────┴─────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXECUTION LAYER                                      │
├─────────────────┬─────────────────┬─────────────────┬───────────────────────┤
│  GITHUB         │  AGENTCORE      │  LOCAL NTM      │   MANUAL              │
│  ACTIONS        │  RUNTIME        │                 │   REVIEW              │
│                 │                 │                 │                       │
│ Tier 1: Unit    │ Tier 2-3:       │ Tier 3:         │ Tier 4:               │
│ tests           │ Integration     │ System tests    │ Security-             │
│                 │ (8hr sessions,  │                 │ sensitive             │
│                 │ microVM isol.)  │                 │                       │
└─────────────────┴─────────────────┴─────────────────┴───────────────────────┘
```

### Cloud Agent Network Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CLAUDE CODE WEB / CODEX CLOUD                             │
│                      (Vendor-Managed Infrastructure)                         │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    ISOLATED VM / CONTAINER                           │    │
│  │                                                                      │    │
│  │   Agent Code ──► Coordination Client ──► HTTPS Request              │    │
│  │                                              │                       │    │
│  └──────────────────────────────────────────────┼───────────────────────┘    │
│                                                 │                            │
│                                    ┌────────────┴────────────┐               │
│                                    │   VENDOR NETWORK PROXY   │               │
│                                    │   (Anthropic/OpenAI)     │               │
│                                    │                          │               │
│                                    │   Enforces allowlist:    │               │
│                                    │   • github.com ✓         │               │
│                                    │   • pypi.org ✓           │               │
│                                    │   • coord.yours.com ✓    │  ◄── Must add│
│                                    │   • random.com ✗         │               │
│                                    └────────────┬─────────────┘               │
└─────────────────────────────────────────────────┼───────────────────────────┘
                                                  │
                                                  ▼
                                    ┌─────────────────────────┐
                                    │  YOUR COORDINATION API   │
                                    │  coord.yourdomain.com    │
                                    └─────────────────────────┘
```

## Decisions

### Decision: Supabase for Coordination State
**Rationale**: Real-time subscriptions, RLS for access control, Postgres functions for atomic operations. Coordination-specific state (locks, work queue, policies, audit logs) stays in Supabase.

**Alternatives considered**:
- Redis: Fast but lacks structured queries and real-time subscriptions
- Custom PostgreSQL: More ops overhead, no built-in real-time

### Decision: AgentCore Memory for Agent Memory (Optional)
**Rationale**: AgentCore Memory provides session + long-term memory with semantic retrieval, reducing custom development. Falls back to custom Supabase tables if AgentCore not used.

**Trade-off**: Adds AWS dependency but eliminates need to build memory retrieval system.

### Decision: MCP for Local Agents
**Rationale**: Native tool integration, automatic schema discovery, no SDK needed. Local agents like Claude Code have built-in MCP support.

**Alternatives considered**:
- HTTP API only: Would work but MCP provides better integration experience
- Custom protocol: Unnecessary complexity

### Decision: HTTP API for Cloud Agents
**Rationale**: Cloud environments (Claude Code Web, Codex Cloud) run in vendor-managed VMs with network restrictions. HTTP is universally accessible and can be allowlisted.

**Key constraint**: Coordination API domain must be added to cloud agent environment's network allowlist.

### Decision: AgentCore Gateway for Strands Agents
**Rationale**: AgentCore Gateway provides MCP connectivity, tool discovery, and API-to-tool conversion for Strands-based orchestrators. Enables Strands agents to use same coordination tools.

### Decision: Strands SDK for Multi-Agent Orchestration
**Rationale**: Strands provides battle-tested patterns (agents-as-tools, swarms, graphs) used in production by AWS teams. Model-driven approach reduces custom orchestration code.

**Alternatives considered**:
- LangGraph: More developer-driven, requires more explicit workflow definition
- Custom orchestration: Significant development effort

### Decision: Deterministic Guardrails via AgentCore Policy
**Rationale**: AgentCore Policy enforces rules outside the LLM reasoning loop—deterministic, not probabilistic. Critical for preventing destructive operations.

**Key insight**: LLM-based guardrails can be convinced to bypass restrictions. Deterministic pattern matching cannot.

### Decision: GitHub-Mediated Fallback Coordination
**Rationale**: Some cloud agents may not reach external APIs. GitHub is universally accessible from all cloud agent platforms. Labels and branches can signal locks and assignments.

### Decision: Hybrid Read/Write Pattern
**Rationale**: Reads direct to Supabase (fast), writes via API (coordinated). Allows optimistic reads while maintaining coordination on writes.

### Decision: Preconfigured Agent Profiles
**Rationale**: Different agent types have different trust levels and capabilities. Preconfigured profiles reduce configuration errors and enforce security boundaries.

## Component Details

### File: `coordination_mcp.py` *(Implemented)*
- **Technology**: FastMCP + Python
- **Purpose**: MCP server for local agents
- **Tools (Phase 1)**: `acquire_lock`, `release_lock`, `check_locks`, `get_work`, `complete_work`, `submit_work`
- **Tools (Phase 2)**: `remember`, `recall` (memory tools, not yet implemented)
- **Resources**: `locks://current`, `work://pending`

### File: `coordination_api.py`
- **Technology**: FastAPI + Python
- **Purpose**: HTTP API for cloud agents (Claude Code Web, Codex Cloud)
- **SDK**: `AgentCoordinationClient` class for easy integration
- **Auth**: API key via `X-API-Key` header, session-derived for cloud agents
- **Endpoints**: Mirror MCP tools as REST endpoints

### File: `guardrails.py`
- **Technology**: Python + regex/AST analysis
- **Purpose**: Pre-execution analysis for destructive operations
- **Integration**: AgentCore Policy for Strands agents, custom for others
- **Patterns**: Git force operations, mass deletions, credential modifications

### File: `gateway.py`
- **Technology**: FastAPI + Python
- **Purpose**: Verification routing engine
- **Webhooks**: `/webhook/github`, `/webhook/agent`, `/webhook/agentcore`

### File: `profiles.py`
- **Technology**: Python + Pydantic
- **Purpose**: Agent profile management and validation
- **Features**: Profile CRUD, trust level enforcement, capability checking

### File: `audit.py`
- **Technology**: Python + Supabase
- **Purpose**: Append-only audit logging
- **Features**: Operation logging, violation tracking, query interface

### AWS Integration Components

### AgentCore Gateway Integration
- **Purpose**: Connect Strands agents to coordination tools
- **Features**: MCP server connectivity, tool discovery, API-to-tool conversion
- **Configuration**: Via AgentCore Gateway console or SDK

### AgentCore Memory Integration
- **Purpose**: Session and long-term memory for Strands agents
- **Features**: Context management, semantic retrieval, cross-session learning
- **Alternative**: Custom `memory_*` tables in Supabase if not using AgentCore

### AgentCore Policy Integration
- **Purpose**: Deterministic guardrail enforcement for Strands agents
- **Features**: Natural language policies, pattern matching, outside-LLM enforcement
- **Policies**: Defined in coordination system, synced to AgentCore

### AgentCore Runtime Integration
- **Purpose**: Execution environment for Strands agents
- **Features**: 8-hour sessions, microVM isolation, multi-model support
- **Use case**: Tier 2-3 verification, complex multi-agent workflows

## Verification Tiers

| Tier | Name | Executor | Use Case |
|------|------|----------|----------|
| 0 | STATIC | Inline | Linting, type checking |
| 1 | UNIT | GitHub Actions | Isolated unit tests |
| 2 | INTEGRATION | Local NTM / E2B | Tests requiring services |
| 3 | SYSTEM | Local NTM | Full environment tests |
| 4 | MANUAL | Human | Security-sensitive changes |

## Key Patterns

### Atomic Lock Acquisition
```sql
-- Clean expired locks, then INSERT ON CONFLICT to prevent race conditions.
-- If INSERT succeeds: lock acquired.
-- If INSERT conflicts: check ownership for refresh vs conflict.
DELETE FROM file_locks WHERE expires_at < NOW();

INSERT INTO file_locks (file_path, locked_by, agent_type, session_id, expires_at, reason)
VALUES (p_file_path, p_agent_id, p_agent_type, p_session_id, v_expires_at, p_reason)
ON CONFLICT (file_path) DO NOTHING;

IF FOUND THEN
    -- Acquired
ELSE
    -- Lock exists: check if same agent (refresh) or different (conflict)
    SELECT * INTO v_existing FROM file_locks WHERE file_path = p_file_path FOR UPDATE;
END IF;
```

### Atomic Task Claiming
```sql
-- Uses FOR UPDATE SKIP LOCKED to prevent double-claiming
SELECT * FROM work_queue
WHERE status = 'pending'
ORDER BY priority
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

### Memory Deduplication
```sql
-- Check for similar recent memory before inserting
SELECT id FROM memory_episodic
WHERE agent_id = p_agent_id
  AND event_type = p_event_type
  AND summary = p_summary
  AND created_at > NOW() - INTERVAL '1 hour';
```

## File Structure

### Implemented (Phase 1)

```
agent-coordinator/
├── README.md
├── pyproject.toml              # Python packaging + dev deps
├── requirements.txt
├── docker-compose.yml          # Local Supabase (PostgreSQL + PostgREST)
├── .env.example
│
├── src/
│   ├── __init__.py
│   ├── config.py               # Environment configuration (incl. rest_prefix)
│   ├── db.py                   # Async Supabase/PostgREST client
│   ├── locks.py                # File locking service
│   ├── work_queue.py           # Task queue service
│   └── coordination_mcp.py     # MCP server (6 tools, 2 resources)
│
├── supabase/
│   ├── migrations/
│   │   ├── 000_bootstrap.sql   # Auth schema, roles, publication (standalone PostgREST)
│   │   └── 001_core_schema.sql # Tables + PL/pgSQL functions
│   └── seed.sql
│
└── tests/
    ├── conftest.py             # Unit test fixtures (respx mocks)
    ├── test_locks.py           # 12 unit tests
    ├── test_work_queue.py      # 19 unit tests
    └── integration/
        ├── conftest.py         # JWT generation, cleanup, skip logic
        ├── test_locks_integration.py      # 11 integration tests
        └── test_work_queue_integration.py # 18 integration tests
```

### Planned (Phase 2+)

```
agent-coordinator/
├── src/
│   ├── coordination_api.py     # HTTP API for cloud agents (FastAPI)
│   ├── gateway.py              # Verification routing
│   ├── guardrails.py           # Destructive operation detection
│   ├── profiles.py             # Agent profile management
│   ├── audit.py                # Audit logging
│   └── github_sync.py          # GitHub-mediated coordination
│
├── agents/                     # Preconfigured agent definitions
│   ├── profiles.yaml
│   ├── network_policies.yaml
│   ├── guardrail_patterns.yaml
│   └── strands/                # Strands agent configurations
│
├── supabase/migrations/
│   ├── 002_memory_schema.sql
│   ├── 003_profiles_schema.sql
│   ├── 004_guardrails_schema.sql
│   └── 005_audit_schema.sql
│
├── clients/                    # Client SDKs for cloud agents
│   ├── python/
│   └── typescript/
│
└── docs/
```

## Configuration

### MCP Server Configuration (Local Agents)
```json
// ~/.claude/mcp.json
{
  "servers": {
    "coordination": {
      "command": "python",
      "args": ["/path/to/coordination_mcp.py"],
      "env": {
        "SUPABASE_URL": "https://xxx.supabase.co",
        "SUPABASE_SERVICE_KEY": "...",
        "AGENT_ID": "claude-code-1",
        "AGENT_TYPE": "claude_code_cli"
      }
    }
  }
}
```

### Claude Code Web Environment Configuration
```json
// Environment settings in Claude Code Web UI
{
  "name": "coordinated-dev",
  "network_mode": "limited",
  "additional_domains": [
    "coord.yourdomain.com"
  ],
  "env_vars": {
    "COORDINATION_API_URL": "https://coord.yourdomain.com",
    "COORDINATION_API_KEY": "${secrets.COORD_API_KEY}",
    "AGENT_TYPE": "claude_code_web"
  }
}
```

```json
// .claude/settings.json (in repository)
{
  "hooks": {
    "SessionStart": [{
      "matcher": "startup",
      "hooks": [{
        "type": "command",
        "command": "pip install agent-coordinator-client"
      }]
    }]
  }
}
```

### Codex Cloud Environment Configuration
```json
// codex-environment.json
{
  "setup_script": "scripts/setup-coordination.sh",
  "internet_access": {
    "enabled": true,
    "allowed_domains": [
      "coord.yourdomain.com",
      "pypi.org",
      "registry.npmjs.org"
    ]
  },
  "environment_variables": {
    "COORDINATION_API_URL": "https://coord.yourdomain.com",
    "AGENT_TYPE": "codex_cloud"
  }
}
```

### Strands Agent + AgentCore Configuration
```python
# agents/strands/orchestrator.py
from strands import Agent
from strands_agentcore import AgentCoreClient

agentcore = AgentCoreClient(
    memory_enabled=True,
    policy_rules=[
        "Never execute git push --force",
        "Acquire locks before modifying files",
        "Log all operations to audit trail"
    ]
)

orchestrator = Agent(
    name="coordinator",
    model="anthropic.claude-sonnet-4-20250514",
    tools=[
        # Coordination tools via AgentCore Gateway
        agentcore.get_tool("acquire_lock"),
        agentcore.get_tool("release_lock"),
        agentcore.get_tool("get_work"),
        agentcore.get_tool("complete_work"),
        # Sub-agents as tools
        reviewer_agent.as_tool(),
        implementer_agent.as_tool()
    ],
    system_prompt="""You coordinate multi-agent coding workflows.
    Always acquire locks before assigning file modifications.
    Monitor agent progress and handle failures gracefully."""
)
```

### Environment Variables
```bash
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...  # Full access for API
SUPABASE_ANON_KEY=eyJ...     # Read-only for agents

# Agent Identity (set per agent instance)
AGENT_ID=claude-code-1
AGENT_TYPE=claude_code_cli
SESSION_ID=session-abc

# API Security
COORDINATION_API_KEYS=key1,key2,key3
COORDINATION_API_URL=https://coord.yourdomain.com

# AWS AgentCore (optional)
AWS_REGION=us-west-2
AGENTCORE_MEMORY_ENABLED=true
AGENTCORE_POLICY_ENABLED=true

# Verification
GITHUB_TOKEN=ghp_...
```

## Risks / Trade-offs

### Risk: Lock Starvation
- **Mitigation**: TTL on all locks ensures automatic release. Monitor for agents that frequently fail to release locks.

### Risk: Memory Storage Growth
- **Mitigation**: Implement retention policies. Archive old episodic memories. Compress procedural memories.
- **Alternative**: Use AgentCore Memory which handles retention automatically.

### Risk: Verification Bottleneck
- **Mitigation**: Tier 0 (static) is inline and fast. Higher tiers are async. Monitor queue depth.
- **Alternative**: AgentCore Runtime provides auto-scaling for Tier 2-3.

### Risk: Cloud Agent Network Restrictions
- **Mitigation**: Coordination API domain must be explicitly allowlisted in cloud agent environments.
- **Fallback**: GitHub-mediated coordination when API unreachable.
- **Risk**: Vendor may change allowlist policies without notice.

### Risk: Guardrail Bypass
- **Mitigation**: Deterministic pattern matching (not LLM-based) prevents social engineering bypass.
- **Mitigation**: AgentCore Policy enforces rules outside LLM reasoning loop.
- **Risk**: Novel destructive patterns may not match existing rules.

### Risk: AWS Vendor Lock-in
- **Mitigation**: AgentCore components are optional; core coordination works with Supabase alone.
- **Trade-off**: More development effort without AgentCore, but no AWS dependency.

### Trade-off: Consistency vs Availability
- Chose consistency for writes (coordinated via Supabase functions)
- Allows eventual consistency for reads (direct Supabase queries)

### Trade-off: Guardrail Strictness vs Productivity
- Stricter guardrails (default-deny) reduce risk but may block legitimate operations
- Looser guardrails (warn-only) improve productivity but increase risk
- **Approach**: Strict for cloud agents, configurable for local agents

### Trade-off: AgentCore vs Custom Implementation
| Aspect | AgentCore | Custom |
|--------|-----------|--------|
| Development effort | Low | High |
| AWS dependency | Yes | No |
| Memory features | Rich (semantic search) | Basic (tag-based) |
| Policy enforcement | Deterministic | Must build |
| Runtime isolation | 8hr microVMs | Must provision |

## Open Questions

1. ~~**Memory embedding model**: Should we use pgvector with embeddings for semantic search, or stick with tag-based retrieval?~~
   **Resolved**: Use AgentCore Memory for semantic search, or pgvector if not using AgentCore.

2. **Cross-repo coordination**: How to handle agents working on multiple related repositories?
   - Option A: Single coordination instance per org, repo as namespace
   - Option B: Separate coordination per repo, federation layer

3. ~~**Trust scores**: Should we implement per-agent trust scores that affect verification requirements?~~
   **Resolved**: Yes, via agent profiles with trust_level 0-4.

4. ~~**Context compression**: What's the right algorithm for compressing working memory when it exceeds token budget?~~
   **Resolved**: Delegate to AgentCore Memory or use sliding window + summarization.

5. **Multi-vendor agent coordination**: How to coordinate when Claude Code Web and Codex Cloud work on same task?
   - Both have different network restrictions
   - Need common coordination API accessible to both

6. **Guardrail pattern updates**: How to update destructive operation patterns without service restart?
   - Hot reload from database?
   - Webhook notification to running servers?

7. **Audit log retention and compliance**: What retention period for audit logs? GDPR/SOC2 implications?

## References

### Core Infrastructure
- [FastMCP Documentation](https://github.com/jlowin/fastmcp) - MCP server framework
- [Supabase Realtime](https://supabase.com/docs/guides/realtime) - For agent notifications

### AWS Agent Infrastructure
- [Strands Agents SDK](https://strandsagents.com/latest/) - Multi-agent orchestration framework
- [Strands Agents 1.0 Announcement](https://aws.amazon.com/blogs/opensource/introducing-strands-agents-1-0-production-ready-multi-agent-orchestration-made-simple/) - Production-ready multi-agent patterns
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) - Agentic platform for deployment and operation
- [AgentCore Policy Controls](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/) - Deterministic guardrails
- [Multi-Agent Collaboration Patterns](https://aws.amazon.com/blogs/machine-learning/multi-agent-collaboration-patterns-with-strands-agents-and-amazon-nova/) - Agents-as-tools, swarms, graphs

### Cloud Agent Platforms
- [Claude Code on the Web](https://www.anthropic.com/news/claude-code-on-the-web) - Anthropic's cloud coding agent
- [Claude Code Web Documentation](https://code.claude.com/docs/en/claude-code-on-the-web) - Environment configuration
- [Codex Cloud](https://developers.openai.com/codex/cloud/) - OpenAI's cloud coding agent
- [Codex CLI](https://developers.openai.com/codex/cli/) - Local Codex agent

### Verification Environments
- [E2B Sandbox](https://e2b.dev/docs) - Cloud verification environments
- [GitHub Actions](https://docs.github.com/en/actions) - CI/CD verification
