# Follow-up: autopilot archetype and apply-outcome post-merge tasks

> Parent change: `fix-autopilot-archetype-and-apply-outcome` (archived 2026-09-08)
> Migrated by: `/cleanup-feature` archive sweep, 2026-09-08

## Why

The parent change fixed two autopilot contract violations (VALIDATE mapping to the
read-only `analyst` archetype; an IMPLEMENT sub-agent transitioning `current_phase`
through `apply-outcome`). Its behavioural fixes are merged: `write_capable` is a
declared field on every archetype in `agent-coordinator/archetypes.yaml`, and the
`skill-workflow` capability carries the four requirements that codify the contract.

Three tasks in the parent were labelled **out of scope for the change, to be done
after merge**. They are real work, and the archive sweep would otherwise drop them
silently — which the cleanup contract forbids.

They are collected here rather than left as unchecked boxes in an archived change,
where nothing would ever surface them again.

## What Changes

- **Documentation propagation.** `docs/parallel-agentic-development.md` still predates
  the parent change. It does not describe the dispatch-prompt prohibitions, nor the
  `write_capable` archetype-field convention that the resolver now fails fast on.
  A contributor reading the guide today gets a stale model of the dispatch contract.
- **Scoping decision — loop-state structural enforcement.** Decide whether the
  `loop-state.json` contract needs enforcement beyond the Layer B+C prompt-level
  prohibitions the parent shipped (filesystem permissions, git hooks). The parent
  deliberately deferred this pending empirical evidence that prompt enforcement is
  insufficient. This change records the decision and, if the answer is yes, opens
  the successor proposal.
- **Scoping decision — harness silent-no-op detection.** Decide whether the
  `Agent(isolation=worktree)`-commits-to-orchestrator-branch failure mode (recorded in
  `memory/feedback_harness_worktree_silent_noop.md` and named in the parent's
  "Out of Scope") warrants its own change.

## Impact

- Docs: `docs/parallel-agentic-development.md`
- Specs: none. See `.openspec.yaml` — the requirements already merged with the parent.
- Two scoping decisions that may each spawn a successor proposal.

## Out of Scope

- Re-litigating the parent's Layer A–D causal analysis. It is settled and archived.
- Any change to `apply-outcome` semantics or the autopilot state machine.
