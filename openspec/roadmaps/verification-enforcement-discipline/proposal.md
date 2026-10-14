# Verification and Enforcement Discipline

## Motivation

A comparative read of Cursor's `pstack` plugin (github.com/cursor/plugins, `pstack/`)
against this repository surfaced a set of disciplines we already half-practise but do
not enforce. The common thread is one sentence: **the absence of evidence is not a
pass.** Exploration of our own code found that sentence violated in concrete, cited
places:

- `skills/expedite/scripts/expedite.py:101-105` reports a missing
  `validation-report.md` as `skip`, and `ready = all(status != "fail")` turns that into
  READY — contradicting the expedite SKILL table, which says "run /validate-feature
  first".
- `skills/merge-pull-requests/scripts/execution_safety.py:58-61` treats a
  non-eligible vendor review (`None`) as a pass; review is also skipped for PRs that
  already carry one approval. The per-PR verdict is not bound to a head SHA:
  `vendor_review.py` never writes `head_sha`, and the only staleness check
  (`execute_plan._iterate_consensus_current`, keyed on `iterate_consensus_path`) is
  dead because that path is only ever initialised to `None` (`build_plan.py:177`).
  `git patch-id` is used nowhere, so we cannot tell "same diff, rebased" from
  "different diff".
- `skills/parallel-infrastructure/scripts/package_executor.py:189` computes
  `verification.passed = all(steps)` — vacuously true for an empty list — and nothing
  checks that a worker's self-reported commit SHA exists.
  `validate_work_result.validate_verification_consistency` returns no errors when there
  are no steps, and `integration_orchestrator.record_package_result` counts a
  `status: failed` result as "present".

The second thread is that **rules live in prose with no index to what enforces
them.** We have well-built one-off guard tests (`test_change_path_stability.py`,
`ci_coverage/_EXEMPT`, `test_prose_free_gates.py`) and a `docs/lessons-learned.md`
full of maxims, but nothing maps rule → enforcer, there is no waiver-with-expiry
mechanism, and a correction that repeats an unenforced rule has nowhere to escalate.
The cite-requirements frontmatter defect fixed on `fix/cite-requirements-frontmatter`
is a fresh instance: the invariant existed in `skill_invariants.py` but was opt-in per
skill, so a skill invisible to the loader shipped green.

The third thread is **independence and calibration of judgement**: decision trails are
audited against the diff but never against what was actually said in the session;
`prototype-feature` tells variants exactly how they will be scored; plan artifacts
(`proposal.md`, `tasks.md`) are checked only by an LLM; and "why is this code like
this" has no tool that walks blame → commit → PR → change-id → decision record.

Success looks like: every gate that can be satisfied by a missing artifact is either
fixed to fail closed or records an explicit, operator-visible waiver; every rule an
agent is corrected on twice has a named enforcer or a recorded reason it cannot have
one; and judgements that gate work are made by an agent other than the author, against
a rubric the author did not see.

## Capabilities

### Capability: SHA-bound independent merge verdict and fail-closed absence handling

Bind every per-PR review verdict in `merge-pull-requests` to the head SHA it reviewed
and to that head's `git patch-id --stable` fingerprint, so a verdict survives a
content-neutral rebase or update-branch but is invalidated by any real content change.
Make "no verdict" a block, not a pass: a non-eligible PR records an explicit waiver
reason that the merge plan and the operator see, instead of returning `None`. Record
the author identity (vendor + session/agent id) of the PR and reject a verdict produced
by the same agent. For stacked PRs, land only the contiguous prefix of verified nodes.
Fix `expedite` so a missing validation report is not READY (except where the change is
declared non-deployable / validation-exempt via the same `gate_logic` rules
`pre_merge_gate` already uses). Either wire or delete the dead
`iterate_consensus_path` staleness check. Thread the bound verdict into autopilot's
`Gate.MERGE` evidence so `/cleanup-feature` can confirm it merges the head that was
verified.

**Acceptance Outcomes:**
- A verdict whose recorded head SHA differs from the live head but whose patch-id
  matches is accepted; one whose patch-id differs is rejected with a "stale verdict"
  block reason — both proven by tests with real `git` repositories.
- `execution_safety` never returns "no block" for a missing or non-eligible verdict
  without a recorded waiver reason present in `merge-plan.json`.
- A verdict whose reviewer identity equals the PR author identity is rejected.
- `expedite` returns BLOCKED (not READY) for a deployable change with no
  validation report; the SKILL table and the code agree, enforced by a test.
- No code path reads `iterate_consensus_path` while nothing writes it.

### Capability: Honest worker results in the package executor

Make the work-queue result contract unable to express a vacuous pass. Empty
`verification.steps` yields `passed: false`; the reported `git.head.commit` must
resolve in the package's worktree; each result carries an explicit outcome of
PASS / ISSUES / BLOCKED alongside the method used for each verification step;
`dag_scheduler.mark_completed` and the integration gate accept a package as done only
from a validated PASS result. A failed or BLOCKED result is "present but not passing"
and blocks dependants the same way a missing one does.

**Acceptance Outcomes:**
- `build_result` with zero steps produces `verification.passed == false`, and
  `validate_work_result` reports it as an error.
- A result naming a commit absent from the worktree fails validation.
- The integration gate returns a blocking status for a package whose only result is
  `failed` or BLOCKED.
- Existing emitters keep validating: any new schema field is optional or every emitter
  is migrated in the same change.

### Capability: Rule-to-enforcer registry with expiring waivers

A machine-readable registry (one file, e.g. `docs/enforcement/rules.yaml`) with one
row per project rule: id, one-line statement, enforcement level (architecture > types
> lint > test > docs — fix at the highest level that can hold the rule), enforcer
(path to the guard test / linter / CI job), the commit the enforcer is proven to fail
on, and the source (lessons-learned entry, review thread, incident). A rendered
rule → enforcer table in AGENTS.md is generated from it and drift-checked. Line-level
waivers carry rule id, reason, expiry date and approver; a guard rejects malformed or
expired waivers. A `prove_enforcer` helper runs a rule's enforcer against its recorded
failing commit and asserts it fails. This item builds the **enforcer side only**:
mining and classifying corrections belongs to `intervention-capture`,
`add-gap-taxonomy-and-ledger-links-to-intervention-records` and
`report-interventions-per-bug-and-rank-gaps`; the registry exposes rule ids those
records can link to, and documents the escalation rule (a `docs`-level rule corrected
twice is flagged for promotion) as the interface they consume.

**Acceptance Outcomes:**
- Every registry row with level other than `docs` names an enforcer path that exists
  and a recorded failing commit; a guard test enforces both.
- `prove_enforcer <rule-id>` demonstrates failure on the recorded commit for every
  seeded rule (at minimum the openspec-path-stability, CI-coverage, and
  skill-loader-frontmatter guards).
- The AGENTS.md table is regenerated from the registry and a drift check fails when
  they diverge.
- A waiver with a past expiry date, or missing reason/approver, fails the guard.

### Capability: Citable principle files injected into archetype prompts

Small principle files (`docs/principles/<id>.md`), each with a "when it applies"
trigger, a checkable bar (something a reviewer or script can verify in a diff), and an
optional link to a registry rule. Seed set: test-behaviour-not-wiring, build-the-lever,
attack-the-premise (after two failed fixes sharing a premise, write the premise down
and a census script), fix-root-causes, subtract-before-you-add. Indexed from AGENTS.md.
`archetypes.yaml` gains a per-archetype `principles:` list; the resolver appends a
compact pointer + bar for each (not the full text) at the same single composition point
that appends `PROCEDURE_MODE_SENTENCES` in `agents_config.py`. Session-log decisions
may cite principle ids, and a validator rejects citations of ids that do not exist.

**Acceptance Outcomes:**
- Each principle file has the three required parts, enforced by a test; a principle
  without a checkable bar is rejected.
- Resolving an archetype with a `principles:` list yields a system prompt containing
  each principle's id and bar, and a size budget test bounds the added text.
- A session-log citation of a non-existent principle id fails validation.

### Capability: Deterministic plan-artifact linter

A script that checks `proposal.md` and `tasks.md` structurally, replacing checks that
today are prose instructions to an LLM: required proposal sections (Why / What Changes
/ Impact, plus any section a later change makes mandatory — this linter is the intended
host for `add-verification-signals-contract-to-plan-feature`'s check); every task has
`**Spec scenarios**`, `**Files**` and `**Dependencies**` fields; spec-scenario
references resolve to scenarios in the change's spec deltas; dependency references
resolve; verification tasks exist for each requirement. Run from `plan-feature`,
`iterate-on-plan`, and CI — in CI as a ratchet that is blocking for changes created
after the linter lands and advisory for existing ones.

**Acceptance Outcomes:**
- The linter reports a missing `**Spec scenarios**` field and an unresolvable scenario
  reference on fixture plans, and passes on the template-shaped fixture.
- CI blocks a newly created change that fails the linter and only warns for
  pre-existing changes.
- plan-feature and iterate-on-plan invoke the linter and surface its findings.

### Capability: Cross-model review of decision trails against the transcript

Extend `audit-choices` so the auditor is a different vendor/model family from the
author (resolved from archetype tiers, never hardcoded), reads the normalized session
transcript (via `collect-transcripts` adapters) in addition to the diff, spec and
session-log, and reports decisions that are in the transcript but missing from the
trail or vice versa. Each ledger evidence cell is a pointer (transcript event id,
commit SHA, or file:line), never a paraphrase. The rendered ledger closes with an
"Attention" section that names the reviewer model and lists the entries a human should
read first. Coordinates with `add-eliminative-adversarial-review-mode`'s
same-vendor refusal so there is one independence rule, not two.

**Acceptance Outcomes:**
- An audit whose auditor vendor equals the author vendor is refused (or recorded as a
  degraded `inline-fallback` with the reason) rather than silently accepted.
- Every ledger entry's evidence is a resolvable pointer; a validator rejects
  free-text evidence.
- The rendered ledger ends with an Attention section naming the reviewer model.

### Capability: "Why" mode for explain-code with epistemic tiers

Add a why mode to `explain-code` (not a new skill): for a file:line or symbol, join
`git blame` → commit → PR → change-id → `docs/decisions/` entries
(`decision_index.py`), and tag every claim in the answer with an epistemic tier —
Direct (quoted from a record), Supported (multiple records agree), Inferred,
Speculative, Unknown. A null result ("no decision record covers this line") is reported
as a finding, not papered over. A hypothesis embedded in the question ("this was added
for X, right?") is treated as a claim to test, not a premise. Add an optional
`evidence_level` field with the same tier vocabulary to
`review-findings.schema.json`, flowing into the prompt contract automatically via
`review_findings_schema.prompt_contract`.

**Acceptance Outcomes:**
- A deterministic `why_trace` script returns the blame → commit → change-id →
  decision chain for a fixture repository, including an explicit empty result when no
  decision covers the line.
- The explain-code SKILL documents the tier vocabulary and the null-result and
  embedded-hypothesis rules.
- `evidence_level` is optional in the schema, appears in the derived prompt contract,
  and every existing emitter still validates.

### Capability: Arena discipline for prototype-feature

Stop telling variant agents the scoring rubric: keep part of the evaluation held out
(scenarios the variants never see), add an optional cross-family model judge whose
recommendation is shown to the human picker (the human still decides), cap grafting
from non-winning variants to one or two named parts, and treat high divergence across
variants as a signal to reframe the plan (an `iterate-on-plan` finding) rather than to
pick.

**Acceptance Outcomes:**
- The variant prompt no longer names the scoring phases; a held-out check set is
  scored after the variants finish.
- When enabled, the judge's model family differs from every variant's, and its
  recommendation is recorded beside the human pick in `prototype-findings.md`.
- A divergence threshold breach emits a reframe finding consumed by
  `/iterate-on-plan --prototype-context`.

## Constraints

- Must not create a second learning or correction store; correction records belong to
  `intervention-capture`, and this roadmap only exposes rule ids for them to link to.
- Must preserve every human gate: autopilot never merges, the prototype pick stays
  human, Gate 1/Gate 2 in plan-feature are unchanged.
- Schema additions (`review-findings`, `work-queue-result`, `decision-choices`) must be
  optional unless every emitter is migrated in the same change; four other active
  changes edit `review-findings.schema.json`, so additions must be additive and small.
- SKILL.md edits to files over 500 lines (merge-pull-requests, autopilot,
  validate-feature, plan-feature, iterate-on-plan) must go into `references/` files or
  be line-neutral, so they do not fight `apply-progressive-disclosure-oversized-skills`.
- `execution_safety.py` and `convergence_loop.py` are also edited by
  `add-orchestrator-adjudication-review-gate`; the merge-verdict item must extend its
  structures rather than add a parallel gate, and declare the overlap.
- Model selection must come from `agent-coordinator/archetypes.yaml` tiers; no
  hardcoded model ids, and no vendor-specific model slugs from the source material.
- Every new guard ships with a self-test proving it detects a violation (the
  repository's existing convention), and registry-backed guards additionally record a
  real commit they fail on.
- Tests must not pin `openspec/changes/<change-id>/` literals (use `change_dir()`).
- Fail-closed changes must keep an explicit, recorded operator override path; no
  override may be silent.

## Phases

### Phase 1: Absence is not a pass

The merge-verdict binding and honest worker results. Highest value, most concrete, and
every later phase relies on gates that actually fail closed.

### Phase 2: Enforcement infrastructure

The rule-to-enforcer registry, then principle files (which may cite registry rules),
and independently the plan-artifact linter (which is itself registered as an enforcer
once the registry exists).

### Phase 3: Calibrated judgement

Cross-model trail review, the explain-code why mode with the shared tier vocabulary,
and arena discipline for prototype-feature.

## Out of Scope

- pstack's anti-planning stance — OpenSpec planning and its gates stay.
- Cursor-specific model slugs, plugin packaging, or command names.
- Autonomy defaults that bypass our approval gates (auto-merge, auto-approve).
- Mining, classifying, or ranking corrections from transcripts (owned by
  `intervention-capture` and the evidence-grounded-debugging roadmap).
- Rewriting AGENTS.md's linked guides into principle files; principles are a small,
  checkable set, not a relocation of policy.
- A standalone `/why` skill; the capability lands inside `explain-code`.
