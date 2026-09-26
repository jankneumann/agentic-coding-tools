# Design: add-model-usage-ledger

Load-bearing decisions for Approach A (transcript-derived ledger pushed from hooks into the
coordinator). Tasks, specs, and contracts reference decisions by ID (D1…D12).

## D1 — Coordinator is the system of record; transcripts are the source; hooks push

The coordinator Postgres holds usage, dispatch, and sanitized transcript events. Vendor transcripts
on the session host are the only complete observation of what a model actually did, so they are the
source, and the push happens from inside the session via the `Stop`/`SubagentStop`/`SessionEnd`
hooks that already reach the coordinator for status. Rejected: Langfuse as system of record (hook
cannot know change/phase at emit time; credentials broken; coordinator stays blind) and Claude Code
native OTel (Claude-only, no phase attribution, no collector reachable from cloud containers).

## D2 — Join key: sub-agent id ↔ sidechain transcript

The Claude harness returns an agent id from `Agent(...)`, and Claude Code writes that sub-agent's
transcript at `<project>/<session>/subagents/agent-<id>.jsonl` with `agentId`, `sessionId`,
`isSidechain`, `effort`, and `message.{model,usage}` on every assistant record. The dispatch record
stores the id when the adapter returns; the usage record stores it from the transcript; the mismatch
report is `dispatch_records ⋈ usage_records ON (session_id, agent_id)`. For non-Claude CLIs the
adapter's own session identifier (Codex rollout id, Grok/Pi session id) is stored in `agent_id`, and
the dispatch record captures it from the adapter result. No inference from timestamps.

## D3 — Granularity: one usage row per vendor API call

One row per assistant message keeps thinking tokens, cache tiers, and `effort` attributable to the
exact call, lets phase/day/model rollups be plain SQL, and gives a natural idempotency key
(`record_hash` over vendor, session, agent, message id, usage). Session-level aggregates were
rejected because they cannot express a mid-session model switch or effort change.

## D4 — Thinking forwarding is a per-provider template in `agents.yaml`

`cli.thinking_flag` is an argv template with a `{thinking}` placeholder (Codex:
`["-c", "model_reasoning_effort={thinking}"]`; Grok: `["--reasoning-effort", "{thinking}"]`;
Antigravity: model-id suffix handled by `model_aliases`, so no flag). Missing template → structured
`thinking_not_forwarded` warning, dispatch proceeds. The Claude `Agent(...)` path has no thinking
parameter, so intent is recorded in the dispatch record and compared with the observed `effort`.
Rejected: hard-coding vendor flags in `provider_dispatch.py` (contradicts `agents.yaml` as single
source of truth).

## D5 — Pricing is a hand-maintained versioned YAML; unknown = null, never zero

`agent-coordinator/pricing.yaml` with `schema_version`, monotonic `version`, and per
`(vendor, model-or-prefix)` USD/Mtok for input, output, cache_read, cache_write, thinking. Every
stored cost carries `pricing_version` and `estimated=true` (NOT NULL constraints). No rate →
`cost_usd NULL`, `cost_reason='no_price'`, counted as `unpriced_records`. Vendor-reported cost
(Grok `total_cost_usd`) is stored separately and preferred in reports. The router's OpenRouter
refresher may later write this file; it is out of scope here.

## D6 — Central transcript events, sanitized at source, 90-day retention

Sanitized normalized events are stored in `transcript_events` so cloud sessions can be deep-analysed
after container reclaim. Sanitization runs on the session host with the `collect-transcripts`
sanitizer and the batch carries `sanitized=true`; the coordinator rejects batches without it (422).
Nightly `WatchdogService` job purges events older than `USAGE_EVENT_RETENTION_DAYS` (90) and audits
the count. `usage_records` and `dispatch_records` are never purged. Rejected: unbounded retention
(operator chose 90 days) and usage-only storage (operator wants central deep analysis).

## D7 — Idempotent, spooled, always-exit-0 collector

The collector advances per-file cursors only after the coordinator acknowledges the batch; on
failure it appends the batch to `~/.claude/state/usage-spool/<ts>.json` and exits 0. Next run replays
spool first. Uniqueness on `(vendor, session_id, record_hash)` makes replay safe. Gate:
`USAGE_LEDGER_ENABLED` (default true when `COORDINATION_API_URL` is set). Budget: p95 ≤ 5 s for
500 new lines; hook timeout 30 s.

## D8 — Langfuse becomes a consumer of the normalized events

`langfuse_hook.py` drops its private parser and calls the Claude Code adapter (parent + sidechains),
emitting one `generation` per assistant message with `usage_details` and `model`, plus `tool`
children. The coordinator-side v2-era middleware stays out of scope and the observability spec says
so. Rejected: fixing the middleware here (widens into coordinator tracing owned by
`add-cross-harness-flow-display`).

## D9 — Archetype enum parity is test-enforced

`report_status.py`, the `/status/report` literal, and the DB CHECK constraint are widened to all
archetypes and a parity test compares each to `archetypes.yaml` keys. Rejected: deriving the client
allow-list from the coordinator at runtime (the status hook must work when the coordinator is down).

## D10 — `usage-viz` copies `kanban-viz` and reads only the coordinator API

React + TypeScript + Vite, Bearer auth, SSE/poll fallback, four views: spend by vendor/model,
per-change phase table with mismatch highlighting, thinking-tier comparison, cloud-session ingest
status. No direct DB or transcript access. The app is the last package and can ship after the report.

## D11 — Provider-less resolution returns a tier name and says so

`resolve_archetype_for_phase` without `provider` returns `model=<tier>`, `thinking=None`, and a
reason `"provider unspecified: model is a tier name, not a dispatchable identifier"`. Callers that
need a dispatchable id must pass `provider`. Rejected: defaulting to `claude_code` (silently wrong
for other harnesses).

## D12 — Supersession and router amendment

`usage-stats-multi-model` is archived with a superseded-by pointer to this change; its
`usage_records`/`usage_ingest_state` shapes are carried forward (extended with `agent_id`,
`parent_session_id`, `effort`, `thinking_tokens`, `vendor_cost_usd`, provenance columns).
`add-adaptive-model-router/design.md` D12 is amended: `usage_records` joined to `dispatch_records` is
an accepted source for the router's spend ledger and feedback posteriors, and the "no transcript
parsing in v1" sentence is struck.

## D14 — The migration sequence number is assigned at implementation, not here

The migration is `<NNN>_model_usage_ledger.sql`, with `<NNN>` taken when the file is
created. The highest occupied sequence as of 2026-09-26 is `044`.

This plan was renumbered twice while waiting for approval — `035` on 2026-09-03, `037` on
2026-09-04 — and the sibling change #467 was renumbered a third time when `044` was taken
within two days of it choosing that number. `main` moves roughly thirty commits a day, so a
number picked at planning time is a guess about merge order that decays for as long as the
proposal waits. Naming the file by intent costs nothing and removes the collision class
rather than re-detecting it. See issue #637, which also proposes a uniqueness guard for the
two duplicates already on `main` (`026` x3, `035` x2).

## D13 — `cost_usd` is always derived; a vendor-billed figure never moves into it

The plan-review remediation constrained priced rows to `estimated IS TRUE`, and raised whether that
would wrongly reject a genuinely vendor-billed cost. It would not, and the reason is already in D5:
`vendor_cost_usd` is stored *alongside* the estimate and reports prefer it, labelled as
vendor-reported. The two columns coexist. Nothing promotes one into the other.

**Decision.** Make that explicit and enforce it, rather than leaving it as a property the schema
happens to have.

- `cost_usd` means "computed by this system from `pricing.yaml`". It is therefore always an
  estimate, always carries `pricing_version`, and is null with `cost_reason` when no rate exists.
- `vendor_cost_usd` means "reported by the vendor". It carries no `pricing_version`, because no
  price table produced it.
- A vendor-reported figure SHALL NOT be written to `cost_usd`, under any circumstance, including
  when `cost_usd` would otherwise be null.

The `estimated IS TRUE` constraint stays. It is not a restriction on what the system can represent;
it is the statement that this column only ever holds one kind of number.

**Alternative rejected: relax to `estimated IS NOT NULL` and allow promotion.** This is the shape
the open question implied, and it is worse in three specific ways.

*`cost_usd` would mean two things.* A consumer summing the column could no longer say whether it had
summed estimates, billings, or a mixture — and the mixture is the common case, since only some
vendors report cost. Reconciling a total against an invoice becomes impossible without re-deriving
the split.

*`pricing_version` becomes meaningless on promoted rows.* Today it answers "which table priced
this", and re-pricing history after a rate correction is a matter of selecting on it. A promoted row
has no pricing version and cannot be re-priced, so the column silently stops being a complete index
of derived costs.

*`unpriced_records` stops being true.* Promotion is most tempting exactly when `cost_usd` is null —
a vendor cost is right there. But those records are counted as `unpriced_records` precisely so the
gap in `pricing.yaml` stays visible. Filling `cost_usd` from the vendor hides the missing rate, and
the rate stays missing for every other model that shares it.

**Consequence for reports, which is where the question came from.** "Prefer the vendor figure" is a
presentation rule, not a storage rule: a report showing spend SHALL use `vendor_cost_usd` when
present and `cost_usd` otherwise, and SHALL label which it used. That gives the accurate number
without collapsing the distinction that makes it auditable.

## Task-sizing notes

Seven implementation packages, each M or smaller. The only L-shaped area was the coordinator
package (migration + pricing loader + routes + retention); it is kept as one package because the
API factory, config, and db modules are a single parallel zone, but its tasks are sized S/M with
checkpoints. `apps/usage-viz` is M and last.

`wp-dispatch` depends on `wp-coordinator` as well as `wp-contracts`: the `agents.yaml` `cli` block
is validated with `additionalProperties: false` in `agents_config.py`, so the `cli.thinking_flag`
key (task 4.8a) is only loadable after the schema accepts it (task 3.18). `agents.yaml` itself is
written by `wp-dispatch` and denied to `wp-coordinator` to keep write scopes disjoint.

"And"-titled tasks that remain are test tasks enumerating multiple assertions of one behaviour
(e.g. 3.5, 3.13) or single-outcome titles where the conjunction joins qualifiers, not outcomes.
Genuine two-outcome tasks were split (2.8/2.8a-b, 3.4/3.4a, 3.8/3.8a, 4.4/4.4a, 4.8/4.8a,
8.1/8.1a).

## Absorption mechanics

- Archive `usage-stats-multi-model` → `openspec/changes/archive/2026-09-03-usage-stats-multi-model/`
  with `superseded_by: add-model-usage-ledger` in its proposal header.
- Add a dated "Amendment" block to `add-adaptive-model-router/design.md` under D12.
