# Using `/supervise`

`/supervise` is the conversational entry point for turning requests and discovery findings into tracked roadmap work. Use it in an agent session with this repository open. The supervisor can organize work, present decisions, and dispatch approved roadmap items; implementation runs in isolated worker worktrees.

## Quick start

| You want to… | Ask the agent to run… | What to expect |
|---|---|---|
| Add a request | `/supervise intake "Add a way to inspect stalled dispatches"` | It finds existing tracked work or creates an OpenSpec change or proposal and places it in a roadmap. It reports the result and any dependency. |
| See what needs attention | `/supervise cycle` | It rehydrates current state, discovers and ranks candidate work, then shows a digest. It stops at decisions; it does not launch implementation. |
| Preview a cycle without writes | `/supervise cycle --dry-run` | It reads existing discovery reports and repository state without refreshing sensors or recording decisions. Missing current reports appear as degraded. |
| Reassess an unchanged repository | `/supervise cycle --force` | It bypasses the unchanged-state early exit. Existing complete scoring caches can still be reused. |
| Run an approved roadmap | `/supervise execute openspec/roadmaps/<roadmap-id>` | It checks recorded roadmap approval, then dispatches dependency-ready items in managed worktrees and reports their outcomes. |

Run these as skill requests in the agent conversation, not as shell commands. Use the active roadmap directory containing `roadmap.yaml`; an archived roadmap is a historical record, not an execution target.

## A typical session

1. Start with `/supervise cycle --dry-run` when you want to inspect the queue without changing tracked state. Use `/supervise cycle` to refresh discovery and publish a durable digest when repository state has changed. An unchanged cycle reuses its prior digest; use `--force` when you need a new sensing pass anyway.
2. Read **Needs a decision** first. It includes pending gates and deadlines. **Ready now** names work whose dependencies are satisfied; **Blocked** gives the reason other work cannot start. **New this cycle** contains ranked candidate work with provenance. **Degraded** tells you which discovery or handoff source was unavailable.
3. If a candidate is useful, tell the supervisor which candidate to approve and the concrete outcome you expect. It prepares a roadmap insertion preview and asks you to confirm that exact insertion. Approval records and plans the work; it does not dispatch an implementer.
4. When the roadmap approval gate proceeds, run `/supervise execute openspec/roadmaps/<roadmap-id>` to execute it. A direct `/autopilot-roadmap <roadmap-path>` invocation is another way to approve and run a roadmap. The supervisor delegates implementation and validation to workers and keeps outcome records rather than child transcripts.
5. Run `/supervise cycle` again after work lands or repository state changes. The next cycle rehydrates checkpoint and change state, so you can continue in a fresh agent session.

For a new idea that is not yet in the digest, start with `/supervise intake "<request>"`. Intake checks for existing work before creating a duplicate. It ends after tracking the request; use a later cycle and execution step to move it forward.

## Decisions and pauses

Roadmap approval is at roadmap scope: once recorded, it covers dependency-ready items until the roadmap's structure changes. A cycle can record that approval decision, but still stops after presenting the digest. If the gate is blocked, answer the pending decision in the conversation; the supervisor records it through the approval gate before execution resumes. A rejected or timed-out gate remains visible for a later answer.

An executing child may park on a pending gate or policy pause. That is a resumable state, not a completed item. Ask the supervisor to resume the parked work after the gate has an answer or the trust posture changes. The supervisor rechecks the current posture and recorded decision before dispatching another attempt.

The supervisor may report **Degraded: handoff** when the coordinator is unavailable. Its tracked mirror remains the fallback for rehydration. For execution progress, the roadmap's `checkpoint.json` and each change's `loop-state.json` are authoritative; a digest or handoff is a view of those records.

## Effective habits

- Give intake requests an observable outcome and any important constraint. This makes the later proposal and roadmap insertion reviewable.
- Use `--dry-run` for inspection. A normal cycle refreshes discovery reports, candidate state, and the digest when repository state has changed.
- The bug-scrub report lists open GitHub issues when `gh` is available. The supervisor checks that list for actionable, untracked issues and selects candidates within its 20-item store limit; the full issue list remains in the report.
- Treat `--force` as a request to reconsider unchanged state, not a way to create duplicate candidates.
- Resolve the gates listed under **Needs a decision** before expecting blocked work to advance.
- Use `/supervise execute` only with an active roadmap and its recorded approval. For a standalone approved roadmap, `/autopilot-roadmap` is also available.

The full procedure and artifact contracts are in the [supervise skill](../../skills/supervise/SKILL.md). See [Durable State Artifacts](state-artifacts.md) for authority and rehydration rules and [Workflow](workflow.md) for the surrounding OpenSpec lifecycle.
