# Design: introduce-fitness-function-gates

## Context

Audit (2026-08-15) found the repo's architectural-quality machinery exists but is
unwired: the Architecture phase can't fail a run, NFR findings can't survive the review
pipeline, planning captures no measurable NFR targets, no coverage signal exists, and
degraded gates are indistinguishable from passing ones. Approach 1 (extend in place) was
selected at Gate 1. This change supersedes `validate-feature-findings-gate`.

## Goals / Non-Goals

**Goals**: make the existing gate/review/template machinery measure and (ratcheted)
enforce architectural qualities; fix the two bugs that make NFR findings meaningless
today; make every fail-open path loudly visible.

**Non-Goals**: a declarative fitness-function registry (recorded follow-up once several
fitness functions exist); performance-budget benchmarks in CI; operability checks
(runbooks/alerts) — follow-up candidates; changing branch-protection required contexts
(documented promotion commands only, consistent with context-drift-gate precedent).

## Decisions

### D1: Extend in place, no new registry subsystem

Fitness checks live where their phase already lives: gate semantics in
`skills/validate-feature/scripts/gate_logic.py`, architecture thresholds in
`architecture.config.yaml`, review axes in `review-findings.schema.json`, NFR capture in
`feature-workflow` templates. Rejected: `fitness-functions.yaml` registry + generic
runner (abstraction before the signals exist — see proposal Approach 2).

### D2: Axis enum grows to 8; all three copies move together

`observability`, `resilience`, `compatibility` join the five existing values. The
canonical schema, the `install_assets` mirror, and the hand-inlined copy in
`agent-coordinator/agents.yaml` (lines ~282/289) are updated in the same commit; the
exact-match test `skills/tests/parallel-infrastructure/test_review_findings_schema.py`
is updated to the 8-value set and additionally asserts the three copies are identical,
so future enum drift fails a test instead of a review. Legacy findings keep the
documented migration defaults (`axis: correctness`, `severity: fyi`).

### D3: Consensus matching gains axis as a first-class field

`consensus_synthesizer.py`'s `Finding` dataclass gains `axis` (default `correctness`
for legacy payloads); `from_dict` reads it; cross-vendor matching keys become
`(axis, file_path, line_range-overlap)`, making the documented behavior true. Same-axis
requirement prevents an observability finding and a correctness finding at the same
lines from merging and losing one signal. `ConsensusFinding` gains `agreed_axis`
(majority vote, ties resolved toward the more severe finding's axis).

### D4: Architecture gate is config-ratcheted, cycles are the first blocking check

New `gates.architecture` section in `architecture.config.yaml`:

```yaml
gates:
  architecture:
    mode: advisory        # advisory | blocking; flip is a one-line PR with date+rationale
    block_on:
      new_dependency_cycles: true
    clean_runs_before_flip: 3
health:
  severity_thresholds:
    new_cycle: critical
    cross_layer_violation: major
    file_size: minor
```

Phase 1 (this change) ships `advisory`: findings render in a prominent
`validation-report.md` block, run never fails. Phase 2 (follow-up one-line PR after 3
recorded clean runs) flips to `blocking`: `gate_logic.py` adds `"Architecture"` to
`REQUIRED_PHASES` when mode is `blocking`, and a new cycle from `make architecture-diff`
maps to `critical`. Rejected: blocking immediately (risks failing in-flight changes on
pre-existing findings); rejected: cycles-only forever (thresholds exist to grow).

### D5: Coverage ratchet is a separate CI job with a stored baseline

New `coverage-ratchet` job runs `pytest --cov` for `agent-coordinator` and `skills`
suites, compares against `coverage-baseline.json` (repo root; per-suite line
percentages, tolerance 0.5pp), fails on decrease, and prints the update command when
coverage improves. Baseline persistence is intentionally explicit: a maintainer runs
the printed `--update` command and commits the resulting upward-only change; CI has no
repository-write permission. Job starts non-required; promotion command documented next
to the context-drift-gate note in `docs/guides/session-completion.md`. Rejected: absolute
threshold (arbitrary bar penalizes legacy code); rejected: coverage in the existing
`test` job (would couple ratchet failures to the required context immediately).

### D6: DEGRADED is a first-class gate status

`validation-report.md` phase table gains `DEGRADED` as a status value (alongside
pass/fail/skip), with a "what was not checked and why" note. `gate_logic.py` parses it:
soft gate warns and continues; hard gate blocks on a DEGRADED required phase unless
`--accept-degraded <phase>` is passed, and any override is echoed into the gate summary.
Producers updated: autopilot GATEKEEPER fallback verdict, review dispatcher <2-vendor
path, security phase under `--allow-degraded-pass`, validate-feature phases whose
checker binary/service is absent. Rejected: treating DEGRADED as failure everywhere
(would make missing optional tooling block merges and incentivize deleting the check).

### D7: Supersede `validate-feature-findings-gate` by marking, not deleting

Its proposal gets a `**SUPERSEDED — do not implement**` header pointing here (house
precedent: `add-update-documentation-skill`). Its 0/31 tasks are not migrated; the
findings-gate intent is covered by D3/D4/D6.

### D8: NFR capture is a template contract, not free text

`proposal.md` template gains `## Non-Functional Requirements` with a
attribute/metric/target/verifying-phase table; `design.md` template gains a
`### Fitness Functions` subsection mapping each declared NFR to its check. `plan-feature`
SKILL.md gains discovery category 7 (NFR elicitation) referencing the article's
attribute themes (observability, resilience, performance, compatibility, operability).
`iterate-on-plan`'s plan-smell list already flags missing observability/pagination —
unchanged, but its findings can now cite the declared NFR targets.

## Risks / Trade-offs

- **Schema-copy drift**: three copies of the enum is the standing hazard; mitigated by
  the new identity test (D2). Root-cause fix (generate `agents.yaml` block from the
  canonical schema) is out of scope, noted as follow-up.
- **Consensus behavior change**: same-line findings with different axes stop merging;
  review reports may show slightly more findings. Accepted — that is the point.
- **Ratchet stall**: if coverage baseline is set while coverage is accidentally high
  (e.g. a flaky suite skipped), the ratchet blocks unrelated work. Mitigated by
  tolerance + non-required start + documented baseline-reset procedure.
- **Config-driven gating**: `gate_logic.py` reading `architecture.config.yaml`
  introduces a config dependency into a previously pure parser; kept behind a small
  loader with defaults so the file remains optional (per report-configuration spec).
- **Conflicting planned changes**: `add-product-management-skills` and
  `add-visual-plan-review` (both 0 tasks) touch the same templates/SKILL.md; this change
  lands first, they rebase.

## Migration Plan

1. Land schema + consumer updates (wp-schema) — no behavior change for existing
   findings (defaults preserved).
2. Land gate/linter/degradation work (wp-gates) with `mode: advisory` — reports change,
   no run fails that passed before, except: schema-invalid linter output becomes valid
   (strictly more information).
3. Land templates + rubric (wp-templates) — new sections appear in newly scaffolded
   changes only; existing changes unaffected.
4. Land coverage job (wp-coverage) — non-required CI job; baseline committed from the
   first green run's measured values.
5. Follow-up (separate one-line PR, not this change): flip `mode: blocking` after 3
   clean advisory runs; optionally promote `coverage-ratchet` to required.

## Open Questions

- Should `agreed_axis` majority-vote ties prefer severity rank or vendor priority?
  (Implementation may pick either; record in code comment + session log.)
- Exact tolerance for the coverage ratchet (0.5pp proposed) — tune after first week of
  runs.
