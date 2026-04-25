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

## Deferred Items

See `openspec/changes/add-per-phase-archetype-resolution/deferred-tasks.md`:
- **D-1**: Persist `phase_archetype` on the discovery agent record so
  `GET /discovery/agents` returns it. Today the value flows through the
  event bus only.
- **D-2**: Wire `INIT` archetype recording (currently a state-only
  transition that bypasses `run_phase_subagent`) and have
  `agent-coordinator/scripts/report_status.py` include
  `phase_archetype` in its `POST /status/report` payload by reading
  `state.phase_archetype` from `loop-state.json`.

Both are additive follow-ups; the core feature is functional today.
