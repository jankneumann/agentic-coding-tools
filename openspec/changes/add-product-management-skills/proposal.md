# Add Product-Management Skills

## Why

Our skills repo is dense **downstream of the decision to build** — the
`explore-feature → plan-roadmap / plan-feature → implement-feature → validate-feature →
cleanup-feature` lifecycle plus mature multi-vendor review/convergence machinery. What it lacks
is a **product-discovery front end**: the structured *why / who / what-outcome* reasoning that
decides which change deserves an OpenSpec proposal in the first place.

Today that front end is a free-text field. `plan-roadmap` decomposes a `proposal.md` whose
`Motivation` is written by operator reasoning or expanded from a one-line pitch (`--draft`).
`explore-feature` picks "what to build next" from architecture artifacts and code signals —
never from customer input, assumptions, or a desired outcome. `prioritize-proposals` ranks on
coupling and debt, with no impact/effort/customer-value axis. Our review culture stress-tests a
plan's *code and specs* but never its *assumptions*.

The public `phuryn/pm-skills` marketplace (68 skills / 9 plugins) supplies exactly this missing
layer. After auditing all 68 against every existing skill (see
[docs/proposals/pm-skills-gap-analysis.md](../../../docs/proposals/pm-skills-gap-analysis.md)),
**12 skills pass a strict seam test** — their output is consumed by, or their input produced by,
a skill already in the pipeline — clustered into **six seams**. The remaining 56 have no seam in
an engineering-coordination repo and are explicit non-goals.

This mirrors the archived `add-engineering-methodology-skills` change, which ported a
*horizontal* methodology layer into our *vertical* orchestration layer and filled the
**"how to build"** gap. This change fills the **"what/why to build"** gap immediately upstream of
it: it ships 12 localized PM skills, wires them into six existing seams, adds one shared
prioritization reference doc, and extends the proposal + roadmap templates so the new artifacts
flow through the pipeline instead of sitting beside it.

## What Changes

### New skills (12, two per seam)

Twelve net-new skills under `skills/<name>/`, each ported from `phuryn/pm-skills` and adapted to
our frontmatter schema and OpenSpec/agent-coordination context. Each user-invocable skill ships
the mandatory `Common Rationalizations / Red Flags / Verification` tail block from day one.

| Seam | Skill | `user_invocable` | Rationale |
|---|---|---|---|
| 1 · Proposal "why" | `create-prd` | `true` | Operator authors a PRD that becomes a `proposal.md`; also loadable by `plan-feature` |
| 1 · Proposal "why" | `opportunity-solution-tree` | `true` | Operator maps outcome→solutions; solution nodes seed `plan-roadmap` |
| 2 · Prioritization | `prioritize-features` | `true` | Adds impact/effort/risk/alignment scoring to `prioritize-proposals` |
| 2 · Prioritization | `identify-assumptions` | `true` | Flags riskiest assumptions before a full plan cycle |
| 3 · Strategy red-team | `strategy-red-team` | `true` | Adversarial assumption stress-test at Gate 1 |
| 3 · Strategy red-team | `pre-mortem` | `true` | Severity-classified failure analysis pre-dispatch |
| 4 · Spec scenarios | `user-stories` | `true` | Stories whose acceptance criteria map to WHEN/THEN scenarios |
| 4 · Spec scenarios | `test-scenarios` | `true` | Happy-path + edge-case enumeration for specs & validation |
| 5 · Shipping verification | `intended-vs-implemented` | `true` | Documented-vs-actual behavior drift check |
| 5 · Shipping verification | `shipping-artifacts` | `false` | Reviewability doc set; orchestrator-loaded by `cleanup-feature` |
| 6 · Outcome roadmaps | `outcome-roadmap` | `true` | Outcome→feature reframing for `roadmap.yaml` |
| 6 · Outcome roadmaps | `brainstorm-okrs` | `true` | OKRs `autopilot-roadmap` can measure against |

**Localization rule** (from the methodology precedent): keep each source skill's substantive
content and examples; *add* OpenSpec/agent-coordination equivalents alongside (a PRD that renders
as `proposal.md`, an opportunity tree whose leaves are change candidates, red-team findings in the
`iterate-on-plan` finding shape). Adopt their content, keep our schema.

### Shared reference doc (1)

`prioritization-frameworks` (RICE, WSJF, Kano, MoSCoW, …) ships as
`skills/references/prioritization-frameworks.md`, cited by `prioritize-features` and
`identify-assumptions` — reference material, not a skill, following the existing `references/`
library precedent.

### Adaptations to existing skills / artifacts (6 seams wired)

| Existing skill / artifact | Adaptation |
|---|---|
| `openspec/schemas/feature-workflow/templates/proposal.md` | Optional PM-artifact sections (PRD linkage, key assumptions, target outcome) so seam-1 output slots in |
| `explore-feature/SKILL.md` | Consume `opportunity-solution-tree` output; add outcome framing to "what next" |
| `prioritize-proposals/SKILL.md` | Add `prioritize-features` scoring axes alongside code-signal ranking |
| `plan-feature/SKILL.md` | Gate-1 discovery incorporates `identify-assumptions` + `strategy-red-team` findings |
| `validate-feature/SKILL.md` (+ `openspec-verify-change` note) | Add `intended-vs-implemented` as a complementary drift check |
| `openspec/schemas/roadmap/templates/*` + `roadmap.yaml` schema | Optional `outcome` / `okr` fields per roadmap item |

### Cross-cutting

- **Frontmatter schema preserved.** Existing keys (`name`, `description`, `category`, `tags`,
  `triggers`, `user_invocable`, `requires`, `related`) kept verbatim. `related:` wires the new
  skills to their seam partners and consumers.
- **Tail-block convention.** All 11 user-invocable new skills ship the three-section tail block;
  `shipping-artifacts` (`user_invocable: false`) is exempt.
- **Test infrastructure.** Each new skill gets `skills/tests/<name>/test_skill_md.py` invoking the
  shared content-invariant assertions (`assert_frontmatter_parses`, `assert_required_keys_present`,
  `assert_references_resolve`, `assert_related_resolve`, `assert_tail_block_present`).
  `skills/pyproject.toml` `testpaths` updated.
- **Catalogue.** `docs/skills-catalogue.md` gains a "Product discovery" group.

### Explicit non-goals

- **The other 56 PM skills** (pricing, Porter's, SWOT, GTM, marketing, NDA, résumé, SQL/analytics,
  meeting/interview summarizers). No current pipeline seam. Catalogued in the gap-analysis doc.
- **`release-notes`** — redundant with existing `changelog-version`.
- **`metrics-dashboard` / `north-star-metric` / `product-strategy` / `product-vision`** — deferred;
  valuable but broader than the six seams. Revisit after the discovery front end lands.
- **A standalone `product-discovery` orchestrator skill** — this change wires the seams into
  existing orchestrators; a dedicated meta-orchestrator (a `plan-discovery` that chains seam 1→3)
  is a possible follow-up, out of scope here.

## Approaches Considered

### Approach A: Port all seam-passing skills as independent islands

Ship the 12 skills; skip the adaptation edits; let operators invoke them ad-hoc.

- **Pros:** smallest change; no edits to existing skills; low conflict risk.
- **Cons:** the skills sit *beside* the pipeline, not *in* it — a PRD that no skill consumes is a
  markdown file. Realizes little of the seam value. Rejected.
- **Effort: M**

### Approach B: Big-bang — skills + all six seam wirings in one linear pass

One agent walks scaffold → 12 skills → 6 adaptations → template/schema edits → tests → docs.

- **Pros:** simplest mental model; single review surface; no work-package coordination.
- **Cons:** doesn't use available coordinator parallelism; long single review cycle; a failure
  mid-sequence forces a long replay.
- **Effort: L**

### Approach C: Scaffold-then-content, parallel by seam (recommended)

The approach the methodology-skills precedent proved. A sequential Phase 0 ships the convention
and shared artifacts *before* content; Phases 1–2 fan out one work package per seam and inherit
it; Phase 3 integrates.

- **Phase 0 — Scaffold (sequential):** `skills/references/prioritization-frameworks.md`; proposal
  + roadmap template edits (so seam wirings in Phase 2 have a target); `pyproject.toml` testpath
  placeholders for the 12 new test dirs; catalogue "Product discovery" section stub.
- **Phase 1 — New skills (parallel, ~6 packages, one per seam):** each package authors its two
  SKILL.md files (born with the tail block) + their `skills/tests/<name>/` dirs.
- **Phase 2 — Seam wirings (parallel, ~3 packages):** clustered by target
  (front-end: `explore-feature` + `plan-feature`; prioritization: `prioritize-proposals`;
  verification/roadmap: `validate-feature` + roadmap schema). Each existing skill touched once.
- **Phase 3 — Integration (sequential):** `install.sh --mode rsync` dry run, `related:` resolution,
  full `openspec validate --strict`, `docs/skills-catalogue.md` finalization, session log.

- **Pros:** maximizes coordinator parallelism (~3× wall-clock over B); seam targets exist before
  wirings land; each existing skill edited exactly once; phase gates are natural review checkpoints.
- **Cons:** most work-package YAML to author; Phase 1–2 have a hard dependency on Phase 0.
- **Effort: L**

### Recommended

**Approach C.** It is the proven precedent for this exact shape of change (port external skills +
adapt existing ones + spec deltas), and it fixes Approach A's fatal flaw — Phase 2 guarantees the
seams are actually wired, so the ported skills feed the pipeline rather than sitting beside it.

### Selected Approach

_Pending Gate-1 direction approval._ Default: **Approach C — scaffold-then-content, parallel by
seam**, as a single OpenSpec change, 12 new skills (11 user-invocable / 1 infrastructure), one
shared reference doc, six seam wirings, frontmatter schema and tail-block convention preserved.

## Impact

- **Specs:**
  - `skill-workflow` (ADDED) — the PM skill suite, its `user_invocable` assignments, tail-block
    and frontmatter conformance, shared reference doc, and test coverage.
  - `product-discovery-workflow` (ADDED, new capability) — the seam contracts: how each new skill's
    artifact flows into an existing orchestrator, the proposal/roadmap template extensions, and the
    `intended-vs-implemented` verification seam.
- **Code / docs touchpoints:** `skills/{create-prd,opportunity-solution-tree,prioritize-features,identify-assumptions,strategy-red-team,pre-mortem,user-stories,test-scenarios,intended-vs-implemented,shipping-artifacts,outcome-roadmap,brainstorm-okrs}/`;
  `skills/references/prioritization-frameworks.md`; `skills/tests/<name>/`; `skills/pyproject.toml`;
  `skills/install.sh` (only if `related:` targets need re-validation — no new mechanism);
  `explore-feature`, `plan-feature`, `prioritize-proposals`, `validate-feature` SKILL.md;
  `openspec/schemas/feature-workflow/templates/proposal.md`;
  `openspec/schemas/roadmap/templates/*`; `docs/skills-catalogue.md`.
- **No runtime/coordinator changes.** This is a skills + templates + docs change; no Python
  services, DB schema, or MCP surface are touched.
