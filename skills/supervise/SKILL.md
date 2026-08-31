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
  `scripts/cycle_state.py snapshot-writes` plus `audit-since` capture the checkout
  before a verb and fail if that verb changes source code, so the boundary is
  enforced without mistaking pre-existing operator edits for supervisor writes.
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

Before either verb does any work, capture its write baseline outside the repository:

```bash
SUPERVISE_WRITE_SNAPSHOT="$(mktemp)"
SUPERVISE_HANDOFF="$(mktemp)"
SUPERVISE_RECORD="$(mktemp)"
SUPERVISE_FINAL_RECORD="$(mktemp)"
python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . \
  snapshot-writes > "$SUPERVISE_WRITE_SNAPSHOT"
```

Keep these temporary files until the verb's final write audit and handoff. A dry run takes the same snapshot:
read-only is a checked outcome, not an exemption from the boundary.

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
5. **Build and mirror the supervisor record.** Rebuild `active_changes` from the
   post-intake repository while carrying the rehydrated durable sections forward, then
   write the tracked mirror:

   ```bash
   python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . \
     supervisor-record --prior "$SUPERVISE_RECORD" > "$SUPERVISE_FINAL_RECORD"
   python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . \
     mirror --record "$SUPERVISE_FINAL_RECORD"
   ```

6. **Audit the verb's writes.** After the mirror and before the coordinator handoff, run:

   ```bash
   python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . \
     audit-since --snapshot "$SUPERVISE_WRITE_SNAPSHOT"
   ```

   A non-zero exit is a stop-the-line violation: preserve the worktree and report the
   forbidden paths. Do not claim intake completed.
7. **Write the supervisor handoff, then report.** Only after the audit succeeds, load
   `$SUPERVISE_FINAL_RECORD` and call the bridge as
   `try_handoff_write(..., content={"supervisor_record": record})`. If the coordinator
   is unavailable, report `Degraded: handoff`; the tracked mirror remains the durable
   fallback. Report what was created and what it is blocked on. Do not begin implementation.

## Verb: `cycle`

The recurring operating loop. Runs SENSE → RANK → digest, and **stops**.

### 1. Rehydrate

The supervisor is a rehydratable role, not a resident process: any fresh session that
loads durable state becomes the supervisor. Read durable state in this order:

1. Through the host bridge, call
   `try_handoff_read(limit=1, supervisor_only=true)`. The filter is required: a newer
   ordinary handoff must not mask the newest supervisor handoff. Save the complete bridge
   response to a temporary JSON file outside the repository.
2. Run the deterministic rehydrator, which also reads
   `openspec/supervise/supervisor-record.json` when present:

   ```bash
   python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . \
     rehydrate --handoff "$SUPERVISE_HANDOFF" > "$SUPERVISE_RECORD"
   ```

   The `rehydrate` subcommand selects the handoff or mirror with the newer `written_at`,
   then invokes the `supervisor-record` builder so `active_changes` is freshly derived.
   **Coordinator unreachable.** When the bridge yields no supervisor handoff, it falls back to
   the mirror and the digest must report `Degraded: handoff`. This one path therefore
   covers handoff-only state, a stale handoff with a newer mirror, and coordinator-down
   mirror recovery.
3. Read every `openspec/roadmaps/*/roadmap.yaml` and
   `openspec/supervise/cycle-ledger.json` — what the last cycle already surfaced.

Then compute the cross-roadmap picture:

```bash
python3 "<skill-base-dir>/../plan-roadmap/scripts/decomposer.py" validate-repo
python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . fingerprint
python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . ready
```

You must be able to state, before sensing: what is ready now, what is blocked and why,
what is in flight. Inspect the fingerprint command's `unchanged` field before SENSE.
When it is `true`, report the prior digest and stop unless the operator supplied
`--force`. This gate applies to normal and dry-run cycles.

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

Despite their analytical purpose, those child skills persist reports. Under
`--dry-run`, the supervisor **MUST NOT invoke** `/bug-scrub`, `/improve-harness`, or
`/explore-feature`. Read already-existing reports and inspect repository state directly,
keeping normalized stubs only in memory or in temporary files outside the repository.
Mark a sensor `Degraded` when no current persisted report exists. This is the
non-persisting sensor lane; it never refreshes artifacts during a dry run.

### 3. Dedupe

Suppress stubs that name work already tracked or already surfaced by an earlier cycle:

```bash
python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . dedupe --stubs stubs.json
```

This is what makes the cycle safe to schedule — see **Idempotency**.

### 4. Rank

Run `/prioritize-proposals` over the surviving stubs plus active proposals and ready
roadmap items. One ranked list, with per-item reasoning: dependency-readiness, value,
effort, staleness, and live signals (recent failures, capability gaps).

`/prioritize-proposals` also persists reports, so a `--dry-run` **MUST NOT invoke** it.
Rank the in-memory inputs in the host session and print that ephemeral result instead.

### 5. Digest, then stop

Report to the operator, decision-first, rendering durable supervisor state explicitly:

- **Needs a decision** — render every `pending_gates` entry with its gate, change,
  disposition, and `deadline`, then other approvals, escalations, and PRs awaiting review
  or merge. Do not flatten away the deadline.
- **Ready now** — reconcile freshly derived `active_changes` (including current phase and
  pending gate) with ready roadmap items; list per roadmap in priority order and say what
  each unblocks.
- **New this cycle** — ranked candidate work with provenance.
- **Blocked** — and on what, distinguishing an external prerequisite (auto-clears) from
  a human decision (does not).
- **Degraded** — any sensor that did not run.

Then **stop**. Do not create roadmaps, scaffold changes, dispatch implementers, push,
or open PRs.

Before stopping, enforce state and write boundaries in this order:

1. For a normal, non-`--dry-run` cycle, write a temporary JSON array containing the
   stable keys of every newly surfaced stub, then record the completed cycle:

   ```bash
   python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . \
     record --keys "$SUPERVISE_KEYS"
   ```

   Do not run `record` under `--dry-run`.
2. Still only for a non-`--dry-run` cycle, rebuild the full record from the rehydrated
   prior and write its non-derivable mirror:

   ```bash
   python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . \
     supervisor-record --prior "$SUPERVISE_RECORD" > "$SUPERVISE_FINAL_RECORD"
   python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . \
     mirror --record "$SUPERVISE_FINAL_RECORD"
   ```

3. For every cycle, including `--dry-run`, audit all repository changes made since the
   entry snapshot:

   ```bash
   python3 "<skill-base-dir>/scripts/cycle_state.py" --repo-root . \
     audit-since --snapshot "$SUPERVISE_WRITE_SNAPSHOT"
   ```

   A non-zero exit is a stop-the-line violation. Preserve the worktree and report the
   forbidden paths instead of claiming the cycle completed.
4. For a non-`--dry-run` cycle, only after that final audit succeeds, load
   `$SUPERVISE_FINAL_RECORD` and call
   `try_handoff_write(..., content={"supervisor_record": record})`. Coordinator failure
   is reported as `Degraded: handoff`; the mirror already records the durable subset.

Under `--dry-run`, write neither the mirror nor a supervisor handoff. The audit still runs
and proves the read-only boundary.

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

1. **Cycle fingerprint.** A deterministic digest over committed tree content plus staged
   and unstaged tracked changes (excluding `openspec/supervise/cycle-ledger.json` and
   `openspec/supervise/supervisor-record.json`, so durable-state writes never change the
   fingerprint), active change-ids, and every
   `(roadmap_id, item_id, status, change_id)` tuple. No wall clock and no mtime — the
   same repository state always fingerprints the same. When it matches the last ledger
   entry, `cycle` reports the prior digest and exits without re-sensing (override with
   `--force`).
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
| `openspec/supervise/supervisor-record.json` | `intake`, non-dry-run `cycle` | Tracked mirror of non-derivable supervisor state |
| Coordinator handoff `supervisor_record` | `intake`, non-dry-run `cycle` | Cross-session transport for full supervisor state |
| `openspec/priorities/<date>/…` | `/prioritize-proposals` | The ranking report |
| Roadmap items / change scaffolds | `intake` (on approval) | Tracked work |

## Scripts

| Script | Role |
|---|---|
| `scripts/cycle_state.py` | Deterministic only: supervisor-record build/rehydration, mirror selection/write, cycle fingerprint, ledger read/write, stub dedupe, cross-roadmap ready set, and write audit. No LLM calls, no network. |

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
