# Split the documentation surface into agent-memory and docs in context-impact rules

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `split-agent-memory-surface-in-context-impact-rules`
> Effort: S
> Priority: 3

## Summary

Replace the single documentation surface in openspec/schemas/context-impact-rules.yaml with an agent-memory surface (AGENTS.md, CLAUDE.md, SKILL.md frontmatter) and a docs surface (README, docs/guides, docs/proposals, docs/decisions), and have the documentation.inventory producer report the byte and estimated-token size of the agent-memory surface.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- context-impact-rules.yaml validates against its schema with agent-memory and docs surfaces and no remaining documentation surface.
- A test asserts AGENTS.md, CLAUDE.md, and skills/*/SKILL.md frontmatter classify as agent-memory while README.md and docs/guides/*.md classify as docs.
- The documentation.inventory producer output includes agent_memory_bytes and agent_memory_tokens_est (bytes/4) fields and its check mode fails when the value exceeds a configured budget.

## Rationale

Section 3.3. The agent surface is paid on every session while human docs are free until pulled; the schema currently lumps both together so nothing machine-visible distinguishes them and nothing reports the always-loaded budget. This gives skill-rightsizing ri-04 and ri-10 (rewrite-skill-frontmatter) a repeatable in-repo measurement of the surface they cut.
