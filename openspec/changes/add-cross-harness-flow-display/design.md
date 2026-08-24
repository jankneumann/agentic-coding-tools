# Design: Cross-harness session flow display

## What zoetrope proves, and what we keep

Zoetrope's architecture rests on one invariant worth adopting verbatim:
the session model is a pure function of the set of facts folded into it,
never of their arrival order — folds are idempotent and commutative, so
seeking rebuilds state from `facts[0..playhead]` and reaches exactly the
state that playing there would have. It also separates two clocks:
content time (transcript timestamps, governs state) and presentation time
(playback, governs animation only). Both carry over unchanged.

What we replace is its input assumption. Zoetrope reads local Claude Code
JSONL and is provably network-free. Our sessions span seven harnesses and
ephemeral cloud containers, so the local filesystem cannot be the only
fact source. The generalization: keep the fold, swap the transport.

## Two capture paths, one fact schema

```
harness session
   │
   ├─ live path ────────────────────────────────┐
   │   Stop/SubagentStop hook                   │
   │   → adapter.normalize_session()            │
   │   → sanitize → Langfuse observations       ▼
   │     (as_type=agent per turn,          Langfuse project
   │      as_type=tool children,           (durable, cross-machine)
   │      session_id + harness tag)             │
   │                                            │
   └─ capture path ─────────────────────────┐   │
       collect-transcripts adapters         │   │
       → sanitize → NormalizedEvent JSONL   │   │
         <transcripts dir>/<date>/<id>.jsonl▼   ▼
                                  agent-coordinator flow API
                                  (read-only; normalizes both
                                   sources to one fact stream)
                                                │
                                                ▼
                                        apps/flow-viz
                                        pure fold → graph + scrubber
```

`NormalizedEvent` (`skills/collect-transcripts/scripts/normalize.py`) is
the single fact type. The Langfuse hook's private `group_into_turns()`
parser is deleted; the hook imports the adapter for its harness and
derives turn grouping from the normalized stream. This closes the
two-schemas gap and makes every future adapter (e.g. Jules, later)
automatically hook-capable.

Schema additions (bump adapter schema versions, regenerate
`references/event-schema.md`):

- `parent_session_id: str | None` — set for subagent sessions.
- `spawned_by_tool_use_id: str | None` — the `tool_use_id` of the Agent /
  Task invocation that launched this session; the flow graph's
  agent-to-subagent edge.
- `agent_label: str | None` — display label when the harness provides one.

Absence of these fields degrades to a single-node session graph, so old
captures stay renderable.

## Harness coverage tiers

| Tier | Harnesses | Mechanism | Latency |
|---|---|---|---|
| Hooked | Claude Code CLI, cloud sessions | Stop/SubagentStop hook → Langfuse | per-turn |
| Batch | Codex, Antigravity, Grok, Pi | `collect-transcripts` run → JSONL + Langfuse batch uploader | post-hoc |
| Absent | Jules (no adapter) | out of scope; adding the adapter later grants both paths | — |

The batch uploader is a small addition to `collect-transcripts`: after
normalize+sanitize, optionally emit the same observation shape the hook
emits (`agent` turn / `tool` child, `session_id`, harness tag). Every
harness then lands in one Langfuse project with a uniform vocabulary; the
flow display filters by tag.

## Fold and graph model

Node kinds: session (root agent), subagent, tool aggregate. Edges:
`spawned_by_tool_use_id` (agent→subagent), `tool_use_id` pairing
(invocation→result closes a tool's pending state). Liveness follows
zoetrope's ruling: derive only where no ground truth exists — pending
tool_use blocks mean working; a spawn acknowledgment is a launch ack,
never a completion; terminal status comes only from explicit completion
facts, and time-derived liveness reverses when contradicted.

The fold is implemented once, client-side, in TypeScript
(`apps/flow-viz/src/lib/fold.ts`): the API serves ordered facts; the
frontend folds `facts[0..playhead]` for seeking, and appends for
live-follow. A property test replays shuffled fact orders and asserts
state equality — the executable form of the idempotent/commutative
contract.

## Flow API (read-only, on agent-coordinator)

- `GET /flows/sessions` — merged session summaries from the configured
  transcripts directory (via `SessionSummary`) and the Langfuse API
  (sessions by tag), deduplicated on `session_id`, paginated.
- `GET /flows/sessions/{session_id}/events` — ordered fact stream;
  `source=transcript|langfuse` resolved server-side, transcript preferred
  when both exist (full fidelity beats reconstructed observations).

The coordinator already holds harness session registration
(`/status/report`) and is the one service every harness can reach, which
makes it the natural credential custodian: Langfuse keys live in its
environment (OpenBao-seeded, per `bao-vault`), never on clients. Both
sources fail soft: an unreachable Langfuse or empty transcripts dir
yields an empty list plus a `source_warnings` field, mirroring
`skills/agent-metrics/scripts/query_metrics.py`. No write surface is
added, and the work-queue truth contract (loop-state is authoritative,
queue is a projection) is untouched — the flow display reads facts, not
queue state.

## Frontend: `apps/flow-viz`

A sibling of `apps/kanban-viz`, following its conventions: React + Vite +
Vitest, `src/{components,hooks,lib}`, optional Tauri shell. Kanban-viz
visualizes work-queue state; flow-viz visualizes session execution —
different data planes, so a separate app beats overloading one.

No graph library exists in the workspace yet. Start dependency-free: a
layered DAG layout computed in `lib/layout.ts` (agent tree depth × 
content-time order) rendered as SVG, which suits agent trees better than
force-direction anyway. Presentation-time effects (fade, camera) never
touch fold state. Reach for a dependency only if interaction outgrows
this.

## Sanitization and limits

Sanitize before any egress, at the capture edge, using the existing
chain: `collect-transcripts/scripts/sanitize_events.py` (which already
extends the `session-log` sanitizer to tool args/results). The Langfuse
SDK metadata limit (str values, 200 chars) means structured flow fields
travel in observation input/output and tags, never metadata. Prompt
bodies obey the existing truncation posture.

## Decisions

1. **This repo owns the capability.** Adapters, hook, and coordinator are
   canonical here; consumer repos (e.g. `agentic-content-analyzer`)
   receive the unified hook via skill mirroring and register it
   themselves. An earlier ACA-local draft proposed embedding the display
   in ACA's `web/` frontend; superseded by `apps/flow-viz` +
   coordinator API, which every repo's sessions can use.
2. **Langfuse is the cross-machine event bus, transcripts are ground
   truth.** Replay/seek needs full-fidelity ordered facts; Langfuse
   observations are a lossy projection good for liveness, aggregation,
   and sessions whose filesystems are gone. Prefer transcript when both
   exist.
3. **Fold client-side, normalize server-side.** Seeking re-folds locally
   without refetching; the server's job is source merging and credential
   custody.
4. **Host default reconciliation:** the hook's `:3050` default and
   consumer profiles' `:3100` self-hosted UI must converge; the hook
   reads `LANGFUSE_HOST` from the OpenBao-backed env script either way.
5. **Hook registration stays consumer-side and opt-in:** tracked script
   location, registered via the existing idempotent
   `install_stop_hook.py`, gated on `LANGFUSE_ENABLED`, never fails
   noisily. Mirror layouts differ per consumer — verify before wiring.

## Risks

- Langfuse observation → fact reverse-mapping is the only new lossy
  boundary; keep it thin and covered by a round-trip test (hook-emitted
  session fetched back must fold to the same graph topology).
- Transcript directories on cloud containers vanish at reclaim; the hook
  path is therefore the only reliable capture there — document that
  cloud sessions may be Langfuse-source-only.
- The coordinator is optional infrastructure in some setups; flow-viz
  must degrade to a purely local mode (open a transcript JSONL directly,
  zoetrope-style) when no coordinator is configured.
