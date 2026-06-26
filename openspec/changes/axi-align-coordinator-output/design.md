# Design: AXI-Aligned Coordinator List Output

## Context

`coordination-cli` is positioned (in its own module docstring) as a
"token-efficient alternative to MCP." The [AXI principles](https://github.com/kunchenguid/axi)
formalize what that should mean for agent-consumed output. This change adopts
the three AXI principles the CLI does not yet meet — explicit truncation
(3), definitive empty states + inline aggregates (4, 5), and contextual
disclosure (9) — while deferring the token-format principle (1, TOON) as a
separately-measured follow-up.

## Goals / Non-Goals

**Goals**
- An agent reading a single list response can tell (a) how many rows it got,
  (b) whether more exist, and (c) what to do next — with no follow-up call.
- Truncation detection is exact, not heuristic.
- Zero regression for existing consumers (verified: they assert exit codes only).

**Non-Goals**
- Token-format optimization (TOON) — deferred, opt-in, A/B-measured later.
- HTTP API parity — sequenced separately (Pydantic + OpenAPI surface).
- Cursor/offset pagination — the envelope flags truncation; it is not a paging protocol.

## Decisions

### D1: Envelope shape `{count, truncated, items, hint?, next_steps?}`

The rows stay under `items` with their existing per-row schema (AXI principle 2,
minimal schemas, is already satisfied and is preserved). `count` and
`truncated` are the always-present agent signals; `hint` and `next_steps`
are conditional. This keeps the common case compact while making the
correctness-critical signals unconditional.

Alternative considered — flat array with a sibling `_meta` field — rejected:
it forces agents to correlate two top-level values and complicates the
human-readable rendering.

### D2: Truncation via `limit + 1` fetch-and-trim

The service layer is asked for `limit + 1` rows; if it returns more than
`limit`, the result was truncated, and the sentinel row is trimmed before
printing. This is exact. The naive alternative — `truncated = len(items) == limit`
— cannot distinguish "exactly `limit` rows exist" from "the first page of
many," which is precisely the ambiguity AXI principle 3 exists to remove.
The `+1` cost is one extra row fetched, never an extra round trip.

### D3: Default shape, not opt-in flag

The envelope is the default for the six list commands, not gated behind
`--meta`. A truncation marker only helps if it reaches the agent *without the
agent knowing to ask*; an opt-in flag the agent won't pass leaves the hazard
in place. A pre-flight trace of every in-repo consumer (unit tests, the
`evaluation/scenarios/**` CLI sweeps, skills that shell out to the CLI) found
that none parse the array shape — the CLI eval steps assert only
`exit_code: 0` — so promoting the envelope to default has a blast radius of a
single spec scenario, updated in this change.

### D4: Per-command `next_steps`

Each list command declares its own follow-up commands inline (e.g.
`feature list` → `feature show`, `feature conflicts`). These are static,
hand-curated strings, not derived from row content, keeping the rendering
pure and free of injection concerns.

## Risks / Trade-offs

- **JSON shape change is technically breaking.** Mitigated by the consumer
  trace (D3) and by keeping rows verbatim under `items`. Any future external
  consumer reads `.items`.
- **Human-readable mode gains a header/footer.** Acceptable — the CLI's
  primary consumer is an agent in `--json` mode; the human view stays compact
  (count line + rows + optional next-steps list).

## Migration

No data migration. Follow-ups (deferred): extend the envelope to the HTTP API
list endpoints, refresh any docs that show example `feature list` output, and
pilot `--format=toon` on the tabular commands.
