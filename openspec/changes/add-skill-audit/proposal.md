# Change: add-skill-audit

## Why

Every SKILL.md in this repo is read by every model tier. `phase_mapping` in
`agent-coordinator/archetypes.yaml` sends PLAN to the `architect` archetype at
`frontier`, IMPLEMENT to `implementer` at `standard`, and INIT / SUBMIT_PR to
`runner` at `economy`, yet the prose those agents follow is identical. A
frontier model at high thinking pays for numbered procedure it would derive
itself; an economy model without the same procedure omits steps. The two
failure modes are opposite, and one skill text cannot be tuned for both. The
roster already encodes the right criterion for tiers ("cost per successful
task, not cost per token" — `archetypes.yaml` line 17); nothing applies that
criterion to skill text.

The `skill-rightsizing` roadmap (20 items, all `candidate`, 0/10 tasks each)
plans the one-shot cuts and a sealed A/B, and `add-harbor-benchmark-routing`
will own the vendor × model × thinking sweep. What neither provides is a
**recurring, evidence-joined audit** that re-runs when the roster rotates
(`reviewed` dates changed on 2026-08-16 and 2026-09-13), when a new tier lands
(`add-frontier-model-tier`, 11/13), or when capability-gap signals tagged
`affected_skill:` accrue in episodic memory. Skills drift out of fit with the
models running them and nobody notices until a transcript shows the struggle.
This change adds the audit that makes the rightsizing cuts repeatable instead
of hand-planned, and gives the dispatch layer one structured knob for
tier-dependent procedure density.

## What Changes

- **New user-invocable skill `skills/skill-audit/`** with a CLI script
  (`scripts/skill_audit.py`) invoked as
  `/skill-audit <skill-name> | --all [--evidence-window <days>] [--convention rightsizing|current] [--propose] [--check-freshness]`.
  It is read-only over the audited skill: it emits reports and candidate-work
  stubs, never edits a SKILL.md.
  - **Layer classification.** Every section of the target SKILL.md and its
    one-level `references/` is labelled `contract`, `constraint`,
    `procedure`, or `teaching`. A deterministic pre-pass assigns the label
    where the shape decides it (fenced commands, exit-code tables, schema
    paths, `<skill-base-dir>` invocations, and frontmatter are `contract`;
    "never/must not" sentences carrying a stated reason are `constraint`;
    numbered imperative steps are `procedure`). Prose that the pre-pass
    cannot decide goes to one LLM call per skill at the `analyst` archetype
    with a strict output schema; invalid responses are dropped with a warning
    and the section is reported `unclassified`, never guessed.
  - **Dispatch profile.** For each audited skill the audit reads
    `phase_mapping` and the archetype table in the `agent-archetypes` spec
    ("Skill Model Hint Integration") to list which archetypes and therefore
    which `(provider, model, thinking)` tiers actually run the skill, using
    `skills/shared/archetype_roster.py` so `{model, thinking}` entries and the
    optional `frontier` tier resolve the same way dispatch resolves them.
  - **Evidence join.** Episodic-memory entries tagged `affected_skill:<name>`
    from all four sources (`self-reported`, `coordinator-emitted`,
    `session-log`, `transcript-mined`) are joined to the tier that ran the
    failing phase: `openspec/changes/**/loop-state.json` (`change_id`,
    `phase_archetype`, `phase_history`) plus coordinator
    `GET /discovery/agents` session `phase_archetype`, resolved through
    `model_aliases`. The result is a per-skill, per-tier failure table with
    source attribution and the cross-source agreement line `/improve-harness`
    already prints. When the coordinator is unreachable the join reports
    "no evidence" and the audit still completes on layer findings alone.
  - **Findings ledger.** `skill-audit-findings.json` (schema shipped under
    `install_assets/openspec/schemas/skill-audit-findings.schema.json`) with
    one entry per finding: `teaching_inferable`, `procedure_without_probe`,
    `constraint_without_reason`, `contract_unpinned` (no test cites the
    section), `missing_deviation_protocol`, `tier_concentrated_failure`,
    `convention_drift`. Each names the layer, the section, the evidence, and
    exactly one remediation from `keep | move_to_reference |
    extract_to_script | add_probe | add_reason | delete`. Sections labelled
    `contract` SHALL never receive `delete`; a guard test enforces it.
  - **Report and hand-off.** A markdown report at
    `docs/reports/skill-audit/<skill>-<date>.md` with the layer histogram,
    dispatch profile, tier failure table, ranked findings, a proposed
    lean-SKILL.md outline plus `references/procedure.md` outline, and a
    freshness stamp (`archetypes.yaml` content hash, `reviewed` dates,
    evidence window). `--propose` additionally writes a schema-valid
    candidate-work stub in the same shape `/improve-harness` emits, so
    findings flow into `/prioritize-proposals` and the rightsizing roadmap.
  - **Freshness check.** `--check-freshness` compares the roster hash in the
    latest report against the current `archetypes.yaml` and exits `1` when a
    re-audit is due. CI wires it as a non-blocking warning job.
  - **Convention selection.** `--convention rightsizing` (default) lints
    frontmatter and tail block against the post-`rewrite-skill-frontmatter` /
    post-`delete-rationalizations-relax-tail-block` shape (no `triggers:`,
    tail block optional, SKILL.md ≤ 500 lines, references one level deep).
    `--convention current` lints against today's
    `skills/tests/_shared/skill_invariants.py`. Skills that satisfy neither
    get `convention_drift` findings naming the offending rule.
- **`archetypes.yaml` schema_version 4: optional `procedure_mode` per
  archetype**, one of `verbatim | guided | goal-directed`. Omitted means
  `guided`, which is today's behaviour (no injection), so existing files
  validate unchanged. There is exactly one injection point:
  `resolve_archetype_for_phase` in `agents_config.py` appends one fixed
  sentence per mode to the returned `system_prompt` and adds an optional
  `procedure_mode` passthrough field to the response. The autopilot fold in
  `skills/autopilot/scripts/phase_agent.py` already forwards that
  `system_prompt` verbatim, and the review dispatcher never composes an
  archetype prompt, so neither needs a code change. The sentences:
  `verbatim` tells the agent to follow the skill's procedure
  reference step by step; `goal-directed` tells it to satisfy the skill's
  acceptance probes by any route and to record every deviation from the
  written procedure as a session-log `Decision` with
  `capability: skill-procedure-deviation`. The authored roster sets `runner`
  to `verbatim` and `architect` to `goal-directed`; all others stay `guided`.
  Tests derive expectations from the YAML, never from literals, per the
  existing `test_archetypes_yaml.py` convention.
- **Spec deltas** in `skill-workflow` (new Skill Audit requirement),
  `agent-archetypes` (schema field, injection contract), and
  `harness-engineering` (evidence join over the capability-gap tag schema).
- **Distribution wiring**: `skills/install-manifest.json` entry with
  `cross_skill_dependencies` on `shared`, `coordination-bridge`,
  `improve-harness`; `skills/tests/skill-audit/` added to `skills/pyproject.toml`
  testpaths; runtime mirrors regenerated by `install.sh`.

### Explicitly deferred to follow-up changes

- **A/B benchmark runs** of current vs. pruned skill variants across tiers.
  The audit emits the variant outline and the tier list; execution belongs to
  `add-harbor-benchmark-routing` (combo sweep) or `packages/agent-scenarios`
  (`skill_under_test`). The findings schema reserves an `evidence.benchmark`
  slot so a later change fills it without a schema bump.
- **`--apply`** that rewrites a SKILL.md into the proposed split. v1 proposes
  only; `apply-progressive-disclosure-oversized-skills` (ri-15) and
  `cut-competence-rules-relocate-policy` (ri-14) own the edits.
- **Reading the `/doctor` context-cost baseline** (ri-04) as the denominator
  for per-skill context cost. The report has a `context_cost` column that
  reads the baseline file when present and prints `n/a` otherwise.
- **Persisting `phase_archetype` per `phase_history` entry.** Today
  `LoopState.phase_archetype` is a scalar for the current phase, so historic
  per-phase tiers are reconstructed from `phase_history` plus handoff
  documents. Making it per-entry is an autopilot change, not this one.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Determinism | Pre-pass layer labels and findings for a fixed SKILL.md and fixed LLM stub | Byte-identical `skill-audit-findings.json` across two runs | `skills/tests/skill-audit/test_classifier.py` |
| Cost | LLM calls per audited skill in `--all` | ≤ 1 call per skill (sections batched), `analyst` archetype only, zero calls when every section is decided by the pre-pass | `test_classifier.py` call-count assertion with a stub backend |
| Operability | Wall time of `--all` over the 74-skill corpus with the LLM backend stubbed | ≤ 60 s on the committed corpus | `test_cli.py` timing assertion (skipped when corpus absent) |
| Resilience | Behaviour with coordinator unreachable or `try_recall` unauthorized | Exit `0`, report carries `evidence: unavailable (<reason>)`, layer findings still emitted | `test_evidence_join.py` with a failing bridge stub |
| Compatibility | Roster shapes accepted | Bare tier ids and `{model, thinking}` entries; missing `frontier` falls back to `premium`; `procedure_mode` absent validates as `guided` | `agent-coordinator/tests/test_archetypes_yaml.py`, `test_agents_config.py` |
| Safety | Findings whose remediation is `delete` on a `contract` section | 0, enforced by schema `if/then` and a guard test | `test_findings_schema.py` |
| Context cost | `skills/skill-audit/SKILL.md` line count; reference depth | ≤ 150 lines (hard cap 500); references one level deep; TOC if > 100 lines | `skills/tests/skill-audit/test_skill_md.py` |
| Compatibility | Skill test result with and without a `triggers:` key in its own frontmatter | Passes in both states | `test_skill_md.py` explicit key assertions |
| Observability | Every report carries a freshness stamp | `archetypes_sha256`, `reviewed_dates`, `evidence_window_days`, `generated_at` present; `--check-freshness` exits `1` on hash mismatch | `test_freshness.py` |

## Approaches Considered

### Approach 1: Standalone recurring audit skill with a structured `procedure_mode` knob

Description: a new `skill-audit` skill runs a deterministic-first layer
classifier over any SKILL.md, joins `affected_skill:` memory signals to the
tier that ran the phase via `loop-state.json` and the discovery endpoint, and
emits a findings ledger, a report with a freshness stamp, and candidate-work
stubs. Tier-dependent procedure density becomes an optional `procedure_mode`
field on archetypes, injected at the three existing prompt-composition points.

Pros:
- Consumes the rightsizing roadmap's substrates (telemetry scorecard, doctor
  baseline, harbor combos) when they land and degrades gracefully until then;
  no item in that roadmap is blocked or duplicated.
- The knob lives where the tier is actually known (archetype resolution), so
  SKILL.md stays single-sourced across tiers and mirrors.
- Re-audit is triggered by data (roster hash, new signals), not by a human
  remembering.
- Reuses `improve-harness` query and dedup code, `archetype_roster.py`
  resolution, and the `audit_triage` strict-schema LLM pattern.

Cons:
- Adds one more field to a schema six consumers pin; requires a schema bump
  and test updates in `agent-coordinator/tests/`.
- Static classification cannot prove a cut is safe; it ranks candidates and
  defers proof to the benchmark changes.
- Name is adjacent to the coordinator `audit` module and the `audit-choices`
  skill; needs a clear description to avoid mis-triggering.

Effort: M

### Approach 2: Append the audit as item ri-21 of the `skill-rightsizing` roadmap

Description: use `/refine-roadmap` to add a "recurring re-audit" item that
depends on ri-14, ri-15, and ri-17, so the audit is built only after the
one-shot cuts and the sealed holdout decision, and inherits the roadmap's
pre-registered accept/reject rule.

Pros:
- Zero duplication with the roadmap by construction; the audit is defined
  against the post-cut skill shape.
- The sealed A/B decision rule applies to audit-proposed cuts automatically.

Cons:
- Nothing ships until the roadmap's 17 upstream items land; all are still
  `candidate` at 0/10 tasks. The roster has rotated twice in the meantime.
- Leaves the `procedure_mode` knob undefined, because no roadmap item owns
  archetype-side behaviour.
- The user's stated need is a recurring audit that runs now, over today's
  skills, and informs the cuts; sequencing it after the cuts inverts that.

Effort: S to scaffold, L end-to-end

### Approach 3: A `--target skill:<name>` mode on `agent-ergonomics`

Description: extend the existing prose-only `agent-ergonomics` skill with a
skill target whose journeys are the skill's invocations, reusing its nine
properties and friction ledger, with no scripts.

Pros:
- Smallest new surface; the rubric and anti-goals already exist and are
  well-written.
- No schema changes anywhere.

Cons:
- `agent-ergonomics` has no scripts, no ledger schema, and no tests, so the
  evidence join and freshness check would be re-narrated prose the model may
  or may not execute; exactly the "procedure transcribed into English" that
  ri-12 is removing.
- Cannot express the tier dimension: the nine properties are tier-agnostic
  by design.
- Adds a second responsibility to a skill whose value is its narrow rubric.

Effort: S

### Recommended

Approach 1. It is the only approach that (a) runs now over today's skills,
(b) puts tier-conditional behaviour where the tier is known instead of in
prose, and (c) is designed to consume rather than compete with the
rightsizing roadmap and the harbor sweep. Approach 2's sequencing cost is the
decisive con given the roster has rotated twice in a month; Approach 3 cannot
carry the tier dimension at all.

### Selected Approach

Selected at Gate 1 by the user on 2026-09-15: **Approach 1**, with the four
discovery answers recorded as binding constraints:

1. Positioning: a standalone recurring audit over the rightsizing roadmap's
   substrates, degrading gracefully while they are unbuilt.
2. Eval depth for v1: static classification plus evidence join; no benchmark
   runs.
3. Procedure hints: a new optional schema key on archetypes in
   `archetypes.yaml`, not `system_prompt` text and not a skill-owned policy
   file.
4. Lint convention: the rightsizing conventions are canonical;
   `add-product-management-skills` is flagged as needing rebase, and
   `--convention current` remains available during the transition.

Approaches 2 and 3 are retained above for the record; neither is scheduled.

## Impact

Architecture layers: **Execution** (the new skill and its tests),
**Coordination** (archetype resolution and prompt composition gain
`procedure_mode`), **Governance** (procedure density becomes declared policy
in the roster rather than implicit in prose). No Trust-layer change: the skill
is read-only over the coordinator and `write_capable` semantics are untouched.

Affected specs and delta files:

| Capability | Delta | Kind |
|---|---|---|
| `skill-workflow` | `specs/skill-workflow/spec.md` | ADDED: Skill Audit Skill (classification, dispatch profile, findings ledger, report, freshness, convention selection, candidate-work hand-off) |
| `agent-archetypes` | `specs/agent-archetypes/spec.md` | MODIFIED: Archetype Definition Schema (optional `procedure_mode`); ADDED: Procedure Mode Prompt Injection |
| `harness-engineering` | `specs/harness-engineering/spec.md` | ADDED: Capability Gap Signals Joined to Dispatch Tier |

Code and docs:

- `skills/skill-audit/` (SKILL.md, `scripts/skill_audit.py`, `scripts/classifier.py`, `scripts/evidence_join.py`, `scripts/report.py`, `references/`, `install_assets/openspec/schemas/skill-audit-findings.schema.json`)
- `skills/tests/skill-audit/`
- `agent-coordinator/archetypes.yaml` (schema_version 4, `procedure_mode` on `runner` and `architect`)
- `skills/autopilot/install_assets/openspec/schemas/archetypes.schema.json`
- `agent-coordinator/src/agents_config.py` (`ArchetypeConfig.procedure_mode`, `compose_prompt`), `agent-coordinator/tests/test_archetypes_yaml.py`, `test_agents_config.py`
- `skills/coordination-bridge/scripts/coordination_bridge.py` (`try_resolve_archetype_for_phase` passes `procedure_mode` through when present; no behaviour change otherwise)
- `skills/install-manifest.json`, `skills/pyproject.toml` (testpaths), `.github/workflows/*` (non-blocking freshness job)
- `docs/guides/skills.md` (one paragraph: when to run the audit), `docs/reports/skill-audit/` (generated)

Not breaking: `procedure_mode` is optional with a default equal to current
behaviour; existing `archetypes.yaml` files validate under schema 4 without
edits. No rollback plan needed beyond reverting the schema bump.

Conflict notes for implementers:

- `reconcile-versions-and-stale-docs-to-one-truth` will consolidate the memory
  tag schema; the evidence join reads the schema through
  `improve-harness/scripts/analyze_failures.py` helpers rather than restating
  it.
- `axi-align-coordinator-output` changes the CLI envelope of `memory query`;
  the join uses the HTTP bridge (`coordination_bridge.try_recall`) and
  `/memory/query`, not the CLI.
- `followup-add-prime-agent-harness` adds a sixth provider to `model_aliases`;
  the dispatch profile enumerates providers from the file, never from a list.
