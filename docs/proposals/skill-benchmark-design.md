# Benchmarking a Self-Generated Codebase

## The problem, stated precisely

Nearly all code in this repository was model-generated between February and July 2026. Its tests were model-written, its specs were model-drafted, and any LLM judge we point at it shares a training distribution with whatever produced the artifact. The obvious objection to an eval suite here is that **the grader is grading itself**: a rubric derived from the same model that wrote the code will systematically fail to see the failures that model is prone to.

The objection is correct as far as it goes. What follows argues that it applies to far less of the problem than it first appears, and that this repository already contains most of the material needed to work around the part where it does apply.

## Reframe: we are not certifying quality, we are comparing two arms

The eval exists to answer one question: **did rightsizing the skills help or hurt?** That is a *paired differential* question, not an absolute one.

- An **absolute** question ("is this code good?") requires ground truth. We don't have it, and manufacturing it is expensive.
- A **differential** question ("is arm B at least as good as arm A on the same task?") requires only a consistent discriminator applied to identical inputs. Systematic grader bias largely **cancels**, because it lands on both arms equally.

This is the standard Anthropic met to defend deleting 80% of their system prompt: not *"we proved the result is good"* but *"no measurable loss on coding evals."* Non-inferiority is a much cheaper claim to support than correctness, and it is the claim we actually need.

Consequences for the design:

- Every task runs under both arms. Never score an arm in isolation.
- Absolute scores are meaningless here and should not be reported. Only deltas are.
- A grader that is consistently wrong in the same direction is still a usable instrument. A grader that is *randomly* wrong is not — so grader **variance**, not grader bias, is the thing to control.

## Rank graders by how circular they are

Not all evidence is equally contaminated. Push as much scoring weight as possible down this ladder.

### Tier 0 — the world grades. Zero circularity.

Does it compile, do the tests pass, does the service boot, does the migration apply, does the container come up, does CI go green, does the PR merge without conflict?

Model-written tests are still valid graders **at execution time**. The risk was never that a model wrote the assertion; it is that the assertion is *vacuous*. Vacuity is separately measurable (Tier 2), and once measured, this tier is clean.

This repo already has the harness: `/validate-feature`'s ten phases, `validate-flows`, `playwright-validator`, the docker-compose stacks.

### Tier 1 — history grades. Near-zero circularity.

The archive is the asset:

| | |
|---|---|
| Archived changes (2026-02-01 → 2026-07-25) | **92** |
| …with a spec containing SHALL/MUST clauses | 91 |
| …with Given/When/Then `#### Scenario:` blocks | 91 |
| …with `tasks.md` | 91 |
| …with `design.md` (recorded decisions) | 69 |
| Total SHALL/MUST clauses in the archive | **5,694** |
| Merge logs (human-witnessed sessions) | 18 |

The property that matters: **in every one of these, the specification was written before the implementation and accepted by a human at a gate.** The spec was model-drafted, yes — but drafted in a different session, in a different context, *before the answer was known*, and then ratified. That temporal and contextual separation is what breaks the circle. It is weaker than an independent human label and enormously stronger than same-session self-grading.

This converts the archive into a SWE-bench-style benchmark of your own work: restore the repo to the pre-change commit, hand the agent `proposal.md` as intent, withhold the implementation, and score the produced diff against the change's own scenarios and tests.

### Tier 2 — construction grades. Zero circularity, by design.

**Seeded-defect (mutation) testing.** Inject a known fault; you know exactly what is wrong because you put it there. No judgment is involved.

This does two jobs, and both are load-bearing here:

1. **It is the direct answer to "our tests were model-written too."** A mutation score is an objective measure of whether the suite has teeth. If you flip a comparison operator, drop a guard clause, or weaken a permission check and the suite stays green, the suite is theater — and you now know it, without anyone's opinion.
2. **It is the only way to measure the validators.** `/security-review`, `/parallel-review-plan`, `/parallel-review-implementation`, `/iterate-on-implementation` and the review-convergence loop currently have *no* measured detection rate. Seed 40 defects drawn from real categories (the merge-log "Observations" and `docs/lessons-learned.md` are the source), run each validator, and you get a recall number. A reviewer that catches 12 of 40 is a reviewer whose 300 lines of prompt you can cut without fear.

### Tier 3 — process telemetry. No grader at all.

Turns, tool calls, tokens, retries, wall-clock to first green build, CI re-runs, number of `rework-report.json` entries, count of `ESCALATE` transitions in `loop-state.json`, human gates hit, worktree GC collisions.

These are **observations, not judgments** — nothing can grade itself. For the specific question "did rightsizing help?", they are arguably the *primary* metrics: an arm that reaches the same Tier-0 outcome in fewer turns with fewer retries is unambiguously better, and no one had to form an opinion.

The instrumentation already exists and is not being used this way: `langfuse` (with its Stop hook), `collect-transcripts` (multi-vendor normalize → triage → deep_analyze), `session-log`, and `loop-state.json`.

### Tier 4 — human labels, strictly rationed.

You cannot fully escape human judgment, but you need far less of it than intuition suggests, and you should spend it on **calibrating the judge rather than grading the system**.

Budget ~40 items, stratified across change size and skill. Label them yourself. Then measure agreement between your labels and the LLM judge (Cohen's κ). Once κ ≥ 0.7 on a dimension, extend that judge across the full set *and quote its measured error rate alongside every result*.

This is the move that converts "the model grades itself" into "the model grades itself, and we know how often it is wrong" — which is a defensible position rather than a fatal one. Re-calibrate whenever the judge model changes.

### Tier 5 — cross-vendor disagreement. A router, not a grader.

You already dispatch across claude, codex, antigravity, grok, and pi.

**State this plainly: agreement between models is not evidence of correctness.** Shared training distributions produce shared blind spots, and a five-vendor consensus can be five-way wrong in exactly the same way. The current review-convergence machinery treats consensus as a proxy for truth; that is the circularity trap in its purest form and it should be renamed and re-scoped, not trusted.

*Disagreement*, however, is genuinely informative: it reliably localizes the hard cases. Use it to route items into the scarce Tier-4 human budget. Disagreement is a triage signal; agreement is not a verdict.

## Anti-circularity discipline for whatever LLM judging remains

1. **The grader must not be the generator.** Different model family, different session.
2. **The grader must not have the skill under test in context.** Otherwise it scores the work against the very rubric that produced it — this is the sharpest form of the circularity failure and the easiest to commit by accident.
3. **Blind the arms.** The judge sees diff A and diff B without knowing which came from the rightsized skills.
4. **Randomize order.** Position bias in pairwise LLM judging is large and well documented.
5. **Judge observable properties, not quality.** "Does the diff touch files outside `write_allow`?" is checkable. "Is this well-architected?" is a vibe with a number attached.
6. **Pre-register the metric and the decision rule** before running the arms.

## Three traps specific to this repository

### Survivorship bias in the archive

All 92 archived changes are changes the *current* skills already completed successfully — archiving happens after merge. Benchmarking exclusively on them flatters arm A and hides the failure modes you most want to fix.

Mitigation: deliberately over-sample failure. The negative examples are the informative ones and they exist —

- the **28 non-archived** active changes (why did these stall?),
- every `ESCALATE` state ever written to `loop-state.json`,
- every `rework-report.json` (it already carries per-scenario failure routing and public/holdout visibility),
- the **"Observations" and "Follow-ups" sections of the 18 merge logs**, which are human-witnessed defects with rationale attached — e.g. *"`worktree.py gc` has a repo-wide blast radius: it swept 5 stale worktrees + pruned local branches beyond the change being cleaned."*

That last category is the highest-value, least-circular material in the repo and it is currently inert prose. Every observation is a genuine label produced by a human watching the system fail.

### Corpus leakage

If skills are edited while looking at the benchmark tasks, the benchmark measures memorization. Split the 92 now, before any rightsizing work starts: **60 development / 32 holdout**, holdout sealed until the accept/reject decision. Prefer the most recent changes for the holdout, since they best represent forward work.

The repo already has holdout machinery (`validate-feature/scripts/tests/test_holdout_gates.py`, `rework_report.py`'s public/holdout split). Reuse the concept at the corpus level.

### The corpus encodes its own era's assumptions

`docs/lessons-learned.md` still advises that skills carry `triggers:` in frontmatter — the field no runtime reads. The archive is a record of what was believed at the time, not what is true. Score against *executable* scenarios and tests from each change, not against its prose conventions.

## The benchmark

**Unit of measurement — a task replay:**

```
(repo state at commit C_before, proposal.md as the intent, acceptance criteria from specs/)
```

**Corpus:** 30 replays sampled from the 60-change development split, stratified by change size (small / medium / large) and by which skill the change primarily exercised. Plus 10 **seeded-defect** tasks for the validator skills. Plus every merge-log Observation converted into a regression scenario.

**Arms:** A = current skills, B = rightsized skills. N = 3 runs per task per arm to estimate variance — agent runs are stochastic and a single run per arm will produce noise you will misread as signal.

**Scorecard:**

| Tier | Metric | Role |
|---|---|---|
| 0 | Acceptance-scenario pass rate; build green; CI green | **Primary** |
| 1 | SHALL/MUST clause coverage in the produced diff | Primary |
| 2 | Mutation score of the tests the arm produced | **Guardrail** — catches "passed by writing weak tests" |
| 2 | Validator recall on seeded defects | Primary, for review skills |
| 3 | Turns, tokens, retries, ESCALATEs, time-to-green | **Primary for the rightsizing question** |
| 4 | Scope discipline, unnecessary abstraction (calibrated judge, κ reported) | Secondary |

**Pre-registered decision rule:**

> Accept the rightsized skills if Tier-0/1 pass rate is **non-inferior within −5 percentage points**, the Tier-2 mutation score does **not** fall, and Tier-3 efficiency improves. Reject otherwise.

The Tier-2 guardrail is what stops the obvious gaming path: an arm can raise its pass rate by writing weaker tests, and only mutation scoring catches that.

## Sequencing

Ordered by value per unit of effort, not by dependency.

| Step | Work | Why first |
|---|---|---|
| 1 | Convert the 18 merge logs' Observations + `lessons-learned.md` into executable regression scenarios | Human-witnessed labels; least circular material available; days of work |
| 2 | Seal the 60/32 corpus split | Costs nothing today, impossible to recover later |
| 3 | Stand up Tier-3 telemetry from existing langfuse / `collect-transcripts` / `loop-state.json` data | No grader needed; produces the arm-A baseline passively while you work |
| 4 | Build the task-replay runner over 10 archived changes; validate the harness before scaling to 30 | Prove the mechanism cheaply |
| 5 | Seed 40 defects; measure validator recall | First real number on whether the review skills earn their tokens |
| 6 | Label 40 items; calibrate the judge; report κ | Only now introduce LLM judgment, with a known error rate |

Steps 1–3 involve no LLM grading at all and are where most of the informational value sits.

## What this buys

After steps 1–4 you can make claims of the form: *"the rightsized `implement-feature` passes 29 of 30 archived acceptance suites versus 29 of 30 for the current version, with a 34% reduction in turns and no change in mutation score."*

That is a non-inferiority result with an efficiency win, established without anyone asserting that the code is good — which is precisely the claim needed to defend a large deletion, and precisely the claim that survives the objection that the grader shares the generator's blind spots.

## Sources

- [The new rules of context engineering for Claude 5 generation models](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models) — Anthropic
- [Skill authoring best practices — evaluation and iteration](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) — Claude Platform Docs
