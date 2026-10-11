# Evidence-Grounded Debugging and Verification

## Motivation

Agents now write most of the code in this repository, and the humans who supervise
them no longer hold a line-by-line mental model of it. Cindy Sridharan's *"How to
effectively debug when you no longer understand the code"* (Oct 2026) documents
what this costs. She describes three production bugs. In each one the agent's
first diagnosis was plausible and wrong. It came from reading code, which tells you
what *can* happen, not what *did* happen. In each case the human fixed the
investigation by supplying something the agent could have produced itself: a
**control** (the same client with the feature flag off), a **constraint** (facts
already in the bug report), or a **demand for citations**. An independent
same-model subagent "validated" the wrong cert-reload theory, because the fact that
disproved it had not been gathered yet.

The essay frames debugging as constraint satisfaction over two tiers. The
**factual tier** holds immutable, gathered evidence: logs, traces, profiles,
configs, DNS, kernel state. The **derivative tier** holds hypotheses, which are only
valid when consistent with *every* fact. Its prescription for software factories is
to measure *human interventions per bug* as the honest gauge of autonomy, and to
treat each intervention as a missing piece of infrastructure rather than a "skill
issue".

This repo already has much of the substrate: causal trace IDs, the effects journal,
`intervention-capture`, cross-vendor review routing, gen-eval, and the
failure-record-to-regression work. What it lacks is the **schema that ties
hypotheses to facts** and the gates that enforce it. `debugging-and-error-recovery`
still teaches the human-first order (reproduce → localize → reduce → fix).
`validate-feature` checks pass/fail rather than signal parity. Adversarial review
corroborates findings instead of trying to eliminate them.

**Success:** an agent debugging in this repo starts from gathered facts and a
control, never presents a root cause without fact citations, and is checked by a
reviewer whose job is elimination. Verification gates compare high-fidelity signals
against a baseline rather than only test outcomes. The count of human interventions
per bug is measured, categorized, and trends down.

## Capabilities

### Capability: Evidence ledger schema and validator

A shared, versioned schema (`evidence-ledger.schema.json`) and deterministic
validator module that every later capability consumes. **Facts** carry `id`,
`kind`, `source`, `gathered_by`, `host`, `time_window`, `tool_version`, and
`role ∈ {variable, control}`. Once recorded they are immutable: the validator
rejects in-place edits, and a disputed fact gets a `reverify_request` instead.
**Signals** are derived from fact pairs (variable vs control) and classified as
`signal` or `noise`. **Hypotheses** carry `cites: [fact_id]`, an optional
`components` list for multi-cause hypotheses, and a `status`. The validator also
computes the **hypothesis-by-fact matrix** (✓/✗/?), column counts (signal
strength) and row completeness (all-✓ survivors). It rejects any `root_cause`
that cites no facts, is contradicted by a fact, or is a multi-cause hypothesis with
a component that is not necessary.

**Acceptance Outcomes:**
- The schema validates a fixture ledger and rejects fixtures that have an
  uncited root cause, a contradicted root cause, and a mutated fact.
- The validator emits the matrix with per-signal hypothesis counts and flags the
  all-✓ rows.
- The necessity check fails a combined hypothesis when removing one component
  leaves no fact unexplained.

### Capability: Rewrite debugging-and-error-recovery around the two-tier method

Rewrite the skill so the default flow is: gather facts (cheapest layer first) →
establish a control → separate signal from noise → rank signals by how many
hypotheses each one admits → validate the leading hypothesis against every fact.
Include the **five refinement tactics** (re-verify fact provenance, split overly
coarse hypotheses, merge overly fine ones, combine complementary ones, then form a
new hypothesis from the facts). Include **progressive signal discovery**: go one
layer down only when every signal is weak, and stop at the first strong signal.
Treat code reading as a late step. Add a **reproduction-parity gate**: a
reproduction is a hypothesis and counts only if it produces the strongest factual
signal. Keep the existing pytest/bisect mechanics as tools within the new flow
rather than as its spine. The skill writes an `evidence-ledger.yaml` per
investigation.

**Acceptance Outcomes:**
- Running the skill on a seeded bug produces a schema-valid evidence ledger with a
  control fact and a computed matrix.
- A behavioural skill test fails if the skill proposes a root cause before
  recording at least one control fact.
- A reproduction that does not reproduce the recorded strongest signal is marked
  `rejected` in the ledger and is never cited as evidence.

### Capability: Eliminative adversarial review mode

Add an `eliminate` mode to `parallel-review-implementation` and to
`iterate-on-implementation` (when it is debugging). The reviewer's job is to
**contradict**, not corroborate. It must (a) find one fact that contradicts the
hypothesis, (b) flag every claim without a fact citation, which then gets culled,
(c) check that the control is not broken the same way as the variable,
(d) re-check fact provenance (host, window, tool version), and (e) run the removal
test on each component of a multi-cause hypothesis. Dispatch routes the reviewer to
a **different vendor/model than the author**, with a context slice drawn from the
ledger rather than the author's transcript, so the review is not one opinion
counted twice. Findings use the existing `review-findings.schema.json` with new
finding types.

**Acceptance Outcomes:**
- In eliminate mode the dispatcher refuses a reviewer whose vendor/model matches
  the author's unless the operator overrides, and records the override.
- A seeded ledger with an uncited claim and a contradicting fact yields findings of
  type `uncited_claim` and `contradicting_fact`.
- The reviewer prompt contains the ledger and excludes the author's reasoning
  transcript.

### Capability: Verification-signals contract in plan-feature

Planning must state *how correctness will be observed* before code is generated.
`plan-feature` adds a required `verification-signals` section to proposals:
named quantitative signals (e.g. RPC count per request, external calls, DB queries,
DNS lookups, token usage), the layer that emits each one, the control or baseline
to compare against, and the tolerance. `iterate-on-plan` gains a finding for
"verification signal missing or not emitted at the top layer". This makes default
data collection a design-time obligation.

**Acceptance Outcomes:**
- `openspec validate --strict` (or a repo-local check) fails a new proposal that
  lacks a `verification-signals` section, with an explicit opt-out marker for
  docs-only changes.
- `iterate-on-plan` reports a finding when a declared signal names no emitting
  layer or no baseline.

### Capability: Signal snapshot capture and baseline-diff gate

`gen-eval` and `validate-feature` record a **signal snapshot** per run: the
signals declared in the change's `verification-signals`, plus a default set from
coordinator instrumentation (call counts, latency distributions, external calls).
Snapshots are stored per commit. A **baseline-diff gate** compares the PR head's
snapshot with the base branch's last green snapshot and flags any deviation beyond
tolerance even when every test passes. This is automated canary analysis for agent
PRs. The gate starts **advisory** (it reports only) and is promoted to blocking per
signal once its false-positive rate is measured.

**Acceptance Outcomes:**
- `validate-feature` writes a snapshot JSON keyed by commit SHA and attaches the
  diff against the base branch's last green snapshot to its report.
- A seeded change that doubles an RPC count with all tests green is flagged by the
  gate.
- Each signal has a recorded mode (`advisory`/`blocking`) and a measured
  false-positive rate before it can be set to blocking.

### Capability: Default-on fact collection (`collect-facts`)

A `collect-facts <trace-id | change-id | PR>` command assembles the factual tier
from sources the agent would otherwise have to pull piecemeal: coordinator audit
trail, effects journal entries, the causal-trace-linked events, git range and
diff stats, resolved config and feature-flag values, vendor/model/tier used,
relevant episodic memories, and the latest signal snapshots. It writes them as
facts into an evidence ledger with full provenance. Access is **read-only, scoped
to the investigation, time-limited, and audited**, and secrets are redacted before
facts are written.

**Acceptance Outcomes:**
- Given a causal trace ID, `collect-facts` produces a schema-valid ledger whose
  facts each carry source, gathered_by, time window, and tool version.
- Each source is optional: a missing source (e.g. no effects journal yet) produces
  an explicit `source_unavailable` fact rather than a failure.
- A secret-pattern fixture placed in a source is redacted in the output, and every
  invocation writes an audit record.

### Capability: Human-interventions-per-bug metric and gap taxonomy

Extend `intervention-capture` records with a **gap category** from a closed
vocabulary: `missing_control`, `missing_constraint`, `missing_citation`,
`missing_data_source`, `wrong_layer`, `policy_decision`, `other`. Link each record
to the evidence ledger of the investigation it corrected. `agent-metrics` reports
**interventions per bug** (total and per category) over time. `improve-harness`
ranks categories by frequency and emits proposal stubs for the top ones. This turns
a "skill issue" into an infrastructure backlog.

**Acceptance Outcomes:**
- An intervention record without a gap category from the vocabulary fails
  validation.
- `agent-metrics` outputs interventions-per-bug with a per-category breakdown for
  a fixture dataset.
- `improve-harness` emits at least one candidate-work stub per category that
  exceeds a configured frequency threshold.

### Capability: Decision-point policy playbook

When a human resolves an escalation that turns on a judgment call (roll back or
fix forward, escalate to another owner, choose between alternative fixes, accept a
signal regression), the resolution is recorded as a **policy entry**: a trigger
condition, the decision, the rationale, the author, and a scope. Agents consult the
playbook before escalating and apply a matching policy automatically, citing it.
Escalations with no matching policy still go to a human, with every option and its
tradeoffs stated. Builds on `owner-routed-escalation`.

**Acceptance Outcomes:**
- Resolving an escalation offers to save a policy entry, which validates against a
  playbook schema.
- A later escalation matching an existing policy's trigger is auto-resolved with a
  citation to the policy ID, and the auto-resolution is audited.
- An unmatched escalation presents at least two options with tradeoffs, not a
  single recommendation.

### Capability: Signal-asserting regression scenarios

Extend the failure-record-to-regression scenarios so each scenario asserts the
**signal that identified the original bug**, not only the final outcome. Gen-eval
scenarios gain a `signal_assertions` block that names a signal, the expected
value or relation against a control, and the source layer. When a debugging
session closes with a validated root cause, the skill proposes a scenario seeded
from the ledger's strongest signal.

**Acceptance Outcomes:**
- The gen-eval scenario schema accepts `signal_assertions`, and the runner fails a
  scenario whose signal deviates even when its outcome assertion passes.
- Closing a debugging ledger with a validated root cause emits a draft scenario
  whose `signal_assertions` reference the ledger's strongest signal.
- At least three existing converted regression scenarios are upgraded with signal
  assertions.

## Constraints

- Facts in an evidence ledger must be immutable once recorded. A disputed fact is
  re-gathered as a new fact, never edited.
- No root cause may be reported, committed, or used to justify a fix without
  citations to facts in the ledger.
- Eliminative review must run on a vendor/model different from the author's
  unless an operator override is recorded.
- All fact collection must be read-only, scoped to one investigation, time-limited,
  audited, and secret-redacted.
- New gates (baseline-diff, verification-signals) must ship advisory-first and only
  become blocking with measured false-positive data.
- Every capability must reuse existing substrate (causal trace IDs, effects
  journal, intervention-capture, review-findings schema, gen-eval format,
  closed-loop-learning store) rather than create parallel stores.
- Skill changes follow the repo convention: edit `skills/`, tests go in
  `skills/tests/<skill-name>/`, and tests resolve OpenSpec paths via
  `change_dir()`.

## Phases

### Phase 1: Foundation

- Evidence ledger schema and validator

### Phase 2: Method

- Rewrite debugging-and-error-recovery around the two-tier method
- Eliminative adversarial review mode
- Default-on fact collection (`collect-facts`)
- Verification-signals contract in plan-feature

### Phase 3: Gates and feedback loops

- Signal snapshot capture and baseline-diff gate (depends on the verification-signals contract)
- Human-interventions-per-bug metric and gap taxonomy (depends on the ledger and the debugging rewrite)
- Signal-asserting regression scenarios (depends on the ledger and snapshot format)
- Decision-point policy playbook

### Cross-roadmap dependencies

- Gap taxonomy extends `intervention-capture` (`multiplayer-collaboration:ri-18`).
- Policy playbook builds on `owner-routed-escalation` (`multiplayer-collaboration:ri-09`).
- `collect-facts` keys on `causal-trace-ids` (`multiplayer-collaboration:ri-03`); the
  effects journal (`durable-execution:ri-01`) is an optional source.
- Signal-asserting scenarios extend `convert-failure-record-to-regression-scenarios`
  (`skill-rightsizing:ri-01`).

## Out of Scope

- Production-environment access for agents in downstream user projects (the
  essay's "develop against production"). This roadmap covers this repo's own
  coordinator and skills. Graduated production access is a separate security epic.
- "Full stack in a box" local replicas of production. The essay argues against it.
- Kernel-, packet- or OS-level collectors. `collect-facts` covers coordinator-
  and repo-level sources. Lower layers are listed as future progressive-discovery
  adapters only.
- Replacing `intervention-capture`, `owner-routed-escalation`, or the
  closed-loop-learning store. This roadmap extends them.
- Formal verification or property-based testing frameworks.
