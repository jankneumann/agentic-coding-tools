# Autopilot Per-Phase Archetype Resolution

Operator guide for the per-phase archetype resolution feature added by
OpenSpec change `add-per-phase-archetype-resolution`.

## Why

Autopilot's state machine has 13 non-terminal phases (`INIT`, `PLAN`,
`PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`,
`IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`,
`SUBMIT_PR`). Before this change, every phase ran on the harness default
model. With this change, each phase resolves an archetype that determines
both the model and the system prompt used for the sub-agent dispatch:

- `PLAN` runs under `architect` (opus) — deeper architectural reasoning.
- `IMPLEMENT` runs under `implementer` (sonnet, escalating to opus on
  large packages).
- `IMPL_REVIEW` runs under `reviewer` (opus) — adversarial code review.
- `VALIDATE` runs under `analyst` (sonnet) — synthesis of test/CI output.
- `INIT`/`SUBMIT_PR` run under `runner` (haiku) — state transitions.

Cost and latency follow naturally from per-phase model selection without
hardcoding decisions in skill scripts.

## Architecture

```
phase_agent._build_options(phase, state_dict)
    │
    ├─► AUTOPILOT_PHASE_MODEL_OVERRIDE? ─► options["model"] = override
    │   (operator override, system_prompt left to harness)
    │
    └─► coordination_bridge.try_resolve_archetype_for_phase(phase, signals)
            │
            ▼ HTTP POST /archetypes/resolve_for_phase
        coordination_api → agents_config.resolve_archetype_for_phase
            │
            ▼ uses archetypes.yaml → phase_mapping
        ResolvedArchetype { model, system_prompt, archetype, reasons[] }
            │
            └─► options["model"], options["system_prompt"] set;
                state_dict["_resolved_archetype"] recorded;
                make_phase_callback propagates → LoopState.phase_archetype
```

The coordinator is the authoritative source of phase mappings. Skills are
pure clients of the resolution endpoint via the `coordination_bridge`
helper.

## The 13-Phase Default Mapping

Defined in `agent-coordinator/archetypes.yaml` under `phase_mapping`:

| Phase | Archetype | Default model | Signals consulted |
|---|---|---|---|
| `INIT` | `runner` | haiku | (none) |
| `PLAN` | `architect` | opus | `capabilities_touched` |
| `PLAN_ITERATE` | `architect` | opus | `capabilities_touched`, `iteration_count` |
| `PLAN_REVIEW` | `reviewer` | opus | `proposal_loc`, `capabilities_touched` |
| `PLAN_FIX` | `architect` | opus | `findings_severity`, `findings_count` |
| `IMPLEMENT` | `implementer` | sonnet (→ opus on escalation) | `loc_estimate`, `write_allow`, `dependencies`, `complexity` |
| `IMPL_ITERATE` | `implementer` | sonnet | `iteration_count`, `write_allow` |
| `IMPL_REVIEW` | `reviewer` | opus | `files_changed`, `lines_changed` |
| `IMPL_FIX` | `implementer` | sonnet | `findings_severity`, `findings_count` |
| `VALIDATE` | `analyst` | sonnet | `test_count`, `suite_duration` |
| `VAL_REVIEW` | `reviewer` | opus | `findings_severity` |
| `VAL_FIX` | `implementer` | sonnet | `findings_severity` |
| `SUBMIT_PR` | `runner` | haiku | (none) |

**Tuning the mapping**: Edit `agent-coordinator/archetypes.yaml` and
restart the coordinator. No code changes required. The schema is validated
on load (`schema_version: 2`); a `phase_mapping` entry referencing an
undefined archetype raises `ValueError` at coordinator startup.

## Operator Override

Force specific models for specific phases via the
`AUTOPILOT_PHASE_MODEL_OVERRIDE` env var. Format:
`<PHASE>=<model>[,<PHASE>=<model>]*`.

```bash
# Run PLAN under opus and IMPL_REVIEW under sonnet for the rest of the session
export AUTOPILOT_PHASE_MODEL_OVERRIDE="PLAN=opus,IMPL_REVIEW=sonnet"

# Force everything to haiku for a cost dry-run
export AUTOPILOT_PHASE_MODEL_OVERRIDE="PLAN=haiku,PLAN_ITERATE=haiku,PLAN_REVIEW=haiku,PLAN_FIX=haiku,IMPLEMENT=haiku,IMPL_ITERATE=haiku,IMPL_REVIEW=haiku,IMPL_FIX=haiku,VALIDATE=haiku,VAL_REVIEW=haiku,VAL_FIX=haiku"
```

**Override semantics**:
- Override takes precedence over the resolved archetype's model.
- Override sets `options["model"]` only — `options["system_prompt"]` is left
  to the harness default. This keeps override behavior predictable: the
  operator chose the model, not the persona.
- Unknown phase names are warned and skipped (typo protection).
- Unknown model names pass through (validated downstream by the harness).

## Failure Mode

If the coordinator endpoint is unreachable or returns a non-200 status, the
bridge helper `try_resolve_archetype_for_phase` returns `None` and emits a
structured `WARNING` log. The autopilot:

1. Dispatches the phase with the harness default model (no `model` /
   `system_prompt` injection).
2. Records `LoopState.phase_archetype = None` for that phase.
3. Continues normally — the phase still runs.

Operator mitigation:
- Investigate coordinator availability (check `/health`, container logs).
- As a temporary mitigation, set `AUTOPILOT_PHASE_MODEL_OVERRIDE` to force
  models for the affected phases.

## Observability

- `LoopState.phase_archetype` (schema bumped 2 → 3) is persisted in
  `openspec/changes/<change-id>/loop-state.json` after every phase
  transition. v2 snapshots load forward with `phase_archetype = None`.
- `POST /status/report` accepts `phase_archetype` in the request body and
  forwards it through the `coordinator_status` event bus context dict.
  Subscribers see `{phase: "PLAN", phase_archetype: "architect", ...}`
  in the event payload.
- The coordinator audit trail records every successful resolution with
  `operation = "resolve_archetype_for_phase"` and the resolved phase +
  archetype + model. Query via `GET /audit?operation=resolve_archetype_for_phase`.

## API Reference

### `POST /archetypes/resolve_for_phase`

**Headers**: `X-API-Key: <key>` (required).

**Request body**:
```json
{
  "phase": "PLAN",
  "signals": {"capabilities_touched": 3}
}
```

**200 response**:
```json
{
  "model": "opus",
  "system_prompt": "You are a software architect. ...",
  "archetype": "architect",
  "reasons": [
    "phase=PLAN maps to archetype=architect",
    "no escalation triggered"
  ]
}
```

**Error responses**:
- `400` — malformed body (missing `phase`, non-dict `signals`).
- `401` — missing or invalid `X-API-Key`.
- `404` — phase not in `phase_mapping`.
- `500` — archetype configuration error (e.g., `phase_mapping` references
  an undefined archetype).

Full OpenAPI 3.1 contract:
`openspec/changes/add-per-phase-archetype-resolution/contracts/openapi/v1.yaml`.

### Skills bridge helper

```python
from coordination_bridge import try_resolve_archetype_for_phase

resolved = try_resolve_archetype_for_phase(
    phase="PLAN",
    signals={"capabilities_touched": 3},
)
# returns dict on 200, None on failure (logs WARNING)
```

## Deferred Items — Closed by `wire-autopilot-phase-subagents`

D-1 and D-2 from the original change are now closed by
`openspec/changes/wire-autopilot-phase-subagents/` (planned 2026-05-05,
landed 2026-05-07):

- **D-1 closed**: `agent_sessions.phase_archetype TEXT` column added in
  migration `023_add_phase_archetype.sql`, with a `CHECK` constraint
  enforcing the 5-value enum at the DB layer. The `discover_agents()`
  RPC returns `phase_archetype` in JSONB; `agent_heartbeat()` accepts
  optional `p_phase_archetype` with `COALESCE` semantics so older
  callers continue to work.
- **D-2 closed**: `report_status.py` reads `state.phase_archetype` from
  `loop-state.json` and includes it in `POST /status/report` (with
  client-side enum validation that drops invalid values). INIT and
  SUBMIT_PR archetype recording wired via
  `autopilot._resolve_phase_archetype_for_state_only()`.

## Production-path execution diagram

```
┌──── orchestrator agent (SKILL.md driven) ────┐
│                                                │
│  for each non-terminal phase:                  │
│    1. runner.py build-dispatch                 │
│       → folds system_prompt with separator     │
│       → writes .phase-resolution-cache.json    │
│       → returns JSON {prompt, model, ...}      │
│                                                │
│    2. Agent(prompt=..., model=...,             │
│             isolation=...)                     │
│       → harness dispatches with archetype model│
│       → returns (outcome, handoff_id)          │
│                                                │
│    3. runner.py apply-outcome                  │
│       → replay rule first; else validate cache │
│       → updates loop-state.json                │
│       → atomically deletes cache               │
│                                                │
│  on Stop hook:                                 │
│    report_status.py reads loop-state.json      │
│      → POSTs phase_archetype to coordinator    │
│      → DiscoveryService persists in            │
│        agent_sessions row                      │
│                                                │
└────────────────────────────────────────────────┘
```

## Phase-by-phase dispatch matrix

| Phase | Sub-agent dispatch? | Archetype recorded? |
|---|---|---|
| `INIT` | No (state-only) | Yes — `runner` |
| `PLAN` | No (delegated to `/plan-feature`) | Yes — `architect` |
| `PLAN_ITERATE`, `PLAN_REVIEW` | **Yes** (Agent block) | Yes |
| `PLAN_FIX` | No (convergence-loop) | Inherited from PLAN_REVIEW |
| `IMPLEMENT` | **Yes** with `isolation="worktree"` | Yes |
| `IMPL_ITERATE`, `IMPL_REVIEW` | **Yes** | Yes |
| `IMPL_FIX` | No (convergence-loop) | Inherited from IMPL_REVIEW |
| `VALIDATE`, `VAL_REVIEW` (when enabled) | **Yes** | Yes |
| `VAL_FIX` | No (convergence-loop) | Inherited from VAL_REVIEW |
| `SUBMIT_PR` | No (state-only) | Yes — `runner` |

Total dispatching phases: 7 of 13.

## Inline fallback

When the coordinator is unreachable OR the harness `Agent(...)` tool is
not available, autopilot falls through to the existing prose path:
invoke the slash-command skill inline. `LoopState.phase_archetype` is
recorded as `None` for affected phases; a structured warning is logged.
This is the documented and tested behavior — see spec scenarios
"Coordinator unreachable, autopilot continues" and "Harness Agent tool
not exposed, fallback to inline path".

## Manual rollout cross-check

After a real autopilot run completes, validate the archetype mapping
was applied by counting model calls in the coordinator audit log:

```bash
python3 skills/autopilot/scripts/audit_log_validator.py \
    --audit-log <path-to-coordinator-audit.jsonl> \
    --change-id <your-change-id> \
    [--archetypes-yaml agent-coordinator/archetypes.yaml]
```

The validator reads `loop-state.json`, derives the expected
(model → count) distribution from `phase_mapping`, and compares against
the audit log's actual model counts. Exit 0 = match, 1 = mismatch
(detailed findings on stdout), 2 = file not found.

## Token-budget CI gate

Folding `system_prompt` into the per-phase task prompt risks token-limit
pressure for IMPL_REVIEW (large change context). The CI gate at
`skills/autopilot/scripts/token_budget_check.py` runs over all 7
sub-agent-dispatching phases:

- **fails** (exit 1) if any phase exceeds **75%** of the resolved model's
  context window
- **warns** (exit 0 with stderr) at 60-75%
- **passes silently** below 60%

Wired into `wp-integration`'s verification block in `work-packages.yaml`.

## Cache file lifecycle

`.phase-resolution-cache.json` is the single shared scratch state
introduced by this design:

1. **Write**: `build_phase_dispatch_kwargs` writes atomically via
   `os.replace(tmp, final)`.
2. **Read**: `apply_phase_outcome` validates `change_id`, `phase`,
   `sha256` checksum.
3. **Delete**: on successful state write, the cache is deleted.
4. **Replay**: a second call with the same `(change_id, phase, outcome,
   handoff_id)` detects replay via `last_handoff_id` match and skips
   cache validation — the missing cache (deleted by the first call)
   is expected.

The cache path is in `.gitignore` and is per-change, never committed.
