# Multiplayer Collaboration

This guide states the ten principles (P1-P10) behind the `multiplayer-collaboration`
roadmap, the single-principal assumptions those principles correct, the solo and team
mode vocabulary, and how each skill behaves in each mode. It is the reference that later
multiplayer changes cite. The change `multiplayer-simulation-harness` serves all ten
principles and is cited here once rather than under each principle.

The toolkit was built by one developer and installed into team repositories. Every
assumption that is only true for a single principal travels with it. These principles lift
patterns the toolkit already applies inside one change (`contracts/`, `wp-contracts`,
variant synthesis) to many changes and many principals.

## Modes

**Principal**: a human on whose behalf an action is taken (P1). Agents act for a principal;
they are never the principal.

**Solo mode**: the ownership resolver yields exactly one distinct human principal for the
repository. This holds when `openspec/owners.yaml` is absent and also when it names only
one human principal.

**Team mode**: the resolver yields two or more distinct human principals.

Solo mode adds no new prompts, gates, or PR checkpoints. A capability may add
passive output in solo mode (for example a PR ledger section or commit trailers), provided
the output requires no human action.

Until the `ownership-map` change ships there is no resolver, so every repository is in solo
mode by definition. `ownership-map` owns detection and must implement these definitions or
amend this guide in the same pull request.

## Principles

**Who decides**

### P1. Principals are explicit

Every action carries an on-behalf-of chain ending in a human principal. Humans are
first-class identities with domains and availability, not an implicit "operator".

**Existing:** [approval.py](../../agent-coordinator/src/approval.py) (`decided_by`, a free string), [audit.py](../../agent-coordinator/src/audit.py)
**Planned:** `ownership-map`, `causal-trace-ids`, `attribution-trailers`, `owner-routed-escalation`, `attention-budgets-digests`

### P2. Own decisions, not labor

Ownership is decision rights plus acceptance rights over a contract or intent.
Implementation is a commons: queue agents build against an agreed contract regardless of
whose domain it is, and the owner accepts or rejects the result.

**Existing:** [work_queue.py](../../agent-coordinator/src/work_queue.py)
**Planned:** `ownership-map`, `owned-intent-blocks`, `contract-dependencies`, `team-work-queue`, `queue-dispatch-owner-acceptance`

### P3. Intent is an owned, single-writer artifact

Goals, non-goals, constraints, and "done means" have one owner; others propose changes.
Agents never arbitrate between two principals' intents; they surface the conflict to the
owners.

**Existing:** [TRUST_POSTURE.md](../../TRUST_POSTURE.md)
**Planned:** `ownership-map`, `owned-intent-blocks`, `team-work-queue`, `reconcile-skill`, `owner-routed-escalation`, `attention-budgets-digests`

**What gets shared, and when**

### P4. Contracts before divergence; unblock at the contract

Publish the interface and invariants before diverging. Dependencies bind to contracts, not
implementations; contract-complete is a milestone in its own right.

**Existing:** [plan-feature](../../skills/plan-feature/) (`contracts/`), [implement-feature](../../skills/implement-feature/) (`wp-contracts`)
**Planned:** `plan-time-collision-detection`, `coordinator-contract-overlap`, `declare-early-draft-pr`, `contract-dependencies`, `queue-dispatch-owner-acceptance`, `consumer-contract-tests`

### P5. Concerns must be executable

A concern that matters is expressed as a test or scenario, ideally written by the consumer
who needs it. A concern that cannot be tested is a preference and carries less weight in
reconciliation.

**Existing:** [gen-eval](../../skills/gen-eval/)
**Planned:** `consumer-contract-tests`, `reconcile-skill`

### P6. Reconcile insight, not diffs

A divergent branch or spec is an experiment. Its durable output is a ledger: decisions,
contracts, concerns-as-tests, evidence, dead ends. Reconcile ledgers; regenerate code from
the reconciled contract.

**Existing:** [variant_descriptor.py](../../skills/parallel-infrastructure/scripts/variant_descriptor.py) (`synthesize_variants`), [audit-choices](../../skills/audit-choices/)
**Planned:** `reconcile-skill`, `reviewer-shaped-prs`

### P7. Detect collisions early, at the highest level of abstraction

Intent conflicts before contract conflicts before file conflicts. A collision found at plan
time is a conversation; at merge time it is a rewrite.

**Existing:** [feature_registry.py](../../agent-coordinator/src/feature_registry.py)
**Planned:** `plan-time-collision-detection`, `coordinator-contract-overlap`, `declare-early-draft-pr`

**How signals flow**

### P8. Attention is the scarce resource

Prepare proactively, commit reactively. Route each decision to its owner, batch the rest
into digests, and interrupt only above a per-principal threshold.

**Existing:** [event_bus.py](../../agent-coordinator/src/event_bus.py) (`classify_urgency`)
**Planned:** `declare-early-draft-pr`, `reviewer-shaped-prs`, `owner-routed-escalation`, `attention-budgets-digests`, `intervention-capture`, `trust-posture-calibration`

### P9. Every action is traceable; every human intervention is a signal

Actions record actor, principal chain, trigger, context versions, authorizing gate, and
outcome under causal IDs. Human edits, overrides, rejections, and reverts are labeled
corrections linked to the trace that produced them, and trust is calibrated from that
evidence.

**Existing:** [audit.py](../../agent-coordinator/src/audit.py), [handoffs.py](../../agent-coordinator/src/handoffs.py), [session-log](../../skills/session-log/)
**Planned:** `causal-trace-ids`, `attribution-trailers`, `intervention-capture`, `trust-posture-calibration`, `toolkit-consistency`

### P10. Agents work the queue; humans are reached by escalation

Implementation flows through a shared work queue drained by agents. A human is engaged only
when an agent needs a decision it may not make; the agent parks that item and continues
with the next ready one, so a pending human decision never idles a worker.

**Existing:** [work_queue.py](../../agent-coordinator/src/work_queue.py), [work-queue-truth-projection.md](work-queue-truth-projection.md)
**Planned:** `team-work-queue`, `queue-dispatch-owner-acceptance`, `owner-routed-escalation`, `attention-budgets-digests`

## Single-principal assumptions

| Assumption | Where it lives | Team failure mode | Addressed by |
|---|---|---|---|
| Whoever runs the skill owns the intent | `/plan-feature` approval, `TRUST_POSTURE.md`, `approval.py` `decided_by` (free string, no routing) | You approve your own gates; teammates' concerns first surface at PR review, after code exists | `ownership-map`, `owned-intent-blocks`, `owner-routed-escalation` |
| The coordinator is the shared rail | locks, claims, work queue, `feature_registry.py` | Each developer runs their own coordinator, or none; primitives coordinate nothing across people | `team-work-queue`, `coordinator-contract-overlap` |
| One change edits a spec at a time | `openspec/changes/*/specs` deltas, `opsx:sync` | Two branches modify the same requirement; the spec conflicts last, at archive | `plan-time-collision-detection`, `declare-early-draft-pr` |
| Dependencies are on whole items | `roadmap.yaml` `depends_on` | Dependents wait for implementation-complete when they only needed the contract | `contract-dependencies`, `consumer-contract-tests` |
| Reviewer throughput ≈ agent throughput | `/autopilot` PR size | Teammates receive large AI-authored PRs; review becomes the bottleneck and branches grow | `reviewer-shaped-prs`, `queue-dispatch-owner-acceptance` |
| Rationale artifacts get read | `session-log.md`, `choices.json` | Teammates read the diff; the insight is recorded where nobody looks | `reviewer-shaped-prs`, `reconcile-skill` |
| Learning is personal | episodic memory, `improve-harness` | Each developer's harness improves alone; installed skill versions drift between developers | `intervention-capture`, `trust-posture-calibration`, `toolkit-consistency` |
| Everyone uses the workflow | the OpenSpec lifecycle | Non-adopters edit code directly; specs drift and agents treat stale specs as truth | `declare-early-draft-pr`, `attribution-trailers` |

## Skills in solo and team mode

Each row is derived from the acceptance outcomes of the delivering change. A *Solo mode*
cell reads "Unchanged" or describes passive output only (see [Modes](#modes)).

| Skill | Solo mode | Team mode | Delivered by |
|---|---|---|---|
| `plan-feature` | Unchanged | Reports collisions with other open changes by level (intent, requirement, contract, file) with the owners involved, before tasks are generated; opens a draft PR with proposal, spec deltas, and contracts; writes consumer contract tests for contracts it consumes | `plan-time-collision-detection`, `declare-early-draft-pr`, `consumer-contract-tests` |
| `implement-feature` | Commit trailers carrying the principal chain (passive output) | Provides a contract-generated stub for each contract dependency not yet implemented | `attribution-trailers`, `contract-dependencies` |
| `validate-feature` | Unchanged | Reports per-consumer contract test results for the upstream change | `consumer-contract-tests` |
| `autopilot` | PR ledger section generated from `choices.json` and contract diffs (passive output) | Pauses at a contract checkpoint for review by a non-running owner when a change exceeds the size budget | `reviewer-shaped-prs` |
| `autopilot-roadmap` | Unchanged | Unblocks dependents at `contract_complete`; dispatches items to the shared queue under the owned priority policy | `contract-dependencies`, `team-work-queue` |
| `supervise` | Unchanged | Runs collision detection at intake; draws from one queue across principals' roadmaps; routes escalations to resolved owners | `plan-time-collision-detection`, `team-work-queue`, `owner-routed-escalation` |
| `cleanup-feature` | PR ledger section (passive output) | Merge of a queue-implemented PR requires the item owner's acceptance | `reviewer-shaped-prs`, `queue-dispatch-owner-acceptance` |
| `reconcile` | Unchanged | New skill: reconciles divergent branches or competing proposals by insight, routing each conflict to its owner as a typed decision | `reconcile-skill` |
| `install.sh` | Records the installed toolkit version and payload hash in a tracked file (passive output) | `--check` reports drift between collaborators' installed skills and the pinned version | `toolkit-consistency` |

## Authority and maintenance

This guide is descriptive; OpenSpec specs are normative. When the guide and a shipped spec
disagree, the spec wins and the guide is corrected in the next change that touches it. A
team-mode behavior counts as shipped once its delivering change is archived; from then on
`openspec/specs/multiplayer-collaboration/spec.md` is the normative statement.

A change that alters a behavior this guide describes updates the affected guide rows in the
same pull request. The guard test
`skills/tests/multiplayer-collaboration/test_multiplayer_guide.py` enforces only what is
mechanical: structure, links, and resolvable change-ids. Whether a solo or team cell is
accurate is checked in review, as is the principle titles' wording against the roadmap.
The guide names the roadmap and sibling changes by id and never links into
`openspec/changes/` or `openspec/roadmaps/`, because archival relocates them.
