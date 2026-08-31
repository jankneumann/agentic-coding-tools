# Extend handoff document with supervisor record

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `extend-handoff-document-with-supervisor-record`
> Roadmap item: `ri-05`
> Effort: M
> Priority: 1

## Why

`skills/supervise/SKILL.md:117` tells a fresh session to rehydrate from "the
SessionStart handoff (active changes, pending gates, standing decisions)". Nothing
produces that data. `HandoffDocument` (`agent-coordinator/src/handoffs.py:21-55`)
has five untyped `list[Any]` fields and a summary; no field has ever been added to
it, it carries no schema version, and `from_dict` drops unknown keys. The
SessionStart hook (`register_agent.py:108-118`) prints `summary[:80]` and
`next_steps` and nothing else.

So today the supervisor is a role a human performs from memory. Killing the session
mid-roadmap loses: which changes are in flight and at what phase, which gates are
parked and for how long, which standing decisions the operator already made (so the
next cycle does not re-ask), and what the last digest showed. The proposal's guiding
principle — "rehydratable role, not resident process" — is unmet, and supervisor
roadmap ri-06 (escalations recorded "as a pending gate with its deadline") and ri-13
(digest state "in the handoff record's back-edge section") both need this record to
exist before they can write into it.

Two constraints shape the design. First, the handoff payload crosses fourteen
hand-written field lists (dataclass, RPC args, SQL `INSERT`/`SELECT`, Pydantic
request, `/handoffs/read` row builder, MCP tool, HTTP proxy, the bridge's key
whitelist, `phase_record.py`, the OpenAPI contract, the local-fallback JSON schema
with `additionalProperties: false`) — the extension must be one key, not four.
Second, the proposal's other principle — "Git is truth; the database is a
projection" — means a record that lives only in the coordinator DB is the wrong
truth for the parts git cannot derive.

## What Changes

1. **One `supervisor_record` JSONB column** on `handoff_documents` (migration
   `034_handoff_supervisor_record.sql`), nullable, default `NULL`; `write_handoff`
   gains a trailing `p_supervisor_record JSONB DEFAULT NULL` (old overload dropped
   explicitly), `read_handoff` selects it and gains a backward-compatible `supervisor_only` filter so newer ordinary handoffs cannot mask supervisor state. `HandoffDocument.supervisor_record:
   dict[str, Any] | None`. Non-supervisor handoffs never set it.

2. **A versioned inner contract**, `contracts/schemas/supervisor-record.schema.json`
   (`schema_version: 1`), with exactly four sections:
   - `active_changes[]` — `{change_id, current_phase, phase_since, branch, worktree,
     pending_gate, roadmap_ref, last_handoff_id}` — **derived** from
     `openspec/changes/*/loop-state.json` and `openspec/roadmaps/*/roadmap.yaml`.
   - `pending_gates[]` — `{gate, change_id, requested_at, deadline, disposition,
     approval_id, source}` — the `deadline` field is what ri-06 writes.
   - `standing_decisions[]` — `{id, decided_at, scope, decision, rationale,
     expires_at}` — operator decisions the next cycle must not re-ask.
   - `back_edge` — `{last_digest_at, last_fingerprint, digested_stubs[]:
     {stub_key, rank, decision, decided_at}}` — the slot ri-13 fills.

3. **One key on every surface.** `HandoffService.write(..., supervisor_record=None)`,
   `HandoffWriteRequest.supervisor_record`, the read row builder, MCP
   `write_handoff`/`read_handoff`, `http_proxy.proxy_write_handoff`, the bridge
   whitelist in `try_handoff_write`, `PhaseRecord.to_handoff_payload()` /
   `from_handoff_payload()`, `openspec/contracts/agent-coordinator/openapi/handoffs.yaml`,
   and `handoff-local-fallback.schema.json` (bumped to accept the optional key).

4. **Deterministic builder, host-assisted.** `cycle_state.py supervisor-record
   [--prior PATH] [--now RFC3339]` composes the record: derivable sections recomputed from the repo;
   non-derivable sections carried forward from the prior record (handoff or mirror)
   and merged with new inputs. No LLM, no network — `TestHostAssistedInvariant`
   keeps applying.

5. **Tracked mirror for the non-derivable half.** `openspec/supervise/supervisor-record.json`
   holds and validates against a dedicated mirror schema `pending_gates`, `standing_decisions`, `back_edge` (never `active_changes`,
   which would churn on every phase). `/supervise` rehydrate reads the handoff via
   `try_handoff_read`; if the coordinator is unreachable or the handoff predates the
   mirror, it rehydrates from the mirror plus a fresh derivation. Handoff is the
   transport; the mirror is the truth for what git cannot derive. Unchanged content is a no-op that preserves `written_at`, and the mirror is excluded from cycle fingerprinting. The path is already
   inside the supervisor's `_ALLOWED_WRITE_PREFIXES`.

6. **Hooks unchanged.** SessionStart, SessionEnd, and PreCompact remain generic. `/supervise` writes the record explicitly and reads it with `supervisor_only=true`, so newer ordinary hook handoffs cannot mask it.

7. **`/supervise` wired.** SKILL.md rehydrate step 1 becomes the bridge read + builder
   call; INTAKE step 6 and CYCLE step 5 end by writing the record (handoff + mirror).
   `skill-workflow` "Session Handoff Hooks" adds `/supervise` to its skill list.

## Approaches Considered

### Approach 1: JSONB envelope + repo-derived builder + tracked mirror (Recommended)

One nullable JSONB column carrying a self-versioned document plus a backward-compatible `supervisor_only` read filter; a deterministic
builder in `cycle_state.py` derives the volatile half from git-tracked state and
carries the durable half forward; the durable half is mirrored to a tracked file.

- **Pros**
  - Exactly one key on each of the fourteen surfaces; inner schema evolves without
    another migration.
  - Honours "git is truth": the coordinator never holds state the repo cannot
    reconstruct or does not mirror.
  - Rehydration works with the coordinator down (mirror + derivation).
  - Gives ri-06 (`deadline`) and ri-13 (`back_edge`) their slots now.
- **Cons**
  - Two writes per cycle (handoff + mirror) that can drift; needs a consistency test.
  - JSONB column is opaque to SQL consumers (no per-section indexing) — acceptable,
    nothing queries handoffs by content.
- **Effort**: M

### Approach 2: Four typed columns + coordinator-side composition

`active_changes`, `pending_gates`, `standing_decisions`, `back_edge_digest` as
separate JSONB columns, with the coordinator composing `active_changes` from
`/status/report` and discovery data at read time.

- **Pros**
  - Mirrors the existing five-list modelling; each section independently queryable.
  - Skills stay thin — no builder in `cycle_state.py`.
- **Cons**
  - Four additions × fourteen surfaces; four Pydantic/MCP/proxy parameters.
  - The coordinator cannot see `loop-state.json`; `/status/report` is per-agent and
    lossy, so `active_changes` would be a projection of a projection — inverts "git
    is truth".
  - No offline rehydration path.
- **Effort**: L

### Approach 3: Repo file primary, handoff carries only a reference

The whole record lives in `openspec/supervise/supervisor-record.json`; the handoff
gains a `supervisor_record_ref: {path, sha256, written_at}` key.

- **Pros**
  - Purest "git is truth"; the coordinator change is trivial.
  - No JSONB payload growth.
- **Cons**
  - A fresh session on another machine must have the commit that carries the file;
    a handoff written from a worktree that was never pushed leaves a dangling ref.
  - `active_changes` churns the tracked file on every phase transition — noisy
    commits, or a stale file, pick one.
  - ri-13's acceptance names "the handoff record's back-edge section"; a ref is not
    a section.
- **Effort**: S

### Recommendation

Approach 1. Approach 3's purity fails at the first unpushed worktree, and it puts
the volatile half in git where it churns. Approach 2 quadruples the surface cost and
makes the coordinator compose from data it does not have. Approach 1 splits the
record along the derivable/non-derivable line, which is exactly where the two
guiding principles stop conflicting.

### Selected Approach

**Approach 1** (Gate 1, 2026-08-29). Discovery decisions carried into the design:
(a) one `supervisor_record` JSONB column; (b) derive what is derivable, mirror the
rest to `openspec/supervise/supervisor-record.json`; (c) `register_agent.py` is not
modified — `/supervise` rehydrates via the bridge read; (d) the builder lives in
`cycle_state.py`.

## Non-Functional Requirements

| Attribute | Metric | Target | Verifying phase |
|---|---|---|---|
| Compatibility | Existing handoff writers/readers | All current tests pass unchanged; a write without `supervisor_record` stores `NULL`; `from_dict` of a pre-034 row yields `None` | VALIDATE (unit + live) |
| Correctness | Round-trip fidelity | `supervisor_record` structurally equal after JSON decoding through service, HTTP, MCP, bridge, and `PhaseRecord` | VALIDATE (unit) |
| Determinism | Builder output | Two builder runs over an unchanged tree produce identical JSON | VALIDATE (unit) |
| Resilience | Coordinator unreachable at rehydrate | `/supervise` rehydrates from mirror + derivation; reports `Degraded: handoff` | VALIDATE (unit) |
| Operability | SessionStart cost | `register_agent.py` wall-clock unchanged (record is not rendered there) | VALIDATE (measure) |

## Impact

- `agent-coordinator/src/{handoffs.py, coordination_api.py, coordination_mcp.py, http_proxy.py, coordination_cli.py, help_service.py}`, migration `034`
- `skills/coordination-bridge/scripts/coordination_bridge.py`, `skills/session-log/scripts/phase_record.py`
- `skills/supervise/scripts/cycle_state.py`, `skills/supervise/SKILL.md`
- Contracts: `openspec/contracts/agent-coordinator/openapi/handoffs.yaml`, `openspec/contracts/phase-record/schemas/handoff-local-fallback.schema.json`, and canonical `openspec/schemas/supervisor-record{,-mirror}.schema.json`
- Specs: `agent-coordinator` (MODIFIED Session Continuity; ADDED Supervisor Record), `skill-workflow` (MODIFIED Session Handoff Hooks), new `supervise` capability (ADDED Rehydration)
- Tests: `agent-coordinator/tests/test_handoffs.py`, e2e `test_handoffs_live.py`, `skills/tests/supervise/`, `skills/tests/phase-record-compaction/`, `skills/tests/session-bootstrap/`

## Out of Scope

- Rendering the record in `register_agent.py` (hook untouched by decision).
- Filing escalations as pending gates (ri-06) and populating `back_edge` (ri-13) — this change provides the slots and the carry-forward, not the writers.
- Coordinator-side composition of `active_changes`; kanban-viz mirroring.
- A `supervise` capability spec beyond the rehydration requirement.

## Dependencies

- `ri-02` create-supervise-skill-with-conversational-intake — completed (`7ba0747c`, `3f4bd096`, `ed283904`)

## Acceptance Outcomes

- Killing the supervisor session mid-roadmap and starting a fresh `/supervise` session loses no state: active changes and phases are freshly derived from repository state, while pending gates, standing decisions, and back-edge state are restored from the newest handoff or tracked mirror.
- The supervisor record round-trips through serialization with all four sections (active changes, pending gates, standing decisions, back-edge digest state) intact, covered by unit tests.
- The existing SessionStart hook remains unchanged and continues fetching the latest handoff; `/supervise` reads and renders the full `supervisor_record` through the bridge.
