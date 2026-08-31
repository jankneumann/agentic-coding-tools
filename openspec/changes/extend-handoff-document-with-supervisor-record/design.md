# Design — extend handoff document with supervisor record

## Context

`HandoffDocument` has never grown a field. The payload crosses fourteen hand-written
field lists between a skill and the database, and the two guiding principles of the
supervisor proposal — "rehydratable role, not resident process" and "git is truth; the
database is a projection" — pull in opposite directions if the record is treated as one
blob. The design splits it along the derivable / non-derivable seam and adds exactly one
key everywhere. Approach 1 (Gate 1).

## D1 — One nullable `supervisor_record` JSONB column, self-versioned inside

**Decision.** Migration `034_handoff_supervisor_record.sql` adds `supervisor_record JSONB
DEFAULT NULL`. The inner document carries `schema_version` (const 1 for this change) and is
validated by `contracts/schemas/supervisor-record.schema.json` at the writer, never in SQL.

**Why one column.** Every surface (dataclass, RPC, INSERT/SELECT, Pydantic, read row, MCP,
proxy, bridge whitelist, PhaseRecord, OpenAPI, fallback schema) grows by one key. Four typed
columns would be four keys × fourteen lists, and nothing queries handoffs by section.

**Why self-versioned.** The outer document has no version; adding one now for all handoffs
is scope creep. Versioning the inner document means later sections (ri-06's escalations,
ri-13's digest) evolve with a `schema_version` bump and no migration.

**Overload hygiene.** Postgres resolves `write_handoff(...)` by argument types; adding a
defaulted ninth parameter creates a second overload and makes eight-argument calls
ambiguous. The migration does `DROP FUNCTION write_handoff(TEXT, TEXT, TEXT, JSONB, JSONB,
JSONB, JSONB, JSONB)` then `CREATE FUNCTION` with the ninth defaulted parameter.
`test_rpc_migration_alignment` (name-level) keeps passing; a new test asserts the arity.
The replacement function otherwise preserves migration 002 behavior: the
`p_session_id` and `p_summary` defaults, empty-summary check, non-`SECURITY DEFINER`
execution mode, and descending aggregate ordering do not change.

## D2 — Derivable vs non-derivable: the seam the record is split on

| Section | Source of truth | On build | In mirror |
|---|---|---|---|
| `active_changes` | `openspec/changes/*/loop-state.json`, `roadmap.yaml` | recomputed | **no** |
| `pending_gates` | gate evaluations (ri-06 writes them) | carried forward | yes |
| `standing_decisions` | operator answers in `/supervise` | carried forward, expired dropped | yes |
| `back_edge` | digest runs (ri-13 writes it) | carried forward | yes |

**Why.** `active_changes` is a projection of tracked files; storing it durably would create a
second truth that drifts by the next phase transition. The other three exist only because
someone decided something — git cannot reconstruct them, so they need a durable home the
coordinator does not own. `openspec/supervise/supervisor-record.json` is that home; it is
already inside `_ALLOWED_WRITE_PREFIXES` and sits beside `cycle-ledger.json`.

**Rejected**: mirroring the whole record. `active_changes` churns on every phase, producing
a tracked-file edit per transition across every worktree — the noise would make the mirror
unreviewable and constantly conflict.

## D3 — The builder lives in `cycle_state.py` and is deterministic

**Decision.** `cycle_state.py supervisor-record [--prior PATH] [--repo-root PATH] [--now RFC3339]` prints the
record as JSON (`indent=2, sort_keys=True`). It reads, per change directory: `loop-state.json`
(`current_phase`, `phase_started_at`, `pending_gate`, `last_handoff_id`), the worktree registry
for `branch`/`worktree`, and `roadmap.yaml` for `roadmap_ref` (`<roadmap-id>:<item-id>` when
an item's `change_id` matches). `--prior` may point at a handoff JSON (uses
the normalized handoff object extracted from `try_handoff_read` at
`data.handoffs[0].supervisor_record`) or at the mirror; the carry-forward merges by section, drops
`standing_decisions` past `expires_at`, and never invents a `pending_gates` entry.

**Why here.** `cycle_state.py` already owns the supervisor's deterministic questions
(fingerprint, ready set, dedupe, write audit) and is covered by `TestHostAssistedInvariant`
(no LLM SDK, no network). The builder is the same kind of function. Determinism is asserted with identical explicit inputs: tests pass the same `--now` value
to two runs over an unchanged tree and require byte-identical output. Production omits
`--now`, so `written_at` records the actual write time; time is an explicit input rather
than hidden nondeterminism.

**`loop-state.json` schema coupling.** `pending_gate` is a v5 field introduced by
`encode-autopilot-gates-and-goal-gate-in-code`; the builder reads it with `.get()` so a v4
state yields `pending_gate: null` rather than a failure. Nothing here depends on that change
landing first.

## D4 — Handoff is the transport; the mirror is the truth for what git cannot derive

**Decision.** Rehydrate order in `/supervise`: (1) `try_handoff_read(limit=1, supervisor_only=true)` and normalize
`data.handoffs[0].supervisor_record` when present; (2) read the
mirror if present; (3) pick the non-derivable sections from whichever has the newer
`written_at`; (4) run the builder with that as `--prior`. Coordinator unreachable → step 1
yields nothing, the digest reports `Degraded: handoff`, and rehydration proceeds from the
mirror.

**Why newer-wins rather than mirror-always.** A session on another machine may have written
a handoff after this checkout's last mirror commit; ignoring it would silently re-ask a
decision already made. Timestamp comparison is cheap and both writers stamp `written_at`.

**Rejected**: coordinator-only. It satisfies the roadmap wording but a fresh session with
the coordinator down would start cold — the exact failure "rehydratable role" is meant to
remove.

## D5 — `register_agent.py` is not modified

**Decision.** The SessionStart hook keeps printing `summary[:80]` and `next_steps`. The
record rides along in the payload the hook already fetches; `/supervise` step 1 reads the
full document through the bridge and renders it.

**Why.** The roadmap outcome is satisfied by the existing hook fetching a handoff whose schema now
permits the record; `/supervise` owns interpretation and rendering. The hook swallows all exceptions and must never slow startup (`record-doctor-context-cost-baseline`
is measuring it). Rendering a multi-section record there would grow every session's startup
output, supervisor or not.


## D6 — One key through the host-side plumbing

`coordination_bridge.try_handoff_write` whitelists payload keys; it gains
`"supervisor_record": structured.get("supervisor_record")` **only when present** (the
existing five are sent as `None` when absent; sending `supervisor_record: null` is
harmless but the test asserts absence to keep old bodies byte-identical). `PhaseRecord` gains
`supervisor_record: dict | None = None`; `to_handoff_payload()` includes the key only when
set, so the four existing round-trip tests and the fallback fixtures do not change.
`handoff-local-fallback.schema.json` `payload` gains the optional key (schema `$id` unchanged,
`schema_version` stays 1 — the envelope is unchanged, the payload merely permits a new key).

## D7 — Schema of the inner record

```
supervisor_record
├── schema_version: 1
├── written_at: date-time
├── written_by: {agent_name, session_id}
├── active_changes[]: {change_id*, current_phase*, phase_since, branch, worktree,
│                       pending_gate: {gate, requested_at} | null, roadmap_ref, last_handoff_id}
├── pending_gates[]:  {gate*, change_id*, requested_at*, deadline*, disposition,
│                       approval_id, source: "autopilot"|"supervise"|"escalation"}
├── standing_decisions[]: {id*, decided_at*, scope*, decision*, rationale, expires_at}
└── back_edge: {last_digest_at, last_fingerprint, digested_stubs[]: {stub_key*, rank*, decision*, decided_at*}}
```
`gate` values are the eight `trust_posture.Gate` members. `deadline` is required on
`pending_gates` so ri-06 cannot file an escalation without one. `back_edge.digested_stubs`
uses `cycle_state.stub_key` as identity so ri-13 can join it to the ledger's `seen_keys`.

## D7A — Reliable retrieval, idempotent mirror, and bounded derivation

**Supervisor lookup.** `read_handoff` gains a trailing `p_supervisor_only BOOLEAN DEFAULT
FALSE`; migration 034 drops the old two-argument overload before recreating it. The
service, HTTP request, MCP/proxy surfaces, and bridge expose `supervisor_only`. `/supervise`
always reads with `supervisor_only=true`, so a newer ordinary handoff cannot mask the
latest supervisor record. Ordinary callers retain the existing default and behavior.

**Mirror lifecycle and idempotency.** A dedicated
`supervisor-record-mirror.schema.json` validates the tracked subset. Integration promotes
both schemas to `openspec/schemas/` so runtime validation survives change archival.
`write_mirror` sanitizes free-form content, writes repo-relative paths only, and is a no-op
that preserves `written_at` when the non-derivable content is unchanged. The mirror joins
`cycle-ledger.json` in the fingerprint exclusion list, so a record write cannot make an
otherwise unchanged next cycle appear new. Dry-run never writes either store; non-dry-run
writes the mirror before the final write audit and the handoff afterward.

**Derivation policy.** A change is active when it has a parseable loop state whose phase is
not `DONE`; `ESCALATE` remains active. Missing or malformed states are skipped and reported
as degraded inputs. Registry selection prefers the non-agent feature entry, ignores stale
child entries, and emits repo-relative worktree paths. Roadmap items are pre-indexed by
`change_id`; duplicate matches are reported as degraded rather than selected arbitrarily.

**Hook behavior.** PreCompact, SessionEnd, and SessionStart remain generic and unchanged.
They may write newer ordinary handoffs, but `supervisor_only=true` prevents masking; the
supervisor record is written explicitly by `/supervise`, so copying it through unrelated
hooks is unnecessary.

## D8 — Sequencing

- `axi-align-coordinator-output` (16/18) changes the read envelope; this change adds a payload
  key. No file overlap in the dataclass; the read-row builder in `coordination_api.py` is the
  one shared edit — rebase whichever lands second.
- `encode-autopilot-gates-and-goal-gate-in-code` introduces `pending_gate` on loop state; the
  builder tolerates its absence (D3).
- Supervisor ri-06 and ri-13 write into `pending_gates` and `back_edge`; they are consumers
  of this contract and not blocked by it beyond the schema.

## Task sizing notes

No task is L or XL. The one M task in Phase 1 (the coordinator surfaces) touches six files
with the same one-key edit; splitting it per file would make six XS tasks that cannot be
tested independently (a write on one surface is only verified by a read on another). The
builder task (3.3) is M because derivation, carry-forward, and expiry are one function's
worth of merge logic.
