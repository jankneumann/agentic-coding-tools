---

## Phase: Plan (2026-04-20)

**Agent**: claude_code | **Session**: merge-pull-requests triage

### Decisions
1. **Approach A: In-place migration** — Two files import fastmcp, no need for adapter layers or parallel modules
2. **Pin to >=3.2.3 exclusively** — Clean break, no dual-version compat shims
3. **Migrate SSE to HTTP Streamable** — SSE is legacy in 3.x, no external consumers depend on it
4. **Sequential tier** — Single architectural boundary (agent-coordinator only)

### Alternatives Considered
- Adapter layer with feature flag: rejected because only 2 import sites make abstraction overhead unjustified
- Parallel server module: rejected because 3000+ line duplication creates merge conflict risk for no proportional benefit
- Keeping SSE: rejected because it's marked legacy and will eventually be removed

### Trade-offs
- Accepted all-or-nothing deployment over gradual rollout because the migration surface is small and well-tested
- Accepted HTTP over SSE despite SSE still working, to align with fastmcp 3.x long-term direction

### Open Questions
- [ ] Does `FastMCP(version=...)` kwarg still exist in 3.x? (verify during implementation)
- [ ] Does gen-eval MCP client need transport URL format changes for HTTP vs SSE?

### Context
Feature originated from Dependabot PR #108 which bumped fastmcp floor to >=3.2.3 but broke tests. Closed #108 and created this planned migration to address the API changes properly rather than merging a broken dependency bump.
