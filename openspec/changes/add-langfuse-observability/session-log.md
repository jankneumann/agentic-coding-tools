# Session Log: add-langfuse-observability

---

## Phase: Plan (2026-04-04)

**Agent**: claude_code | **Session**: plan-feature

### Decisions
1. **Langfuse SDK Direct Integration** — Selected over OTel GenAI OTLP bridge because Langfuse's OTLP path has known bugs (#11135, #11030), GenAI conventions are still experimental, and session grouping requires `langfuse.*` attributes anyway (partial vendor coupling). The SDK provides the most mature integration today.
2. **Extend existing observability spec** — Langfuse requirements added as delta to `openspec/specs/observability/` rather than creating a standalone spec, keeping all observability concerns in one place.
3. **Include future roadmap in proposal** — Phase 2 items (offline queue, permission governance, token estimation, MCP tracing, multi-session correlation) documented in proposal and tasks as future roadmap, not just as-built.
4. **Self-hosted primary deployment** — Self-hosted Langfuse stack is the spec'd and tested path. Cloud and BYOL are documented alternatives in the setup script but not spec-tested.
5. **Reuse existing Postgres** — Langfuse uses a separate `langfuse` database on the existing ParadeDB instance rather than a second Postgres container, reducing resource footprint.

### Alternatives Considered
- OTel GenAI OTLP bridge: Rejected due to experimental conventions, known Langfuse bugs, and loss of scoring/prompt features
- Coordinator-only tracing (no hook): Rejected due to major blind spot for local agent conversation content
- Standalone Langfuse spec: Rejected in favor of extending existing observability spec for cohesion

### Trade-offs
- Accepted vendor-specific Langfuse SDK dependency over vendor-neutral OTel-only approach because the SDK provides richer LLM-specific features (session grouping, generations, scoring) and the OTLP integration path is not yet stable
- Accepted dual observability systems (OTel for infrastructure, Langfuse for LLM sessions) because they serve complementary purposes and the pattern is proven in AI-native stacks

### Open Questions
- [ ] Should Phase 2 items (offline queue, permission governance) be separate proposals or extensions of this one?
- [ ] Should the Langfuse hook be distributed via `skills/install.sh` to runtime directories?

### Context
Planning session for adding Langfuse cross-agent coding session observability. The implementation was completed first on branch `claude/add-langfuse-observability-pIi9D`, and the OpenSpec artifacts document the as-built Phase 1 plus a Phase 2 roadmap. Sequential tier selected — single architectural boundary (observability layer), no coordinator available.
