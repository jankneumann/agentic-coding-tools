# Symphony Supersession Audit

> Audited against `roadmap-always-on-agent-automation` (24 items).
> Trigger: symphony's 16 items were all `candidate` — dark to the executor — while
> `docs/proposals/always-on-agent-automation.md` states it "deliberately reuses the
> `symphony` roadmap items where they exist rather than re-deriving them." Approving
> symphony wholesale would have dispatched duplicate work against completed and
> in-flight always-on items.

## Method

Each symphony item was compared against every always-on item by capability, not by
title. Five always-on items name their symphony origin explicitly (ri-04, ri-07,
ri-08, ri-18, ri-21); the rest were matched on described behavior. Items were sorted
into three dispositions rather than a supersede/keep binary, because several symphony
items are neither duplicated nor independently executable — they are internals of the
daemon that always-on ri-08 builds.

## Disposition summary

| Disposition | Count | Encoding applied |
|---|---:|---|
| Superseded | 6 | `status: skipped` + supersession recorded below |
| Partially superseded — residual live | 1 | `status: approved`, description narrowed to the residual |
| Daemon-internal (deferred) | 5 | `status: blocked`, `blocked_by` → always-on ri-08 |
| Independent | 4 | 2 `approved`, 2 `blocked` on always-on ri-07 (see *Stranded dependencies*) |

### Partially superseded: `trust-posture-binding`

The first pass of this audit marked it fully superseded by always-on ri-04. **That was
wrong**, and ri-04's own proposal says so — its *Out of scope* section reads:

> **Deployment-level posture** (sandbox mode, network allowlist, coordinator trust
> level, guardrail posture) — that is symphony `trust-posture-binding`, bound to
> `profiles.py` / `policy_engine.py`, not this per-gate layer.

Verified against the tree: `TRUST_POSTURE.template.md`'s front matter contains only a
`gates:` block — no sandbox mode, network allowlist, trust level, or guardrail posture —
and `grep` finds **zero** references to `trust_posture` / `TRUST_POSTURE` anywhere in
`agent-coordinator/src/` or `agent-coordinator/profiles/`. The deployment-binding half
never shipped and has no other owner.

Restored to `approved` with its description narrowed to the residual. Its dependency on
`workflow-md-contract` is in-roadmap and stands. `harness-readiness-audit`'s dropped
reference to this item stays dropped: that item only checks *"`TRUST_POSTURE.md`
present"*, which the shipped per-gate half satisfies.

**Lesson for the typed-edge work:** supersession is not always total. `superseded_by`
needs to express partial absorption — or an item's scope must be split before the edge
is drawn — otherwise a residual capability disappears the moment someone marks the
parent superseded.

### Stranded dependencies

Marking superseded items `skipped` stranded three of the four independent
items: `_get_ready_items` clears a dependency only when it appears in the checkpoint's
`completed_items`, and a `skipped` item never does — so an approved item depending on a
skipped one is permanently unready, silently. Each dead reference was repointed at the
prerequisite that actually supersedes it:

| Item | Dead reference | Resolution |
|---|---|---|
| `harness-readiness-audit` | `trust-posture-binding` | Reference dropped and it stays dropped after the partial-supersession correction above: this item checks only that `TRUST_POSTURE.md` is present and valid, which the per-gate half shipped by always-on ri-04 satisfies. It does not need the deployment-binding residual that `trust-posture-binding` still owns. Remaining dep `workflow-md-contract` is in-roadmap and stands. Stays `approved`. |
| `coordinator-issue-tool` | `coordinator-tracker-adapter` | Superseded by always-on **ri-07**, not complete. Reference dropped; item set `blocked` on ri-07. |
| `linear-tracker-adapter` | `coordinator-tracker-adapter` | Same as above. |

This failure mode is itself an argument for the typed-edge work: with `superseded_by`
edges the resolver could have followed the supersession to the always-on item and
computed readiness correctly, instead of the dependency silently dead-ending.

## Superseded (6)

Absorbed by an always-on item. Do not execute from symphony.

| Symphony item | Superseded by | Notes |
|---|---|---|
| `coordinator-tracker-adapter` | always-on **ri-07** (`build-coordinator-tracker-adapter-for-dispatch`) | ri-07's description says "Implement the symphony coordinator-tracker-adapter item". |
| `dispatcher-daemon` | always-on **ri-08** (`build-dispatcher-daemon-on-the-always-on-host`) | Deliberate design change: symphony holds authoritative orchestrator state **in memory**; ri-08 recovers state from tracker + worktree + `loop-state.json` with no runtime DB. The always-on form is the one consistent with the git-is-truth principle — do not reintroduce the in-memory authority. |
| `reconciliation-stall-detection` | always-on **ri-08** + **ri-09** (`harden-heartbeats-and-worktree-registry-for-daemon-operation`) | Split: terminal-state run cancellation is ri-08 daemon logic; inactivity/staleness detection and workspace cleanup are ri-09's four-clock reconciliation. |
| `token-ratelimit-accounting` | always-on **ri-10** (`cross-vendor-arbitrage-instrument`) | ri-10 is the superset — durable cost/quota/ToS signals feeding the roadmap policy engine. |
| `operator-http-status-surface` | always-on **ri-18** (`expose-operator-status-surface`) | ri-18 names this item and offers an alternative delivery (extend kanban-viz instead of a FastAPI sidecar). |
| `github-tracker-adapter` | always-on **ri-21** (`add-github-two-way-tracker-adapter`) | Superseded with **expanded** scope: symphony specified one-way projection, ri-21 makes it bidirectional with GitHub as human-facing system of record. |

## Daemon-internal — deferred behind always-on ri-08 (5)

Not duplicated anywhere, but not independently executable either: each is a component
of the dispatcher daemon. Executing them before ri-08 exists would produce interfaces
with no caller. Marked `blocked` with `blocked_by` naming ri-08.

| Symphony item | Why it waits |
|---|---|
| `agent-runner-port` | Vendor-agnostic `start/stream_events/cancel` port. Overlaps the **existing** `CliVendorAdapter`/`SdkVendorAdapter` in `review_dispatcher.py`, which is batch (`subprocess.run`) rather than streaming. Scope on unblock should be "extend the existing adapters with a streaming event surface", not a parallel port. |
| `workspace-manager-hooks` | Issue-keyed workspaces plus `after_create`/`before_run`/`after_run`/`before_remove` hooks in `worktree.py`. The registry-locking and gc half is always-on ri-09; the hooks half is additive and has no consumer until the daemon runs. |
| `retry-queue-backoff` | Centralized dispatch retry with exponential backoff. The always-on proposal's appendix assigns dispatch retry to "Phase 2 daemon" but ri-08 does not enumerate it — this is the item that fills that gap, once there is a dispatcher to retry from. |
| `turn-based-continuation` | Same-thread continuation across `max_turns` with tracker re-check between turns. Meaningless without the daemon's session lifecycle. |
| `coordinator-integration` | Daemon registration via `discovery.py`, lock-namespace claims via `feature_registry.py`, audit on state transitions. Peer integration for a peer that does not exist yet. |

## Independent (4)

No always-on counterpart, no daemon dependency.

| Symphony item | Rationale |
|---|---|
| `workflow-md-contract` | A repo-owned `WORKFLOW.md` (typed YAML front matter + strict-template prompt body, schema-validated, hot-reloadable). Distinct from `TRUST_POSTURE.md`, which covers gate dispositions only. Nothing in always-on covers runtime prompt-template config. |
| `coordinator-issue-tool` | Agent-callable scoped tool wrapping `issue_service` operations with audit capture. ri-07 builds the adapter the *dispatcher* reads; this is the surface *agents* write through. |
| `harness-readiness-audit` | Scores a target repo against the prerequisites (hermetic tests, machine-readable build/test docs, valid `WORKFLOW.md`, `TRUST_POSTURE.md` present, openspec initialized). Useful independent of the daemon. |
| `linear-tracker-adapter` | Linear counterpart to the GitHub projection; proves the external-projection port generalizes. Genuinely optional — low priority, not blocked. |

## Encoding limitation

`skipped` is the closest status the current roadmap schema offers for "superseded" —
there is no `superseded` status and no `superseded_by` edge type, so the mapping in
the Superseded table above lives in this document rather than in machine-readable
form. The supervisor roadmap's typed-cross-roadmap-edges item exists to fix exactly
this: on landing, these seven rows become `superseded_by: <roadmap-id>:<item-id>`
references that the readiness resolver can traverse and report, and this document
becomes the provenance record rather than the source of truth.

## Incidental finding: ri-04's change is implemented but not archived

`openspec/changes/add-trust-posture-contract-file/` is still in the active changes
directory although always-on ri-04 is marked `completed`. Its `tasks.md` shows 29
checked and 4 unchecked, and all four unchecked are process steps — *Review*, *Done*,
*6.1 Orchestrator review*, *6.2 Merge* — not implementation work. This is the same
class always-on **ri-03** ("Archive the implemented-not-archived change backlog")
exists to flush, but ri-03 names only `factory-missions-architecture-alignment` and
`extract-gen-eval-package`; this is a third instance and should be added to its scope.

Related: `skills/shared/trust_posture.py` (15 KB) and `skills/shared/approval_gate.py`
both exist with **no consumers** outside `skills/shared/` and their tests. That is
expected — always-on **ri-06** is the wiring change and has not run — but it means two
completed items currently deliver no runtime behavior. Worth stating plainly so
"completed" is not misread as "in effect".
