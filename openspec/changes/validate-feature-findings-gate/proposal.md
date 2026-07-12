# Proposal: Findings-Model + Enforcement Gate for `validate-feature`

**Change ID**: validate-feature-findings-gate
**Status**: Draft
**Created**: 2026-06-26
**Tier**: coordinated

## Why

`validate-feature` is **deep but advisory**. It deploys the feature locally, runs
security/behavioral/E2E/spec phases, and writes a human-readable
`validation-report.md` — but its output is prose, its enforcement is optional
("Option 3: Skip non-critical failures and proceed"), and its isolation reuses
the live feature worktree. The external [no-mistakes](https://github.com/kunchenguid/no-mistakes)
workflow ("kill all the slop, raise clean PR") occupies the same goal space from
a different layer — a git push-proxy — and is forced by that position into four
properties we lack:

1. **Findings as first-class data** with an auto-fix vs human-escalation tier
   ("safe, mechanical fixes are applied automatically; anything that touches your
   intent is escalated to approve / fix / skip").
2. **A hard enforcement gate** — "nothing reaches the configured push target
   until every check is green."
3. **Disposable-worktree-per-run isolation** — validation runs against a
   throwaway copy, leaving zero residue on the branch under test.
4. **Interactive per-finding triage** (a TUI plus a `-y` auto mode).

These are the four approaches the no-mistakes-vs-validate-feature analysis
flagged as worth adopting. This change adapts them onto our existing
infrastructure — crucially **reusing** `openspec/schemas/review-findings.schema.json`
(already produced by our architecture linters) and the
`consensus_synthesizer` / `fix-scrub` / `simplify` machinery — rather than
inventing parallel structures or importing a Go push-proxy.

The change is explicitly scoped to **strengthen** `validate-feature`, never to
weaken its depth. The live deploy, security scans, Playwright E2E, and the
CRITICAL task-drift gate (SKILL.md §7.0) all remain. We are bolting a structured
output model, an opt-in gate, an ephemeral mode, and an interactive triage
surface onto a pipeline that already does the hard evidence-gathering.

## What Changes

Four capabilities, delivered as ordered phases of a single change. Phase 1 is the
backbone the others consume; Phase 4 depends on Phase 1's data model.

- **Phase 1 — Findings model + auto-fix tier (item #3 in the analysis).** Every
  `validate-feature` phase emits its issues as finding records — reusing the
  `review-findings.schema.json` *record* shape (not just prose) — into a per-run
  `validation-findings.json`, and records an explicit per-phase status
  (`pass` / `fail` / `skip` / `not-run` / `error`) so a pass is never merely
  inferred from the absence of findings. The file as a whole uses a thin new
  `validation-findings.schema.json` envelope (findings + phase statuses + the
  validated commit), because the review schema's `review_type` (plan/implementation)
  can't describe a validation run. Each finding carries a new optional `fixability`
  tier of `auto-fix` (mechanical, behavior-preserving) or `escalate` (touches
  intent) — a *new* field, leaving the review schema's existing `disposition` field
  and `review_type` enum untouched. A new triage step auto-applies `auto-fix`
  findings by delegating to the existing `simplify` / `fix-scrub` low-risk fixers,
  then re-runs the affected phase. The markdown report is rendered *from* the
  findings file, so humans and automation read the same source of truth.

- **Phase 2 — Opt-in pre-push enforcement gate (item #1).** Add an opt-in
  `pre-push` git hook (alongside the existing `.githooks/pre-commit` /
  `post-merge`) that runs the **critical** subset of `validate-feature`
  (`smoke`, the spec task-drift gate, and `security` thresholds) and **blocks the
  push** when any critical finding is unresolved. A documented kill-switch
  (`VALIDATE_GATE=0` / config flag) and a `--no-verify` escape hatch keep it
  non-coercive. This directly closes the incident class recorded in SKILL.md §7.0
  (the `specialized-workflow-agents` change shipped 29 tasks to main with 0/29
  checkboxes flipped).

- **Phase 3 — Ephemeral disposable-worktree mode (item #2).** Add a
  `--ephemeral` flag that clones the current `HEAD` into a throwaway scratch
  worktree, runs validation there, and discards it on completion — so deploy
  artifacts, security-scan output, and log files never mutate the branch under
  test. Cloud-harness environments (which already short-circuit worktree ops)
  fall back to the existing in-place behavior.

- **Phase 4 — Interactive per-finding triage (item #4).** Add a `--triage` mode
  that walks `escalate` findings one at a time and collects an
  `approve` / `fix` / `skip` `triage_state` per finding (via `AskUserQuestion` in
  the agent harness, or a prompt loop in CLI), plus a `-y` / `--auto` mode that
  applies the default `triage_state` non-interactively. The `triage_state` is a
  new field written back into the Phase 1 findings file (the existing
  `disposition` field is never touched) so a re-run resumes from curated state.

### Non-goals

- Replacing the live-deploy / security / E2E / spec depth of `validate-feature`
  with no-mistakes' lighter review/test/docs/lint set. We adopt its *structure*,
  not its scope.
- Building a standalone Go push-proxy or a separate TUI binary. The gate is a git
  hook; the triage surface rides the existing agent/CLI harness.
- Making the enforcement gate on-by-default or mandatory. It is opt-in with a
  kill-switch and a `--no-verify` escape hatch.
- A new finding-*record* schema. We reuse the `review-findings.schema.json` record
  shape and extend it only with additive optional fields (`fixability`,
  `triage_state`); the existing required `disposition` field and `review_type` enum
  are unchanged. We do add one thin `validation-findings.schema.json` *envelope*
  (findings + phase statuses + validated commit), because a validation run is not a
  plan/implementation review and needs a phase-status container (see Risks).

## Approaches Considered

### Approach A — Phased enhancement reusing the findings schema *(Recommended)*

One change, four ordered phases, built on `review-findings.schema.json` and the
existing `simplify` / `fix-scrub` fixers and `consensus_synthesizer` matching.
The gate is an opt-in git hook; the ephemeral mode reuses the `worktree` skill;
triage rides `AskUserQuestion` / a CLI prompt loop.

- **Pros**
  - Maximal reuse — the findings schema, low-risk fixers, worktree lifecycle,
    and consensus dedup are all existing assets; net-new surface is the
    finding-emit shims, the hook, the ephemeral flag, and the triage loop.
  - Unifies `validate-feature` output with `fix-scrub` and the consensus
    synthesizer, so findings flow across skills instead of dead-ending in prose.
  - Each phase is independently shippable and independently valuable; Phase 1
    alone is useful even if 2–4 never land.
  - Adopts no-mistakes' transferable structure without its transport coupling.
- **Cons**
  - Touching every phase's output path is broad (but mechanical and test-guarded).
  - Two human-loop surfaces (gate block message + triage loop) to keep coherent.
- **Effort**: L

### Approach B — Import the no-mistakes push-proxy model wholesale

Install a local git proxy that intercepts `git push` and runs the full pipeline
in a disposable repo before forwarding, mirroring no-mistakes' architecture.

- **Pros**
  - Strongest enforcement guarantee — the gate owns the `push` verb itself.
  - Disposable isolation comes for free from the proxy's design.
- **Cons**
  - A second, parallel orchestration layer competing with our OpenSpec lifecycle
    and coordinator — high operational surface and conceptual overlap.
  - Transport-level interception is opaque to the change-id / coordinator / memory
    loop that the rest of our stack depends on.
  - A push-proxy can't see the OpenSpec change context (specs, tasks.md drift)
    that makes our validation valuable.
- **Effort**: XL

### Approach C — Findings model only (skip the gate, ephemeral, and triage)

Ship Phase 1 alone: structured findings + auto-fix tier, but keep enforcement
advisory and isolation in-place.

- **Pros**
  - Smallest change; delivers the highest-leverage single idea (findings-as-data).
  - No new git hook or worktree mode to document and maintain.
- **Cons**
  - Leaves the documented enforcement gap (SKILL.md §7.0 incident) unaddressed —
    findings can still be ignored by walking past the advisory report.
  - No isolation improvement; validation residue still lands on the branch.
  - Triage has no home, so the auto-fix/escalate split is only half-realized.
- **Effort**: M

### Selected Approach

**Approach A — phased enhancement reusing the findings schema.** It captures all
four adoptable ideas from the analysis while honoring our existing posture:
OpenSpec-lifecycle-bound, coordinator-aware, schema-reusing, and opt-in for
anything coercive. Approach B's wholesale proxy import duplicates orchestration
we already own and severs the change-context coupling that gives our validation
its depth; Approach C under-delivers by leaving the enforcement gap open.

### Recommendation

**Approach A.** It is the only option that adopts no-mistakes' four transferable
properties — findings-as-data, a hard gate, disposable isolation, and interactive
triage — without importing its transport-layer architecture or sacrificing the
OpenSpec/coordinator integration that distinguishes `validate-feature`. Phasing
keeps each idea independently shippable, with Phase 1 (the findings model) as the
backbone the gate and triage build on.

## Risks

- **Schema churn on `review-findings.schema.json`.** The schema already defines a
  required `disposition` field (enum `fix`/`regenerate`/`accept`/`escalate`) used
  by the parallel-review pipeline; repurposing it would break existing consumers
  (architecture linters, consensus synthesizer). *Mitigation*: do **not** touch
  `disposition` or `review_type`; add the new tier/triage state as **optional,
  additive** fields on the finding record (`fixability` default `escalate`;
  `triage_state` unset until triaged); put the validation-only concepts (phase
  statuses, validated commit) in a **separate** thin `validation-findings.schema.json`
  envelope that reuses the review finding record, so the review schema and its
  consumers are untouched; add contract tests asserting the `disposition` enum and
  `review_type` are unchanged and a full validation-findings file validates.
- **Auto-fix applying an unsafe change.** A finding mis-classified as `auto-fix`
  could alter behavior. *Mitigation*: `auto-fix` delegates only to the existing
  `simplify` / `fix-scrub` low-risk, behavior-preserving fixers (same boundary
  they already enforce); every auto-fix re-runs the affected phase and reverts on
  regression; the classifier defaults to `escalate` when uncertain.
- **Enforcement gate blocking a legitimate emergency push.** *Mitigation*: opt-in
  install, `VALIDATE_GATE=0` kill-switch, and the standard `git push --no-verify`
  escape hatch, all documented at the block message.
- **Ephemeral clone cost / cloud-harness incompatibility.** *Mitigation*:
  `--ephemeral` is opt-in; cloud-harness detection (`environment_profile.detect()`)
  short-circuits to in-place behavior, matching the rest of the worktree stack.
- **Triage loop divergence between agent (`AskUserQuestion`) and CLI surfaces.**
  *Mitigation*: both write the same `triage_state` fields back to the findings
  file; a single render/apply path consumes them regardless of how they were
  collected.

## Impact

- **New**: a finding-emit helper shared by `validate-feature` phases; a
  findings→markdown renderer; an auto-fix triage step delegating to
  `simplify`/`fix-scrub`; `.githooks/pre-push` + installer entry; a `--ephemeral`
  worktree path; a `--triage` / `-y` triage-state loop.
- **Modified**: `skills/validate-feature/SKILL.md` (phase output contracts, new
  flags, gate/triage/ephemeral sections); `skills/validate-feature/scripts/*`
  (phases emit findings); the report-rendering step (§11) reads the findings file;
  `openspec/schemas/review-findings.schema.json` (additive optional `fixability` /
  `triage_state` fields on the finding record; existing `disposition` / `review_type`
  unchanged); a new `openspec/schemas/validation-findings.schema.json` envelope
  (findings + `phase_statuses[]` + validated commit).
- **Reused**: `review-findings.schema.json`, `simplify` + `fix-scrub` fixers,
  `consensus_synthesizer.py` matching, the `worktree` skill lifecycle,
  `environment_profile.detect()`, `AskUserQuestion`, coordinator
  `memory`/`audit`, and the existing `.githooks` installer.
