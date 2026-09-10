# Durable State Artifacts

This guide is the canonical inventory and rehydration order for durable orchestration state. Authority is question-scoped: no single artifact answers every question, and a transport record never overrides the file that owns execution truth for its scope.

## Artifact inventory

| Artifact class | Path / holder | Canonical writer | Authority | Consumers | Missing or stale behavior |
|---|---|---|---|---|---|
| **Per-change loop state** | `openspec/changes/<change-id>/loop-state.json`, held in the change feature worktree and branch | Autopilot `save_state()` and canonical `runner.py` state commands | Authoritative for that run's phase, iteration, package status, gates, and transition history | Autopilot resume, supervisor result checks, and one-way queue projection | Absence is valid before the run starts. If a handoff claims prior progress, absence, invalid JSON, schema mismatch, or change-id mismatch is an inconsistency: stop automatic advancement and report degradation. Never reconstruct it from advisory artifacts or queue rows. |
| **Roadmap checkpoint** | `openspec/roadmaps/<roadmap-id>/checkpoint.json`, held in the roadmap workspace and branch | `roadmap-runtime` checkpoint helpers through Autopilot Roadmap | Authoritative for roadmap execution position, active item, terminal sets, and recorded roadmap gates | Autopilot Roadmap resume and supervisor ready/blocked/in-flight derivation | Absence is valid for a never-started roadmap. If advisory state claims prior progress, a missing, invalid, or identity-mismatched checkpoint is an inconsistency. Never rebuild progress or terminal sets from learnings or handoffs. |
| **Roadmap learning entry** | `openspec/roadmaps/<roadmap-id>/learnings/<item-id>.md`, held beside the roadmap; `learning-log.md` is its index | `roadmap-runtime` learning writer after an item reaches a terminal phase | Advisory history: decisions, blockers, deviations, recommendations, and vendor evidence; never resumable execution state | Later item planning, roadmap retrospection, and supervisor context assembly | Missing learning reduces context but does not change readiness. A stale or conflicting learning is reported and ignored for execution decisions; checkpoint and loop state win. |
| **Phase record** | Phase entries in `openspec/changes/<change-id>/session-log.md`, held on the change branch | `session-log` `PhaseRecord.write_both()` appends and sanitizes the tracked record | Durable historical rationale and evidence for a completed workflow phase; not current phase or roadmap position | Later phase context, decision-index generation, validation, and reviewers | Missing records are a context/evidence gap, not permission to infer execution state. Conflicts with checkpoint or loop state are reported; canonical execution state wins. |
| **Handoff document** | Coordinator `handoff_documents`; local fallback `openspec/changes/<change-id>/handoffs/<phase>-<N>.json`; supervisor mirror `openspec/supervise/supervisor-record.json` | `PhaseRecord.write_both()` through the coordination bridge, or supervise's deterministic record writer and bridge call | Bootstrap locator and bounded cross-session context only; not execution authority | Fresh sessions, downstream phases, and supervisor bootstrap | Coordinator loss uses the tracked fallback or mirror and is reported as degraded. Stale handoffs may be ignored. A newer advisory timestamp never overrides canonical state. |

The coordinator work queue is a derived projection, not a sixth authority class. Its one-way contract is documented in [Work-Queue Truth / Projection](work-queue-truth-projection.md).

## Canonical rehydration order

The first step locates candidate work. Later steps verify whether that work is actually active before advisory context is applied.

1. Bootstrap locator — select the newest valid supervisor handoff or tracked supervisor mirror only to identify candidate roadmaps and changes.
2. Roadmap definition — load and validate each named `roadmap.yaml`; reject missing or mismatched identities.
3. Roadmap execution state — load and validate `checkpoint.json` before using claimed roadmap progress. Its absence is valid for a never-started roadmap, but conflicts with a locator that claims prior progress.
4. Change execution state — load and validate each claimed active change's `loop-state.json`, including change identity and verified branch/worktree provenance.
5. Learning context — load direct-dependency learnings and the bounded recent learning window only after roadmap and change truth are known.
6. Phase history — read `session-log.md` phase records for decisions, evidence, and trade-offs; do not derive the current phase from them.
7. Handoff context — apply bounded next steps from the newest relevant handoff only when they agree with steps 2–4.
8. Rebuild projections — re-derive coordinator queue and display projections from canonical state; never reverse that edge.

## Missing and conflicting state

- First-run absence is not corruption. The canonical writer creates the checkpoint or loop state before recording progress.
- Claimed prior progress without the corresponding canonical artifact is a fail-loud inconsistency. Park automatic advancement and name the missing path.
- Valid canonical state wins over phase records, learnings, handoffs, and queue projections, even when the advisory artifact has a later timestamp; a newer advisory timestamp never overrides canonical state.
- Invalid JSON, schema/version mismatch, identity mismatch, or verified-path mismatch is not repaired from advisory content. Preserve the evidence and require the owning writer or operator to reconcile it.
- When two advisory records disagree, choose the applicable newest valid record only for bootstrap or context, then repeat canonical verification.

## Writer ordering

Writers persist the authoritative artifact before emitting dependent records or projections. Autopilot saves loop state before queue projection. Autopilot Roadmap saves its checkpoint before publishing progress. `PhaseRecord.write_both()` appends and sanitizes the tracked phase record, attempts the coordinator handoff with a tracked local fallback when transport is unavailable, and then regenerates the derived capability decision index. These rules make interruption recoverable without promoting derived state.

## Skill contract

Skills keep phase-specific commands, schemas, and gate behavior locally. They reference this canonical guide for shared holder, writer, authority, missing/stale, and rehydration semantics. If runtime behavior and this guide disagree, stop and fix the guide or implementation together; do not add another local restatement.
