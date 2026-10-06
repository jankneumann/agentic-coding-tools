# Backpass and the memory-file loop: what to adopt, adapt, and skip

**Status**: Draft / research
**Created**: 2026-09-08
**Source repo analyzed**: [`kunchenguid/backpass`](https://github.com/kunchenguid/backpass) (README, VISION.md, `src/prompts/*`, `src/proposal.js`, `src/memory.js`, `src/state.js`, `src/bootstrap.js`, `src/overlap.js`)
**Theme**: instruction-file hygiene, transcript-derived evidence, human-gated memory edits
**Related**: `docs/proposals/skill-rightsizing-roadmap.md`, `docs/proposals/frontier-model-skill-architecture.md`, `docs/proposals/repo-improvement-roadmap.md` (RI-12), `docs/proposals/lavish-axi-html-artifact-feedback.md`, `docs/guides/memory-conventions.md`

## Executive synthesis

backpass and this repository start from the same premise and diverge on where the
evidence lands. Both treat session transcripts as the loss signal for the agent
instruction surface. backpass closes that loop against one narrow object: the
always-loaded memory file plus every skill's `description:` line, edited in five
named actions, each gated in code by evidence floors and a token budget, and applied
only through a per-edit human gate. This repository has built the wider harness
(seven transcript adapters, a shared capability-gap tag schema with four emitters,
a supervisor with a surfaced-once ledger, a rightsizing roadmap with a pre-registered
non-inferiority rule) but the loop from transcript to instruction file is not closed:
nothing measures the always-loaded surface, nothing attributes evidence to a specific
instruction, nothing edits `CLAUDE.md` or a skill description, and the transcript
pipeline never actually calls a model or writes memory.

The recommendation is to adopt backpass's **evidence model and gate design** wholesale,
adopt its **canonical-file convention** (AGENTS.md canonical, CLAUDE.md as an import
pointer), and adopt its **five-action vocabulary** as this repo's definition of a
memory action. Adapt its budget and placement rules to our roadmap's measurement
discipline rather than replacing that discipline. Skip its harness-probing ladders,
its browser review surface, user-scope training, and the adapters we do not use.
The cheapest first step is a bounded spike: run backpass against this checkout with
`skillsDir` pointed at `skills/`, use its budget bar as the ri-04 context-cost
baseline, and decide from the first proposal whether to run it as the engine or port
its concepts into `collect-transcripts`.

## 1. What backpass does, stage by stage

| Stage | Mechanism | Enforced how |
|---|---|---|
| Collect | Reads seven harness stores from disk; four-tier session-to-repo association (worktree cwd, sibling clone, recorded remote, dead-path name) | Deterministic tiers labelled; best-effort tier opt-in only |
| Distill | User and assistant turns verbatim, each tool call collapsed to one line, output truncated, scaffolding dropped, secrets redacted; 96-99% reduction | Deterministic code, before any model call |
| Sample | Above `maxTranscripts` (100), recency-weighted draw with 14-day half-life, sticky per transcript identity, 20% floor per interactive/non-interactive category | Deterministic seed from transcript identity |
| Analyze (cheap model) | One call per transcript against an instruction index (`AG-nnn`); returns strict JSON of positive, negative, and gap items, each with a verbatim quote | Quoteless items discarded in code; negatives carry `harm` / `non-compliance` / `irrelevant`; gaps carry `project` / `orchestration` |
| Cache | Evidence keyed on transcript content, memory-surface hash (file plus all skill descriptions), and analysis-index version | Surface edit invalidates evidence automatically |
| Fold | Per-instruction positive/negative counts, harm-session count, relevance (share of sessions where it mattered, split by interactivity); gap clusters; cross-surface overlap with skill descriptions and bodies | Gap identity judged by one consolidation call, degrading to lexical |
| Gap ledger | Sightings persist across runs per gap and session; graduate at `minGapEvidence` (2) distinct sessions; retire when covered; expire after 90 days | File `.backpass/gap-ledger.json` |
| Synthesize (strong model) | Agent edits a **staging copy** with its own file tools; backpass diffs the copy and asks the agent to annotate each measured hunk | Nothing textual taken from the model; hunks cut from the real file |
| Gates | Max edits per run (5, or one per ~40 tokens of overage up to 20 in a shrink plan); every add/rewrite/remove needs quotes from 2 distinct sessions; removal needs `harm` from 2 sessions; extract preserves every removed line; move matches line multisets; post-edit surface fits budget | Violations re-prompted at most twice, then loud failure with the rejected proposal preserved |
| Budget | 5,000 estimated tokens for memory file plus every skill `description:` line; at budget the prompt goes zero-sum | Measured from staged files, bytes/4 |
| Apply | One card per edit with diff and quotes; accept or reject; rejections remembered until strictly more transcripts back the same edit; file fingerprints checked before write; all-or-nothing per file | Only writing command |

The vision document states the design invariant that matters most for us: *"Every
rule here is enforced in code and never merely asked for in a prompt, because a rule
the model can decline is not a rule."*

## 2. Side-by-side map

| Concept | backpass | This repository | State here |
|---|---|---|---|
| Transcript adapters | claude, codex, pi, opencode, grok, cursor, hermes; fail-soft; golden fixtures | claude_code_cli, claude_code_web, codex_cli, codex_web, antigravity_cli, grok_cli, pi_cli; fail-soft (`skills/collect-transcripts/scripts/adapters/base.py:35-85`) | Present, comparable |
| Session-to-repo association | Four tiers incl. worktree list and recorded remote | Adapters glob everything under the cwd-encoded store; no worktree or remote matching | Absent |
| Distillation | Deterministic, 96-99% reduction | None; full event stream passed forward | Absent |
| Sampling and caps | Recency-weighted, sticky, category floor | None | Absent |
| Evidence cache | Keyed on transcript + surface hash | None | Absent |
| Per-transcript analysis | Cheap model, strict JSON, instruction-anchored, verbatim quotes | Deterministic keyword and counter triage (`triage.py`), heuristic deep analysis; `analyze_session_llm` referenced but not defined (`deep_analyze.py:99`) | Partial, no model call |
| Evidence unit | Instruction id (`AG-nnn`) with positive / negative / gap and harm class | `capability_gap` free text plus `affected_skill`; no positive evidence, no attribution to an existing instruction | Different object |
| Domain split | `project` vs `orchestration`; orchestration gaps are report-only | `affected_skill` names the harness component; this repo is the orchestrating tool | Complementary |
| Corroboration floor | 2 distinct sessions, enforced in code | "Cross-source agreement is the strongest signal" is printed as a percentage, never filters (`generate_report.py:156-159`) | Advisory only |
| Persistent gap ledger | Yes, 90-day expiry, retire-on-coverage | None for `/improve-harness`; supervisor has a surfaced-once ledger (`skills/supervise/scripts/cycle_state.py:702-757`) | Absent at this layer |
| Rejection memory | Keyed on edit content; re-proposed only with strictly more transcripts | Supervisor standing decisions with `expires_at`; nothing at the edit level | Absent at this layer |
| Editing actions | `add`, `remove`, `rewrite`, `extract`, `move` with per-kind floors | No vocabulary defined; keep / cut / relocate appears as a heuristic in prose | Absent |
| Editor | Staging copy, measured diff, annotated hunks | No code edits `CLAUDE.md`, `AGENTS.md`, or skill descriptions | Absent |
| Budget on always-loaded surface | 5,000 tokens, memory file plus skill descriptions | CLAUDE.md line cap of 120 enforced by test; skill descriptions unmeasured; `/doctor` baseline is roadmap item ri-04, status candidate | Partial |
| Placement rule | Broad (≥20% sessions or safety) → memory file; narrow with trigger → skill; narrow without trigger → delete | Keep/cut test (project decision vs competence); progressive disclosure CLAUDE.md → `docs/guides/` | Complementary |
| Skill descriptions as weights | Failed trigger → description edit, counted via `coveredBySkill` | ri-10 rewrites all descriptions once | One-shot only |
| Human gate | Per-edit accept/reject cards via lavish-axi | PR review; trust-posture gates all resolve to `block` while `TRUST_POSTURE.md` is absent | Coarser but present |
| Canonical memory file | `AGENTS.md` canonical; `CLAUDE.md` is `@AGENTS.md` | `CLAUDE.md` canonical; `AGENTS.md` is a symlink to it (`README.md:7`) | Opposite direction |

## 3. Alignment on the four questions raised

### 3.1 The gradient signal: evidence-gated extraction

The principle matches what the skill-rightsizing roadmap already demands: no cut
without a measurement whose ground truth comes from outside the model's judgment.
backpass's answer to "outside the model" is different from ours and cheaper. Ours is a
sealed replay benchmark with a pre-registered non-inferiority rule. Theirs is
structural: a claim without a verbatim quote from a real session is discarded; a
change needs two independent sessions; a removal needs harm, not mere
non-compliance; and text is never taken from the model, only measured from a file
it edited.

Three parts of that model are missing here and are worth adopting on their own,
independent of any tooling decision.

- **Attribution to a specific instruction.** Our tag schema records what was
  missing. It never records that an existing instruction helped, was ignored, or
  caused harm. Without that, the pipeline can add lines but can never justify
  removing one, which is exactly the "easier to grow than to shrink" failure the
  backpass vision names.
- **The harm versus non-compliance distinction.** A rule that agents skip argues
  for reinforcement or a better trigger. A rule that agents followed into damage
  argues for deletion. Our `failure_type` enum cannot express this.
- **Verbatim quotes as the admission ticket.** Our deep-analysis evidence is
  counters and error text truncated to 100 characters. That is enough to rank, not
  enough to review.

One caution specific to our corpus. Most of our sessions are autopilot dispatches,
so a single systematic harness defect will clear a two-session floor trivially.
backpass already reports relevance split by interactive and non-interactive
sessions. For this repo the floor should probably count distinct *changes* or
distinct *interactive* sessions, not raw sessions.

### 3.2 Step structure gated by the size of the existing files

backpass makes the budget the constraint the whole loop optimizes under, and scales
the step with the overage: five edits near budget, up to twenty in a shrink plan, and
zero-sum at budget where every addition names the removal that pays for it. Our
equivalents are static caps: CLAUDE.md at most 120 lines (enforced), SKILL.md at most
500 lines (roadmap target), and the 300-line rule in the skill-workflow spec that
still refers to CLAUDE.md and AGENTS.md as two files that could diverge.

The important reframing is **what counts as always-loaded**. Our CLAUDE.md is 62
lines and already a table of contents. The real per-session tax here is 74 skill
descriptions, which is precisely the surface backpass bills and which ri-04 and
ri-10 plan to measure and rewrite once. backpass's budget bar is the harness-neutral
denominator ri-04 asks for, and its failed-trigger detection is the continuous
follow-on that ri-10 lacks. The two programs compose: use the replay benchmark as
the acceptance gate for the one-time bulk cut, and a backpass-style bounded step as
the maintenance loop afterwards.

### 3.3 Human- versus agent-facing documents, and which file is canonical

backpass says nothing about human documentation. Its scope is the agent surface only,
and its cost model implicitly gives us the split we have been circling: the agent
surface is what is paid on every session (memory file plus skill descriptions);
everything else is free until pulled. Under that model `docs/guides/` topic docs are
already skill bodies in all but name, and `README.md`, `docs/proposals/`, and
`docs/decisions/` are outside the agent budget entirely. Today
`openspec/schemas/context-impact-rules.yaml:62-73` lumps human docs, agent rules
files, and SKILL.md into one `documentation` surface. Splitting that into an
`agent-memory` surface (AGENTS.md, CLAUDE.md, skill frontmatter) and a `docs`
surface would make the distinction machine-visible and would let the
`documentation.inventory` producer report the budget for the first one.

On the symlink question, the recommendation is to **flip the direction**: make
`AGENTS.md` the canonical, self-contained file and make `CLAUDE.md` a Claude-specific
preamble ending in `@AGENTS.md`. Four reasons.

- **Portability.** A symlink is a git mode-120000 object. A checkout with
  `core.symlinks=false` (Windows, some CI images, some container copies) yields a
  one-line text file containing `CLAUDE.md`, and Codex would read that literal as
  its instructions. An `@` import is plain text and Claude Code inlines it.
- **Vendor neutrality matches the repo's stated identity.** The README's first
  claim is harness-agnosticism. AGENTS.md is the cross-vendor convention; CLAUDE.md
  is one vendor's filename.
- **There is Claude-specific content in CLAUDE.md today.** The Sub-Agent
  Authorization block reasons about the `Agent(...)` tool and Claude Code harness
  instructions. Through the symlink, Codex reads it too. With an import pointer,
  vendor-specific text lives above the import and the shared contract lives in
  AGENTS.md.
- **Tool compatibility.** backpass resolves the whole path and refuses read-only
  targets; a symlink works but reports the wrong name as canonical. The pointer form
  is what it recognizes as "nothing to report".

The cost is small and mechanical: retarget `skills/session-log/tests/test_claude_md_restructure.py`
to AGENTS.md, update `README.md:7` and `skills/context-engineering/SKILL.md:100-107`,
and fix the spec text that still says "if either file exceeds 300 lines"
(`openspec/specs/skill-workflow/spec.md:88-90`). Codex does not follow `@` imports, so
AGENTS.md must stay complete on its own; that is the same constraint the symlink
already imposes.

### 3.4 Memory actions and review before apply

No action vocabulary exists in this repo today; the closest thing is the keep / cut
/ relocate heuristic in prose. backpass's five kinds are worth adopting verbatim as
the definition of a memory action, because each carries its own evidence floor and
its own mechanical check:

| Action | Evidence floor | Mechanical check |
|---|---|---|
| `add` | 2 sessions with quotes | Post-edit surface within budget |
| `rewrite` | 2 sessions with quotes, whatever the shape | Same |
| `remove` | 2 sessions with `harm` class | Never satisfiable for skill-body text |
| `extract` | Exempt | Every removed line reappears in the created or extended SKILL.md; description delta charged to budget |
| `move` | Exempt | Removed and added line multisets match exactly |

Our keep/cut/relocate maps onto these as no-op / `remove` / `move` or `extract`.
The mapping exposes a real difference in evidence standards: ri-14 plans to cut
competence-restating rules on the strength of a replay benchmark, while backpass
would demand per-instruction harm evidence for each one. Both are legitimate. The
benchmark is stronger and one-shot; the transcript evidence is cheaper and
continuous. The practical resolution is to let relevance (share of sessions where an
instruction drew any evidence) **prioritize** what the bulk cut looks at, and let the
benchmark **accept** the cut.

For the review gate, the repo's gate is the pull request, with Claude Approvals and
the trust-posture gates all resolving to `block` while `TRUST_POSTURE.md` is absent.
That is coarser than backpass's per-edit cards but it is already the place humans
look. The adaptation that keeps backpass's properties without a new UI is: one
proposal branch, **one commit per edit**, with the action kind, the instruction ids,
and the verbatim quotes in the commit body, plus a `proposal.json` that a rejection
ledger can key on. Rejecting an edit is reverting its commit and recording the key.
The lavish-axi review surface was already assessed in
`docs/proposals/lavish-axi-html-artifact-feedback.md` and is a separate decision.

## 4. Adopt, adapt, skip

### Adopt as-is

1. **Verbatim quote or discard.** Any finding that enters memory from a transcript
   carries a quote copied from the trace; the writer drops quoteless items in code.
2. **Instruction index with stable ids.** Parse AGENTS.md into units (list items and
   paragraphs under headings), hash each, alias `AG-nnn`, and make every analysis
   refer to instructions by id. `src/memory.js:49-130` is a small, portable parser.
3. **Positive / negative / gap with harm class and domain.** Extend the D4 tag
   schema with `instruction:AG-nnn`, `polarity:positive|negative`,
   `class:harm|non-compliance|irrelevant`, and `domain:project|orchestration`.
   New prefixes need no code change (`docs/guides/memory-conventions.md:80-82`).
4. **The five memory actions and their floors** (section 3.4).
5. **Rejection memory keyed on edit content**, re-proposable only with strictly more
   evidence (`src/state.js:252-287`).
6. **Persistent gap ledger** with retire-on-coverage and expiry, counting each
   session once.
7. **Surface hash as the cache key** for per-transcript evidence, so editing a
   description invalidates exactly the evidence that depends on it.
8. **Staging copy plus measured diff.** Whatever edits the memory file, the text
   that lands is cut from the file, never pasted from a model reply.
9. **Rules enforced in code, briefed in prose.** This is the same diagnosis the
   frontier-model proposal makes about our skills; backpass shows what it looks
   like when done all the way down.
10. **AGENTS.md canonical, CLAUDE.md as `@AGENTS.md` pointer** (section 3.3).

### Adapt to our framework

1. **Budget denominator.** Use memory file plus every skill description as the
   always-loaded surface for ri-04, measured bytes/4, and record the number in the
   dated baseline the change already calls for. Keep our line caps as secondary
   guards.
2. **Corroboration floor for a robot-heavy corpus.** Count distinct changes or
   distinct interactive sessions rather than raw sessions, and report the
   interactive / non-interactive split the way backpass does.
3. **Placement policy as one written rule.** Merge the keep/cut test with
   backpass's placement table and the progressive-disclosure tiers into a single
   "what goes where" section of `docs/guides/documentation.md`, with measured
   relevance as the criterion rather than taste.
4. **Human gate as commits, not cards.** One commit per edit with evidence in the
   body; PR review is the accept/reject; the ledger records reversions.
5. **Orchestration-domain gaps as an emitter.** backpass sets aside gaps caused by
   the orchestrating harness. For repos that use our skills, that is exactly the
   signal `/improve-harness` wants. Its report-only orchestration diagnostics map
   directly onto `source:transcript-mined` entries with `affected_skill`.
6. **Distillation before any model call.** Add a deterministic reduction pass to
   `collect-transcripts` (turns verbatim, tool calls to one line, output truncated)
   before the LLM triage that the spec describes but the code does not perform.
7. **Association tiers.** Our sessions run in managed worktrees and cloud
   containers whose paths die with them. Adopt worktree-list and recorded-remote
   matching; the dead-path tier is what our `claude_code_web` sessions will need.

### Skip

- Harness probe ladders, `acpx`, and provider-auth ranking. Our archetype system
  and vendor routing already own model selection.
- The lavish-axi browser review surface, for this loop. Already a separate proposal.
- User-scope memory training. Out of scope for a repo tool.
- opencode, cursor, hermes adapters, unless someone here uses them.
- The bootstrap starter. We have a file.
- The TUI progress view and theming.
- TOON or other output-format work. Same reasoning as the AXI change: the
  correctness principles carry the value.

## 5. Two ways to get there, and a recommendation

**Option A, run backpass as the engine.** It is an npm package with no API keys of
its own, reads the same stores our adapters read, and could be pointed at this
checkout today. Configuration that matters: `memoryFiles: ["AGENTS.md"]` after the
flip, `skillsDir: "skills"` so edits land in the canonical tree rather than in a
mirror `install.sh` overwrites, and `discovery.since` wide enough to cover the
autopilot history. Expect it to report the surface over budget on the first run
because 74 descriptions are billed; the README says this is the one-time re-tune,
not a regression. Its `.backpass/` state stays out of git via the local exclude.

**Option B, port the concepts into `collect-transcripts` and `/improve-harness`.**
This keeps everything in Python under our test suite and our coordinator memory, but
it means building the instruction index, the evidence schema, the gap ledger, the
staging editor, and the gates ourselves, on top of a pipeline whose LLM path and
memory writes do not yet exist (section 6).

**Recommendation: A as a bounded spike, then decide.** The spike costs no code. Its
exit criteria: the budget bar becomes the ri-04 baseline; the first proposal is
reviewed edit by edit; the orchestration-domain diagnostics are checked against what
`/improve-harness` would have said. If the proposals are good, keep backpass as the
engine for the always-loaded surface and write a thin emitter from its gap ledger
into D4 memory. If they are not, the spike has still produced the instruction index,
the evidence rows, and the budget number that Option B would need, and the port can
be scoped from real output rather than from the README.

## 6. Defects surfaced while mapping the pipeline

These are independent of backpass and should be filed regardless.

1. `/improve-harness` posts `time_window_days` and no `agent_id` to `POST /memory/query`;
   `MemoryQueryRequest` requires `agent_id` and has no such field, so the request
   fails validation (`skills/improve-harness/scripts/analyze_failures.py:45-57`,
   `agent-coordinator/src/coordination_api.py:121-125`).
2. The same query filters on the bare tag `capability_gap`, but the SQL predicate
   is exact array overlap (`tags && p_tags`), so it never matches stored
   `capability_gap:<text>` tags (`agent-coordinator/database/migrations/004_memory_tables.sql:134`).
   `skills/agent-metrics/scripts/query_metrics.py:87` has the same pattern.
3. `analyze_failures.py` computes deduplicated multi-source findings and then
   discards them, ranking raw memory entries instead (self-documented at
   `analyze_failures.py:390-399`). `generate_report_multi_source` is never called
   from `main()`.
4. `collect-transcripts` never calls a model and never writes memory: `--enable` is
   documented but not implemented, `analyze_session_llm` is referenced but not
   defined, and both CLIs default to dry-run.
5. The coordinator's audit-triage classifier has no caller outside its tests and is
   disabled by default (`agent-coordinator/src/audit_triage.py:51-64`).
6. `openspec/specs/skill-workflow/spec.md:88-90` and three skills still describe
   CLAUDE.md and AGENTS.md as two files that can diverge.

Taken together, the four-source capability-gap pipeline is a contract with one
working emitter (session-log) and a consumer that cannot currently read from the
coordinator. That changes the adoption calculus in favour of Option A: there is less
to protect than the documentation suggests.

## 7. Where this lands in the existing roadmaps

| Roadmap item | Relationship |
|---|---|
| skill-rightsizing ri-04, record the `/doctor` context-cost baseline | backpass's budget bar is a harness-neutral measurement of the same surface; use it as the denominator or alongside `/doctor` |
| skill-rightsizing ri-10, rewrite skill frontmatter | One-shot rewrite; backpass's failed-trigger detection is the continuous follow-on and its description-delta accounting prices each rewrite |
| skill-rightsizing ri-14, cut competence rules and relocate policy | `remove` and `move`/`extract` actions with evidence floors; relevance prioritizes, replay benchmark accepts |
| skill-rightsizing ri-15, progressive disclosure | `extract` action; every removed line must reappear in the reference file |
| repo-improvement RI-12, scheduled learning pipeline | The scheduled run becomes `backpass` (or its port) plus `/improve-harness` over the orchestration-domain output |
| repo-improvement ri-02, reconcile stale docs | Fix the two-file spec text and the symlink references in the same pass |

## 8. Open decisions for the owner

1. Flip the canonical file to AGENTS.md with CLAUDE.md as an import pointer, or keep
   the symlink and accept the portability and vendor-specific-content caveats.
2. Corroboration unit for this corpus: distinct sessions, distinct changes, or
   distinct interactive sessions.
3. Whether the maintenance loop's human gate is PR review with one commit per edit,
   or whether the lavish-axi review surface proposal should be revived for it.
4. Whether to run the Option A spike before or after ri-09's arm-A baseline lands.
   Running it before gives ri-04 its number earlier; running it after keeps the
   rightsizing sequencing untouched.

## Adoption phases

The phases below turn sections 3 through 7 into an executable sequence. Phase 0 is a
decision point: its outcome decides whether phases 3 and 4 wrap backpass as the
engine or port its concepts into `collect-transcripts`. Everything in phases 1 and
2 is independent of that decision and can start immediately.

### Phase 0, Spike: run backpass against this checkout

- Install backpass and `acpx`, write `.backpassrc.json` with `memoryFiles:
  ["AGENTS.md", "CLAUDE.md"]`, `skillsDir: "skills"`, and `discovery.since` wide
  enough to cover the autopilot history; keep `.backpass/` out of git.
- Run `backpass scan`, `backpass status`, and one full `backpass` run; do not run
  `backpass apply` against the shared checkout.
- Record the always-loaded budget bar (memory file plus all skill descriptions) as a
  dated context-cost baseline alongside the ri-04 `/doctor` figure.
- Review the first proposal edit by edit and record, per edit, whether the evidence
  would have justified the change under this repo's standards.
- Compare backpass's orchestration-domain diagnostics with what `/improve-harness`
  reports over the same window.
- Write the engine-versus-port decision as a capability-timeline entry in
  `docs/decisions/`, with the spike's numbers attached.

### Phase 1, Conventions (independent of the spike)

- Flip the canonical file: AGENTS.md becomes the self-contained canonical
  instruction file, CLAUDE.md becomes a Claude-specific preamble ending in
  `@AGENTS.md`; retarget `test_claude_md_restructure.py`, `README.md:7`, the
  context-engineering skill, and the "either file exceeds 300 lines" spec text.
- Define the five memory actions (`add`, `rewrite`, `remove`, `extract`, `move`)
  with their evidence floors and mechanical checks as a section of
  `docs/guides/documentation.md`, and reference it from the skill-workflow spec.
- Write the placement policy, "what goes where", merging the keep/cut test, the
  broad/narrow/trigger table, and the progressive-disclosure tiers, with measured
  relevance as the criterion.
- Split the `documentation` surface in `openspec/schemas/context-impact-rules.yaml`
  into `agent-memory` (AGENTS.md, CLAUDE.md, SKILL.md frontmatter) and `docs`.

### Phase 2, Pipeline repairs (independent of the spike)

- Fix the `/improve-harness` memory query: send the fields `MemoryQueryRequest`
  declares, and match `capability_gap:*` tags with a prefix query rather than the
  bare tag; add a test against a live or fake coordinator.
- Make `analyze_failures.py` rank the deduplicated multi-source findings and call
  the multi-source report from `main()`.
- Either implement `collect-transcripts --enable` with the LLM triage and deep
  analysis the spec describes, or amend the spec and SKILL.md to describe the
  heuristic-only behaviour that exists.
- Decide and record whether the coordinator audit-triage classifier is wired to a
  background task or removed; do not leave it as documented-but-uncalled.

### Phase 3, Evidence model (shape depends on the Phase 0 decision)

- Instruction index: parse AGENTS.md into hashed units with stable `AG-nnn` ids and
  expose it as a shared script.
- Extend the D4 tag schema with `instruction:`, `polarity:`, `class:`, and
  `domain:` prefixes and document them in `docs/guides/memory-conventions.md`.
- Add a deterministic distillation pass to `collect-transcripts` before any model
  call, with a measured reduction figure in its dry-run report.
- Add a persistent gap ledger and an edit-keyed rejection ledger for
  `/improve-harness`, with retire-on-coverage and expiry.
- Key per-transcript evidence on a surface hash of the memory file plus all skill
  descriptions.
- Add worktree-list and recorded-remote session association to the adapters.

### Phase 4, Integration (shape depends on the Phase 0 decision)

- Emit backpass's gap ledger (or the ported equivalent) into episodic memory as
  `source:transcript-mined` entries with `affected_skill`.
- Deliver memory-file proposals as one commit per edit with the action kind,
  instruction ids, and verbatim quotes in the commit body, plus a `proposal.json`
  the rejection ledger keys on; PR review is the accept/reject gate.
- Schedule the run as the RI-12 learning pipeline: backpass (or its port) followed
  by `/improve-harness` over the orchestration-domain output.

## Out of scope

- Harness probe ladders, `acpx` provider ranking, and any new model-selection layer.
- The lavish-axi browser review surface; that is its own proposal.
- User-scope memory training.
- New transcript adapters for opencode, cursor, or hermes.
- TOON or other output-format work.
- Replacing the skill-rightsizing replay benchmark; this loop prioritizes cuts, the
  benchmark accepts them.
