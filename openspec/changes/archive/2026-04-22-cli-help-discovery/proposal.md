# Proposal: Progressive Discovery Help System

**Change ID**: `cli-help-discovery`
**Status**: Draft
**Created**: 2026-04-09

## Why

The agent coordinator exposes **53 MCP tools** across ~15 capability groups. When an MCP session starts, all tool schemas are eagerly loaded into the agent's context window (~6-8K tokens of JSON Schema). This creates three problems:

1. **Context bloat**: Tool schemas consume valuable context space that could be used for task work. After context compaction, agents retain function signatures but lose nuance about _how_ to use tools effectively.

2. **No workflow guidance**: MCP schemas describe parameters and return types, but not multi-tool choreography (e.g., "check locks before acquiring, always release even on error"). This workflow knowledge is exactly what enables effective tool use.

3. **No progressive discovery**: Agents must absorb all 53 tool schemas upfront, even if they only need 3-4 tools for their current task. There's no way to ask "what can you do?" and drill into specific areas on demand.

The CLI pattern (e.g., `git --help` vs `git commit --help`) solves this elegantly: a compact overview for orientation, with detailed per-topic help pulled on demand.

## What Changes

Add a `help` capability to the coordinator that provides **two-tier progressive discovery**:

- **Tier 1 (Overview)**: `help()` returns a compact listing (~200 tokens) of all capability groups with one-line summaries and tool counts
- **Tier 2 (Detail)**: `help(topic="locks")` returns a rich guide (~400 tokens) with description, ordered workflow steps, best practices, code examples, and related topics

This capability is exposed across all three coordinator transports:
- **MCP**: `help(topic?)` tool for local agents
- **HTTP**: `GET /help` and `GET /help/{topic}` (no auth required) for cloud agents
- **CLI**: `coordination-cli help [topic]` for direct command-line usage

### Design Decisions

- **Static registry, extensible interface**: Help topics are defined in code at build time (simple, fast, no DB dependency). The service interface (`get_help_overview`, `get_help_topic`, `list_topic_names`) is designed so runtime extension can be added later without breaking changes.
- **Transport-agnostic content**: Same help content regardless of whether the caller is an MCP, HTTP, or CLI agent. Help focuses on _what capabilities do_, not transport-specific details.
- **Show all topics always**: Help returns all 15 topics regardless of which capabilities are currently online. Agents decide relevance themselves and can learn about capabilities they might want enabled.
- **No auth on help endpoints**: Help is a discovery mechanism -- requiring auth would defeat the purpose for agents that haven't authenticated yet.

## Approaches Considered

### Approach 1: Pure Service Layer (Recommended)

**Description**: Add a new `help_service.py` module that defines help content as a static registry of `HelpTopic` dataclasses. Each transport (MCP, HTTP, CLI) delegates to this shared service. No database dependency, no configuration -- pure Python data.

**Pros**:
- Zero infrastructure dependencies (no DB, no config)
- Follows existing transport-abstraction pattern perfectly
- Easy to test (pure functions, no mocking)
- Fast -- no I/O, just dictionary lookups
- Content is version-controlled alongside code

**Cons**:
- Adding new topics requires code changes + deployment
- Content is duplicated from tool docstrings (not auto-generated)
- No runtime customization per-agent or per-deployment

**Effort**: S

### Approach 2: Auto-Generated from Tool Introspection

**Description**: Generate help content automatically by introspecting MCP tool docstrings, parameter schemas, and FastAPI endpoint metadata. Help topics are synthesized from existing code annotations rather than manually authored.

**Pros**:
- Always in sync with actual tool implementations
- No manual content maintenance
- Could generate help for new tools automatically

**Cons**:
- Quality ceiling is limited by docstring quality (which varies)
- Can't include workflow choreography, best practices, or anti-patterns that aren't in docstrings
- Complex implementation -- needs to parse FastMCP decorators + FastAPI routes
- The most valuable help content (workflow guidance, examples) can't be auto-generated

**Effort**: M

### Approach 3: Database-Backed Dynamic Registry

**Description**: Store help topics in a database table, managed via admin endpoints. Topics can be updated at runtime without code changes or deployment.

**Pros**:
- Runtime updatable without deployment
- Supports per-deployment customization
- Could support user-contributed content

**Cons**:
- Adds database dependency for a read-only feature
- Requires migration, seeding, and admin endpoints
- Overkill for 15 topics that change infrequently
- Introduces failure mode (help unavailable if DB is down)

**Effort**: L

### Selected Approach

**Approach 1: Pure Service Layer** -- selected because the most valuable help content (workflow choreography, best practices, anti-patterns) must be manually authored regardless of approach. The pure-service pattern matches the project's existing transport-abstraction architecture, has zero infrastructure overhead, and the interface is designed so Approach 2 or 3 can be layered on later without breaking changes.

## Scope

### In Scope
- `help_service.py` with 15 help topics covering all coordinator capability groups
- `help()` MCP tool with optional `topic` parameter
- `GET /help` and `GET /help/{topic}` HTTP endpoints (no auth)
- `coordination-cli help [topic]` CLI subcommand with human-readable and JSON output
- Unit tests for service, CLI, and HTTP API layers
- Spec delta for the agent-coordinator spec

### Out of Scope
- Runtime topic registration (future extensibility)
- Transport-specific content variations
- Capability-aware filtering
- Auto-generation from tool introspection
- Help for MCP resources (only tools covered)
- Internationalization / localization

## Success Criteria

1. An agent can call `help()` and get a compact overview of all capability groups in ~200 tokens
2. An agent can call `help(topic="locks")` and get actionable workflow guidance in ~400 tokens
3. Help is available on all three transports (MCP, HTTP, CLI) with consistent content
4. All 24 tests pass covering service, CLI, and HTTP API layers
5. No auth required on help endpoints
6. The interface supports future runtime extension without breaking changes
