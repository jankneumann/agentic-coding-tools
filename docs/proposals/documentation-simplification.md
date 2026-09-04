# Documentation simplification: a `/simplify-docs` skill and a layered doc structure

> Status: proposal (pre-`/plan-feature`). Companion to the `/simplify` skill and
> the opt-in SIMPLIFY autopilot phase: the same read → pin → edit discipline,
> applied to prose instead of code.
> Author's intent: a newcomer opens `README.md`, gets the concept in one screen,
> and can follow links from concept → lifecycle → coordinator → execution
> environments → lessons without ever hitting a claim the code contradicts.

## 1. What already exists (and what it does not do)

| Mechanism | Owner | Covers | Does not cover |
|---|---|---|---|
| `documentation.inventory` producer + `context-drift-gate` CI job | `skills/project-context-refresh`, ri-05 / ri-10 | Generated inventories (`docs/architecture-analysis/skills-inventory.md`, contracts inventory, `docs/decisions/`) are byte-checked against filesystem truth on every PR | Hand-authored prose. `README.md`, `CLAUDE.md`, `docs/*.md`, `docs/guides/*.md` have no truth check at all |
| *Documentation Update Per Iteration* (skill-workflow spec) | `iterate-on-*`, `implement-feature` | Adds a lesson when an iteration discovers one; refactors CLAUDE.md into `docs/` above 300 lines | Append-only. Never retires, merges, or re-verifies an existing lesson |
| `make decisions` → `docs/decisions/<capability>.md` | `explore-feature/archive_index.py` | Projects `architectural:`-tagged **Decisions** from session logs, with supersedes links | **Trade-offs**, **Capability Gaps Observed**, **Open Questions** sections of the same session logs (188 trade-off bullets across 115 archived changes) are projected nowhere |
| `documentation-and-adrs` skill | Methodology | How to write a durable ADR or README skeleton | Auditing what is already written |
| `improve-harness`, `collect-transcripts`, episodic memory | Learning loop | Capability-gap signals → improvement reports → proposal stubs | Never lands as human-readable "pitfalls still relevant" text |
| `refresh-architecture` | `docs/architecture-analysis/` | Structural graph, Mermaid views, narrative report | Conceptual docs |
| `add-update-documentation-skill` (superseded) | Historical | Recorded the drift audit and the marker engine, both absorbed by ri-05 | Its hook / cleanup / merge-time wiring was deliberately dropped |

**Evidence of the gap, measured on this checkout (2026-09-04):**

- `docs/lessons-learned.md` cites `/parallel-implement`, which has no `skills/` directory. Its "Task() Parallelization Patterns" section describes a dispatch model the coordinator archetypes replaced.
- 112 mentions of Beads or Railway remain in `docs/*.md`, `README.md`, and `CLAUDE.md` outside the two migration runbooks. Beads was removed 2026-05-18; the coordinator moved from Railway to local behind Cloudflare.
- `README.md` says "≈55 skills"; the generated inventory says 73. `docs/agent-coordinator.md` carries a Phase 1–4 "Implementation Status" table and a "Future Capabilities" section that predate archetypes, the merge queue, and the task router.
- Every file under `docs/` shows the same last-commit date (a single squash), so **git age cannot serve as a staleness signal**. Freshness has to be content-based, which is the same rule the producers already follow.
- There is a `vision` skill and no `VISION.md`. The README's opening paragraphs are the only statement of what the repo refuses to become.

The pattern mirrors what `/simplify` was created for on the code side: accretion with no owner for reduction. The mandatory update rule guarantees docs grow; nothing guarantees they stay true.

## 2. Target structure: three layers, one map

The goal is a strict concept → mechanism → reference gradient, where each layer links down and never sideways into detail it does not own.

```
Layer 0  README.md                    one screen: problem, three roles, the loop, where to go next
         VISION.md                    what the repo is for and what it refuses (from /vision)
Layer 1  docs/guides/                 one concept per guide, prose, stable names
           lifecycle.md               explore → plan → implement → validate → cleanup, gates, tiers   (exists as workflow.md + skills-workflow.md + skill-flow/)
           coordinator.md             why a coordinator, what it offers, truth vs projection, archetypes (today: agent-coordinator.md + work-queue-truth-projection.md + lock-key-namespaces.md)
           execution-environments.md  local vs cloud, isolation posture, worktree short-circuit, deploy topology (today: cloud-vs-local + cloud-deployment + local-migration + cloud-session-hooks)
           roadmaps-and-autopilot.md  multi-change orchestration, learning feedback, loop-state
           learning-loop.md           session logs → decisions → episodic memory → improve-harness → lessons
           lessons-learned.md         curated, status-tagged pitfalls (see §4)
           + the existing operational guides (python-environment, git-conventions, skills, worktree-management, session-completion)
Layer 2  reference                    generated or formal; never hand-edited prose
           openspec/specs/            requirements
           docs/decisions/            capability timelines (generated)
           docs/architecture-analysis/ inventories, graph, views (generated)
           docs/skills-catalogue.md   → becomes a thin wrapper around skills-inventory.md, or is retired
           runbooks/ (cloudflare, openbao, cross-repo, migration) — setup procedures, dated
```

`docs/guides/documentation.md` becomes the single map (it already lists every doc by category; it becomes the *only* place that does, and the README links to it once).

Rules that make the structure self-enforcing:

1. **Every hand-authored doc carries frontmatter**: `layer: 0|1|2`, `owns: [<concept>]`, `sources: [<paths/specs/skills it describes>]`, `verified_against: <short SHA>`. `sources` is what the skill checks claims against; `verified_against` is how "stale" is defined without mtimes (see §3).
2. **One concept, one home.** A concept named in `owns:` may appear in exactly one Layer 1 guide. The skill reports duplicates.
3. **Layer 0 never explains mechanism.** README paragraphs link to a Layer 1 guide within two sentences of introducing a term.
4. **Layer 2 is generated or formal.** Anything a producer can render is not hand-written. `skills-catalogue.md` is the first candidate to retire in favour of the generated inventory plus a short "how to read it" preface.

## 3. The skill: `/simplify-docs`

Shape mirrors `/simplify` deliberately so operators and autopilot treat both the same way.

| `/simplify` (code) | `/simplify-docs` (prose) |
|---|---|
| Inspect a focused diff or module | Inspect a focused doc set: `--scope readme`, `--scope guide <name>`, `--scope lessons`, or the docs whose `sources:` intersect a change's touched paths |
| Coverage gate: no edits on unpinned code | **Claim gate**: no edits until every checkable claim in scope has a verdict (see below) |
| Characterization tests pin behaviour | **Claim ledger** (`docs/architecture-analysis/doc-claims.json`, generated): each claim, its source, verdict, and the revision it was verified at |
| Chesterton's Fence per candidate | **Supersession check per deletion**: a lesson, section, or link is removed only when the ledger names the decision, archived change, or commit that made it obsolete. Otherwise it is marked `unverified`, not deleted |
| Dual-run the suite | **Dual-check**: link checker + claim checker + `make context-drift-gate` before and after; the after-run must have zero new failures |
| Rule of 500 | Rule of 3 guides per run. Larger restructures go through `/plan-feature` |
| Findings taxonomy: dead code, deep nesting, duplication… | Findings taxonomy: `stale` (contradicts a source), `orphan` (no inbound link from the map), `duplicate` (same concept owned twice), `misplaced` (mechanism text in Layer 0, or prose in Layer 2), `unverifiable` (claim with no checkable source), `superseded-lesson` |
| Manual only; opt-in SIMPLIFY phase in autopilot | Same: manual by default, opt-in `DOCS` phase in autopilot after IMPL_REVIEW, plus a scheduled sweep (§5) |

**Checkable claim types** (what the claim gate can verify deterministically):

- Path or file exists (`skills/<x>/SKILL.md`, `docs/…`, `scripts/…`).
- Skill is user-invocable / has a given trigger (from frontmatter).
- Command or Makefile target exists (`make <target>`, `python … <script>`) and `--help` exits 0.
- Spec requirement heading exists in `openspec/specs/<cap>/spec.md`.
- Decision referenced is `active` (not `superseded`) in `docs/decisions/`.
- Count claims ("≈55 skills", "21 specs", "19 tools") match the generated inventories. These are rewritten to link to the inventory rather than restate the number.
- Anchor and relative link resolve.

Everything else (design rationale, "why local vs cloud") is `unverifiable` by tooling and gets a human-judgement pass with the source `sources:` open. The skill lists these explicitly rather than pretending they were checked.

**Output per run**

1. Findings report (`docs/architecture-analysis/doc-simplify-report.md`) in the same ranked-findings format `bug-scrub` uses, so `fix-scrub` can pick them up.
2. Edits applied one finding-type at a time, one commit per type (`docs(simplify): retire superseded lessons`, `docs(simplify): move mechanism out of README`), matching `/simplify`'s "one pattern per commit".
3. `verified_against` bumped only on the docs whose claims all passed.

## 4. Lessons as a maintained corpus, not an append log

`docs/lessons-learned.md` is the file the author most wants to trust and the one with the least machinery behind it. Proposed contract:

```markdown
- **Keep skill executables in skill-local scripts/** `status: active` `evidence: openspec/specs/skill-workflow/spec.md#install-payload-closure`
- **Use Task() for parallel work** `status: superseded` `by: docs/decisions/agent-archetypes.md#2026-06-…`
```

- Every lesson carries `status: active | superseded | retired` and an `evidence:` pointer (spec requirement, decision entry, archived change, or code path). The claim gate checks the pointer resolves and, for decisions, that it is still `active`.
- `superseded` lessons stay for one release with the `by:` link, then move to `docs/archive/lessons-retired.md` on the next sweep. Retired lessons remain greppable; that is the Chesterton's Fence record.
- **New source of lessons.** A `lessons.candidates` producer (or a step in the skill) mines the `Trade-offs` and `Capability Gaps Observed` sections of archived session logs, plus `improve-harness` reports, into `docs/architecture-analysis/lessons-candidates.md`. A human (or the DOCS phase) promotes candidates into `lessons-learned.md` with evidence attached. This closes the loop the author described: pitfalls found while building become documented lessons, and only the still-relevant ones survive re-verification.

**Feeding lessons back into implementation.** `context-engineering` already assembles the worker context pack from rules, specs, and source files. Add one input: active lessons whose `evidence:` path intersects the work package's `write_allow` globs. A worker touching `skills/worktree/` sees the worktree pitfalls and nothing else. This is the cheapest place to make documentation *inform* implementation rather than merely describe it.

## 5. Keeping it in sync: three cadences

| Cadence | Trigger | Scope | Blocking? |
|---|---|---|---|
| **Per change** | `implement-feature` / `iterate-on-implementation` doc-update step | Docs whose `sources:` intersect the touched paths. The existing mandatory update rule gains a second half: "and run the claim gate on the docs you touched" | Yes, on the docs in scope (extends `context-drift-gate` with the claim ledger for those files only) |
| **Per autopilot run** | Opt-in `DOCS` phase, after IMPL_REVIEW, sibling of SIMPLIFY | Same as per change, plus `orphan` and `duplicate` checks on the map | No: findings go to the review ledger |
| **Periodic sweep** | `supervise` discovery cycle or a roadmap item, roughly monthly | Whole Layer 0 and Layer 1; lesson candidates promotion; `verified_against` refresh | No: produces a report and a `docs(simplify)` PR |

A doc's staleness is defined as **the number of merged changes since `verified_against` whose diff touched any of its `sources:`**, never wall-clock time. That number is derivable from git alone and is stable across squashes, which the one-date-for-everything history shows is required here.

## 6. Phasing

**Phase A — one-time restructure (manual, using the skill's checklist before the skill exists).**
README rewritten to the Layer 0 shape and cut to one screen; `docs/guides/coordinator.md` and `docs/guides/execution-environments.md` written by merging the current five coordinator/cloud docs (the "why local vs cloud" rationale lives in exactly one place); `lessons-learned.md` triaged with `status:` and `evidence:` on every bullet; `docs/guides/documentation.md` promoted to the single map; frontmatter added to every hand-authored doc. Stale-count claims replaced by inventory links. This is an S/M change and can go through `/plan-feature` directly.

**Phase B — the skill.** `skills/simplify-docs/SKILL.md` plus `scripts/claim_check.py` (claim extraction, verdicts, ledger), `scripts/doc_map.py` (orphan and duplicate detection from frontmatter), `scripts/lessons_candidates.py` (session-log mining). Register `doc-claims.json` and `lessons-candidates.md` as `project-context-refresh` producers so the existing drift gate, manifest, and CI job cover them with no new CI wiring. Spec delta on `skill-workflow`: *Documentation Simplification* requirement, and the existing *Documentation Update Per Iteration* requirement gains the claim-gate scenario.

**Phase C — wiring.** Opt-in `DOCS` phase in autopilot (same TRANSITIONS/LoopState pattern as SIMPLIFY); `context-engineering` lesson injection; `supervise` sweep cadence.

## 7. What this deliberately does not do

- Does not gate merges on prose freshness beyond the docs a change touched. A whole-repo blocking gate on hand-written prose would recreate the problem the superseded proposal had: every unrelated PR pays for global drift.
- Does not auto-rewrite rationale. The skill can prove a path is gone; it cannot prove a design argument is wrong. Those findings are `unverifiable` and go to a human.
- Does not reintroduce a hand-maintained skills catalogue. The generated inventory is the truth; prose links to it.

## 8. Open questions for the author

1. Retire `docs/skills-catalogue.md` outright, or keep a short hand-written "how to read the inventory" preface above a generated block?
2. Should `VISION.md` be produced first (via `/vision`) so the README's Layer 0 has a source to cite, or is the current README opening sufficient as the vision statement?
3. Is a monthly supervise-driven sweep the right cadence, or should the sweep be tied to release tagging (`changelog-version`)?
