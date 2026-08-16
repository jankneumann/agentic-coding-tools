---
name: supervise
description: "Single conversational entry point for the supervisor role — intake a request, or run the recurring discovery-to-approval cycle"
category: Automation
tags: [supervisor, orchestration, roadmap, discovery, cycle]
triggers:
  - "supervise"
  - "supervisor cycle"
  - "run the cycle"
  - "what should we work on"
---

# Supervise

The single conversational counterpart the operator talks to. This skill does not
add an orchestration layer — it *names* one that already exists: the host harness
session, playing the `supervisor` archetype, driving the skills below it.

Two verbs:

| Verb | Question it answers |
|---|---|
| `intake` | "Here is a thing I want." → an OpenSpec change or proposal, slotted into a roadmap |
| `cycle` | "What should we work on?" → a ranked digest of remaining work, stopped at the operator's approval gate |

## Role contract

The supervisor archetype (`agent-coordinator/archetypes.yaml`) is `write_capable: false`
and resolves at the `frontier` tier. That is not advisory:

- **The supervisor decomposes, delegates, and adjudicates gates. It does not implement.**
  Implementation work is dispatched to a write-capable archetype in its own worktree.
- The only writes a supervise run may perform are *coordination artifacts*: roadmaps,
  proposal/tasks scaffolds, priorities reports, the cycle ledger, and handoffs.
  `scripts/cycle_state.py audit-writes` classifies any path and fails on a source-code
  write, so the boundary is checkable rather than aspirational.
- Judgment stays in the session. This skill's Python is deterministic plumbing only —
  see **Design principle** below.

## Arguments

```
/supervise intake "<natural-language request>"
/supervise cycle [--dry-run] [--force]
```

- `--dry-run` — compute and print the digest; write nothing (not even the ledger).
- `--force` — run the cycle even when the fingerprint is unchanged (see **Idempotency**).

## Prerequisites

- `openspec/roadmaps/<id>/roadmap.yaml` for at least one roadmap.
- The discovery generators for `cycle`: `bug-scrub`, `improve-harness`, `explore-feature`.
- `openspec/schemas/candidate-work.schema.json` (ri-11) — the one shape every generator emits.
- Optional: coordinator reachable, for handoff read/write and episodic recall.

## Local CLI mutation boundary

`intake` and a non-`--dry-run` `cycle` write coordination artifacts. In local CLI
execution they MUST run from a managed worktree:

```bash
CHANGE_ID="supervise-cycle"
eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "$CHANGE_ID")"
cd "$WORKTREE_PATH"
python3 "<skill-base-dir>/../shared/checkout_policy.py" require-mutation
```

`--dry-run` is read-only and may run from the shared checkout.

---

## Verb: `intake`

Turn a natural-language request into tracked work, without the operator invoking
`/plan-roadmap` by hand.

1. **Rehydrate** (see below) so the request is placed against real current state.
2. **Locate or scaffold.** Search active changes and roadmap items for something the
   request already belongs to. If found, report it rather than creating a duplicate —
   an intake that silently forks existing work is the failure this verb exists to avoid.
3. **Size it.** A single reviewable change → scaffold one OpenSpec change. A body of
   work spanning several changes → write a proposal and hand it to `/plan-roadmap`.
4. **Slot it.** Add the item to the appropriate roadmap with dependencies, including a
   typed `external_depends_on` (ri-17) when the prerequisite lives in another roadmap.
5. **Report** what was created and what it is blocked on. Do not begin implementation.

## Verb: `cycle`

The recurring operating loop. Runs SENSE → RANK → digest, and **stops**.

### 1. Rehydrate

The supervisor is a rehydratable role, not a resident process: any fresh session that
loads durable state becomes the supervisor. Read, in order:

1. The SessionStart handoff (active changes, pending gates, standing decisions).
2. Every `openspec/roadmaps/*/roadmap.yaml`.
3. `openspec/supervise/cycle-ledger.json` — what the last cycle already surfaced.

Then compute the cross-roadmap picture:

```bash
python3 "<skill-base-dir>/../plan-roadmap/scripts/decomposer.py" validate-repo
python3 "<skill-base-dir>/scripts/cycle_state.py" ready --repo-root .
```

You must be able to state, before sensing: what is ready now, what is blocked and why,
what is in flight.

### 2. Sense

Run the read-only discovery generators — `/bug-scrub`, `/improve-harness`,
`/explore-feature` — and collect their findings as **candidate-work stubs** conforming
to `openspec/schemas/candidate-work.schema.json`. Where a generator does not yet emit
that shape (ri-12 migrates them), normalize its output into the schema and validate:

```bash
python3 "<skill-base-dir>/../prioritize-proposals/scripts/validate_candidate_work.py" stubs.json
```

If a generator is unavailable, **say so in the digest**. A silently skipped sensor
makes an empty cycle indistinguishable from a healthy one.

### 3. Dedupe

Suppress stubs that name work already tracked or already surfaced by an earlier cycle:

```bash
python3 "<skill-base-dir>/scripts/cycle_state.py" dedupe --repo-root . --stubs stubs.json
```

This is what makes the cycle safe to schedule — see **Idempotency**.

### 4. Rank

Run `/prioritize-proposals` over the surviving stubs plus active proposals and ready
roadmap items. One ranked list, with per-item reasoning: dependency-readiness, value,
effort, staleness, and live signals (recent failures, capability gaps).

### 5. Digest, then stop

Report to the operator, decision-first:

- **Needs a decision** — approvals, escalations, PRs awaiting review or merge.
- **Ready now** — per roadmap, priority order, and what each unblocks.
- **New this cycle** — ranked candidate work with provenance.
- **Blocked** — and on what, distinguishing an external prerequisite (auto-clears) from
  a human decision (does not).
- **Degraded** — any sensor that did not run.

Then **stop**. Do not create roadmaps, scaffold changes, dispatch implementers, push,
or open PRs.

> **Why the gate sits here.** The operator approves a *roadmap*, not fifteen items:
> one decision at roadmap altitude authorizes a DAG of work. Human attention goes to
> intent — what gets built and in what order — while correctness is delegated to
> structural checks (validation phases, vendor-diverse review, goal gates). A cycle
> that planned work autonomously would quietly move that gate.

On approval, the operator's "yes" flows into `/plan-roadmap`, and execution proceeds
through `/autopilot-roadmap` — dispatching to archetype workers under the routing cost
policy (ri-18: subscription+local → subscription+cloud → metered).

---

## Idempotency

A scheduled cycle fires on whatever tree it finds, including an unchanged one. Two
mechanisms keep a re-run from duplicating work:

1. **Cycle fingerprint.** A deterministic digest over the tracked tree content
   (excluding `openspec/supervise/` itself, so committing the ledger never changes the
   fingerprint), active change-ids, and every `(roadmap_id, item_id, status, change_id)`
   tuple. No wall clock, no mtime — the same tree always fingerprints the same. When it
   matches the last ledger entry, `cycle` reports the prior digest and exits without
   re-sensing (override with `--force`).
2. **Stub keys.** Every candidate stub has a stable key — its `suggested_change_id`, or a
   digest of `(provenance.source_artifact, sorted finding_ids)`. A stub is suppressed when
   its key was already recorded by a previous cycle, or names a change that already exists
   under `openspec/changes/`, or is already claimed by a roadmap item.

Both live in `openspec/supervise/cycle-ledger.json`, which is tracked: a rehydrated
session on another machine inherits what has already been surfaced.

## Output

| Artifact | Written by | Purpose |
|---|---|---|
| Digest (chat) | `cycle` | The operator-facing decision surface |
| `openspec/supervise/cycle-ledger.json` | `cycle` | Fingerprint + surfaced stub keys, for idempotency |
| `openspec/priorities/<date>/…` | `/prioritize-proposals` | The ranking report |
| Roadmap items / change scaffolds | `intake` (on approval) | Tracked work |

## Scripts

| Script | Role |
|---|---|
| `scripts/cycle_state.py` | Deterministic only: cycle fingerprint, ledger read/write, stub keying and dedupe, ready-set assembly across roadmaps, and the write-boundary audit. No LLM calls, no network. |

## Design principle: host-assisted only

**This skill makes no direct LLM API calls.** All reasoning happens in the host session
(the supervisor) or in a dispatched sub-agent; `scripts/` stays deterministic — the same
invariant `autopilot-roadmap` enforces, for the same reason: the session already has a
paid-for model loaded, and a second API path would double-bill and fragment context.

Sensing, ranking, and sizing are model work performed *by the session*, not by this
skill's Python. The Python answers only questions with one right answer: what is ready,
what did we already surface, has anything changed, is this write allowed.

## Next step

After the operator approves a cycle's ranked set:

```
/plan-roadmap <proposal-path>        # turn approved candidates into roadmap items
/autopilot-roadmap <workspace-path>  # execute the ready queue
```
