# Change: add-decision-choices-ledger

**Status**: Draft

## Why

Every decision-capture mechanism in this repo is self-reported: the implementing
agent writes its own `Decisions` / `Alternatives Considered` / `Trade-offs`
sections into `session-log.md` at phase boundaries, and the CI-enforced
`docs/decisions/` index is generated from those same self-reported, opt-in-tagged
entries. A model reviewing its own work is primed by its own intent — it under-reports
the choices it did not notice it was making (an invented retry policy, a silently
chosen concurrency model, two features sharing a table). Our multi-vendor review
infrastructure audits the *code* for defects, but nothing audits the *choices*:
the decisions made where the spec was silent, which are exactly what bites three
months later even when every test is green.

The gap has already produced ad-hoc workarounds: the
`fix-autopilot-archetype-and-apply-outcome` change hand-wrote an unregistered
`audit-result.md` recording layered audit findings and decision traces — evidence
of unmet demand for a first-class artifact. This change adds the audit counterpart
to the self-reported archive: an independent, read-only auditor pass that
reconstructs implementation-time decisions from git history and session artifacts,
and hands the human a single ranked ledger — least-confident first — so reviewing
thirty choices replaces reading ten thousand lines.

## What Changes

- New **`choices` artifact pair** per change: `openspec/changes/<id>/choices.md`
  (human-primary, entries ranked least-confident first, each entry standalone) and
  `choices.json` (machine-readable, validated by a new
  `openspec/schemas/decision-choices.schema.json`, carrying the 6-field codeviz
  artifact header).
- Each ledger entry records: **the choice** (headline + concrete scenario),
  **the gap** (what the spec/design left unspecified), **the reach** (what the
  choice constrains or enables later), **verdict** (`sound` / `unsound` /
  `needs-user`), **confidence** (`low` / `medium` / `high`), plus provenance
  (commit range, files, matching session-log decision ref when one exists).
- New **`audit-choices` skill**: dispatches an independent read-only sub-agent
  (separate from the implementer) over `git log`/`git diff` for the change branch
  plus session artifacts (`session-log.md`, `design.md`, spec deltas,
  `impl-findings.md`). Callable standalone (`/audit-choices <change-id>` or an
  arbitrary commit range) and from workflow hooks.
- **Cross-reference, never write-back**: entries link matching self-reported
  decisions by `<change-id>#D<n>`; decisions the implementer did *not* self-report
  are explicitly flagged (`self_reported: false`). The auditor never writes to
  `session-log.md`, `docs/decisions/`, or any source file.
- **Workflow hooks (non-blocking)**: `iterate-on-implementation` gains a Step 11.5
  (after multi-vendor review, before summary) invoking the audit;
  `validate-feature` / `cleanup-feature` surface open `needs-user` entries at
  their existing human gates, the same way `deferred-tasks.md` is surfaced today.
  The audit itself never blocks and never gates.
- **Artifact registration**: new optional entry in
  `openspec/schemas/feature-workflow/schema.yaml` + `templates/choices.md`,
  mirrored byte-identically into
  `skills/plan-feature/install_assets/openspec/schemas/feature-workflow/`,
  plus a `rules:` block in `openspec/config.yaml` and an `## ADDED Requirements`
  delta against the `skill-workflow` capability spec.
- **Namespace discipline** vs the in-flight `ambient-review-ledger` change
  (plan-only, 0/33): this artifact is consistently named the *choices ledger*;
  no writes to `.review-ledger/`, no `ledger.changed` event, no modification of
  `review-findings.schema.json`.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Compatibility | `make decisions` diff after an audit run | zero diff (auditor never perturbs the generated decision index) | CI decisions freshness gate |
| Compatibility | Files written outside `openspec/changes/<id>/` by the auditor | 0 | Skill test asserting read-only posture (checkout_policy snapshot) |
| Operability | Auditor exit code when ledger contains `needs-user`/`unsound` entries | 0 (never blocks a run) | Skill unit test |
| Observability | `choices.json` header fields (`schema_version`, `generated_at`, `git_sha`, `generator`, `run_id`, `event_kind`) | all present and schema-valid | jsonschema validation test |
| Operability | Ranking invariant in `choices.md` | entries strictly ordered ascending by confidence | Skill unit test on renderer |

## Approaches Considered

### Approach 1: New artifact + standalone auditor skill with workflow hooks

Description: A new `audit-choices` skill dispatches an independent read-only
sub-agent that reconstructs decisions from git history + session artifacts and
emits the `choices.md`/`choices.json` pair as a new optional feature-workflow
artifact; thin non-blocking hooks in `iterate-on-implementation` and gate-surfacing
in `validate-feature`/`cleanup-feature`.

- Pros:
  - True to the audit's core requirement: the auditor sees the *diff*, not just
    what the implementer chose to self-report — catches unreported decisions.
  - Follows the `validate-feature-findings-gate` precedent (new schema instead of
    overloading `review-findings.schema.json`, whose validator hard-rejects
    entries without `axis`/`severity`).
  - Composes with existing infra: `parallel-review-implementation`'s read-only
    reviewer posture, the codeviz artifact header, future `ambient-review-ledger`.
  - Standalone invocation works over arbitrary commit ranges and historical changes.
- Cons:
  - Adds a fourth decision-adjacent store (session-log, docs/decisions,
    learning-log, choices) — mitigated by explicit cross-referencing.
  - Requires the schema.yaml + install_assets mirror discipline (CI-tested).
- Effort: M

### Approach 2: Extend `PhaseRecord`/session-log with audit fields in place

Description: Add `gap`/`reach`/`verdict`/`confidence` to the `Decision` dataclass
in `skills/session-log/scripts/phase_record.py`; a verifier agent annotates the
existing self-reported decisions inside `session-log.md`, and a renderer produces
the ranked view from it.

- Pros:
  - Single decision store; no new artifact, no schema.yaml change.
  - Smallest diff; reuses the sanitize/handoff pipeline as-is.
- Cons:
  - **Structurally defeats the purpose**: the auditor can only annotate decisions
    the implementer self-reported — the unreported-decision signal (the most
    valuable output) is unobtainable.
  - Mixes self-report and independent audit in one file, breaking the
    read-only-auditor principle and muddying `docs/decisions/` provenance.
  - Session-log parser/sanitizer churn ripples into every workflow skill and the
    deterministic context-drift gates.
- Effort: S–M

### Approach 3: Ride the `ambient-review-ledger` substrate

Description: Implement (or wait for) the `.review-ledger/` library from the
in-flight `ambient-review-ledger` change and store choices as a new entry kind
with its lifecycle machinery (stable_id, transitions, compact, kanban lane).

- Pros:
  - One shared ledger infrastructure (content-derived stable ids, append-only
    transitions, local-first + coordinator sync) instead of two.
  - Free kanban-viz surface once that change's Phase 5 lands.
- Cons:
  - Blocks on a change that is 0/33 implemented with a ~2.5-month-old plan.
  - Entity mismatch: defects auto-retire when the code is fixed; choices are
    judgments at a point in time and do not — the lifecycle machinery fits badly.
  - Scope balloons far past the S–M artifact-plus-skill this needs to be.
- Effort: L

### Recommended

**Approach 1.** Approach 2 is cheaper but cannot deliver the defining feature —
independently discovering decisions the implementer never reported — and its
session-log churn threatens the deterministic drift gates (a Compatibility NFR).
Approach 3 couples an S–M change to an unstarted L-sized substrate. Approach 1 is
the only one that keeps the auditor genuinely independent and read-only while
following the established new-artifact precedent; its "fourth store" con is
addressed head-on by the cross-reference design (every entry links or explicitly
flags the absence of a self-reported counterpart).

### Selected Approach

**Approach 1** (new artifact + standalone auditor skill with workflow hooks),
selected at Gate 1 with no modifications. Discovery answers baked into the
design: invocation is both standalone and workflow-hooked; output is the
Markdown + JSON sidecar pair; relationship to `docs/decisions/` is
cross-reference-only; `needs-user` verdicts surface at existing human gates
(audit itself never blocks).

## Impact

- **Specs**: `skill-workflow` (ADDED requirements: choices artifact, independent
  read-only audit, ranking invariant, gate surfacing).
- **Schemas**: new `openspec/schemas/decision-choices.schema.json`; new artifact
  entry + template in `openspec/schemas/feature-workflow/` and its
  `skills/plan-feature/install_assets/` mirror; `rules:` block in
  `openspec/config.yaml`.
- **Skills**: new `skills/audit-choices/`; small additive edits to
  `skills/iterate-on-implementation/SKILL.md` (Step 11.5),
  `skills/validate-feature/SKILL.md` and `skills/cleanup-feature/SKILL.md`
  (surface `needs-user` entries at existing gates).
- **Docs**: `docs/guides/workflow.md` mention; positioning note in
  `docs/decisions/README.md` distinguishing audit ledger from generated index.
- **Not touched**: `review-findings.schema.json`, `.review-ledger/` namespace,
  `docs/decisions/*` generated files, `session-log.md` format.
