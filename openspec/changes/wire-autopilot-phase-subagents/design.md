# Design — Wire Autopilot Per-Phase Sub-Agent Dispatch

This design covers the production wiring of `make_phase_callback` /
`run_phase_subagent` into autopilot's actual run path, plus the two
deferred coordinator surfaces (D-1, D-2) needed to make the wiring
observable.

## Context

The archived change `2026-05-03-add-per-phase-archetype-resolution`
shipped the resolution machinery but explicitly deferred end-to-end
wiring (`deferred-tasks.md` D-1, D-2). Today:

- `phase_agent.run_phase_subagent` returns `(outcome, handoff_id)` only,
  consuming the sub-agent transcript internally — but **no caller invokes
  it** in production.
- `make_phase_callback` produces a `(state) -> outcome` callback for
  autopilot's `run_loop`, but `run_loop` is itself never invoked from
  production code paths.
- SKILL.md prose tells the orchestrator agent to invoke slash commands
  inline; the orchestrator's session model and system prompt apply for
  the entire run.

This proposal provides the bridge from "designed" to "running."

## Goals

- **G1**: Every non-terminal autopilot phase actually dispatches with the
  archetype-resolved `model` and `system_prompt`.
- **G2**: `LoopState.phase_archetype` is non-null on the production path
  for every phase that successfully resolved an archetype.
- **G3**: `report_status.py` includes `phase_archetype` in `POST /status/report`
  so dashboards can correlate phase behavior with archetype.
- **G4**: `AgentInfo.phase_archetype` persists across heartbeats so
  `GET /discovery/agents` exposes which archetype each agent is running.
- **G5**: When the harness `Agent(...)` tool or coordinator is unavailable,
  fall back to today's prose path without crashing.

## Non-Goals

- **Migrating `/iterate-on-plan` and `/iterate-on-implementation` through
  `make_phase_callback`** — these slash-command skills already dispatch
  their own sub-agents internally, so wrapping them adds an indirection
  layer with no archetype benefit. Tracked as a possible future change.
- **Replacing `convergence_loop.py`'s vendor-CLI dispatch** — review
  phases (`PLAN_REVIEW`, `IMPL_REVIEW`, `VAL_REVIEW`) already have a CLI
  path that invokes opus on multiple vendors. The new wiring complements
  it, doesn't replace it.
- **Building a Python CLI adapter for `Agent()`** — rejected at
  Gate 1 (Approach C). Not in scope.

## Decisions

### D1: SKILL.md prose dispatches the harness `Agent(...)` tool

**What**: Each non-terminal phase section in `skills/autopilot/SKILL.md`
gets an explicit dispatch block of the form:

```
1. Run `python3 ... build_phase_dispatch_kwargs.py --phase IMPLEMENT --change-id <id>`
2. Parse the JSON output. Capture `prompt`, `model`, `system_prompt`, `isolation`.
3. Call `Agent(prompt=<system_prompt>\n\n<prompt>, model=<model>, isolation=<isolation>)`.
4. Parse the agent's last message for `(outcome, handoff_id)` per the protocol in
   `phase_agent._validate_result`.
5. Update LoopState via `python3 ... apply_phase_outcome.py --change-id <id>
   --phase IMPLEMENT --outcome <outcome> --handoff-id <handoff_id>`.
```

**Why**: Matches the established repo convention. Every parallel-execution
skill in this codebase has SKILL.md instruct the orchestrator to call
`Agent(...)` directly; there is no Python harness adapter library. User
explicitly chose this in discovery.

**Why not D1-alt (Python `subprocess.run('claude --print …')`)**: Would
introduce a second pattern. Vendor CLIs are not always installed, and
worktree isolation primitives don't compose with subprocess calls.
Rejected at Gate 1 as Approach C.

### D2: `system_prompt` is folded into `prompt` text, not passed as a separate option

**What**: The harness `Agent(...)` tool surface in this codebase does not
expose a `system_prompt` parameter. The dispatch block prepends the
resolved archetype's `system_prompt` to the per-phase task prompt:

```
prompt = f"{system_prompt}\n\n---\n\n{phase_prompt}"
```

**Why**: Verified by inspecting `Agent` tool schemas: the only sub-agent
options are `prompt`, `subagent_type`, `model`, `isolation`,
`run_in_background`. There is no `system_prompt` parameter. Folding
preserves archetype semantics without requiring harness changes.

**Why not D2-alt (push for harness `system_prompt` support)**: Out of
scope for skills work; would require an Anthropic harness change for
trivial gain. The folded approach is functionally equivalent.

### D3: `build_phase_dispatch_kwargs` returns a dict, not invokes Agent itself

**What**: New helper in `skills/autopilot/scripts/phase_agent.py`:

```python
def build_phase_dispatch_kwargs(
    phase: str,
    state_dict: dict[str, Any],
    incoming_handoff: PhaseRecord,
    artifacts_manifest: list[str] | None = None,
) -> dict[str, Any]:
    """Return {prompt, model, system_prompt, isolation} for the orchestrator
    to unpack into Agent(...). Pure function — no side effects."""
```

**Why**: SKILL.md prose can't directly call `run_phase_subagent` (which
expects a Python callable). The orchestrator agent reads the dict from
JSON, unpacks it into the Agent tool call, then writes the outcome
back via a separate apply-script. This keeps Python and prose layers
each doing what they do best.

**Why not D3-alt (in-process callable injected into autopilot.py)**:
Would require a long-running Python process that the orchestrator agent
streams into — incompatible with the prompt-and-tool-call shape of
the harness.

### D4: `LoopState.phase_archetype` writes happen via `apply_phase_outcome.py`, not in-process

**What**: A second helper script wraps `make_phase_callback`'s state-update
protocol:

```bash
python3 .../apply_phase_outcome.py \
  --change-id <id> --phase IMPLEMENT \
  --outcome continue --handoff-id <handoff>
```

It loads `loop-state.json`, runs the same logic `make_phase_callback`
runs (set `last_handoff_id`, append to `handoff_ids`, propagate
`_resolved_archetype` from a side-channel cache file), and saves.

**Why**: Mirrors the in-process logic but works across the prose
boundary. The orchestrator can't hold Python state across tool calls,
so the state lives on disk.

**Cache file**: `build_phase_dispatch_kwargs.py` writes the resolved
archetype name to `openspec/changes/<id>/.phase-resolution-cache.json`
so `apply_phase_outcome.py` can pick it up for the LoopState write.
This is the only "shared scratch state" introduced and is documented
explicitly.

### D5: Inline fallback path

**What**: When `try_resolve_archetype_for_phase` returns `None` OR the
harness `Agent(...)` tool is not exposed in the current orchestrator
(tested by checking for the tool's presence in the system prompt),
SKILL.md falls through to the existing prose:

> If the dispatch block fails or no archetype is resolvable, run the
> existing inline path: invoke `/implement-feature <change-id>` (or the
> phase-appropriate slash command) directly.

`apply_phase_outcome.py` then writes `phase_archetype = None` for that
phase — already supported by schema v3.

**Why**: User chose "inline fallback" at discovery. Backward-compatible:
operators on minimal harnesses still get an autopilot run.

### D6: `report_status.py` reads `phase_archetype` from `loop-state.json`

**What**: Extend the existing `loop_state.json` read at
`agent-coordinator/scripts/report_status.py:97-100` to also pull
`phase_archetype`, then add it to the POST body at lines 118-128.

**Why**: D-2 deferred-task. Two-line change. The coordinator endpoint
already accepts the field per the archived change.

**Why not D6-alt (push from autopilot directly)**: `report_status.py`
is the established Stop-hook reporter; piggybacking on it avoids a new
HTTP client in the autopilot driver.

### D7: INIT phase archetype recording

**What**: Add `_resolve_phase_archetype_for_state_only(state, phase)` to
`autopilot.py`. Called at INIT entry; sets `state.phase_archetype` for
state-only phases that don't dispatch a sub-agent.

**Why**: D-2 deferred-task. The spec scenario "every non-terminal phase
has non-null `phase_archetype`" currently fails for INIT because INIT
bypasses `run_phase_subagent`. This closes that hole.

**Why not D7-alt (route INIT through `run_phase_subagent`)**: INIT is
state-only by design D13 (archived). Routing it would require restructuring
the dispatch table and would dispatch a sub-agent that does nothing.

### D8: AgentInfo schema migration via dedicated column

**What**: Migration `agent-coordinator/database/migrations/N_add_phase_archetype.sql`:

```sql
ALTER TABLE agent_sessions ADD COLUMN phase_archetype TEXT;
```

`AgentInfo` dataclass gets `phase_archetype: str | None = None`.
`DiscoveryService.heartbeat` accepts and persists. `GET /discovery/agents`
surfaces it in the response dict.

**Why**: D-1 deferred-task. The deferred-tasks doc identified two
options: dedicated column or `metadata JSONB` key. Dedicated column wins
because: (1) `phase_archetype` is queried for filtering ("show all
agents in `reviewer` archetype"), and JSONB key access is awkward in
SQL; (2) migrations are first-class in this repo (raw SQL files), so
adding one column is cheap; (3) JSONB usage in `metadata` is for free-form
keys, and `phase_archetype` is structured.

**Why not D8-alt (`metadata.phase_archetype` JSONB key)**: Slower queries,
weaker schema discoverability.

### D9: Two-phase rollout per scope (within Approach A)

Approach A is the chosen direction, but within it we sequence by
work-package dependency: `wp-contracts` first (schemas + migration),
then `wp-skills-autopilot` and `wp-coordinator-status-discovery` in
parallel, then `wp-integration` last. See `work-packages.yaml`.

## Architecture diagram

```
┌────────────────────── orchestrator agent (SKILL.md driven) ─────────────────┐
│                                                                              │
│   for each phase in [INIT → PLAN → … → SUBMIT_PR → DONE]:                    │
│     1. python3 build_phase_dispatch_kwargs.py --phase X --change-id Y        │
│        └─→ phase_agent.run_phase_subagent's prompt-and-options assembly      │
│        └─→ writes .phase-resolution-cache.json                               │
│        └─→ returns JSON {prompt, model, system_prompt, isolation}            │
│                                                                              │
│     2. orchestrator inlines the JSON values into:                            │
│        Agent(prompt=<system_prompt>\n\n<prompt>, model=..., isolation=...)   │
│        └─→ harness dispatches sub-agent with the resolved archetype model    │
│        └─→ sub-agent does the work, returns (outcome, handoff_id)            │
│                                                                              │
│     3. python3 apply_phase_outcome.py --phase X --outcome ... --handoff-id   │
│        └─→ updates loop-state.json: last_handoff_id, handoff_ids,            │
│            phase_archetype (from .phase-resolution-cache.json)               │
│                                                                              │
│   on Stop hook:                                                              │
│     report_status.py reads loop-state.json → POSTs {phase, phase_archetype}  │
│       to coordinator → DiscoveryService persists in agent_sessions row       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Affected components

| Component | File | Change |
|---|---|---|
| Skills autopilot | `skills/autopilot/scripts/phase_agent.py` | Add `build_phase_dispatch_kwargs`, `apply_phase_outcome` Python entry points |
| Skills autopilot | `skills/autopilot/scripts/runner.py` (NEW) | CLI entry points for the two new functions |
| Skills autopilot | `skills/autopilot/SKILL.md` | Replace inline-prose phase steps with explicit Agent() dispatch blocks; add D5 fallback |
| Skills autopilot | `skills/autopilot/scripts/autopilot.py` | Add `_resolve_phase_archetype_for_state_only` for INIT; minor — no run_loop changes |
| Coordinator | `agent-coordinator/scripts/report_status.py` | Read & POST `phase_archetype` |
| Coordinator | `agent-coordinator/src/discovery.py` | `AgentInfo.phase_archetype`; `heartbeat` accepts; API surfaces it |
| Coordinator | `agent-coordinator/src/coordination_api.py` | Heartbeat + discovery endpoint contract update |
| Migrations | `agent-coordinator/database/migrations/N_add_phase_archetype.sql` (NEW) | One ALTER TABLE statement |
| Tests | `skills/tests/autopilot/test_phase_dispatch_e2e.py` (NEW) | Mock-Agent end-to-end through one full loop |
| Tests | `agent-coordinator/tests/test_phase_archetype_persistence.py` (NEW) | Round-trip via heartbeat → discovery |

## Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Prompt-size bloat from system_prompt + task prompt + state JSON | Medium | Medium | `phase_token_meter` already tracks per-phase prompt tokens; CI check at 80% of model context window |
| Cache file `.phase-resolution-cache.json` goes stale across resumes | Low | Low | `apply_phase_outcome` validates cache phase matches its `--phase` arg; if mismatch, write `phase_archetype=None` and warn |
| Discovery service migration races with running agents | Low | Medium | Run migration before deploying coordinator update; `phase_archetype` defaults to NULL for existing rows |
| Orchestrator forgets to call `apply_phase_outcome` after `Agent()` | Medium | High | SKILL.md dispatch block makes it explicit step 3 of 3; e2e test asserts `last_handoff_id` updates after each phase |
| `system_prompt` folding hits a phase whose system prompt clobbers the task prompt's instructions | Low | Medium | Use `\n\n---\n\n` separator (clear visual + structural break); test renders the joined prompt and snapshot-asserts |

## Open questions

- **Q1**: Should `apply_phase_outcome.py` be idempotent — i.e. safe to
  call twice with the same handoff-id? Probably yes (orchestrator might
  retry on transient errors). Will validate during wp-skills-autopilot.
- **Q2**: Should the cache file include a checksum so stale caches
  (different change-id) are detected automatically? Likely yes; default
  to fail-closed (write `phase_archetype=None`) when checksum mismatches.
- **Q3**: Should the e2e test assert against an in-process FastAPI
  TestClient (per the archived test pattern at `test_phase_archetype_e2e.py`)
  or against the live coordinator? Default: in-process for hermeticity.
