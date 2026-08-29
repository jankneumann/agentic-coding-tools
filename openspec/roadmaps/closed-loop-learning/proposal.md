# Closed-Loop Learning: Reactive Recall, Earned Delegation, and the Flywheel

<!--
Drafted by /plan-roadmap --new closed-loop-learning --draft from the Abacus
harness evaluation (2026-08-17). Prior art: the Abacus agent
(https://github.com/empero-org/abacus) — papercuts, memories/rethink,
tethering, and hive maturity tiers. All mechanisms below are clean-room
adaptations to this repo's coordinator-Postgres, multi-vendor architecture;
no Abacus code is ported. Deliberate departure from the prior art: Abacus
triggers lesson recall by exact-string tripwire matching; this epic replaces
that trigger with semantic signal detection (a cheap classifier mapping
diagnoses to a signal-type registry), keeping only the recall economics
(strength decay, shrinking cooldowns, force-recall).
-->

## Motivation

This repository records learning signals exhaustively and consumes almost none
of them. Five persistence stores exist — `memory_episodic`,
`handoff_documents`, `learnings/*.md`, `session-log.md`, and
`factory-intelligence/*.json` — but only the roadmap `learnings/` loop has both
a writer and a reader, and that reader is a regex priority nudge. The
repo-improvement roadmap names this candidly: the learning pipeline is "built
but not turned on" (repo-improvement:ri-12), and dispatch outcomes are
"recorded but never consulted by any routing decision" (repo-improvement:ri-13). Failure lessons tagged
`capability_gap:*` accumulate in episodic memory until a human runs
`/improve-harness` by hand — which nothing schedules.

An external evaluation of the Abacus coding agent (session 2026-08-17, branch
`claude/abacus-harness-eval-upjgfx`) found a working existence proof that
closing these loops changes agent behavior materially: failure lessons with
*tripwire strings* re-injected at the exact moment the same failure recurs,
delegation confidence *earned* from recorded swarm outcomes instead of
statically configured, and a bounded reflection pass that captures knowledge
right before context compaction destroys the evidence. Abacus binds all of
this to a single process's private JSON files; our coordinator inverts that
constraint — a lesson learned by a Codex drone in one worktree can trip for a
Claude validator in a cloud container. That fleet-wide sharing is only
reachable on our side, and it is the strategic payoff of this epic.

Success looks like: every learning store has an automated reader; a recorded
failure lesson pre-empts its own recurrence anywhere in the fleet; and
delegation aggressiveness per vendor and archetype is a number derived from
outcomes, not a hand-set constant.

## Capabilities

### Capability: Learning flywheel scheduler

Turn on the existing `collect-transcripts → episodic memory → improve-harness
→ proposal stub` pipeline as a scheduled job instead of a manual invocation.
A recurring trigger (coordinator cron or harness scheduled task, per the
adapter seam) runs transcript collection and gap analysis weekly, emits a
coordinator issue for any capability gap exceeding a frequency × severity
threshold, and feeds candidate proposals into `/prioritize-proposals`. This
capability supersedes repo-improvement:ri-12 and unblocks
repo-improvement:ri-13; it is sequenced first because every other capability in this
epic consumes the signal it produces.

**Acceptance Outcomes:**
- A scheduled job runs the transcript-collection and gap-analysis pipeline at
  least weekly with no human invocation, and its runs appear in the audit log.
- Capability gaps above the configured frequency × severity threshold
  automatically produce a coordinator issue with the memory-conventions tag
  set attached.
- The repo-improvement roadmap marks repo-improvement:ri-12 superseded by this
  item and gives repo-improvement:ri-13 a typed external dependency.

### Capability: Semantic signal detection and lesson recall

Recall failure lessons by *meaning*, not by string match. A coordinator-served
**signal-type registry** extends the memory-conventions `failure_type:*`
taxonomy: each signal type carries an associated **detection prompt**
describing how that failure manifests. Lessons recorded via the existing
`remember` tool are mapped to one or more signal types alongside the
`capability_gap:*` / `affected_skill:*` tags. Detection runs in a
`PostToolUse` hook (per-harness adapter; Claude Code first) in two stages: a
deterministic **anomaly gate** decides *when* to classify — failed tool
calls, nonzero exits, error-shaped output — and a cheap classifier
(economy-tier / auxiliary model per the archetype vocabulary) then parses the
recent trace and maps its diagnosis to signal types with a confidence score.
The anomaly gate is purely a cost valve; it never decides *what* matched.
Exact string matching is deliberately excluded as a recall mechanism: this
repo has been bitten by its fragility before (the regex ID-matching
`replanner` and stdout regex-scraping are both named "fragile" in the
repo-improvement roadmap), and the same root cause routinely surfaces under
different wording across vendors — the case string tripwires structurally
cannot recall.

Classifier inputs are a bounded, normalized, sanitized trace rather than the
raw transcript. Sanitization precedes external dispatch, fingerprinting,
caching, audit, and logging; raw traces are never persisted, and sanitizer
failure produces neither classification nor injection. Traces, registry
prompts, and lesson bodies are untrusted data inside a fixed structured wrapper
with length limits, escaping, a closed verdict schema, and an allowlist. They
cannot create roles, tools, permissions, or instructions or override the
instruction hierarchy and authorization policy.

On a confident, format-conforming verdict, the lessons mapped to the detected
signal types are injected as additional context at the point of failure — the
one place the model is guaranteed to be looking. The recall economics are
adopted from the Abacus prior art unchanged, since they are independent of
the trigger mechanism: lesson strength decays with a 14-day half-life, the
recall cooldown shrinks from 4 hours toward 5 minutes as strength grows, and
the strongest lessons are force-recalled after two consecutive failed tool
calls. Cost is bounded structurally: detection prompts for all active signal
types are batched into a single windowed classification call (never one call
per lesson), verdicts are cached per session against a context fingerprint,
and malformed or low-confidence verdicts are discarded with no steering power
(the Abacus tether rule). The registry is versioned and updated through the
flywheel: `improve-harness` may propose new signal types and detection-prompt
refinements from clustered capability gaps, so the taxonomy itself learns.
Storage is coordinator Postgres so recall is fleet-wide; a local file
fallback follows the coordination-bridge degradation ladder.

Every persisted lesson carries repository scope, authenticated author, source
session, evidence, confidence, and a lifecycle state of candidate, active,
quarantined, or retired. Only policy-authorized active lessons for the current
repository are eligible for injection. Improve-harness proposals remain inert
until an authorized activation transition; promotion, quarantine, retirement,
and rollback record the actor, prior state, new state, and reason. Lesson
bodies remain quoted data throughout recall and never gain authority to steer
outside their approved injection field.

**Acceptance Outcomes:**
- A lesson recorded from one failure is injected into a later session (any
  vendor, any machine reaching the coordinator) when the same root cause
  recurs under *different surface wording* — asserted by a gen-eval
  paraphrase-recall scenario that exact string matching would fail.
- Classifier invocations are anomaly-gated and batched: no classification on
  clean tool results, one windowed call per detection event, economy-tier
  model, with per-session detection cost attributed in usage accounting and
  capped.
- Tests prove secrets are redacted before dispatch, fingerprinting, caching,
  audit, and logging; sanitizer failure produces no classification or injection.
- Adversarial eval cases cover prompt injection in traces and registry prompts,
  poisoned or unauthorized candidates, repository-scope isolation, and decay
  boundaries; all fail closed with no secret transmission or unauthorized steering.
- Effective strength is recorded strength multiplied by 2 raised to the
  negative elapsed-time-over-14-days power, using an injected UTC clock.
- Fake-clock tests prove S at time zero, S/2 at day 14, and S/4 at day 28
  within tolerance, monotonic decay, and exact surfacing-threshold behavior
  without sleeps.
- Injection volume remains bounded by the cooldown schedule and per-turn cap.
- The signal-type registry with detection prompts is coordinator-served and
  versioned; adding or refining a signal type requires no skill-code change.
- Enablement-by-default is gated on the evaluation beating the no-injection
  baseline (per the semantic-context-injection norm).

### Capability: Earned delegation tiers

Derive a maturity tier per (vendor × archetype) from recorded dispatch
outcomes — clean-run count and failure rate over a rolling window — replacing
"confidence is configured" with "confidence is earned." Starting thresholds
adopt the Abacus priors: a pool leaves the probing tier after 3 clean runs
and reaches full-trust delegation after 12 clean runs with under 30% worker
failure rate; failures pay the tier back down. The tier is exposed via a
coordinator endpoint and injected as guidance into orchestrator skills
(`autopilot`, `implement-feature`, `plan-feature`) at dispatch time: probing
tiers get low-risk separable sub-work and scouts first, mature tiers get
aggressive parallel fan-out. Earned tiers only ever *narrow* within the
statically configured `trust_level` ceiling in `agents.yaml` and the
`TRUST_POSTURE.md` gates — they never exceed them. The per-(vendor ×
archetype) outcome aggregates this capability maintains are the same numbers
the repo-improvement:ri-13 routing scorecard needs, so this capability feeds the
`add-adaptive-model-router` signal ledger rather than competing with it.

**Acceptance Outcomes:**
- The coordinator serves a maturity tier per (vendor × archetype) computed
  from the dispatch ledger, with the computation covered by unit tests
  including tier demotion on failures.
- Orchestrator skills consult the tier at dispatch time and their fan-out
  behavior differs observably between probing and mature tiers (asserted by a
  gen-eval scenario with a synthetic ledger).
- No dispatch ever exceeds the configured `trust_level` or a
  `TRUST_POSTURE.md` gate regardless of earned tier.
- The outcome aggregates are queryable in the shape the repo-improvement:ri-13 routing
  scorecard specifies, and the adaptive-model-router change consumes them
  without schema translation.

### Capability: Compaction-edge knowledge capture

Phase-boundary handoffs capture knowledge at *phase* edges; context
compaction destroys evidence at *context* edges, which is currently
unguarded. Compose with the existing Claude Code `PreCompact` handoff flow
rather than registering a competing hook. Before compaction, a one-shot,
reentrancy-guarded mediated child receives only a bounded sanitized view of
the turn's actions, with no ambient repository or host tools and no inherited
coordinator credential. It returns schema-validated candidate records to a
trusted adapter; only that adapter may perform policy-authorized writes to
episodic memory, signal-type lessons, or the handoff. The reflection
transcript is discarded, and the existing flag-clear and handoff behavior
always continues. Sanitization, dispatch, validation, or coordinator failure
fails open for compaction and produces no reflection writes. Other harnesses
degrade to Stop/SessionEnd hooks through their adapter where PreCompact does
not exist. The pass remains bounded to one dispatch and a small step cap on
an economy-tier model.

**Acceptance Outcomes:**
- When compaction fires, reflection composes with precompact_handoff.py; tests
  prove existing flag clearing and handoff persistence still run exactly once.
- A reentrancy guard permits at most one bounded reflection per compaction.
- The child receives only a sanitized bounded action view, no ambient
  repository or host tools, and no inherited coordinator credential.
- Only schema-valid candidates reach the trusted adapter, which rechecks
  authorization before writing; the child cannot write durable state directly.
- The transcript is discarded; sanitization, dispatch, validation, and
  coordinator failures preserve compaction and the existing handoff behavior
  without reflection writes.
- Harnesses without a PreCompact hook run the same bounded reflection at
  session end via their adapter, with coverage documented in the adapter matrix.

### Capability: Behavioral drift check

An eval-gated, off-by-default drift monitor adapted from Abacus tethering.
At session start, an intent snapshot is derived from the loaded handoff and
the active goal or change proposal. A step-counting hook triggers a periodic
check (economy-tier model) that compares recent activity — user prompts,
assistant text, and tool-call names, never tool outputs — against the intent,
with a reserved share of the check window for user prompts so a long build
phase cannot flush them out. An off-track verdict produces a course
correction injected for a bounded number of subsequent turns, surfaced
visibly in the transcript, and recorded to episodic memory as a
`failure_type:scope_violation` candidate. This capability is sequenced last
and ships behind a flag: it must beat a no-drift-check baseline in a gen-eval
scenario before default-on, per the repo's injection-evidence norm.

**Acceptance Outcomes:**
- A seeded drifting session (gen-eval scenario) receives an off-track verdict
  and a bounded course correction; an on-track session receives no injection.
- The check never includes tool outputs in its window, reserves a fixed share
  for user prompts, and its per-check cost is bounded and attributed in usage
  accounting.
- The feature is off by default, with enablement gated on a recorded
  evaluation verdict of pass against the baseline.

## Constraints

- All persistent learning state must live in coordinator Postgres (with the
  documented file-fallback ladder), never in per-machine local state — fleet
  sharing is the point of reimplementing rather than adopting Abacus's local
  JSON stores.
- No new memory table may ship without both a wired writer and a wired
  automated reader (decision ri-15 in memory-conventions); the deleted
  `memory_working` / `memory_procedural` tables must not be reintroduced.
- Any mechanism that injects context into a running session must be
  eval-gated: off by default until a gen-eval scenario records a pass against
  the no-injection baseline (the semantic-context-injection precedent).
- All harness integration must land behind the existing adapter seam;
  SKILL.md contracts stay vendor-neutral, hooks are per-harness adapter
  concerns, and every capability must degrade gracefully (no-op, never block)
  when the coordinator or a hook surface is unavailable.
- Skill Python must stay deterministic — no LLM SDK calls inside
  `scripts/`; semantic work is dispatched via the orchestrator or vendor
  CLIs (the host-assisted invariant).
- Implementations must be clean-room: mechanisms and parameter values may be
  adopted from Abacus, but no Abacus source code may be ported (its license
  carries an attribution requirement that clean-room work does not trigger);
  Abacus is cited as prior art in the relevant docs.
- Earned-delegation tiers shall never exceed statically configured trust
  ceilings (`agents.yaml` `trust_level`, `TRUST_POSTURE.md` gates).
- Injection volume shall be bounded everywhere (cooldowns, per-turn caps,
  bounded correction lifetimes) so learning mechanisms cannot become context
  pollution.
- Memory writes must use the memory-conventions tag schema; this epic extends
  that schema in exactly one place (the signal-type registry with detection
  prompts) and updates the guide, not per-skill copies.
- External classification receives only bounded, normalized, sanitized input;
  sanitization precedes dispatch, fingerprinting, caching, audit, and logging,
  raw traces are never persisted, and sanitizer failure grants no steering.
- Trace content, registry prompts, and lesson bodies are untrusted data in a
  fixed wrapper and closed allowlisted schema; they cannot create roles, tools,
  permissions, or instructions or override higher-priority authorization.
- Persisted lessons require repository scope, authenticated provenance,
  evidence, confidence, and an auditable lifecycle; only authorized active
  lessons for the current repository may be injected.
- PreCompact reflection must compose with the existing handoff hook, use a
  reentrancy-guarded mediated child with no ambient repository or host tools
  and no inherited coordinator credential, and route schema-valid candidates
  through a trusted authorized writer. Failure must preserve compaction,
  flag clearing, and the existing handoff behavior.
- Lesson recall shall not depend on exact string matching anywhere in the
  detection path; deterministic checks are permitted only as cost gates
  (deciding when to classify), never as match verdicts.

## Phases

### Phase 1: Turn on the flywheel

- Learning flywheel scheduler (supersedes repo-improvement:ri-12, unblocks repo-improvement:ri-13)

### Phase 2: Reactive recall and earned delegation

- Semantic signal detection and lesson recall
- Earned delegation tiers (feeds the repo-improvement:ri-13 scorecard and the
  adaptive-model-router signal ledger)

### Phase 3: Edge capture and drift (eval-gated)

- Compaction-edge knowledge capture
- Behavioral drift check

## Out of Scope

- Adopting Abacus as an execution harness, in whole or in part — the
  evaluation verdict was to adopt mechanisms, not the runtime.
- Adding Abacus as a sixth vendor adapter for open-weight/local-model
  workers; that is a separate future proposal if open-weight workers are
  wanted.
- Training-trace capture for fine-tuning (Abacus's post-assembly request
  capture is structurally impossible from inside vendor harnesses;
  `collect-transcripts` remains the approximation and is only *scheduled*
  here, not extended).
- Implementing routing itself — `add-adaptive-model-router`,
  `implement-the-task-router-vendor-x-location-x-model`, and
  `make-the-orchestrator-obey-the-router` own routing; this epic only
  produces the outcome signals they consume.
- Re-opening decision ri-15 (working/procedural memory tables) or replacing
  the episodic-memory store.
- Per-turn ambient injection of general memories (as opposed to
  trigger-driven tripwire recall); any future proposal there must carry its
  own eval evidence.
