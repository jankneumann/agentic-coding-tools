# Operator Front Door

## Motivation

The operator runs several projects and roadmaps at once and switches between them constantly.
Today the conversational surface and the execution surface are split badly. Planning happens in
the Claude mobile app. Implementation is started by hand in herdr panes on the always-on GX10,
and reaching those from a phone means typing into sshhip and reading through a terminal that is
too small to carry the context needed for a decision. Every gate an autopilot run parks on — a
merge, an escalation resume, a plan approval — reaches the operator as a bare prompt with no
re-entry context, so answering it means mentally reloading the project first. Many of those gates
are mechanical: they are resolved the same way every time, but still interrupt a human.

A second gap is capacity. The operator pays for Claude Max ($200, with the Claude app and Claude
Code drawing on the same limits), Codex ($100), Grok ($30), Gemini AI Pro, and metered
OpenRouter, and also has free local models on the GX10. Nothing routes work across that pool on
purpose. Phase dispatch also has a structural problem: a sub-agent cannot spawn its own
sub-agents. A supervisor that fans out autopilot runs as sub-agents therefore loses the
per-phase archetype routing that autopilot depends on, and phases fall back to running inline.
That happened on evidence-grounded-debugging ri-01: phases ran inline and the reviews came from
a single vendor.

This epic builds a **single conversational front door**. The native Claude app — on phone,
MacBook Air and Surface Pro — holds one long-lived "Supervisor" thread that is the operator's
cross-project decision inbox. Worker threads sit next to it for drill-down. Execution runs on
the GX10. Workers there are top-level `claude remote-control` sessions, so each one keeps the
Agent tool and full per-phase archetype routing, and they appear in the same Claude app. Codex
and Gemini workers run beside them, chosen by archetype. Cloud sessions are overflow capacity
only. herdr becomes an invisible process host on the GX10, and sshhip becomes break-glass
access.

Success looks like this:

- The operator answers every decision from any device by voice or one quiet tap, without
  reloading context.
- Mechanical gates never reach a human.
- Capacity across all six sources is spent deliberately and visibly.
- The headline metric — **human decisions per merged change** — goes down release over release.

## Capabilities

### Capability: Runner-decided gate tiering and decision cards

Today a gate is either `auto`, `notify_with_timeout`, or `block`, decided by the trust posture.
This capability adds a **tier** to every gate the runner raises:

- `auto` — resolved by policy and logged;
- `batched` — delivered in the digest;
- `interrupt` — pushed immediately.

The tier is decided by the runner from the gate kind, the posture, and the evidence attached. The
supervisor does not decide it. Every non-auto gate is rendered as a **decision card**: a
self-contained re-entry brief. A card carries:

- the project › roadmap › item breadcrumb;
- what happened since the operator last looked;
- the decision being asked and its evidence;
- 2–4 numbered options with a recommendation;
- a default action and a deadline.

The card is short enough to read on a phone and answerable in a single token such as `2` or
`1a`. The card is a versioned JSON schema plus a deterministic markdown renderer. The card is
data: any surface — Claude app thread, PR comment, digest — renders the same object.

The worker's dispatch-result summary envelope gains an `escalation_request` field. Through it a
worker asks for a higher model tier, a different vendor, or a human, and gives a reason and
evidence. The escalation request becomes a decision card, or an auto-approved ladder step (see
the escalation-ladder capability).

A **Stop-hook turn-end guard** keeps a worker session from ending its turn silently. A turn may
end only with work still in progress, a pending gate recorded as a decision card, or a terminal
loop-state. A turn that would end silently is blocked and must report what it is waiting on.

**Acceptance Outcomes:**
- Every gate raised by autopilot and autopilot-roadmap carries a runner-computed tier, and the
  tier is recorded in loop-state and the dispatch result.
- A decision-card JSON schema exists, is versioned, and validates every card emitted in tests.
  Every card has a breadcrumb, a since-last-seen summary, numbered options, a recommendation,
  a default, and a deadline.
- The rendered markdown of a card fits within 1,200 characters for the canonical merge and
  escalate-resume gates.
- The dispatch-result schema accepts an `escalation_request` with target tier or vendor, reason,
  and evidence refs, and rejects malformed requests.
- A Stop-hook guard blocks a worker turn that ends with no in-flight work, no pending decision
  card, and no terminal loop-state, and this is covered by a hook test.
- Under the operator's posture, auto-merge of an agent PR in this repository resolves as tier
  `auto` when CI is green on the head, reviews have converged, and there is no security finding.
  Any one of those conditions failing raises an `interrupt` card.

### Capability: Coordinator dispatch queue, decision inbox, and project index

The coordinator (postgres-backed) becomes the shared spine. It holds:

- **Dispatch queue.** Signed dispatch requests that workers claim exactly once, with leases,
  heartbeats, and requeue on lease expiry. It reuses the dispatch-request and dispatch-result
  schemas from multiplayer-collaboration ri-21.
- **Cross-project decision inbox.** Decision cards from every project and roadmap, with states
  open → answered → applied (or expired-to-default). Answers are idempotent.
- **Project index.** Every registered repository, its active roadmaps, in-flight items, and
  pending cards. The Supervisor thread can therefore answer "what needs me, across everything?"
  from one query instead of rehydrating each repo.

This capability builds on the coordinator-tracker adapter (always-on-agent-automation ri-07)
rather than duplicating it: the adapter becomes one producer into the dispatch queue.

**Acceptance Outcomes:**
- Two workers that claim from the queue at the same time never receive the same dispatch, and
  a lease that expires without a heartbeat returns the dispatch to the queue. Both are proven by
  a concurrency test.
- Dispatch requests without a valid signature are rejected at claim time.
- A decision card posted by a worker in project A is visible in an inbox query that spans all
  registered projects. Answering it twice applies exactly once.
- An unanswered card past its deadline resolves to its declared default, and that resolution is
  logged as an expiry rather than as a human decision.
- The project index lists every registered repository with its active roadmaps, in-flight
  items, and open-card count, from a single coordinator call.

### Capability: Continuous decision delivery to the Claude app

The operator chose continuous, unbatched delivery. As soon as an `interrupt` card is opened it
reaches the operator in two places:

- the long-lived Supervisor thread in the Claude app;
- the related pull request as a comment, when the card concerns a PR.

The operator answers in the thread by voice or by typing the option token, and the answer is
written back to the inbox. `batched` cards accumulate in the inbox and appear the next time the
Supervisor thread is opened or the digest runs. Phone push (for example ntfy) is explicitly
deferred: notifications in this epic come from the Claude app and PR events only.

**Acceptance Outcomes:**
- An `interrupt` card is visible in the Supervisor thread within one coordinator poll interval
  of being opened.
- An answer given as an option token (`2`, `1a`) or as free text in the Supervisor thread is
  recorded against the right card. The worker that raised the card resumes using that answer.
- A PR-scoped card also appears as one PR comment that ends with the attribution footer, and is
  not re-posted on retry.
- Opening the Supervisor thread shows every open card across all projects, oldest-deadline
  first, without the operator naming a project.

### Capability: GX10 launcher for Remote Control and vendor workers

A launcher service on the GX10 claims dispatches from the coordinator queue and starts the right
kind of worker:

- `claude remote-control` sessions for Claude archetypes, so each worker is a top-level session
  that keeps the Agent tool and per-phase archetype routing, and is reachable from the Claude
  app;
- `codex exec` workers for archetypes where Codex is the primary implementer;
- Gemini workers for long-context reading and review archetypes.

Each worker runs in a worktree created by the existing worktree skill, never in the shared
checkout. herdr is the process host: each worker gets a pane, and the operator can attach over
sshhip as break-glass, but herdr is not the interface. Free local models on the GX10 write
decision cards and digests and classify gate tiers, so none of that spends subscription capacity.

This capability supersedes the dispatcher-daemon design in always-on-agent-automation ri-08
where the two conflict. ri-08 spawned headless sessions. This launcher spawns Remote Control
sessions so the operator can drill into any worker from the app. The hardening work in ri-09
(heartbeats, worktree registry locking) remains a prerequisite.

Security boundaries:

- Dispatches must be signed by the coordinator.
- Only repositories on an explicit allowlist can be launched.
- Each archetype maps to a fixed permission mode.
- The launcher never widens a worker's permissions beyond what its archetype declares.

**Acceptance Outcomes:**
- Claiming a Claude-archetype dispatch starts a `claude remote-control` session in a fresh
  managed worktree. That session appears in the operator's Claude app session list, and its
  autopilot run records sub-agent phase dispatch rather than `phase_fallback_inline`.
- Claiming a dispatch whose archetype names Codex as primary implementer starts a `codex exec`
  worker in a managed worktree, which returns a schema-valid dispatch result.
- A dispatch for a repository not on the allowlist, or with an invalid signature, is refused
  and logged, and no process is started.
- After a launcher restart, in-flight workers are re-adopted or their dispatches requeued,
  using only coordinator, worktree, and loop-state records.
- Decision cards and gate-tier classifications in the pilot are produced by a GX10 local model,
  with zero subscription tokens spent on them, as shown in the usage ledger.
- The evidence-grounded-debugging ri-01 attempt-2 pilot runs end-to-end through the launcher,
  from VALIDATE to a merge decision, with cross-vendor review.

### Capability: Account-wide usage governor

The usage governor is a single view and policy over all six capacity sources:

- Claude Max — the app and Claude Code share limits;
- Codex;
- Gemini AI Pro;
- Grok;
- OpenRouter — metered, so it may be spent only within an explicit budget the operator has set;
- GX10 local models — free.

Before each dispatch the governor answers two questions. Which source should run this
archetype now? Is there headroom? Routing follows the operator's preferences:

- Claude for supervision, planning, and the main implementation archetypes;
- Codex as primary implementer for selected archetypes, and as cross-vendor reviewer and
  escalation rung;
- Gemini for review and long-context reading;
- Grok as a third opinion or for research;
- local models for cards, digests, and triage.

The governor **never silently downgrades**. If the preferred source has no headroom, it raises a
decision card or queues the dispatch; it never quietly substitutes a cheaper model. It builds on
the model usage ledger, multi-model usage stats, the coordinator LLM gateway, and the
rate-limit accounting in always-on-agent-automation ri-10, rather than introducing a parallel
ledger.

**Acceptance Outcomes:**
- A single governor query returns the current headroom estimate and observed consumption for
  each of the six capacity sources.
- A dispatch whose preferred source lacks headroom is queued or raises a decision card. A test
  proves that no dispatch is ever executed on a lower tier or a different vendor without a
  recorded decision.
- OpenRouter spend stops at the operator-set budget. A dispatch that would exceed it is refused
  with a card, not executed.
- The routing table is configuration: changing the primary implementer for an archetype from
  Claude to Codex needs no code change.

### Capability: Escalation ladder backed by the evidence ledger

When a worker asks for escalation, or a phase fails repeatedly, the escalation climbs a defined
ladder:

1. more thinking budget on the same model;
2. the premium tier;
3. the frontier tier;
4. a cross-vendor attempt;
5. a human.

Each rung is either auto-approved by policy or raised as a decision card, according to the gate
tiering. The evidence for each step comes from the evidence ledger (evidence-grounded-debugging
ri-01): which facts were established, which hypotheses were eliminated, and what the previous
rung tried. That way a higher rung starts from the evidence rather than from scratch, and the
human at the top gets a card that summarises the whole climb.

**Acceptance Outcomes:**
- An `escalation_request` from a worker moves exactly one rung up the ladder and records the
  rung, the reason, and the ledger refs in the dispatch result.
- A rung that policy auto-approves runs without a human decision. A rung that policy does not
  cover raises a decision card.
- The human-rung decision card links the evidence ledger entries accumulated across all
  previous rungs.
- The ladder never skips the cross-vendor rung before reaching a human unless the governor
  reports no cross-vendor headroom, and that skip is itself recorded.

### Capability: Cloud worker-session adapter (overflow)

When the GX10 is saturated or unreachable, the launcher can place a dispatch on a cloud Claude
Code session instead. It uses the same dispatch-request and dispatch-result contract, the same
decision cards, and the same inbox. Cloud is overflow only, never the default placement, and a
cloud placement is visible in the dispatch result and in the governor.

**Acceptance Outcomes:**
- When the GX10 launcher reports saturation or is unreachable past a threshold, a dispatch is
  placed on a cloud session, and its result flows back through the same inbox and dispatch-result
  schema.
- A dispatch is never placed on cloud while the GX10 has free capacity, as proven by a placement
  test.
- Cloud placement is recorded as a degradation in the dispatch result's `degradations[]`.

### Capability: Gate-to-policy promotion and decisions-per-merge metric

Every resolved decision card is logged with its gate kind, context features, and the answer
given. When a gate kind has been resolved the same way repeatedly under similar evidence, the
system proposes promoting it to an `auto` policy rule. The operator approves the promotion
itself, through one decision card, and later identical gates stop reaching a human. This
capability complements, and should reuse, the decision-point playbook from
evidence-grounded-debugging ri-14 and ri-15.

The system reports **human decisions per merged change** per project and per roadmap as the
headline metric of this epic.

**Acceptance Outcomes:**
- After a configurable number of identical resolutions of a gate kind under matching features,
  a promotion card is raised once, and it is not raised again while it is pending.
- An approved promotion causes the next matching gate to resolve as tier `auto`, with the rule
  ID recorded.
- A report gives human decisions per merged change, by project and roadmap, over a time window.

## Constraints

- The supervisor must never write implementation source. It decomposes, delegates, and
  adjudicates. Implementation runs in write-capable workers in their own worktrees.
- Workers that run autopilot must be top-level sessions (Remote Control, `codex exec`, or cloud
  sessions), never sub-agents of the supervisor, so that per-phase archetype dispatch is
  preserved.
- The system must use a single Claude account. Rotating across several Max seats is out of
  bounds because it conflicts with the terms of service.
- The system must never silently downgrade a model or vendor. Any substitution is either an
  explicit policy rule or a recorded human decision.
- OpenRouter must be spent only within an explicit operator-set budget, and never as a silent
  fallback.
- Operator decision (auto-merge): in this repository, agent PRs shall auto-merge only when CI is
  green on the current head, reviews have converged, and there are no security findings.
  Otherwise an `interrupt` decision card is raised. Other repositories default to `block`.
- Operator decision (delivery): decisions shall be delivered continuously and unbatched for the
  `interrupt` tier.
- Operator decision (notifications): notifications shall use the Claude app and PR events only
  in this epic. A separate phone-push channel is deferred.
- Operator decision (implementers): Codex shall be a primary implementer for archetypes the
  routing table assigns to it, not only a reviewer.
- Operator decision (pilot): evidence-grounded-debugging ri-01 attempt 2, resumed from VALIDATE
  on the GX10 as the first Remote Control worker, is the pilot. Its PR (#690) shall not merge
  until that pilot revalidates it with cross-vendor review.
- The GX10 launcher must refuse unsigned dispatches and repositories not on its allowlist, and
  must not grant a worker a permission mode beyond its archetype's declared mode.
- Decision cards must be self-contained: readable without opening the repository, and
  answerable by voice or a single token.
- The system must degrade visibly. Any sensor, worker placement, or delivery channel that
  falls back must be named in the dispatch result or digest.
- New coordinator tables and endpoints must reuse the existing dispatch-request and
  dispatch-result schemas (multiplayer-collaboration ri-21) and the approval-gate service
  (always-on-agent-automation ri-05) rather than forking them.

## Phases

### Phase 1: Contracts

- Runner-decided gate tiering, decision card schema, `escalation_request` envelope field, and
  Stop-hook turn-end guard.

### Phase 2: Spine

- Coordinator dispatch queue, cross-project decision inbox, and project index.
- Account-wide usage governor, which can proceed in parallel with the queue.

### Phase 3: Execution and delivery

- GX10 launcher for Remote Control and vendor workers, including the ri-01 pilot.
- Continuous decision delivery to the Claude app.
- Escalation ladder backed by the evidence ledger.

### Phase 4: Overflow and learning

- Cloud worker-session adapter (overflow).
- Gate-to-policy promotion and the decisions-per-merge metric.

## Out of Scope

- A custom mobile or web UI. The native Claude app is the interface, and this epic builds no
  front-end of its own.
- Phone push notification channels (ntfy or similar). These are deferred until the Claude app
  plus PR events prove insufficient.
- Making herdr, firstmate, or ntm the operator interface. herdr remains only a process host on
  the GX10.
- Multi-account seat rotation or any scheme that pools several subscriptions of the same vendor.
- Rewriting the autopilot phase machine. This epic changes how gates are tiered and delivered,
  not which phases exist.
- Merging PR #690 now. That waits on the pilot.
- The evidence ledger itself. That is evidence-grounded-debugging ri-01, consumed here.
