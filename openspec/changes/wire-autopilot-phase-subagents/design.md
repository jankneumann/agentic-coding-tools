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

### D2: `system_prompt` is folded into `prompt` text with a fixed `\n\n---\n\n` separator

**What**: The harness `Agent(...)` tool surface in this codebase does not
expose a `system_prompt` parameter. The dispatch block prepends the
resolved archetype's `system_prompt` to the per-phase task prompt with
a fixed separator:

```
SEPARATOR = "\n\n---\n\n"
prompt = f"{system_prompt}{SEPARATOR}{phase_prompt}"
```

The separator is **fixed**, not parameterized — every phase uses the
same separator, every dispatch in this skill uses it, and it is
asserted verbatim in the spec scenario.

**Why**: Verified by inspecting `Agent` tool schemas: the only sub-agent
options are `prompt`, `subagent_type`, `model`, `isolation`,
`run_in_background`. There is no `system_prompt` parameter. Folding
preserves archetype semantics without requiring harness changes.

**Why this separator string**: `\n\n---\n\n` is the standard markdown
horizontal-rule on its own line, surrounded by blank lines. It is
visually unmistakable in rendered output and parsable by any markdown
processor as a section break. Three alternatives were considered and
rejected:

- `\n---\n` (single-newline rule): renders as a horizontal rule but
  lacks the surrounding paragraph separation, so adjacent prose can
  visually run together in some renderers.
- `<!-- SYSTEM_PROMPT_END -->`: HTML comment is hidden in rendered
  output, which is *worse* than visible — silent boundary, easier to
  misread.
- A unique sentinel like `==SYSTEM-END==`: invented strings have no
  shared interpretation; using existing markdown semantics makes the
  fold a normal section break that any reader (human or model)
  immediately recognizes.

**Separator clash mitigation**: If a phase prompt happens to contain
the literal string `\n\n---\n\n`, the joined prompt has two ambiguous
section breaks. Test 2.9 covers this case explicitly with a phase
prompt containing `---` and asserts (a) the separator after the
system prompt is exactly the SEPARATOR constant string and (b)
key task-instruction keywords from `phase_prompt` survive the fold
unchanged. This is asserted via regex (not just substring presence).

**Why not D2-alt (push for harness `system_prompt` support)**: Out of
scope for skills work; would require an Anthropic harness change for
trivial gain. The folded approach is functionally equivalent.

### D3: `build_phase_dispatch_kwargs(phase, change_id)` returns a dict, not invokes Agent itself

**What**: New helper in `skills/autopilot/scripts/phase_agent.py` exposed
through `runner.py`:

```python
def build_phase_dispatch_kwargs(phase: str, change_id: str) -> dict[str, Any]:
    """Return {prompt, model, system_prompt, isolation, archetype} for the
    orchestrator to unpack into Agent(...). Side effects: writes
    .phase-resolution-cache.json so apply_phase_outcome can pick up the
    resolved archetype later."""
```

The implementation reads `loop-state.json` for `state_dict`, constructs
a bootstrap incoming `PhaseRecord` (or hydrates one from
`state.last_handoff_id` if present), and computes the standard prompt
+ options scaffold via the existing `_build_options` and `_build_prompt`
internals.

**Why this signature, not the four-parameter `run_phase_subagent` shape**:
SKILL.md prose (the caller) only knows `phase` and `change_id`. The
remaining inputs (state, incoming handoff, artifacts manifest) are
recoverable from disk: `loop-state.json` is at a deterministic path
under the change, and the incoming handoff is keyed by
`state.last_handoff_id`. Threading those through the CLI as JSON args
would force the prose layer to know about LoopState internals — exactly
the boundary D3 is trying to keep clean. Earlier drafts of this design
showed the four-parameter signature; that was a copy of the in-process
`run_phase_subagent` API and is not appropriate for the prose-Python
boundary.

**Why not D3-alt (in-process callable injected into autopilot.py)**:
Would require a long-running Python process that the orchestrator agent
streams into — incompatible with the prompt-and-tool-call shape of
the harness.

**Note on D13**: D13 referenced in this design is from the archived
change `2026-05-03-add-per-phase-archetype-resolution` (see its
`design.md`). It established that `INIT` and `SUBMIT_PR` are state-only
phases that record an archetype but do not dispatch a sub-agent. This
proposal preserves that decision and closes the spec-scenario gap that
the archived change deferred to D-2.

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
`phase_archetype` from the cache file), and saves.

**Why**: Mirrors the in-process logic but works across the prose
boundary. The orchestrator can't hold Python state across tool calls,
so the state lives on disk.

**Why two state mechanisms (`state_dict["_resolved_archetype"]` AND
`.phase-resolution-cache.json`)**: The `_resolved_archetype` key in
`state_dict` is the **in-process** path used by `make_phase_callback`
(written by `_build_options`, read in `make_phase_callback`'s closure,
propagated to `LoopState.phase_archetype`). That path was built first
and the unit tests cover it. It is **not used on the production prose
path** — production goes through `build_phase_dispatch_kwargs` (which
also writes to `_resolved_archetype` for backward-compat with the
unit-tested helpers) AND writes to the on-disk cache so
`apply_phase_outcome` (a different process invocation) can read it
later. The two mechanisms are not redundant; they serve the in-process
test path and the cross-process production path respectively.

**Cache file contract** (resolves Open Question Q2):

- **Path**: `openspec/changes/<change-id>/.phase-resolution-cache.json`.
- **Path validation**: `change-id` MUST match `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`
  (the same pattern OpenSpec already enforces on change identifiers).
  `build_phase_dispatch_kwargs` rejects any value that fails this regex
  with a `ValueError` — no path traversal possible because `..` and `/`
  are excluded by the character class. The resolved path is verified
  with `pathlib.Path.resolve()` and confirmed to live under
  `openspec/changes/`; any escape raises.
- **Schema**:
  ```json
  {
    "schema_version": 1,
    "change_id": "<change-id>",
    "phase": "<phase-name>",
    "archetype": "<archetype-name | null>",
    "checksum": "<sha256 of change_id + phase + archetype>"
  }
  ```
- **Atomic write**: Use `os.replace(tmp_path, final_path)` after writing
  to a sibling temp file. `os.replace` is atomic on POSIX and preserves
  visibility semantics on macOS/Linux.
- **Lifecycle**:
  - Created/overwritten by `build_phase_dispatch_kwargs`.
  - Read by `apply_phase_outcome` at the same path.
  - **Deleted** by `apply_phase_outcome` after a successful state write
    (cleanup-on-success). On failure, the cache stays so a manual retry
    can pick up where it left off.
- **Validation in `apply_phase_outcome`** (resolves implicit ambiguity
  flagged by review):
  - Parse the JSON. On parse error → write `phase_archetype=None` and
    log a structured warning; do NOT raise.
  - Verify `cache.change_id == --change-id arg` (string equality).
    On mismatch → write `phase_archetype=None`, warn, do not raise.
  - Verify `cache.phase == --phase arg` (string equality). On mismatch
    → same handling.
  - Verify the SHA-256 checksum. On mismatch → same handling.
  - On any successful path, write `phase_archetype = cache.archetype`
    to `loop-state.json` (which may be `null` legitimately when the
    bridge could not resolve).
- **gitignore**: `openspec/changes/*/.phase-resolution-cache.json` is
  added to the project's `.gitignore` as a one-line addition. The
  cache is per-run scratch state and never belongs in commits.
- **Multi-agent safety**: The cache is per-change. Two agents working
  on the same change-id (highly unusual — typically one autopilot
  run per change at a time) would share the cache; the second agent's
  `build-dispatch` would clobber the first's, but each `apply-outcome`
  validates change_id+phase+checksum so a clobbered cache becomes a
  null write rather than a wrong write.

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

## Resolved questions (formerly open)

- **Q1 — `apply_phase_outcome.py` idempotency**: **Resolved as MUST be
  idempotent**. Safe to call twice with the same `(change_id, phase,
  outcome, handoff_id)`. Verified by task 2.3. Implementation reads
  `loop-state.json`, checks if `last_handoff_id == handoff_id` and if
  `handoff_id` already appears in `handoff_ids`, and skips the append
  if both are true. The `phase_archetype` write is deterministic and
  rerunnable.
- **Q2 — cache file checksum**: **Resolved as MUST validate**. The
  cache schema includes a SHA-256 checksum over `change_id + phase +
  archetype` (see D4 above). On any mismatch (including missing
  checksum, parse error, change-id mismatch, or phase mismatch),
  `apply_phase_outcome` writes `phase_archetype=None` and logs a
  structured warning rather than raising.
- **Q3 — e2e test harness**: **Resolved as in-process FastAPI
  TestClient**, matching the archived `test_phase_archetype_e2e.py`
  pattern. Hermetic, no external coordinator dependency, runs in CI
  without docker. The mocked `Agent(...)` runner returns canned
  `(outcome, handoff_id)` tuples and writes the cache file as a real
  `build_phase_dispatch_kwargs` call would.

## Phase-by-phase dispatch matrix

The spec MODIFIED requirement lists 13 non-terminal phases. **Not all
13 dispatch a sub-agent** — some are state-only, some are skill-delegated,
some are convergence-loop-driven. This table is the canonical mapping
and is the source of truth for which phases SKILL.md MUST rewrite as
explicit `Agent(...)` dispatch blocks (per D1):

| Phase | Dispatch type | Archetype recorded? | SKILL.md change? |
|---|---|---|---|
| `INIT` | State-only (D7) | Yes (via `_resolve_phase_archetype_for_state_only`) | No — stays as state transition |
| `PLAN` | Skill-delegated | Yes (via `/plan-feature`'s own dispatch) | No — proposal-creation stays inline |
| `PLAN_ITERATE` | **Sub-agent dispatch** | Yes (via `make_phase_callback` flow) | **Yes — explicit Agent() block** |
| `PLAN_REVIEW` | **Sub-agent dispatch** | Yes | **Yes — explicit Agent() block** |
| `PLAN_FIX` | Convergence-loop-driven (no separate dispatch) | Yes (recorded for audit) | No — happens inside `convergence_loop.converge` |
| `IMPLEMENT` | **Sub-agent dispatch** with `isolation="worktree"` | Yes | **Yes — explicit Agent() block** |
| `IMPL_ITERATE` | **Sub-agent dispatch** | Yes | **Yes — explicit Agent() block** |
| `IMPL_REVIEW` | **Sub-agent dispatch** | Yes | **Yes — explicit Agent() block** |
| `IMPL_FIX` | Convergence-loop-driven | Yes (recorded for audit) | No — happens inside `convergence_loop.converge` |
| `VALIDATE` | **Sub-agent dispatch** | Yes | **Yes — explicit Agent() block** |
| `VAL_REVIEW` | **Sub-agent dispatch** (when enabled) | Yes | **Yes — explicit Agent() block** |
| `VAL_FIX` | Convergence-loop-driven | Yes (recorded for audit) | No — happens inside `convergence_loop.converge` |
| `SUBMIT_PR` | State-only (D7) | Yes (via `_resolve_phase_archetype_for_state_only`) | No — stays as state transition |

**Total SKILL.md rewrite count**: 7 phases get explicit `Agent(...)`
dispatch blocks (PLAN_ITERATE, PLAN_REVIEW, IMPLEMENT, IMPL_ITERATE,
IMPL_REVIEW, VALIDATE, VAL_REVIEW). Task 2.10's "rewrite each phase
block" refers to these 7. The remaining 6 phases (INIT, PLAN, PLAN_FIX,
IMPL_FIX, VAL_FIX, SUBMIT_PR) keep their existing prose but record
`phase_archetype` either via the state-only resolver (INIT, SUBMIT_PR)
or via the convergence loop's audit path (`*_FIX` phases).
