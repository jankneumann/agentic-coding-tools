# Design — add-skill-audit

## Context

Every SKILL.md is read by every tier the roster dispatches, and the roster is
the only place the tier is known. `resolve_archetype_for_phase` in
`agent-coordinator/src/agents_config.py` returns `{model, system_prompt,
archetype, reasons, write_capable}`; the autopilot fold in
`skills/autopilot/scripts/phase_agent.py` prepends that `system_prompt` to the
phase prompt verbatim; the review dispatcher only resolves `(model, thinking)`
and never composes an archetype prompt. Capability-gap signals land in
episodic memory under a shared tag schema with `affected_skill:` but no tier
tag; `LoopState.phase_archetype` is a scalar for the current phase and reaches
the coordinator through `POST /status/report` into `agent_sessions`.

The `skill-rightsizing` roadmap (ri-01..ri-20, all `candidate`) owns the
one-shot cuts, the sealed corpus, the replay runner (superseded by
`add-harbor-benchmark-routing`), and the blinded judge. Two in-flight changes
disagree on conventions: `rewrite-skill-frontmatter` and
`delete-rationalizations-relax-tail-block` remove `triggers:` and relax the
tail block; `add-product-management-skills` keeps both. Architecture
artifacts are last-known-good (20 commits behind) and do not cover `skills/`.

## Goals / Non-Goals

Goals:

- Classify any SKILL.md by layer deterministically first, with at most one
  model call per skill for the remainder.
- Say, per skill, which `(provider, model, thinking)` tiers run it, from the
  roster file only.
- Join `affected_skill:` failures to the tier that ran the failing phase and
  surface tier-concentrated failures.
- Emit a schema-valid findings ledger and a stamped report that goes stale
  when the roster changes, plus candidate-work stubs in the existing shape.
- Give the roster one structured field for procedure density, injected at
  the one place the tier is resolved.

Non-goals (deferred per proposal):

- Running A/B benchmarks; rewriting any SKILL.md (`--apply`); reading the
  `/doctor` baseline beyond an optional column; per-entry `phase_archetype`
  in `phase_history`.

## Decisions

### D1 — Deterministic pre-pass first; one batched model call per skill

The classifier runs a rule-based pass over the parsed markdown AST (headings,
fenced blocks, tables, ordered lists, paragraphs) and labels every section the
rules can decide. Only undecided prose sections are collected and sent in a
single call whose output schema is `{section_id: label}` with `label` drawn
from the four layers. Invalid output labels the whole batch `unclassified`.
This mirrors `audit_triage`'s strict-schema posture and makes the NFRs for
determinism and cost testable without an LLM in CI: with a fixed stub the
ledger is byte-identical, and the call count is asserted directly.

Alternative rejected: LLM-first classification with rule-based validation.
It inverts the cost profile (74 calls minimum for `--all`) and makes the
common case non-deterministic.

### D2 — Layer definitions are shape rules, written once

| Layer | Pre-pass rule | Why the model cannot derive it |
|---|---|---|
| `contract` | frontmatter; fenced command blocks; tables whose header names exit codes, schemas, paths, or flags; paragraphs with `<skill-base-dir>` | Another agent depends on it; cannot be inferred |
| `constraint` | prohibition (`never`, `must not`, `SHALL NOT`, `do not`) plus a reason clause (`because`, `so that`, `otherwise`, parenthetical) in the same paragraph | Operator intent; a strong model given the reason generalises, given only the rule it argues |
| `procedure` | ordered list whose items start with an imperative verb | The lever that varies by tier |
| `teaching` | model-labelled only | Generic competence a frontier model already holds |
| `unclassified` | pre-pass undecided and model output invalid | Never guessed |

The rule table lives in `skills/skill-audit/references/layers.md` and is the
single source both the classifier docstring and the report legend cite.

### D3 — `procedure_mode` on the archetype, injected at coordinator resolution only

The mode is a property of the archetype (the role), not of the tier it
escalates to, so it belongs on the archetype entry. It is injected in
`resolve_archetype_for_phase` by appending one module-level constant sentence
to `system_prompt` and adding `procedure_mode` to `ResolvedArchetype` and the
HTTP response. The autopilot fold forwards `system_prompt` unchanged and the
bridge passes the new field through when present, so no skills-side prompt
code changes. `guided` appends nothing, so the default is byte-identical to
today.

Alternatives rejected: writing the sentence into each `system_prompt` string
(unstructured, untestable, drifts); a skill-owned policy file (second source
of truth for archetype behaviour); tier-conditional text in SKILL.md (models
do not know their tier; multiplies mirrors).

Authored values: `runner: verbatim` (economy phases INIT and SUBMIT_PR omit
steps when unguided), `architect: goal-directed` (frontier planning pays for
scaffolding it would derive). All others remain `guided` until evidence from
the audit says otherwise.

### D4 — Evidence join precedence and the `unknown` bucket

For each memory entry: loop-state by `change_id` (nearest `phase_history`
entry to `created_at`), then discovery session by `agent_id` and heartbeat
window, then `unknown`. Entries are never dropped; `unknown` is a row. Tier
resolution goes through `archetype_roster.resolve_tier_for_provider` with the
provider from the entry's `agent_type`, so `{model, thinking}` entries and the
`frontier → premium` fallback behave exactly as dispatch. Query and tag
parsing reuse `analyze_failures.py` (`build_memory_query`, `_extract_tag`,
`deduplicate_findings`) so the tag schema is stated once; when
`reconcile-versions-and-stale-docs-to-one-truth` moves it, this skill follows.

### D5 — Findings schema with a guard, and a reserved benchmark slot

`skill-audit-findings.schema.json` declares `kind`, `layer`, `section`,
`evidence`, `remediation`, and uses an `if layer == contract then remediation
!= delete` clause. `evidence` has `status: available|unavailable`,
`repo_specific_tokens`, `tier_rows`, `sources`, and an optional `benchmark`
object that v1 never fills; a later benchmark change fills it without a
schema bump. The classifier raises before writing if the guard would fail,
so the schema is a second line, not the first.

### D6 — Freshness is a content hash, checked non-blocking in CI

The report stamp carries `sha256(archetypes.yaml)`, the list of `reviewed`
dates, the evidence window, and `generated_at`. `--check-freshness` compares
the newest report's hash to the file and exits `1` on mismatch. CI adds a
job `skill-audit-freshness` with `continue-on-error: true` that runs
`--check-freshness --all` and annotates; it never blocks merges because
staleness is a prompt to re-audit, not a defect in the change under review.

### D7 — Convention selection defaults to rightsizing; the skill's own tests pass in both states

`--convention rightsizing` is the default per the user's Gate 1 answer. The
skill's own `SKILL.md` ships with `triggers:` present (today's invariants
require it) and `test_skill_md.py` asserts keys explicitly, as
`add-visual-code-explainer` D6 does, so removing `triggers:` when
`rewrite-skill-frontmatter` lands changes nothing in the test. The tail block
is present because `assert_tail_block_present` still runs on
`user_invocable: true` skills.

### D8 — Candidate-work stubs through the improve-harness projection helper

`--propose` calls `project_candidate_work` and `write_projection` from
`skills/improve-harness/scripts/improve_candidate_work.py` with findings
adapted to that helper's input shape, so both skills emit one
`candidate-work.schema.json` shape and `/prioritize-proposals` needs no new
reader. Dedup key is `(kind, section)`; `suggested_change_id` is
`rightsize-<skill>-<kind>`.

### D9 — Read-only over the audited skill; output location; name collision

The skill never writes under `skills/<audited>/` or the mirrors. Reports and
ledgers go to `docs/reports/skill-audit/` (new, tracked; large reports are
fine, they are the evidence trail). The name `skill-audit` sits beside the
coordinator `audit` module and the `audit-choices` skill; the description
says "audit a SKILL.md for model-tier fit" so triggering does not collide,
and `related:` does not list `audit-choices`.

### D10 — Tests are deterministic and LLM-free in CI

Fixtures under `skills/tests/skill-audit/fixtures/` hold synthetic SKILL.md
files (all-shaped, mixed, oversized, nested-references, no-tail-block), a
minimal `archetypes.yaml` with bare and `{model, thinking}` tiers and a
provider lacking `frontier`, a `loop-state.json`, and a recorded memory
response. The model backend is a protocol with a fixed stub and a failing
stub. The coordinator is a stubbed bridge. Timing assertions skip when the
real corpus is absent.

### Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| Determinism: byte-identical ledger across two runs | `skills/tests/skill-audit/test_classifier.py::test_ledger_is_byte_identical` | new |
| Cost: ≤ 1 model call per skill; 0 when fully shaped | `test_classifier.py::test_one_call_per_skill`, `::test_zero_calls_when_shaped` | new |
| Operability: `--all` ≤ 60 s with stub backend | `test_cli.py::test_all_wall_time` (skips without corpus) | new |
| Resilience: exit 0 with evidence unavailable | `test_evidence_join.py::test_coordinator_down` | new |
| Compatibility: roster shapes, missing frontier, absent `procedure_mode` | `agent-coordinator/tests/test_archetypes_yaml.py`, `test_agents_config.py` (extended) | existing, extended |
| Safety: no `delete` on `contract` | `test_findings_schema.py::test_contract_delete_rejected` | new |
| Context cost: SKILL.md ≤ 150 lines, refs one level | `test_skill_md.py::test_line_budget`, `::test_reference_depth` | new |
| Compatibility: passes with and without `triggers:` | `test_skill_md.py::test_frontmatter_both_states` | new |
| Observability: freshness stamp and `--check-freshness` exit codes | `test_freshness.py` | new |

## Task decomposition notes

Three packages. `wp-procedure-mode` touches only coordinator files plus the
bridge passthrough; `wp-skill-audit` touches only the new skill and its
tests; they share no write paths and run in parallel. `wp-integration`
owns manifest, testpaths, CI, docs, mirrors. The skill reads
`archetypes.yaml` read-only and does not depend on `procedure_mode` landing;
its dispatch profile reports the field when present.

No task is L. The largest, `classifier.py`, is M because the rule table is
fixed by D2 and the AST parser can be the existing markdown helper used by
`skill_invariants.py`.

"And" audit (plan-feature Verification item 2): every task line matching
` and ` joins file names or fixture names inside one outcome (two test files
extended for one behaviour in 1.1; two stub backends in 2.3; two package
branches merged in 3.4). None describes two completion criteria. 1.4 is kept
as one task because field, parse, constants, append, and response field are
one contract ("`procedure_mode` resolves end to end") and land in one commit;
splitting would leave an intermediate state the tests in 1.2 cannot pass.

## Risks

| Risk | Mitigation |
|---|---|
| Schema bump breaks six consumers that pin `archetypes.yaml` | Field is optional; v3 files load unchanged; consumers' tests run in `wp-procedure-mode` before push |
| `add-atomic-harness` also modifies "Archetype Definition Schema" | Edits are orthogonal (a bullet and a schema clause vs. provider roster); whichever lands second rebases the requirement text |
| Layer rules misclassify and propose cutting something load-bearing | v1 proposes only; contract guard; `repo_specific_tokens` downgrade to `keep` |
| Evidence join attributes to the wrong tier when loop-state is stale | Nearest `phase_history` entry by time; `unknown` bucket; report prints attribution source per row |
| Convention flag becomes dead once ri-10/ri-13 land | Flag stays; `current` collapses to `rightsizing` when `REQUIRED_FRONTMATTER_KEYS` drops `triggers`; one-line removal later |
| Name confusion with `audit-choices` | Description and `related:` per D9 |

## Migration Plan

Roll-out: land `wp-procedure-mode` (additive schema v4, defaults preserve
behaviour) and `wp-skill-audit` in parallel; `wp-integration` wires manifest,
testpaths, CI, and mirrors. First audit run targets `merge-pull-requests`,
`validate-feature`, and the four teaching-heavy skills named in the
originating discussion; reports are committed under `docs/reports/skill-audit/`.

Rollback: revert the schema bump and the `resolve_archetype_for_phase`
append (one commit); the skill and its reports are inert without it. No data
migration; no coordinator DB change.
