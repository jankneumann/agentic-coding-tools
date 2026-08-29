# Tasks: Cross-harness session flow display

## Phase 0 — Spike (prove the fold)

- [ ] Run `collect-transcripts` normalize on one real Claude Code session
  and one Codex session; confirm transcript JSONL output shape.
- [ ] Prototype the TypeScript fold over a captured session; verify graph
  topology (agents, subagents via spawn linkage, tool pairing) and the
  shuffled-order equality property.

## Phase 1 — Unify the capture substrate

- [ ] Add `parent_session_id`, `spawned_by_tool_use_id`, `agent_label` to
  `NormalizedEvent`; bump adapter schema versions; regenerate
  `skills/collect-transcripts/references/event-schema.md`.
- [ ] Rewrite `skills/langfuse/scripts/langfuse_hook.py` to parse via
  `skills/collect-transcripts/scripts/adapters/claude_code_cli.py`;
  delete `group_into_turns()`; keep incremental cursor state and
  sanitizer.
- [ ] Reconcile self-hosted Langfuse host defaults (`:3050` vs `:3100`)
  across hook, consumer profiles, and docs.

## Phase 2 — Capture paths live

- [ ] Verify Stop and SubagentStop registration via
  `install_stop_hook.py` against each mirror layout; confirm silent
  no-op without `LANGFUSE_ENABLED`.
- [ ] Add the batch Langfuse uploader to `collect-transcripts` (same
  observation vocabulary: `agent` turn, `tool` child, `session_id`,
  harness tag), opt-in flag, `--dry-run` default.
- [ ] Round-trip test: hook-emitted session fetched from Langfuse folds
  to the same topology as its transcript.

## Phase 3 — Flow API on agent-coordinator

- [ ] `GET /flows/sessions` and `GET /flows/sessions/{id}/events` —
  transcript + Langfuse sources, transcript preferred, fail-soft
  `source_warnings`, pagination.
- [ ] Langfuse observation → fact reverse mapping with unit coverage.
- [ ] Generate `flow-fact` and `flow-session-summary` contract schemas
  from the dataclasses (see `contracts/README.md`).

## Phase 4 — apps/flow-viz

- [ ] Scaffold `apps/flow-viz` per kanban-viz conventions (React + Vite
  + Vitest; `src/{components,hooks,lib}`).
- [ ] `src/lib/fold.ts` with the shuffled-order property test;
  `src/lib/layout.ts` layered DAG layout (dependency-free SVG).
- [ ] Session list, graph view, scrubber timeline, live-follow polling;
  local mode that opens a transcript JSONL without a coordinator.

## Phase 5 — Validation and docs

- [ ] `openspec validate add-cross-harness-flow-display`; sync delta
  specs.
- [ ] Document the capability (docs index, harness coverage tiers,
  cloud-container Langfuse-only caveat, consumer-repo hook opt-in).
