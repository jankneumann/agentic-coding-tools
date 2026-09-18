# Where a System One model (TypeSafe Jev) fits in this codebase

**Status**: Assessment (2026-09-18). No code changed by this document.
**Scope**: every decision site in `skills/`, `agent-coordinator/`, and `packages/` that either
(a) encodes a judgment as a hand-tuned rule, or (b) asks a text-generating LLM to emit a small
structured verdict.

## Summary

Jev is a good fit for a narrow, well-defined class of call sites in this repo: places where code
already needs a **closed-vocabulary verdict** (a label, a yes/no, a 1–5 grade) over **unstructured
state** (a diff, a proposal, a transcript, a PR), and where the consumer is code that can act on a
**probability** rather than a person who needs an explanation. The repo has more of these than most,
because it already separates `deterministic` from `judgment` evidence and already treats model
verdicts as advisory inputs to gates computed in code.

Twenty call sites clear that bar. They fall into three groups:

| Group | Count | What changes |
|---|---|---|
| **A. Brittle rule → calibrated judgment** | 7 | A keyword list, Jaccard band, path prefix or weighted sum becomes a `Choice`/`Noul`/`Score` question; the code keeps the threshold and the fallback. |
| **B. LLM prompt → typed decision** | 5 | A prompt that asks a frontier or economy model to return a tiny JSON object is replaced (fully or as a first stage) by one `system_one` call. |
| **C. Loop switch → confidence-routed decision step** | 8 | The label an orchestrator loop switches on (a phase outcome, a fix disposition, an escalation action) stops being the actor's self-report or a fixed table and becomes a judged `Choice` whose probability decides whether code acts, asks for approval, or escalates. Design in the companion note [`jev-twelve-factor-decision-loops.md`](jev-twelve-factor-decision-loops.md). |

Nine further sites were considered and should be **left alone**; the reasons are listed, because
in this repo the reasons matter as much as the picks.

The single most important constraint: **Jev cannot emit free text.** Every site that needs a
rationale, a `capability_gap` description, a `file:line` citation, or a 200-character
justification keeps an LLM for that part. The recommended pattern is therefore usually a
**two-stage** call: Jev screens or grades every item cheaply and calibratedly; an LLM writes prose
only for the items that cross a threshold.

## What Jev is, in the terms this repo uses

Sources: TypeSafe's SDK and skill repositories (fetched directly) and press coverage of the launch
(the typesafe.ai domains are blocked by this session's egress proxy).

- **Contract.** One call: `client.system_one(state=..., questions={...})`. `state` is a JSON
  document (any shape). Each question is one of three primitives:
  - `Choice(instructions, criteria={label: description|None})` → `ChoiceAnswer(choice, confidence, probabilities: dict[label, float])`
  - `Noul(instructions, criteria={"true": ..., "false": ...})` → `NoulAnswer(noul: float)` — the probability of yes, no separate confidence
  - `Score(instructions, criteria=[level0, level1, ...])` → `ScoreAnswer(score: float, confidence, probabilities: dict[int, float], legend)`
  All questions in one call are answered **in parallel over the shared state**, in one pass.
- **Calibration.** Trained with proper scoring rules (Brier) on ground truth, so an 85 % answer is
  right about 85 % of the time. This is the property the repo's `calibrate-llm-judge-against-human-labels`
  change is trying to *measure into* an LLM after the fact; Jev ships with it.
- **Limits.** State plus the longest question must fit in about 32 K tokens (roughly 150 K
  characters); state plus all questions in about 64 K. At most 255 options per `Choice`. No
  image input. **No free text output.**
- **Cost and latency.** About $0.042 per million input tokens, output free; roughly 70–500 ms per
  call. A 16 K-token state costs about $0.0007.
- **SDK.** `typesafe-sdk` on PyPI (`uv add typesafe-sdk`), `TYPESAFE_API_KEY`, sync and async
  clients, typed errors, `RetryPolicy`. `system-one-adapter` is a drop-in `TypeSafeClient`
  replacement backed by OpenAI or Anthropic APIs — useful as this repo's dry-run / CI substitute,
  with the caveat that the adapter's probabilities are an LLM's self-report and are **not**
  calibrated. There is also a Claude Code plugin (`claude plugin install typesafe@typesafe-ai`)
  whose skill carries the design guidance summarised below.
- **Design guidance from the vendor skill.** One narrow judgment per question; put the judgment in
  `instructions` and the answer space in `criteria`; give each question enough state (source text,
  identities, relationships, policies); include a no-match option when nothing may fit; evaluate
  thresholds on your own data and consequences; "verify and escalate: send uncertain or failing
  cases to a person or reasoning model."

### The fit test used below

A site is a candidate only if all five hold:

1. The output is a **closed set** — enum, boolean, or ordered rubric — or can be decomposed into several.
2. The input is **judgment over unstructured state**, not a fact the code can look up (a branch
   prefix, a file path, a schema field).
3. **No prose is required** from the model at this step, or prose can be deferred to a second stage.
4. The state fits in **32 K tokens**, or the site already has a size gate that bounds it.
5. The consumer can act on a **probability with a threshold**, and a degraded path exists when the
   call fails. Consistent with `consensus_synthesizer.JUDGMENT`, a Jev answer is *judgment*
   evidence: it never overrides a deterministic gate, and it never enters `context_eval.verdict`.

## Group A — brittle deterministic rules that should become calibrated judgments

Ranked by expected value. Each entry names the rule as it exists, the questions that replace it,
what stays deterministic, and the risk.

### A1. Cross-vendor finding matching — `consensus_synthesizer.match_score`

`skills/parallel-infrastructure/scripts/consensus_synthesizer.py:335` decides whether two vendors
reported the *same* defect with hand-tuned bands: line overlap → 0.95/0.8, identical normalised
snippet → 0.9, otherwise Jaccard token overlap over the descriptions with three cut-offs, against
`MATCH_THRESHOLD = 0.6` (line 427). The module's own docstring admits the bands are "calibrated so
each is reachable … independent LLMs never produce verbatim-identical descriptions." PR #484 (see
`add-orchestrator-adjudication-review-gate`) merged with 23 findings and `match_score: 0.0` on all
of them, two of which were real defects phrased differently by two vendors.

**Replace with**: for each candidate pair that shares axis and file (keep those two deterministic
prefilters), one `Noul("Findings A and B describe the same underlying defect")` with the two
findings as state. Batch all pairs for one file into one call as N questions over shared state.
Keep the line-overlap and snippet bands as fast paths that skip the call.

**Why it matters beyond dedup**: `rescope-review-convergence-disagreement-routing` wants to route
*contested* findings to a human. A calibrated "same defect" probability is exactly the signal that
distinguishes "two vendors disagree" from "two vendors phrased one thing differently."

**Risk**: low. Output already feeds a threshold; the fallback is the existing bands.

### A2. Transcript struggle triage — `collect_transcripts.triage`

`skills/collect-transcripts/scripts/triage.py:137` computes
`retries×1 + tool_errors×2 + scope_violations×3 + user_corrections×2.5` and buckets it at 5 and 10.
Scope violations are counted by six substrings (line 67); a user message after any tool error is a
"correction." The sibling prompt `prompts/triage_v1.md` asks an LLM to do the same counting and is
wired nowhere.

**Replace with**: keep the four counters (they are facts about the event stream), then ask Jev
over a compacted transcript plus the counters:
`Choice(struggle_level, {none, low, medium, high})`,
`Noul("A human had to redirect the agent after a failure")`,
`Noul("The agent attempted work outside its declared scope")`,
`Noul("This session warrants deep analysis")` → replaces `flagged_for_deep_analysis`.
Deep analysis (`deep_analyze.py`) stays an LLM because `capability_gap` is prose.

**Risk**: low. Transcripts can exceed 32 K tokens; `normalize.py` already produces a compact event
form and the triage only needs the assistant/user/tool-result text, not tool payloads.

### A3. Implementation strategy selection — `implementation_strategy_selector`

`skills/autopilot/scripts/implementation_strategy_selector.py:73` sums four binary criteria
(`loc < 200`, `alternatives_count ≥ 2`, `kind ∈ {algorithm, data_model}`, `vendors ≥ 3`) and picks
`alternatives` at ≥ 2.0. The signature already carries `design_path` "reserved for future
inference" (line 131) — a hook waiting for exactly this.

**Replace with**: `Choice(strategy, {alternatives: "≥2 plausible designs worth comparing",
lead_review: "one obvious implementation; review is the value"})` with the package YAML and the
matching design.md section as state; keep the vendor-count gate deterministic (it is a fact about
availability, not a judgment). Use `confidence` to fall back to `lead_review` when the model is
unsure, since `alternatives` costs three implementations.

**Risk**: low; the decision is already advisory and reversible.

### A4. Vendor-review eligibility — `vendor_review.check_review_eligibility`

`skills/merge-pull-requests/scripts/vendor_review.py:38,103` skips multi-vendor review for PRs
under 50 changed lines or 3 files. A 40-line change to `guardrails.py` or a Cedar policy is
"small" by this rule; a 300-line docs move is "large."

**Replace with**: `Noul("This PR warrants independent multi-vendor review")` and
`Score(risk, ["docs/config only", "internal refactor", "behaviour change", "security or data path"])`
over title, body, file list, and diff stat (not the diff). Keep the origin skip list
(`dependabot`, `renovate`, Jules subtypes) deterministic — those are facts about provenance.

**Risk**: low; the current threshold stays as the degraded path.

### A5. Decision-tag backfill — `backfill_decision_tags`

`skills/explore-feature/scripts/backfill_decision_tags.py:26` maps seven capability tags to
keyword lists ("lock" → agent-coordinator, "skill" → skill-workflow) and already emits a
`confidence` the report buckets at 0.5 and 0.8 (line 193). Keyword confidence is not calibrated;
Jev's `ChoiceAnswer.probabilities` is, and the report format needs no change.

**Replace with**: `Choice(capability, {seven tags + "none"})` over the decision title and
rationale, batched as many questions over one session-log phase as state. This is the textbook
Jev shape (ticket routing with a no-match option).

**Risk**: none operationally; the script proposes, an agent reviews before edits.

### A6. Fix-tier classification — `fix_scrub.classify`

`skills/fix-scrub/scripts/classify.py:33,44` decides a TODO marker has "sufficient context" if
≥ 10 characters follow it, and a deferred finding has a fix if the text contains "proposed fix"
or "resolution." Both are judgments dressed as string tests.

**Replace with**: `Noul("An agent could act on this marker without asking a human")` and
`Noul("This finding includes a concrete, applicable fix")`; keep `_is_ruff_fixable` (a fact about
ruff rule prefixes) and the source-based routing deterministic.

**Risk**: low; tiers are a plan, not an action.

### A7. Deployable-surface derivation — `gate_logic.classify_deployable_surface`

`skills/validate-feature/scripts/gate_logic.py:102,383` decides whether a change needs the
container phases (smoke, security, E2E) by path prefix, failing closed to "deployable" when
unsure. Fail-closed is correct; the cost is running Docker-dependent phases on changes that do not
need them.

**Replace with (narrowly)**: only for the `unknown` bucket, `Noul("This change alters the
behaviour of a running service")` over the file list and diff stat, accepted as *non-deployable*
only above a high threshold (say 0.9), otherwise still fail closed. Declared frontmatter and the
proven-non-deployable prefix set stay authoritative.

**Risk**: this is a gate input. Record `DEGRADED`-style provenance ("derived by system_one, p=0.93")
in the report so a reviewer can see it, mirroring how `autopilot.record_degraded` works.

## Group B — LLM prompts whose job is a typed decision

### B1. Autopilot GATEKEEPER — `autopilot._phase_gatekeeper`

`skills/autopilot/scripts/autopilot.py:1492` dispatches a **premium-tier** read-only judge
(archetype at `agent-coordinator/archetypes.yaml:180`) that reads `gate_signals` plus the plan
artifacts and returns one of `proceed` / `proceed_with_review` / `escalate`. The headless
fallback (`complexity_gate.default_gate_verdict`, line 237) is a two-key rule.

This is the cleanest fit in the repo. The rubric is already two named dimensions:

- `Score(verifiability, ["no acceptance criteria", "criteria exist but untestable",
  "testable criteria for most outcomes", "every outcome has an objective check"])`
- `Score(risk, ["reversible, narrow", "reversible, broad", "hard to reverse, narrow",
  "hard to reverse, broad"])`
- `Choice(verdict, {proceed, proceed_with_review, escalate})`

State = `gate_signals` + proposal.md + tasks.md + the work-packages summary; a typical change fits
in 32 K tokens, and the site already knows when it does not (`gather_signals` counts packages and
LOC). The gate outcome would then be **computed in code from the two scores** — the pattern
`add-orchestrator-adjudication-review-gate` explicitly prefers ("never asserted by the
adjudicator") — with the `Choice` retained as a cross-check.

Saves a premium-tier call per autopilot run and replaces an uncalibrated three-way verdict with two
calibrated distributions the operator can threshold. Keep `--force` and the scope-safety floor
untouched.

### B2. gen-eval semantic judge — `semantic_judge.evaluate_semantic`

`packages/gen-eval/src/gen_eval/semantic_judge.py:22,99` asks an LLM for
`{"pass": bool, "confidence": 0–1, "reasoning": str}` and applies `min_confidence`. The confidence
is the model's self-report and, as the active `calibrate-llm-judge-against-human-labels` change
documents, that is the number nobody trusts.

**Replace with**: `Noul("The actual output satisfies the criteria")` over `{criteria, actual_output}`;
`noul` becomes the confidence, and `min_confidence` works unchanged. `reasoning` is lost. The
module already returns `skip` when the backend is unavailable, so the degradation path exists.
Where a failure needs an explanation for a human, call the LLM **only on failures**, which is the
two-stage pattern.

### B3. Diff-grounded fact check — `fact_check.run`, first stage

`skills/parallel-infrastructure/scripts/fact_check.py:215` sends every finding batch to an
economy-tier LLM with a 90-line prompt and parses a tool-call-shaped JSON. Ground A ("the code the
finding describes is not in the subject file's diff") is a pure `Noul`. Ground B needs a quoted
diff line that the code then verifies literally (`_evidence_line_in_subject_diff`), which Jev
cannot produce.

**Replace with**: stage 1, one call with one `Noul` per finding for Ground A and one
`Noul("A line in this diff directly contradicts the finding's central claim")` as a *screen*;
stage 2, the existing LLM prompt only for findings whose Ground-B probability exceeds a threshold.
Protected-subject vetoes stay in code. Most review batches would never reach stage 2.

### B4. Coordinator audit triage — `audit_triage.drain_and_classify`

`agent-coordinator/src/audit_triage.py:140` hands a batch of audit entries to an LLM and expects a
list of findings, each with a free-text `capability_gap`. The prompt says "prefer recall over
precision" — a calibration statement.

**Replace with (two-stage)**: stage 1 per session batch:
`Noul("This session shows a capability gap in the harness")`,
`Choice(failure_type, {six enum values + none})`,
`Score(severity, [low, medium, high, critical])`. Stage 2, the current LLM prompt only for
sessions above the recall-oriented threshold, seeded with the stage-1 labels so its output is
constrained. `validate_finding` (line 106) stays as is. The hot-path ring buffer is untouched.

### B5. Supervise rubric scoring — `supervise` analyst dispatch

`skills/supervise/templates/rubric-prompt.md` asks the analyst archetype to score up to 20 stubs
on five factors (1–5) with a ≤ 200-character justification each, under a 120-second timeout with
one retry, and rejects "missing, partial, invalid, or late output." That last clause is a
description of the failure mode Jev was built to remove: 100 `Score` questions over one ≤ 64 KiB
manifest fit in a single call and return in under a second with a 0 % structural error rate.

**Blocker**: the archived contract `rubric-score.schema.json` marks `justification` **required**
per factor. Options, in order of preference: (1) relax `justification` to optional and let the
digest render the `Score` legend level instead; (2) keep an LLM justification pass for the top-N
stubs only; (3) leave as is. The digest is deterministic and host-assisted by design
(`digest.py` docstring), so this is a contract change, not a code-architecture change.

## Group C — orchestrator loops whose switch should route on confidence

Groups A and B replace a *value*. Group C changes *who decides the next step* in the repo's
12-factor loops. The autopilot already has the shape those factors prescribe: an explicit
transition table, sub-agents that return only `(outcome, handoff_id)`, `ESCALATE` as a phase,
`loop-state.json` as the reducer's state. What it lacks is a calibrated judge between state and
switch: outcome labels are either the actor grading itself (`complete`, `fixed`, `proceed`) or a
fixed table (`EscalationHandler`, the stall rule). The companion note defines one primitive,
`decide_intent(state, intents, fallback, ...)`, that returns a label plus its distribution and
lets the code route by probability: below an act floor → the human intent; an irreversible
intent below an approval floor → pause between selection and invocation; service unavailable →
the existing rule, marked degraded. Every decision is appended to the loop's event log with its
distribution, which makes it replayable and gives the calibration measurement for free.

| # | Loop decision point | Today | Jev question(s) | Floor kept in code |
|---|---|---|---|---|
| C1 | Phase outcome, `autopilot.apply_phase_outcome` | Sub-agent's self-reported outcome string | `Choice(outcome, phase's allowed outcomes)` + `Noul("evidence supports the claimed outcome")` over handoff, diff stat, test tail | Disagreement below approval floor → `escalate` with both labels |
| C2 | Convergence continue/stop, `convergence_loop.converge` | `trend[-1] >= trend[-stall_window]`, `max_rounds` | Per finding `Choice(disposition, {fix_now, defer, reject_out_of_scope, needs_human})`; per round `Noul("another round will reduce blocking findings")` | `max_rounds` ceiling; `needs_human` parks a disagreement |
| C3 | Escalation action, `EscalationHandler.handle` | One prescribed action per type | `Choice(action, EscalationAction values)` over summary, impact, attempt history | `REQUIRE_HUMAN` mandatory where the table says so; Jev chooses only among recoverable actions |
| C4 | Roadmap item failure, `orchestrator._handle_failure` | `replan` boolean from `_normalize_outcome` | `Choice(next, {retry_same_vendor, retry_other_vendor, skip_item, request_replan, escalate})` | `request_replan` still passes the `REPLAN_REQUIRED` gate |
| C5 | Merge thread triage, `execute_plan` `delegate_comments` | Any unresolved thread → delegate | Per thread `Choice({needs_code_change, needs_reply_only, already_addressed, outdated})` over thread text and current file diff | Fact-based gates (staleness, security, live state) stay deterministic |
| C6 | Task routing profile, `implement-the-task-router-vendor-x-location-x-model` | Nothing or an LLM produces the profile | `Score(duration)`, `Noul(interactive)`, `Noul(needs_secret)`, `Choice(scope)` | Routing rules stay deterministic in `routing.yaml`; Jev only fills the typed inputs |
| C7 | Human reply intent, `relay.parse_reply` | First-word keyword | `Choice({approve, deny, resolved, skip, guidance})` | Sender allowlist; `approve` requires `p ≥ 0.97`; else `guidance`. Security review item. |
| C8 | Retry classification, `phase_fixer` and roadmap dispatch | Consecutive-failure count | `Noul("same failure as the previous attempt")`, `Noul("transient; retry unchanged likely to succeed")`, `Choice(failure_type, D4 enum)` | Retry ceiling unchanged; same-and-not-transient stops early |

Boundaries that hold for every row: Jev picks a label, never parameters, so any branch that
needs free-form arguments is a branch whose action is an LLM; it never drives a coding
sub-agent's inner Read/Edit/Bash loop; it routes toward gates and never around one; and every
row keeps its current rule as `fallback`.

## Considered and left alone

| Site | Why not |
|---|---|
| `guardrails.check_operation` regex block list (`guardrails.py:64,308`) | Fail-closed destructive-command detection on a hot path with a latency histogram. A 70–500 ms network call does not belong there, and a probabilistic "is this destructive?" must never *loosen* a block. At most, an **advisory** `Noul` on the `warn` tier, off the hot path. |
| `risk_scorer.compute_score` (`risk_scorer.py:61`) | Inputs are already structured numbers (trust level, op class, violation count). There is no unstructured state to judge. |
| `model_routing.resolver` | Already a Bayesian blend of prior and posterior with explicit confidence weighting. It is the model of what the rest of the repo should look like, not a candidate. |
| `context_eval.verdict` | The module's thesis is "no judge parameter, no waiver." Adding one would be a reviewable diff by design; do not open it. |
| `semantic_context` ranking | Determinism is load-bearing (design D5); a reranker would break the reproducibility the tests hold. |
| `github_classifier.classify_pr` (`github_classifier.py:48`), `classify_kind`, `event_bus.classify_urgency`, `expedite` | Facts about branch names, authors, paths, and report presence. Rules are the right tool. The Jules subtype title regexes are the one judgment inside, and it is low value. |
| `relay.parse_reply` (`relay.py:39`) | First-word keyword matching *is* brittle ("Looks good, go ahead" falls to `guidance`), and a `Choice{approve, deny, resolved, skip, guidance}` would be smarter. But this is a human **authorization** channel; widening what counts as "approved" changes the trust model. If pursued: allowlist stays, approval requires `probabilities["approve"] ≥ 0.97`, everything else stays `guidance`. Treat as a security review item, not a quick win. |
| Secret and PII sanitizers (`sanitize_session_log.py:47,143`, `roadmap-runtime/sanitizer.py`) | Specific-pattern tiers (AWS, GitHub, Anthropic keys) are correct as regex. The `generic-secret` heuristic (any 21+ char token) over-redacts and a `Noul("This token is a credential")` would cut false positives — but sending suspected secrets to a third-party API to ask whether they are secrets is the wrong direction. Leave alone unless a self-hosted System One endpoint appears. |
| `plan-roadmap` generation, `deep_analyze`, adversarial review prompts | These produce prose, YAML, or open-ended findings. Not the primitive. |

## Integration seam

The repo dispatches to vendors as CLIs (`agents.yaml` `cli:` blocks) or OpenAI-compatible HTTP
(`openai_compat_adapter.py`, `provider_dispatch._dispatch_local`). Jev is neither: it is a
different call shape, not another chat model. Do not model it as a vendor or an archetype tier.

Recommended shape, mirroring how `skills/shared/github_classifier.py` is the portable home for
shared logic:

- `skills/shared/system_one.py` — two entry points. `decide(state, questions, *, site)` for
  Groups A and B, and `decide_intent(state, intents, *, fallback, human_intent, act_floor,
  irreversible, approve_floor, site)` for Group C, which wraps one `Choice` in the
  confidence-routing rules above and appends the decision to the caller's event log. Both: read
  `TYPESAFE_API_KEY`; returns `None` (never raises) when the key is absent, the network is
  unavailable, or state exceeds the token budget, so every caller's existing rule remains the
  fallback; records `site`, latency, `usage.input_tokens`, and the answered probabilities to the
  existing Langfuse hook; and is the only place `typesafe_sdk` is imported.
- `skills/pyproject.toml` — add `typesafe-sdk` under a new optional extra `decisions`, alongside
  `sdk`, so the cloud harness's PyPI-only network policy is respected and nothing new is required
  at import time.
- **Dry-run / CI** — the repo's convention is `--dry-run` with no API calls. Use
  `system-one-adapter` (Anthropic provider, `llm_answer_mode="probabilities"`) only for
  *behavioural* tests of the wiring; mark its probabilities uncalibrated in test names. Unit tests
  stub `decide`.
- **Thresholds live in config, not code.** Per site, in `architecture.config.yaml` or the skill's
  own config, next to the existing thresholds they replace (`MATCH_THRESHOLD`,
  `SMALL_PR_MAX_CHANGED_LINES`, `min_confidence`). Follow `context_eval`'s rule that no threshold
  literal appears in a scoring module.
- **Provenance.** Every Jev-derived value that reaches a report carries
  `evidence_class: judgment` and the probability. This keeps the deterministic/judgment boundary
  the consensus synthesizer already enforces.
- **Security boundary.** Reuse the supervise rubric's framing: everything in `state` is untrusted
  data. Jev cannot follow injected instructions into free text, which removes one class of prompt
  injection, but a poisoned finding description can still bias a `Noul`. Thresholds and vetoes
  in code remain the defence.

## Pilot order and acceptance

0. **The helper, fallback-only** — land `skills/shared/system_one.py` with the `fallback` path
   and the event-log write but no network call. Every existing rule decision in Group C becomes
   a recorded, replayable event before any model is consulted.
1. **B2 semantic judge** — smallest surface, already has `skip` semantics, and the
   `calibrate-llm-judge-against-human-labels` change is about to produce a 40-item human-labelled
   set. Score Jev's `noul` against those labels with Cohen's kappa exactly as that change scores the
   LLM. Ship only if kappa ≥ 0.7 on the judged dimension, which is that change's own bar.
2. **A1 finding matching** — replay the seeded-defect set from `measure-validator-recall-seeded-defects`
   and the `pr484-consensus.json` fixture; acceptance is that the two real #484 defects match across
   vendors and routing precision on seeded defects does not drop.
3. **B1 GATEKEEPER and C1 phase outcome** — both in shadow mode beside the current decider for a
   sprint of autopilot runs: log the judged label next to the claimed or table-derived one, act
   on neither, measure the disagreement rate and which side the next review round vindicated.
   B1 is the largest cost saving per run; C1 is the largest correctness gain.
4. **A2, A3, A4, A5, A6, C2** — each is a one-file change with an existing fallback; land as
   independent small changes. C2 removes the most wasted fix dispatches.
5. **B3, B4, B5, C6** — two-stage rewrites; B5 needs the schema decision first; C6 waits for
   the task router to land so the router never needs an LLM.
6. **C3, C4, C5, C8** — loop decision points behind existing gates, as independent changes.
7. **A7 and C7** — last: A7 is a gate input, C7 is an authorization channel.

Rough cost at current prices: a full autopilot run's Jev calls (B1 + A1 + A3 + B3 stage 1 + C1
+ C2 across a few rounds) total well under one cent; the premium-tier GATEKEEPER call they
replace costs more than that alone.

## Sources

- SDK types: `typesafe-sdk-python/src/typesafe_sdk/_core/question_types.py` and `response_types.py` (github.com/typesafe-ai)
- Vendor skill: `typesafe-ai/skills/skills/typesafe-ai/SKILL.md`; adapter: `typesafe-ai/system-one-adapter-python`
- Launch coverage used for limits, pricing and training method: [TypeSafe blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev),
  [DataCamp](https://www.datacamp.com/blog/system-one-models-jev), [flaviocopes.com](https://flaviocopes.com/jev/),
  [lilting.ch](https://lilting.ch/en/articles/typesafe-ai-jev-system-one-model), [The Register](https://www.theregister.com/ai-and-ml/2026/09/16/typesafe-ai-debuts-model-for-machines-that-plays-doom/5296711),
  [Vercel changelog](https://vercel.com/changelog/typesafe-ai-jev-now-available-on-ai-gateway), [dev.to guide](https://dev.to/valyuai/how-to-use-jev-a-practical-guide-to-typesafes-system-one-model-g5e)
- Docs index (blocked from this session, cited for the reader): https://docs.typesafe.ai/llms.txt, https://docs.typesafe.ai/primitives.md, https://docs.typesafe.ai/api.md
