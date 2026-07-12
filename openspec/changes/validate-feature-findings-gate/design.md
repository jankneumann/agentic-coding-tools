# Design — Findings-Model + Enforcement Gate for `validate-feature`

## Context

`validate-feature` (skills/validate-feature/SKILL.md) runs a 9-phase pipeline
(`deploy → smoke → gen-eval → security → e2e → architecture → spec → logs → ci`)
and emits a prose `validation-report.md`. Its only structured output today is the
architecture phase, which already produces `review-findings.schema.json` records
(SKILL.md §6b). This change generalizes that one structured output into the
pipeline-wide contract, then layers a gate, an ephemeral mode, and a triage loop
on top — adapting the four transferable properties of
[no-mistakes](https://github.com/kunchenguid/no-mistakes) onto our stack.

Affected architecture layers: **Execution** (validation run), **Governance**
(enforcement gate, task-drift). No Coordination/Trust schema changes.

## Goals / Non-Goals

- **Goal**: one machine-readable findings file per run that the report renders from.
- **Goal**: opt-in hard gate on the critical subset; advisory remains the default.
- **Goal**: isolation that leaves no residue on the branch under test beyond the
  intentionally-persisted `validation-report.md` / `validation-findings.json`.
- **Goal**: an interactive + headless triage surface over escalated findings.
- **Non-goal**: a Go push-proxy, a new TUI binary, or modifying the existing
  `review-findings.schema.json` contract. (We *do* add one new self-contained
  `validation-findings.schema.json` — see D1 — but leave the review schema alone.)
- **Non-goal**: making the gate default-on or weakening pipeline depth.

## Decisions

### D1 — Reuse the review-*finding record*, not the review *envelope*; new `validation-findings.schema.json`

`review-findings.schema.json` describes a *review* artifact: its `review_type`
enum is `plan` / `implementation`, its top level is just `findings[]` (no
per-phase status), and its finding record *requires* `disposition`, `axis`, and
`severity` — review-specific fields that don't map onto a validation phase. Every
attempt to reuse that schema for validation findings created friction (overloading
`disposition`, then the missing envelope, then the required review-only fields).
So we stop reusing the schema and instead add a **self-contained**
`validation-findings.schema.json`: an envelope (`schema_version`, `change_id`,
validated commit), a `phase_statuses[]` array, and a `findings[]` whose item is a
validation finding record (`id`, `type`, `criticality`, `description`, `phase`,
file/endpoint, optional `fixability`, optional `triage_state`). It borrows familiar
field *names* for ergonomics but shares no required-field set with the review
schema.

`review-findings.schema.json` is therefore **left byte-for-byte unchanged** — we do
not add `fixability`/`triage_state` to it, do not touch `disposition`, and do not
add `validation` to `review_type` — so the parallel-review pipeline, architecture
linters, and `consensus_synthesizer` are wholly unaffected (Risk: schema churn →
eliminated). Contract tests assert the review schema is unchanged and that a
complete `validation-findings.json` validates against the new schema.

### D2 — Auto-fix delegates to existing low-risk fixers only

`auto-fix` does not implement its own mutation logic. It calls the `simplify` and
`fix-scrub` skills, which already enforce a "low-risk, behavior-preserving"
boundary — the same boundary that defines the auto-fix/escalate split. This keeps
one definition of "safe to apply headless" instead of two. Every auto-fix
re-runs its originating phase and reverts on regression (Risk: unsafe auto-fix).

### D3 — Classifier defaults to escalate

Disposition assignment is conservative: only an allowlist of mechanical
finding-types (formatting, import-order, naming-convention from the structural
linters) maps to `auto-fix`; everything else, and anything ambiguous, is
`escalate`. This makes the dangerous direction (auto-applying an intent change)
the one that requires explicit opt-in classification.

### D4 — Gate is a git hook, not a proxy

The enforcement gate is a `pre-push` hook installed by the existing `.githooks`
installer, running only the **critical** subset (`smoke`, spec task-drift,
`security` thresholds) — fast enough for a push-time gate, unlike the full
deploy/E2E pipeline. We reject no-mistakes' transport-proxy model (proposal
Approach B) because a proxy can't see OpenSpec change context and duplicates
orchestration we already own. Escape hatches: `VALIDATE_GATE=0` and
`git push --no-verify`.

### D5 — Ephemeral mode reuses the `worktree` skill

`--ephemeral` clones `HEAD` via the existing `worktree` lifecycle scripts rather
than inventing a clone path, and short-circuits to in-place behavior under
`environment_profile.detect()` cloud-harness detection — matching the rest of the
worktree stack (CLAUDE.md worktree-management guide). The report/findings file is
copied back to the change branch before teardown so results survive.

### D6 — One triage_state model, two collection surfaces

Triage writes the same `triage_state` (`approve` / `fix` / `skip`) + resolution
fields whether collected via `AskUserQuestion` (agent harness) or a CLI prompt
loop, and never mutates the existing `disposition` field. A single render/apply
path consumes them, so agent and CLI runs converge on identical findings-file
state and are resumable.

## Risks / Trade-offs

See proposal "Risks". The sharpest trade-off is **breadth**: Phase 1 touches
every phase's output path. Mitigated by a shared `emit_finding()` helper (one
call site per phase) and a per-phase contract test asserting findings validate.

## Migration / Rollout

- Phase 1 ships first and is independently useful (structured report) even if
  2–4 never land.
- Phase 2 (gate) is opt-in install — zero impact until an operator installs it.
- Phase 3 (`--ephemeral`) and Phase 4 (`--triage`/`-y`) are new flags; default
  invocation is unchanged.
- No data migration: `validation-findings.json` is regenerated per run.

## Open Questions

- Should the gate's `security` threshold reuse `--allow-degraded-pass` (treat a
  degraded scanner as pass) or block on degraded? Leaning **allow-degraded-pass**
  to avoid blocking pushes on a missing local Java/container runtime.
- Should `auto-fix` results be committed automatically in the gate path, or only
  staged for the operator? Leaning **staged-only** at push time to avoid
  surprising commits mid-push.
