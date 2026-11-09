# Multi-Player Agentic Collaboration: Owned Contracts, Early Collisions, Reconciled Insight

## Motivation

This toolkit is built and dogfooded by one developer, then installed into team repositories
with `skills/install.sh`. Every assumption that is only true for a single principal travels
with it as an invisible constraint. In team use those assumptions fail in a recognizable way.

**The motivating incident.** A small team planned an agentic memory store using these
skills. One developer wrote a detailed specification; another wrote a competing, simplified
specification; the two had to be reconciled, and the reconciliation was argued as "whose
spec wins" rather than "what does each spec know." Work was then split into large feature
domains owned by individuals. One developer's part depended on a capability in another's
domain, so they waited for that developer's AI-assisted implementation, even though their
own agents could have built the dependency from the agreed spec faster. The two failures are
distinct:

1. **Divergence reconciled at the wrong level.** Branches and specs were reconciled as text
   ("whose diff survives") rather than as insight (decisions, contracts, concerns, evidence).
   Each author defended their artifact because it was the only place their concern lived.
2. **Ownership bundled with labor.** Domain ownership meant "I write this code." That was
   right when code was the scarce resource. With agents, code is cheap; decision rights and
   acceptance are scarce. Bundling them put the slowest implementation on everyone's
   critical path.

**The single-principal assumptions that cause this**, as they exist today:

| Assumption | Where it lives | Team failure mode |
|---|---|---|
| Whoever runs the skill owns the intent | `/plan-feature` approval, `TRUST_POSTURE.md`, `approval.py` `decided_by` (free string, no routing) | You approve your own gates; teammates' concerns first surface at PR review, after code exists |
| The coordinator is the shared rail | locks, claims, work queue, `feature_registry.py` | Each developer runs their own coordinator, or none; primitives coordinate nothing across people |
| One change edits a spec at a time | `openspec/changes/*/specs` deltas, `opsx:sync` | Two branches modify the same requirement; the spec conflicts last, at archive |
| Dependencies are on whole items | `roadmap.yaml` `depends_on` | Dependents wait for implementation-complete when they only needed the contract |
| Reviewer throughput ≈ agent throughput | `/autopilot` PR size | Teammates receive large AI-authored PRs; review becomes the bottleneck and branches grow |
| Rationale artifacts get read | `session-log.md`, `choices.json` | Teammates read the diff; the insight is recorded where nobody looks |
| Learning is personal | episodic memory, `improve-harness` | Each developer's harness improves alone; installed skill versions drift between developers |
| Everyone uses the workflow | the OpenSpec lifecycle | Non-adopters edit code directly; specs drift and agents treat stale specs as truth |

Within a single change the toolkit already does the right thing: `/plan-feature` emits
`contracts/`, `/implement-feature` runs `wp-contracts` first and parallel packages build
against it, and `/prototype-feature` treats variant branches as disposable experiments whose
*findings* (not code) are synthesized into `design.md`. This epic lifts those patterns from
"one change, one principal" to "many changes, many principals."

**Execution model.** Implementation is done by agents working down a shared work queue, not
by individuals driving interactive sessions. Humans own intent and contracts, accept results,
and are engaged through escalation when an agent needs a decision — not by pairing with the
agent that builds their domain. This makes the queue the primary execution surface and
ownership-routed escalation the primary human interface, so both are foundations of this
epic rather than refinements.

**Success looks like:** a team of humans, sharing a queue of agents, can plan overlapping work,
discover collisions on the day they are introduced, unblock on agreed contracts rather than
finished implementations, reconcile divergent work by its insight, route every decision to
the human who owns it, and learn from every human correction — while a solo developer sees
no new friction at all.

## Principles

The capabilities below derive from ten principles. Each capability cites the principles it
serves; a capability that serves none does not belong in this epic.

**Who decides**

- **P1. Principals are explicit.** Every action carries an *on-behalf-of* chain ending in a
  human principal. Humans are first-class identities with domains and availability, not an
  implicit "operator."
- **P2. Own decisions, not labor.** Ownership is decision rights plus acceptance rights over
  a contract or intent. Implementation is a commons: queue agents build against an agreed
  contract regardless of whose domain it is, and the owner accepts or rejects the result.
- **P3. Intent is an owned, single-writer artifact.** Goals, non-goals, constraints, and
  "done means" have one owner; others propose changes. Agents never arbitrate between two
  principals' intents — they surface the conflict to the owners.

**What gets shared, and when**

- **P4. Contracts before divergence; unblock at the contract.** Publish the interface and
  invariants before diverging. Dependencies bind to contracts, not implementations;
  *contract-complete* is a milestone in its own right.
- **P5. Concerns must be executable.** A concern that matters is expressed as a test or
  scenario, ideally written by the consumer who needs it. A concern that cannot be tested is
  a preference and carries less weight in reconciliation.
- **P6. Reconcile insight, not diffs.** A divergent branch or spec is an experiment. Its
  durable output is a ledger — decisions, contracts, concerns-as-tests, evidence, dead ends.
  Reconcile ledgers; regenerate code from the reconciled contract.
- **P7. Detect collisions early, at the highest level of abstraction.** Intent conflicts
  before contract conflicts before file conflicts. A collision found at plan time is a
  conversation; at merge time it is a rewrite.

**How signals flow**

- **P8. Attention is the scarce resource.** Prepare proactively, commit reactively. Route
  each decision to its owner, batch the rest into digests, and interrupt only above a
  per-principal threshold.
- **P9. Every action is traceable; every human intervention is a signal.** Actions record
  actor, principal chain, trigger, context versions, authorizing gate, and outcome under
  causal IDs. Human edits, overrides, rejections, and reverts are labeled corrections linked
  to the trace that produced them, and trust is calibrated from that evidence.
- **P10. Agents work the queue; humans are reached by escalation.** Implementation flows
  through a shared work queue drained by agents. A human is engaged only when an agent needs
  a decision it may not make; the agent parks that item and continues with the next ready
  one, so a pending human decision never idles a worker.

## Capabilities

### Capability: Collaboration principles guide

Publish the principles above as `docs/guides/multiplayer-collaboration.md`, linked from
`AGENTS.md`, with the single-principal assumption table and how each skill behaves in solo
versus team mode. Serves all principles; it is the reference later capabilities cite.

**Acceptance Outcomes:**
- `docs/guides/multiplayer-collaboration.md` exists and is linked from `AGENTS.md` and `docs/guides/documentation.md`
- Each principle names at least one capability or existing mechanism that implements it

### Capability: Human principal registry and ownership map

Introduce human principals alongside agent principals (extending, not duplicating, the
`principal-credential-architecture` roadmap's registry) and a git-native ownership map,
`openspec/owners.yaml`, that assigns owners, decision rights, and acceptance rights to
OpenSpec capabilities (`openspec/specs/<capability>`), roadmap items, and contract files. The
map can emit or reconcile with `CODEOWNERS` so GitHub review routing agrees with it. A
resolver library answers "who owns X?" for any skill. Serves P1, P2, P3.

**Acceptance Outcomes:**
- A schema-validated `openspec/owners.yaml` resolves an owner set for any capability, roadmap item, or contract path, with a declared repository-default owner as fallback
- A check reports capabilities with no owner and owners that are not registered principals
- With no `owners.yaml` present, every resolver call returns the sole repository principal and no skill behavior changes (solo mode)

### Capability: On-behalf-of attribution and causal trace IDs

Every coordinator audit entry, event, approval, handoff, phase record, and skill-created PR
carries an `on_behalf_of` principal chain and `correlation_id` / `causation_id` fields so a
chain event → triage → action → outcome can be reconstructed. Extends `audit.py`,
`event_bus.py`, `handoffs.py`, `approval.py`, and `PhaseRecord.write_both()`. Git-native
fallback: the same IDs appear as commit trailers and PR-body metadata. Serves P1, P9.

**Acceptance Outcomes:**
- Given any audit entry, a query returns its full causal chain back to the originating event or human request
- Skill-authored commits carry `On-Behalf-Of:` and `Correlation-Id:` trailers
- Events caused by an agent's own action are identifiable as echoes by causation ID, and loop guards cap causal-chain hop count

### Capability: Plan-time collision detection

Extend `feature_registry.py` overlap analysis from lock keys and files to OpenSpec
requirements and contract files, and add a git-native scanner that reads `openspec/changes/*`
deltas and `contracts/` on all open PRs and remote branches. `/plan-feature` and
`/supervise intake` run it and report collisions by level (intent, requirement, contract,
file) with the owners involved. Serves P4, P7.

**Acceptance Outcomes:**
- When two open changes modify the same `### Requirement:` of a capability, the second `/plan-feature` run reports the collision, the other change, and its owner before tasks are generated
- The scanner works with only a git remote; coordinator availability adds live claims but is not required
- Collisions are classified by abstraction level, and an unavailable scanner degrades to a warning, never a block

### Capability: Declare-early draft PR

`/plan-feature` (and `/autopilot` at plan completion) opens a draft PR containing only the
proposal, spec deltas, and contracts before implementation begins. The draft PR is the claim,
the contract announcement, and the review invitation — legible to teammates who do not use
the skills. Serves P4, P7, P8.

**Acceptance Outcomes:**
- A planned change has a draft PR with proposal, spec deltas, and `contracts/` before the first implementation commit
- The draft PR body lists contracts introduced or changed and the owners whose review is requested
- The behavior is opt-out per repository and is skipped in solo mode unless enabled

### Capability: Owned intent artifacts

Give each proposal a structured intent block (goals, non-goals, constraints, done-means)
with a declared owner, and enforce single-writer change control: a non-owner's edit to an
intent block is valid only as a proposed amendment that the owner accepts. A CI check
compares the PR author's principal with the intent owner. Agents that detect conflicting
intents between principals raise a conflict escalation instead of choosing. Serves P2, P3.

**Acceptance Outcomes:**
- `openspec validate` accepts a proposal intent block with an `owner` that resolves in the ownership map
- A PR that edits another owner's intent block without an accepted amendment fails the intent-ownership check
- An agent encountering two principals' conflicting intents emits a conflict escalation naming both owners and makes no choice between them

### Capability: Contract-level roadmap dependencies

Extend the roadmap schema so `depends_on` can bind to a dependency's contract rather than
its implementation (`{item: ri-03, on: contract}`), add a `contract_complete` item state, and
teach `/autopilot-roadmap` and `/supervise` to unblock dependents at contract-complete.
Dependents build against stubs or fakes generated from the contract. Serves P2, P4.

**Acceptance Outcomes:**
- A roadmap item depending `on: contract` becomes ready when its dependency reaches `contract_complete`, before that dependency is implemented
- Existing bare `depends_on: [id]` entries keep implementation-complete semantics unchanged
- `/implement-feature` provides a contract-generated stub for each contract dependency that is not yet implemented

### Capability: Team work queue across principals

Make the coordinator work queue the shared execution surface for a team: queue entries carry
the owning principal, the originating roadmap item, and its contract dependencies, and any
eligible agent may claim any ready entry regardless of whose domain it belongs to. Entries
remain one-way projections of canonical `roadmap.yaml` / `loop-state.json` state per
`docs/guides/work-queue-truth-projection.md`, so a lost queue is rebuilt from git. Ordering
across principals follows an explicit, owned priority policy rather than first-come claims,
because whose work goes first is an intent decision. Extends `work_queue.py`, `/supervise`,
and `/autopilot-roadmap`. Serves P2, P10, P3.

**Acceptance Outcomes:**
- Roadmap items from two principals' roadmaps appear in one queue, each entry attributed to its owner and source item
- An agent claims the highest-priority ready entry under the declared priority policy, independent of entry owner
- Deleting all queue rows and re-running reconciliation reproduces the same entries from git state
- A change to the cross-principal priority policy is accepted only from the policy's owner

### Capability: Queue-dispatched implementation with owner acceptance

Separate `owner` (decision and acceptance rights) from `implementer` on roadmap items and
changes. The default implementer is the agent queue; an owner may restrict an item to a named
principal's agents. Queue agents implement from the agreed contract and open a PR into the
owner's domain; the owner accepts or rejects with a reason. Claims are visible through the
queue and mirrored as draft PRs so non-adopters can see in-flight work and nothing is
silently duplicated. Serves P2, P4, P10.

**Acceptance Outcomes:**
- A roadmap item with default implementer policy is dispatched to the queue without requiring its owner to start a session
- A queue-implemented PR requests review from the item owner and cannot be merged without the owner's acceptance
- Claimed, in-flight implementation is visible from the git remote alone via a draft PR naming the item and claim time
- An owner rejection is recorded with its reason and linked to the contract, so spec gaps surfaced by rejection become amendments

### Capability: Consumer-driven contract tests

When `/plan-feature` plans a change that consumes another change's contract, it writes the
consumer's needs as executable contract tests and files them into the upstream change's
contract test suite (via PR to the upstream owner). Upstream `/validate-feature` runs the
consumer tests. A kernel/backlog split rule follows: a requirement belongs in a contract
kernel if and only if some consumer test needs it; the rest is ranked backlog with recorded
rationale. Serves P4, P5.

**Acceptance Outcomes:**
- A consuming change's plan produces contract tests attributed to the consumer and proposed to the upstream change
- Upstream validation reports per-consumer contract test results
- A spec-split helper partitions a capability's requirements into kernel (consumer-tested) and backlog (untested), preserving backlog rationale

### Capability: Branch and spec reconciliation workflow

A `/reconcile` skill takes two or more divergent branches or competing proposals and
reconciles them by insight: run `/audit-choices` per branch, extract contracts and
concerns-as-tests, build an agree / complementary / conflicting / unique matrix, route each
conflict to its owner as a typed decision, detect shared missing abstractions, and emit an
OpenSpec change for the reconciled contract plus the union of reconciled tests. Code is
regenerated by `/implement-feature`; source branches become reference material. Reuses the
`/prototype-feature` synthesis path (`synthesize_variants()`), which already does this for
intentional variants. Serves P5, P6, P3.

**Acceptance Outcomes:**
- Given two branches, `/reconcile` produces a reconciliation matrix in which every conflicting item names an owner and a pending decision
- The output change validates with `openspec validate --strict` and includes the reconciled test union as acceptance tests
- Given two competing proposals for one capability, the workflow emits a kernel/backlog split with no requirement from either proposal silently dropped

### Capability: Reviewer-shaped pull requests

Skill-authored PRs lead with a ledger — decisions made where the spec was silent, contracts
changed, concerns-as-tests added, evidence — before the diff. A configurable size budget
makes `/autopilot` split work or pause at a contract checkpoint for review by a principal
other than the one who ran it. Serves P6, P8.

**Acceptance Outcomes:**
- PRs created by `/autopilot` and `/cleanup-feature` render a ledger section generated from `choices.json` and contract diffs
- A change exceeding the size budget pauses at a contract checkpoint requesting review from a non-running owner when one exists
- In solo mode the checkpoint is skipped and only the ledger section is added

### Capability: Ownership-routed escalation and attention budgets

The approval gate routes each request to the owner set resolved from the ownership map, with
a fallback chain; `decided_by` must belong to that set. Trust posture can declare gate owners
per capability. Each principal has an urgency threshold and digest cadence: events below the
threshold are batched into a per-principal digest, above it they notify. A dedicated
escalation type covers conflicts between principals. A queue agent that escalates parks the
item in a resumable state and claims the next ready entry, and the item re-enters the queue
when the owner answers. Each principal has one escalation inbox that is the primary human
interface to queue work. Extends `approval.py`, the trust-posture contract, and
`event_bus.classify_urgency`. Serves P1, P3, P8, P10.

**Acceptance Outcomes:**
- An approval request records its resolved owner set, and a decision by a principal outside it is rejected
- A principal receives notifications only above their configured threshold; the remainder appear in their digest
- An unresolvable owner fails closed to the repository-default owner and is reported
- An escalating queue agent parks the item and claims another ready entry; the parked item becomes ready again within one reconciliation cycle of the owner's answer
- A principal can list every open escalation addressed to them, with its item, options, recommendation, default action, and deadline

### Capability: Intervention capture and trust calibration

Record human edits to agent output, overrides, rejections, reverts of autonomous actions,
and unnecessary or missed escalations as labeled corrections linked by causal ID to the
producing trace, classified as intent-level or execution-level. Compute per-gate and
per-owner approve-unchanged and override rates, and propose trust-posture changes — which are
themselves gated to the posture owner, never self-applied. Corrections feed the
`closed-loop-learning` flywheel rather than a parallel store. Serves P9, P8.

**Acceptance Outcomes:**
- A reverted or human-edited agent commit produces a correction record linked to its trace and classified intent vs execution
- A gate report shows approve-unchanged and override rates per gate and owner over a window
- A trust-posture change proposal is generated when a gate crosses a configured threshold and requires the posture owner's approval to apply

### Capability: Team toolkit consistency

`install.sh` stamps the installed toolkit version and payload hash into the consumer
repository, and a check warns when collaborators' installed skills differ from the
repository's pinned version. Shared, repository-scoped learnings can be opted into so
improvements from one developer's sessions reach teammates' agents. Serves P9.

**Acceptance Outcomes:**
- A consumer repository records the installed toolkit version and payload hash in a tracked file
- `install.sh --check` reports drift between the pinned version and the local runtime copy
- Repository-scoped learnings are opt-in and never include private transcript content

### Capability: Multi-player simulation harness

A `gen-eval` scenario pack that simulates two or more principals with separate identities,
worktrees, and agents working overlapping changes, used to reproduce team failure modes
(competing specs, blocked dependencies, late collisions) and to verify each capability.
The first scenario reproduces the memory-store incident. This makes multi-player behavior
testable in a solo-maintained repository. Serves all principles.

**Acceptance Outcomes:**
- A scenario with two principals modifying the same requirement fails to detect the collision before plan-time collision detection lands and detects it after
- The memory-store scenario measures time-blocked-on-dependency and drops it once contract-level dependencies land
- Scenarios run in CI without network access to a shared coordinator

## Constraints

- Canonical state must live in git (proposals, specs, contracts, `roadmap.yaml`, `loop-state.json`, `owners.yaml`); the shared coordinator queue is the execution surface and a rebuildable projection of that state, never its source of truth. Planning-time capabilities (collision detection, declare-early PRs, ownership, reconciliation) must function with only the git remote, so teammates without coordinator access are never blocked.
- Implementation shall be performed by queue agents by default; interactive human sessions are an escalation path, not the execution path.
- Solo mode must be unchanged: with one principal and no `owners.yaml`, no new prompts, gates, or PR checkpoints shall appear.
- Teammates who do not use the skills must not be blocked; every new artifact shall be readable as plain markdown or YAML in a PR.
- Agents shall never resolve a conflict between two principals' intents; they shall surface it to the owners.
- Authority decisions shall fail closed (unknown owner escalates to the repository-default owner); advisory signals shall fail open (an unavailable collision scan warns, never blocks).
- New durable artifacts must be registered in `docs/guides/state-artifacts.md` with writer, authority, and missing/stale behavior; derived projections must never feed back into canonical state.
- Skills must remain portable through `install.sh`: no references to private coordinator source from installed payloads.
- Human principals extend the `principal-credential-architecture` registry, and corrections feed the `closed-loop-learning` flywheel; this epic must not create parallel registries or learning stores.
- Tests must resolve change paths with `change_dir()` per the OpenSpec path stability rule.
- Intervention capture shall record only artifacts in the shared repository and coordinator, never private session transcripts unless the principal opts in.

## Phases

### Phase 1: Identity and early visibility

- Collaboration principles guide
- Human principal registry and ownership map
- On-behalf-of attribution and causal trace IDs
- Plan-time collision detection
- Multi-player simulation harness

### Phase 2: Queue-driven, contract-first execution

- Team work queue across principals
- Ownership-routed escalation and attention budgets
- Contract-level roadmap dependencies
- Queue-dispatched implementation with owner acceptance
- Declare-early draft PR
- Owned intent artifacts
- Consumer-driven contract tests

### Phase 3: Reconciliation and review

- Branch and spec reconciliation workflow
- Reviewer-shaped pull requests

### Phase 4: Learning and consistency

- Intervention capture and trust calibration
- Team toolkit consistency

## Out of Scope

- Real-time co-editing of documents or code; collaboration is asynchronous through git, PRs, and the coordinator.
- Replacing GitHub review, branch protection, or `CODEOWNERS`; the ownership map integrates with them.
- A hosted multi-tenant coordinator or organization-wide identity provider integration.
- Cross-repository ownership federation; ownership is scoped to one repository.
- Chat-platform integrations beyond the existing notification channel seam.
- Agent principal identity, credentials, and isolation, which belong to `principal-credential-architecture` and `dispatch-governance`.
- The learning flywheel's recall and earned-delegation mechanics, which belong to `closed-loop-learning`.
