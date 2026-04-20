# Proposal: Migrate FastMCP 2.x to 3.x

## Why

FastMCP 3.x (PrefectHQ/fastmcp) is the actively maintained version with improved transport layer, better client API, and long-term support. The current `>=0.3.0` floor resolves to 2.14.5, which works but:

1. **SSE transport is deprecated** — marked "legacy" in 3.x, will eventually be removed
2. **New features unavailable** — structured tool results (`result.data`), HTTP Streamable transport, improved client connection handling
3. **Dependabot can't bump** — the floor constraint blocks auto-updates since 3.x has breaking changes
4. **Security/bug fixes** — 3.x receives active patches; 2.x is effectively in maintenance mode

The coordination MCP server is the central nervous system of the agent coordination system (28 tools, 10 resources). A clean migration ensures long-term maintainability.

## What Changes

1. **Dependency**: Bump `fastmcp>=0.3.0` to `fastmcp>=3.2.3` in `agent-coordinator/pyproject.toml`
2. **Server transport**: Replace SSE with HTTP Streamable transport in `coordination_mcp.py`
3. **Decorator syntax**: Update `@mcp.tool()` to `@mcp.tool` (3.x preferred style, no parentheses)
4. **Client migration**: Update `mcp_client.py` to use 3.x Client API (proper async context manager, `result.data` access)
5. **MCP registration**: Update `make claude-mcp-setup` if transport arguments changed
6. **Tests**: Verify all 28 tools and 10 resources work against 3.x API

## Scope Boundaries

- **In scope**: `agent-coordinator/` only — server, client, tests, pyproject.toml
- **Out of scope**: `skills/` (no fastmcp dependency), other repos, infrastructure changes
- **No external consumers**: Only this repo's Claude Code (stdio) and gen-eval tests (network) connect

## Approaches Considered

### Approach A: Incremental In-Place Migration (Recommended)

**Description**: Migrate the two fastmcp-importing files (`coordination_mcp.py`, `mcp_client.py`) directly, updating API patterns to 3.x style. Single PR, single branch.

**Pros**:
- Simplest execution — two files to change plus pyproject.toml
- No compatibility shims or conditional imports
- Clean git history (one logical change)
- Tests validate immediately against 3.x

**Cons**:
- All-or-nothing — can't partially ship
- If 3.x has unexpected issues, must revert entirely

**Effort**: S

---

### Approach B: Adapter Layer with Feature Flag

**Description**: Introduce a thin adapter module (`src/mcp_compat.py`) that abstracts fastmcp version differences behind a stable internal API. Feature flag controls which version's code path runs.

**Pros**:
- Gradual rollout possible
- Easy rollback via flag
- Tests can run against both versions

**Cons**:
- Over-engineered for a library with 2 import sites
- Adapter adds indirection that outlives its usefulness
- More code to maintain and eventually remove

**Effort**: M

---

### Approach C: Parallel Server Module

**Description**: Create `coordination_mcp_v3.py` alongside the existing module. Switch the entry point once validated. Delete old module after confirmation.

**Pros**:
- Zero risk to existing server during development
- Can A/B test both versions
- Easy to delete old code

**Cons**:
- Duplicates 3000+ lines of server code temporarily
- Merge conflicts if tools are added during migration
- Confusing which module is "live"

**Effort**: M

---

### Selected Approach

**Approach A: Incremental In-Place Migration** — The migration surface is small (2 files importing fastmcp), the breaking changes are well-documented, and there are no external consumers. An adapter layer or parallel module would be over-engineering for what is fundamentally: update decorators, swap transport string, fix client response parsing.
