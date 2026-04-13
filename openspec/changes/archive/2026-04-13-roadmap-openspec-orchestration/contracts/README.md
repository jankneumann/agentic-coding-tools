# Contracts: Roadmap-Oriented OpenSpec Orchestration

## Artifact Contracts

Machine-readable schemas defining the interface between `plan-roadmap` and `autopilot-roadmap`:

| Artifact | Schema | Description |
|----------|--------|-------------|
| `roadmap.yaml` | [roadmap.schema.json](roadmap.schema.json) | Roadmap items, dependency DAG, status, priority, policy config |
| `checkpoint.json` | [checkpoint.schema.json](checkpoint.schema.json) | Resumable execution state: phase pointer, vendor state, pause/block info |
| `learnings/<item-id>.md` | [learning-log.schema.json](learning-log.schema.json) | Per-item learning entries (frontmatter schema + markdown body) |

### Learning Log Structure

The learning log uses a **progressive disclosure** model:

- **`learning-log.md`** (root) — Index document listing all learning entries with one-line summaries
- **`learnings/<item-id>.md`** — Per-item detailed learning entry with YAML frontmatter conforming to `learning-log.schema.json` and a markdown body for narrative context

This structure bounds context loading: `autopilot-roadmap` reads only the root index to decide relevance, then loads specific entries as needed — avoiding unbounded growth in context assembly.

### Sanitization Contract

All artifact writers MUST comply with these redaction rules:

- **NEVER** persist: credentials, API keys, tokens, raw vendor prompts/responses, environment variable values
- **ALWAYS** persist: structured summaries, decision rationale, cost/latency metrics, capability observations
- Learning entries MUST pass sanitization validation before write (implementation provides a sanitizer utility)

## External Contract Categories

- **OpenAPI**: Not applicable — no new HTTP endpoints
- **Database**: Not applicable — no new DB schemas
- **Events**: Not applicable — no new event payloads

If implementation introduces coordinator APIs or persistent DB state, this directory MUST be expanded with the corresponding machine-readable contracts.
