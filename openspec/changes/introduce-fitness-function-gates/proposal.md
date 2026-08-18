# Change: introduce-fitness-function-gates

## Why

The repo's two existing feedback loops — spec-driven (OpenSpec artifacts) and test-driven
(pytest/mypy/ruff) — verify *functional* intent. Architectural qualities ("-ilities":
observability, resilience, compatibility, maintainability) are reviewed extensively but
never *measured or enforced*. A repo audit (2026-08-15, this session) found the machinery
exists but is systematically unwired:

- The Architecture validation phase is non-critical in `validate-feature` and absent from
  `REQUIRED_PHASES` in `gate_logic.py`; `architecture.config.yaml` ships
  `severity_thresholds: {}`. `make architecture-diff` already detects new dependency
  cycles — a ready-made, deterministic fitness function that gates nothing.
- NFR review findings cannot survive the pipeline: the `axis` enum in
  `review-findings.schema.json` lacks NFR values, `consensus_synthesizer.py` silently
  drops `axis` entirely (contradicting its documented "axis + file_path + line_range"
  matching), and the validate-feature linters emit schema-invalid findings (missing
  required `axis`/`severity` — untested because the linter test loads the schema but
  never validates against it).
- Planning artifacts have no NFR slot: `proposal.md`/`design.md` templates and the
  `plan-feature` interview never capture a measurable quality target, so reviewers check
  observability/resilience against an implicit house standard. There is nothing to write
  a fitness function *against*.
- No coverage signal exists anywhere (no `--cov`, no threshold), and degraded gates fail
  open indistinguishably from passing (GATEKEEPER without adapter, <2-vendor review,
  `--allow-degraded-pass`, `continue-on-error` CI jobs).

Fitness-function-driven development (Thoughtworks, Paul & Wang 2019) closes this gap:
express architectural standards as executable, objective checks in the delivery pipeline,
so architectural drift is caught during development, not after.

This change **supersedes `validate-feature-findings-gate`** (0/31 tasks, untouched),
which planned a findings-model + enforcement-gate rewrite of the same surface; its intent
is absorbed here.

## What Changes

- **Planning NFR capture**: `feature-workflow` templates `proposal.md` and `design.md`
  gain a "Non-Functional Requirements / Fitness Functions" section (measurable targets,
  not adjectives); the `plan-feature` discovery rubric gains an NFR elicitation prompt.
- **Findings schema**: `axis` enum gains `observability`, `resilience`, `compatibility`
  — updated in all three schema copies (canonical, `install_assets` mirror,
  `agents.yaml` inline), the exact-match schema test, both `parallel-review-*` SKILL.md
  axis tables, and the normative `skill-workflow` spec.
- **Bug fix — consensus axis matching**: `consensus_synthesizer.py`'s `Finding` gains the
  `axis` field and consensus matching uses it as documented. (Currently silently dropped.)
- **Bug fix — schema-valid linter findings**: the three validate-feature linters emit
  required `axis`/`severity` fields; the linter test gains actual `jsonschema.validate`
  assertions.
- **Architecture gate promotion (two-phase ratchet)**: Phase 1 wires the Architecture
  phase into `REQUIRED_PHASES` behind a config flag in `architecture.config.yaml` with
  populated `severity_thresholds`, reporting loudly but advisory; Phase 2 (dated flip,
  after N clean runs) makes new-dependency-cycle findings and above-threshold severities
  blocking in `cleanup-feature`'s hard gate. **BREAKING** (Phase 2): changes that
  introduce dependency cycles will fail the merge gate.
- **Coverage signal**: advisory `pytest --cov` reporting in CI and
  `validation-report.md`, with a stored baseline and a no-decrease ratchet check.
- **Degradation transparency**: every gate that can fail open (GATEKEEPER fallback,
  <2-vendor review, `--allow-degraded-pass`, degraded security scans) writes an explicit
  `DEGRADED` status into `validation-report.md` and the gate summary, so "passed" and
  "couldn't check" are distinguishable in every report.

## Approaches Considered

### Approach 1: Extend existing machinery in place

Wire fitness functions into the current phase/gate model: extend `validate-feature`
phases, `gate_logic.py`, the findings schema, and the feature-workflow templates where
they already live. No new subsystem.

- **Pros**: Smallest conceptual surface — every touched file already owns the concern;
  reuses the consensus pipeline, validation-report format, and phase criticality ladder;
  bug fixes land in the same files the feature touches; agents and CI share one code path.
- **Cons**: Fitness thresholds stay scattered across `architecture.config.yaml`, CI
  YAML, and gate logic rather than being declaratively centralized; adding a *new*
  fitness function later still means editing skill scripts.
- **Effort**: L (decomposes into M-sized staged packages)

### Approach 2: Declarative fitness-function registry

Introduce a first-class `openspec/fitness-functions.yaml` registry (metric, threshold,
phase, criticality per entry) plus a generic runner script; `validate-feature` executes
the registry instead of hard-coding checks.

- **Pros**: Most faithful to the article — architecture standards as versioned,
  reviewable code; adding/tuning a fitness function becomes a data change; one place to
  audit all "-ility" thresholds.
- **Cons**: A new subsystem to spec, test, and maintain on top of (not instead of) the
  existing phase model; duplicates `validate-feature`'s phase/criticality semantics;
  higher risk while the underlying signals (coverage, architecture severities) don't
  exist yet — abstraction before there's anything to abstract over.
- **Effort**: XL

### Approach 3: CI-first enforcement

Implement everything as GitHub Actions jobs and branch-protection contexts (coverage
ratchet job, architecture-gate job, degradation-status job), leaving skills and schemas
untouched.

- **Pros**: Smallest code footprint; branch protection makes gates genuinely
  unbypassable; no skill/schema migration.
- **Cons**: Misses the agent-side loop entirely — agents validate via
  `validate-feature` before push, so failures surface at PR time instead of during
  development (exactly the "after the fact" feedback the article argues against); does
  nothing for NFR capture in planning or NFR findings in review; leaves both discovered
  bugs standing.
- **Effort**: M

### Recommended

**Approach 1.** The audit's central finding is that the machinery already exists but is
unwired — the cheapest correct move is wiring it, not rebuilding it. Approach 2's
registry is attractive as a *future* refactor once several fitness functions exist and
their shape is known (noted as a follow-up candidate), but today it abstracts over two
signals that don't exist yet. Approach 3 fails the article's core requirement of feedback
*during* development and leaves the schema/consensus bugs — prerequisites for NFR
findings to mean anything — unfixed.

### Selected Approach

**Approach 1 — Extend existing machinery in place** (selected at Gate 1, 2026-08-15, no
modifications requested). The declarative registry (Approach 2) is recorded as a
follow-up candidate once several fitness functions exist and their common shape is
known.

## Impact

- **Specs**: `skill-workflow` (axis enum values, validation phase criticality — MODIFIED),
  `report-configuration` (architecture.config.yaml thresholds — MODIFIED or ADDED
  requirement), new delta requirements for NFR template capture and degradation
  reporting.
- **Schemas/templates**: `openspec/schemas/review-findings.schema.json` (+ 2 mirrored
  copies), `openspec/schemas/feature-workflow/templates/{proposal.md,design.md}`.
- **Skills**: `plan-feature` (rubric + templates), `validate-feature`
  (`gate_logic.py`, linters, validation-report), `parallel-infrastructure`
  (`consensus_synthesizer.py`), `parallel-review-plan` / `parallel-review-implementation`
  (axis tables), `autopilot` (GATEKEEPER degradation reporting).
- **CI**: `.github/workflows/ci.yml` — additive coverage job (three prior changes
  landed jobs in this file; edits must not clobber them).
- **Config**: `architecture.config.yaml` (`severity_thresholds`, ratchet flag).
- **Superseded**: `validate-feature-findings-gate` (recorded here without touching
  its change directory; absorbed by this proposal).
- **Known conflicts to sequence around**: `add-product-management-skills` and
  `add-visual-plan-review` both plan edits to the same templates/SKILL.md (both at 0
  tasks; this change lands first).
