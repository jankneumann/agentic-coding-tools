# AXI-Align Coordinator Agent-Output Contract

## Why

The `coordination-cli` and HTTP API exist to be a token-efficient alternative to MCP for agent consumers (the CLI module docstring says so explicitly). An analysis of the [AXI design principles](https://github.com/kunchenguid/axi) ("Agent Experience Interface" — agent-native tooling that beats both raw CLIs and MCP on cost/turns in benchmarks) found that this coordinator already satisfies most of them by convention — minimal list schemas, structured errors, exit codes, progressive help disclosure. Three principles are unmet, and one of them is a latent correctness bug:

1. **No explicit truncation markers (AXI principle 3).** List commands that accept `--limit` (`audit query`, `memory query`, `handoff read`) pass the limit straight to the service and emit a bare JSON array. An agent receiving exactly `limit` rows cannot distinguish "this is everything" from "this is page one of many." It must either silently miss data or burn a turn re-querying defensively. This is a turn-cost regression *and* a correctness hazard, independent of any token-format question.

2. **No pre-computed list aggregates / definitive empty states (AXI principles 4, 5).** A bare `[]` is ambiguous to an agent — it can read as "the call failed" as easily as "zero results." There is no inline `count`, so an agent that needs a tally issues a second call.

3. **No contextual next-step disclosure (AXI principle 9).** After `feature list`, the agent must already know that `feature show`/`feature conflicts` are the follow-ups. Surfacing them in-band measurably reduces turns in AXI's own benchmarks.

AXI's headline feature — TOON output for ~40% token savings — is deliberately **out of scope here** (see below); the cheap, format-agnostic correctness principles capture most of the value with none of the format risk, and AXI's benchmark wins come mostly from turn-reduction, not per-payload bytes.

## What Changes

- Introduce an **AXI-aligned list-output envelope** for `coordination-cli` list commands. Each list response gains:
  - `count` — definitive empty state (`count: 0`), never an ambiguous bare `[]`.
  - `truncated` — `true` when a `--limit` cut the result short, plus a `hint` telling the agent how to page.
  - `next_steps` — suggested follow-up commands (contextual disclosure).
  - `items` — the existing rows, unchanged in schema.
- Detect truncation **precisely** via the `limit + 1` fetch-and-trim probe (avoids the off-by-one ambiguity of `len(items) == limit`).
- Apply the CLI envelope to: `feature list`, `merge-queue status`, `lock status`, `handoff read`, `memory query`, `audit query`.
- Extend the **same contract to the HTTP API** list endpoints (`GET /features/active`, `GET /merge-queue`, `GET /audit`, `POST /memory/query`, `POST /handoffs/read`) — but **additively**: the existing named array key (`features`, `entries`, `memories`, `handoffs`) is preserved and `count` / `truncated` / `hint` / `next_steps` are added as sibling fields, because the HTTP API has live external consumers (the coordination bridge, skills, cloud agents) that read those keys. (Handoffs omit the top-level `next_steps` suggestion to avoid colliding with each handoff row's own semantic `next_steps` field.)
- Factor the transport-agnostic logic (the `limit + 1` probe, the hint string, the HTTP envelope builder) into a shared `src/axi_output.py` so both surfaces compute the contract identically.
- Add unit tests for the envelope and truncation-probe helpers (no DB required) and strengthen the existing `/memory/query` and `/audit` API tests to assert the new envelope keys.
- Update the `agent-coordinator` capability spec: ADD the CLI list-output contract requirement and the HTTP additive-envelope requirement, MODIFY the `CLI Entry Point` feature-list scenario whose assertion changes from "JSON array" to "envelope object with an `items` array."

A working prototype of all of the above is implemented in this change's branch (`src/axi_output.py`, `src/coordination_cli.py`, `src/coordination_api.py`, plus tests) and passes `mypy --strict`, `ruff`, and the unit/API test suites.

## Out of Scope

- **TOON output format (AXI principle 1).** Defer to a separate, opt-in `--format=toon` change behind a flag. Rationale: TOON only wins on *uniform* arrays — the coordinator's nested handoff/phase-record payloads would regress — and it adds an encode/decode dependency plus a parsing-reliability risk. The turn-reduction principles in this change are the higher-leverage, lower-risk subset; TOON should be A/B-measured on the genuinely tabular commands afterward, not adopted by default.
- **Pagination cursors / offsets.** The envelope flags truncation; it does not add `offset`/`cursor` parameters. Agents page by raising `--limit`. A real cursor protocol is a larger, separate design.
- **Ambient session hooks (AXI principle 7).** Already covered by the existing SessionStart hooks, coordinator registration, and `coordination-bridge` capability detection — no action needed.

## Approaches Considered

### Approach 1: Opt-in `--meta` / `--axi` flag (Rejected)

Keep the bare array as default; emit the envelope only when an agent passes `--meta`.

Pros:
- Purely additive; zero risk to existing consumers.

Cons:
- Defeats the purpose. The whole point of a truncation marker is that the agent learns the result was cut *without knowing to ask*. An opt-in flag the agent won't pass leaves the correctness hazard in place.
- Splits the output contract into two shapes, doubling the surface agents must reason about.

Effort: S

### Approach 2: Default envelope for list commands (Recommended)

Promote the envelope to the default shape for the six list commands. Detect truncation via `limit + 1`.

Pros:
- The truncation/empty-state signals reach the agent by default — the AXI-aligned behavior.
- A pre-flight consumer trace (tests, eval YAMLs, skills) confirms **no consumer parses the array shape** — every existing CLI eval asserts only `exit_code: 0`. Blast radius is just the one spec scenario.
- Single, richer contract instead of two.

Cons:
- Technically a breaking change to the JSON shape (`[...]` → `{count, truncated, items, ...}`). Mitigated: rows live under `items`; the only in-repo assertion that cares is one spec scenario, updated here.

Effort: S–M

### Approach 3: Envelope everywhere including HTTP, plus TOON (Rejected for now)

Do the full AXI sweep — CLI + HTTP + TOON — in one change.

Cons:
- Couples a cheap correctness fix to a risky format migration and a Pydantic/OpenAPI change set, enlarging review surface and blast radius.
- TOON's value here is unproven and data-shape-dependent; it deserves its own measured A/B, not a blind bundle.

Effort: L
