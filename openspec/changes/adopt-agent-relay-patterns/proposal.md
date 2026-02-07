# Change: Adopt Agent Relay Patterns for Agentic Coordination

## Why

Our Agent Coordinator (Phase 1 MVP) provides file locking and work queue primitives, but lacks session continuity, agent discovery, and lifecycle management. [Agent Relay](https://docs.agent-relay.com/introduction) is an external multi-agent communication middleware that solves similar coordination problems with a different architecture. Rather than adding it as a dependency (incompatible architecture), we should adopt five specific patterns that fill real gaps in our system.

## What Changes

- Add **session continuity documents** (handoff/ledger pattern) to the Agent Coordinator MCP server
- Add **agent discovery** by extending `agent_sessions` with capabilities, status, and heartbeat
- Add **declarative team composition** via a `teams.yaml` schema
- Add **lifecycle hooks** for auto-registration and lock cleanup on session start/end
- Add **heartbeat and dead agent detection** to the `agent_sessions` table

## Impact

- Affected specs: `agent-coordinator`
- Modified code: `agent-coordinator/src/coordination_mcp.py`
- New code: `agent-coordinator/src/handoffs.py`, `agent-coordinator/src/discovery.py`, `agent-coordinator/src/teams.py`
- New migrations: `agent-coordinator/supabase/migrations/002_handoff_documents.sql`, `agent-coordinator/supabase/migrations/003_agent_discovery.sql`
- New scripts: `agent-coordinator/scripts/register_agent.py`, `agent-coordinator/scripts/deregister_agent.py`
- New config: `agent-coordinator/teams.yaml`, `.claude/hooks.json`

## Analysis: Agent Relay vs Our System

### Architecture Comparison

| Dimension | Agent Relay | Our System | Winner |
|-----------|------------|------------|--------|
| **Communication** | stdout text injection (`->relay:Bob ...`) | MCP native tool calls | Ours (native, type-safe) |
| **State persistence** | In-memory daemon (lost on restart) | Supabase/PostgreSQL (durable) | Ours (durable, queryable) |
| **File locking** | Not provided | Atomic PostgreSQL locks with TTL | Ours (already built) |
| **Work queue** | Not provided | Priority queue with `SKIP LOCKED` | Ours (already built) |
| **Session continuity** | Ledger + handoff docs | Not implemented | Agent Relay (pattern to adopt) |
| **Agent discovery** | `listAgents()` with filtering | Basic `agent_sessions` table | Agent Relay (pattern to adopt) |
| **Team composition** | `teams.json` auto-spawn | Not provided | Agent Relay (pattern to adopt) |
| **Lifecycle hooks** | 7 event types (start, end, idle, error...) | None | Agent Relay (pattern to adopt) |
| **Dead agent detection** | PING/PONG heartbeat | 2-hour TTL expiration only | Agent Relay (pattern to adopt) |
| **Provider support** | Claude, Codex, Gemini, Cursor | Claude-focused, Codex in specs | Agent Relay (broader) |
| **Consensus/voting** | 5 consensus types | Not provided | Agent Relay (premature for us) |
| **Shadow agents** | Reviewer, auditor, active roles | Phase 3 guardrails (deterministic) | Ours (more reliable) |
| **Pub/sub** | Channel-based messaging | Supabase Realtime (planned) | Equivalent |

### Why NOT Incorporate Agent Relay Directly

1. **Architecture mismatch**: Agent Relay injects messages by monitoring agent stdout for text patterns and injecting text into terminal stdin. Our MCP approach uses native tool calls — type-safe, structured, and invisible to the user's terminal. Running both simultaneously would fragment coordination across two incompatible paradigms.

2. **State durability gap**: Agent Relay's daemon holds state in memory. When it crashes or restarts, coordination state is lost. Our Supabase-backed system survives restarts, supports real-time subscriptions, and enables SQL-based querying and auditing.

3. **We already have the hard parts**: The most difficult coordination primitives — atomic file locking, deadlock-free work queues, dependency tracking — are already built and tested (~1,500 lines + 60 tests). Agent Relay doesn't provide these. Our gaps are in softer patterns (discovery, continuity, lifecycle).

4. **Dependency risk**: Agent Relay is a young project with agent limits tied to pricing tiers (3 free, 10 pro). Our MCP-based approach has no such limits and doesn't require running an external daemon process.

### Patterns Worth Adopting

#### Pattern 1: Session Continuity Documents (HIGH value, LOW cost)

**Problem**: When a Claude Code session hits context limits mid-implementation, the next session starts cold — losing context about what was done, what's in progress, and what decisions were made.

**Agent Relay's approach**: Two-tier persistence: "ledger" (ephemeral session state) and "handoff" (permanent records). Auto-triggers on task completion, context limits, or session end.

**Our adaptation**: Add `write_handoff` and `read_handoff` MCP tools backed by a `handoff_documents` table. Store: summary (required), plus optional completed work, in-progress items, decisions, next steps, and relevant files. Auto-load most recent handoff on session start via lifecycle hooks.

#### Pattern 2: Agent Discovery (MEDIUM value, MEDIUM cost)

**Problem**: Agents working on the same codebase can't answer "who else is working here?" or "which agent has expertise in X?"

**Agent Relay's approach**: `listAgents()` with filtering by activity status, project, and capabilities.

**Our adaptation**: Extend `agent_sessions` with `capabilities` (array), `status` (enum: active/idle/disconnected), and `last_heartbeat` (timestamp). Add `discover_agents` MCP tool that returns active sessions with their capabilities and current work context.

#### Pattern 3: Declarative Team Composition (MEDIUM value, LOW cost)

**Problem**: Setting up multi-agent teams requires manual spawning and configuration. No single source of truth for "what agents should be working on this project."

**Agent Relay's approach**: `teams.json` with agent names, CLI tools, and initial tasks. Auto-spawn with `agent-relay up --spawn`.

**Our adaptation**: Create a `teams.yaml` schema that defines agent roles, required capabilities, and coordination rules. Not auto-spawn (that's Phase 4), but a declarative contract that future orchestration can consume.

#### Pattern 4: Lifecycle Hooks for Auto-Registration (MEDIUM value, MEDIUM cost)

**Problem**: Agents must manually register and deregister. If a session crashes, locks remain held until TTL expires (up to 2 hours).

**Agent Relay's approach**: 7 lifecycle hooks (onSessionStart, onSessionEnd, onIdle, onError, etc.) that can inject/suppress/stop actions.

**Our adaptation**: Use Claude Code's existing `SessionStart` hook to auto-register the agent session and load handoffs. Use `SessionEnd` (or a trap-based hook) to release all held locks and write a final handoff document.

#### Pattern 5: Heartbeat / Dead Agent Detection (LOW value now, HIGH value later)

**Problem**: Dead agents hold locks for up to 2 hours (TTL). No way to distinguish "agent is thinking for 10 minutes" from "agent session crashed."

**Agent Relay's approach**: PING/PONG every 5 seconds with exponential backoff reconnection.

**Our adaptation**: Add `last_heartbeat` column to `agent_sessions`. Add a `heartbeat` MCP tool that agents call periodically. Add a PostgreSQL function `cleanup_dead_agents()` that releases locks held by agents whose heartbeat is stale (>15 minutes, accommodating long-running operations like test suites). Run on-demand via MCP tool or automatically when `discover_agents` is called.
