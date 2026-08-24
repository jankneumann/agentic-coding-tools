# Skill Rightsizing for Frontier Models

## Motivation

Changes to this repository are getting slower while the abstractions deliver less. The cause is structural: `skills/` is written as a program for a weak interpreter rather than a briefing for a capable colleague, and the maintenance surface of that program now exceeds its value.

Measured today: 74 `SKILL.md` files totalling 17,945 lines, of which 66 use no progressive disclosure at all; 24,740 lines of content-invariant test code policing that prose; 104 hard-coded cross-skill script paths and 243 `<skill-base-dir>` placeholders coupling skills by filesystem layout; 52 skills maintaining a `triggers:` field no runtime reads; and 69 of 74 descriptions omitting the when-to-use clause that actually drives skill selection.

Anthropic removed over 80% of Claude Code's own system prompt for Opus 5 and Fable 5 with no measurable loss on coding evals, having concluded they were overconstraining the agent through the system prompt, `CLAUDE.md` files, and skills. The same guardrails-for-weaker-models pattern is present here and can be cut on the same evidence standard.

That standard is the constraint that shapes this roadmap. The repository is almost entirely model-generated between February and July 2026, so an LLM judge pointed at it shares the blind spots of whatever produced it. Cuts cannot be justified by taste. They must be justified by a measurement whose ground truth comes from outside the model's judgment — and that measurement infrastructure does not exist yet.

Two source documents carry the detail:

- `docs/proposals/frontier-model-skill-architecture.md` — the measured diagnosis and the eight rightsizing recommendations.
- `docs/proposals/skill-benchmark-design.md` — how to benchmark a self-generated codebase without the grader grading itself.

## Capabilities

### Measurement foundation

The repository already contains most of the raw material and none of the harness.

- **Failure-record regression suite.** The 18 dated files in `docs/merge-logs/` and `docs/lessons-learned.md` record human-witnessed defects with rationale attached — genuine labels produced by a person watching the system fail. These are the least circular evidence available and are currently inert prose. They should become executable regression scenarios.
- **Sealed benchmark corpus.** 92 archived OpenSpec changes span 2026-02-01 to 2026-07-25; 91 carry SHALL/MUST specs and Given/When/Then scenarios, 91 carry `tasks.md`, 69 carry `design.md`, totalling 5,694 SHALL/MUST clauses. In each, the specification was written before the implementation and ratified at a human gate — the temporal separation that breaks circularity. The corpus must be split into development and holdout partitions before any rightsizing begins, or it measures memorization.
- **Task-replay runner.** Restore the repo to a change's pre-implementation commit, hand the agent `proposal.md` as intent, withhold the implementation, and score the produced diff against that change's own scenarios and tests.
- **Seeded-defect harness.** Inject known faults drawn from real defect categories and measure validator recall. This is the only way to learn whether `/security-review`, `/parallel-review-plan`, `/parallel-review-implementation`, and the review-convergence loop earn their tokens; none has a measured detection rate today.
- **Mutation-score guardrail.** A model-written test suite is only a valid grader if it is not vacuous, and vacuity is objectively measurable. This also blocks the obvious gaming path, where an arm raises its pass rate by producing weaker tests.
- **Process telemetry.** Turns, tool calls, tokens, retries, `ESCALATE` transitions in `loop-state.json`, `rework-report.json` entries, and time-to-green are observations rather than judgments, so nothing can grade itself. The instrumentation exists — `langfuse`, `collect-transcripts`, `session-log` — and is not aggregated for this purpose.
- **Calibrated judge.** Where LLM judgment is unavoidable, a small stratified set of human labels establishes agreement (Cohen's κ) so results can be quoted with a known error rate rather than an unknown one.
- **Disagreement routing.** Cross-vendor agreement is not evidence of correctness — shared training distributions produce shared blind spots — but disagreement reliably localizes hard cases and should route them into the scarce human-labelling budget.

### Rightsizing

- **Context-cost baseline.** Every skill's name and description is preloaded into every session. `/doctor` prices that listing and identifies its biggest contributors.
- **Frontmatter economics.** Delete the dead `triggers:` field; rewrite all 74 descriptions to carry both what and when.
- **Self-describing tool interfaces.** Replace relative-path invocation with console entry points that take `--json`, exit non-zero with actionable messages, and document themselves via `--help`. Only 43 of 329 scripts emit JSON today.
- **Mechanical preamble collapse.** Coordinator detection, tier selection, worktree setup, branch resolution, and worker-vendor recording appear as transcribed procedure in seven skills. One tool returning structured state replaces all of them.
- **Guardrail deletion.** The mandated tail block's Common Rationalizations table argues pre-emptively against excuses a frontier model does not make, costing 578 lines behind a test-enforced minimum. Rules that restate ordinary engineering competence go the same way; rules encoding genuine project policy move to `CLAUDE.md` and are stated once.
- **Progressive disclosure.** The 11 skills over 500 lines become an index plus reference files one level deep.
- **Test-suite inversion.** Shape assertions give way to behavioural scenarios.

## Constraints

- No rightsizing change may be accepted without a measurement. The measurement harness must land and produce an arm-A baseline before the first deletion.
- The accept/reject rule is pre-registered: accept when Tier-0/1 acceptance pass rate is non-inferior within −5 percentage points, the mutation score does not fall, and process-telemetry efficiency improves.
- The holdout partition stays sealed until the decision run. Skills must not be authored while looking at holdout tasks.
- Graders must be blind to arm identity, must not be the generator, and must not have the skill under test in their context.
- Every task runs under both arms with N=3 runs to estimate variance. Absolute scores are not reported; only deltas are.
- Behaviour-preserving deletions only. Rules encoding real project policy are relocated, not dropped.
- Scoring uses each archived change's executable scenarios, never its prose conventions — the corpus encodes its own era's assumptions, including the `triggers:` convention that is now dead.

## Phases

1. **Instrument.** Build measurement that involves no LLM grading: failure-record regressions, sealed corpus split, process telemetry, `/doctor` context-cost baseline.
2. **Harness.** Task-replay runner, seeded-defect recall, mutation guardrail, judge calibration, and the arm-A baseline scorecard.
3. **Cut.** Frontmatter, tool interfaces, mechanical preamble, guardrail prose, progressive disclosure — each measured against the baseline.
4. **Decide.** Run the sealed holdout, apply the pre-registered rule, and invert the test suite to match what now matters.

## Out of Scope

- Rewriting the tiered execution model. Coordinated / local-parallel / sequential is a real architectural decision and stays; only its restatement across seven skills is removed.
- Removing low-freedom exact-script instruction where operations are genuinely fragile: merge and rebase sequences, worktree teardown, anything irreversible.
- Removing vendor-neutral dispatch. It moves behind a tool interface rather than being re-explained in seven preambles.
- Changes to the coordinator service, its database schema, or its deployment.
- Establishing absolute code-quality scores for the repository. The programme answers whether arm B is non-inferior to arm A, not whether the code is good.
