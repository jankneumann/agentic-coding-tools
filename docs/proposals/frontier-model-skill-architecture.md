# Rightsizing `skills/` for Frontier Models

## Context

Changes to this repo are getting slower, and the abstractions are buying less than they cost. This document argues that the cause is structural: `skills/` is written as a **program for a weak interpreter** rather than a **briefing for a capable colleague**, and the maintenance surface of that program now exceeds the value it delivers.

The framing comes from Anthropic's July 2026 guidance for Claude 5 generation models ([The new rules of context engineering](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models), summarised by [Thariq Shihipar](https://x.com/trq212/article/2080710971228918066)): Anthropic removed **over 80% of Claude Code's own system prompt** for Opus 5 and Fable 5 with no measurable loss on coding evals. Their diagnosis was that they "were overconstraining Claude Code, both through our system prompt and in our CLAUDE.md files and skills." The fix was not better few-shot examples — it was deleting constraints that once prevented worst cases and now merely create conflicting instructions and burn tokens.

The same conclusion holds for GPT-class frontier models: over-specified procedure competes with a model that plans better than the procedure does.

## The criteria

Combining that article with the [skill-authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices), eight criteria are actionable here:

1. **Unhobble.** Delete guardrails written for weaker models. Every rule should trace to a failure this model actually exhibits.
2. **Rules → judgment.** Don't write "never do X" without a specific, demonstrable failure mode the model can't reason its way out of.
3. **Examples → interface design.** Examples constrain the model to a narrow exploration space. Make tool interfaces self-describing instead.
4. **The context window is a public good.** Only add context the model doesn't already have. Challenge each paragraph: does it justify its token cost?
5. **Degrees of freedom match fragility.** Low freedom (exact scripts) only on narrow bridges with cliffs — database migrations, irreversible ops. High freedom (prose direction) in open fields — review, design, analysis.
6. **Progressive disclosure.** SKILL.md is a table of contents, not a manual. Under 500 lines; details in sibling files, one level deep.
7. **`description` is the only load-bearing metadata.** It is what the runtime uses to select among 100+ skills. It must say *what* and *when*.
8. **Evals are the source of truth.** Not content linters. Measure whether the skill changes agent behaviour on real tasks.

## Measured state of `skills/`

| Metric | Value |
|---|---|
| `SKILL.md` files | 74 |
| Total `SKILL.md` lines | 17,945 (avg 242) |
| Skills over the 500-line guidance | 11 |
| Skills over 300 lines | 24 |
| All markdown under `skills/` | 175 files / 26,588 lines |
| Content-invariant test code (`skills/tests/`) | 210 files / **24,740 lines** |
| `SKILL.md` files with **zero** links to sibling markdown | **66 of 74** |
| Skills with more than one markdown file | 16 of 74 |
| Mandatory "tail block" prose (Rationalizations / Red Flags / Verification) | 20 skills / 578 lines |
| `<skill-base-dir>` path placeholders | 243 occurrences across 40 skills |
| Hard-coded cross-skill script paths (`../<skill>/scripts/*.py`) | 104 references |
| `sys.path.insert` hacks inside `SKILL.md` prose | 13 occurrences across 8 skills |
| Inline `python3 - <<PY` heredocs in `SKILL.md` | 5 skills |
| Skills carrying a `triggers:` frontmatter list | 52 |
| Runtime code that reads `triggers:` | **0** |
| Descriptions lacking an explicit "use when" clause | **69 of 74** |
| Numbered procedural steps in the largest skills | plan 27, cleanup 26, validate 21, implement 17, merge 17 |
| Scripts under `*/scripts/` | 329 (99 with `argparse`, 43 with `--json`) |

Two of those numbers explain the slowdown on their own:

- **24,740 lines of tests police 17,945 lines of skill prose.** More than a line of test per line of instruction, and much of it asserts *shape* — that a heading exists, that a table has at least three rows — not behaviour.
- **66 of 74 skills have no progressive disclosure at all.** Everything is inline. The 887-line `validate-feature` loads in full whether the task needs the security phase or not.

## Diagnosis: five structural problems

### 1. Procedure lives in prose, where it can't be tested or reused

`implement-feature/SKILL.md` opens with steps `0`, `0a`, `1`, `2`, `3`, `3z`, `3a`, `3b` — 17 numbered steps before the model does any implementing. Steps 0 through 3z are pure mechanics: detect the coordinator, branch on four tier conditions, set up a worktree, resolve a parent branch, verify the current branch matches, map `AGENT_TYPE` to a vendor short-name and record it. Roughly 150 lines of markdown, including a shell `case` statement and a Python heredoc with a `sys.path.insert`.

None of that is a decision. It is a function, transcribed into English, that a model must re-execute correctly every run. The step-id sequence (`0a`, `3z`) is the visible scar tissue of insertions made without renumbering — the signature of prose being used as a program.

This is also why changes are slow: modifying worktree behaviour means editing `worktree.py`, then finding and editing the 36 hard-coded invocations of it scattered across `SKILL.md` files, then updating the tests that assert those invocations appear.

### 2. Skills are coupled by filesystem path rather than interface

104 hard-coded `../<skill>/scripts/*.py` references and 243 `<skill-base-dir>` placeholders make the skill tree a build system with no build tool. Nothing can move. `worktree.py` is effectively a public API with 36 call sites and no interface contract, no versioning, and no `--help` most callers were written against.

This is the direct inverse of criterion 3. Instead of a self-describing interface the model can discover, there's a path template the model must interpolate correctly — and a fragile note in `autopilot/SKILL.md` warning it to run a probe "BARE — do not pipe" because `$?` in a pipeline reports the wrong status. That warning exists because the *interface* leaks; a tool returning structured JSON wouldn't need it.

### 3. The mandated tail block is anti-rationalization prompting for a model that no longer needs it

`references/skill-tail-template.md` requires every `user_invocable` skill to end with **Common Rationalizations** (≥3 rows), **Red Flags** (≥3 bullets), and **Verification** (≥3 items), in that order, enforced by `skills/tests/_shared/skill_invariants.py`.

The Rationalizations table is the clearest example of a Claude-3-era guardrail. Its content is of the form *"I'll skip tests because the deadline is tight" → "Later never comes."* This is pre-emptive argument against an excuse a frontier model does not make, and it costs 578 lines plus a test-enforced minimum that every new skill must satisfy before it can merge. Criterion 2 is explicit: no "never do X" without a demonstrable failure mode.

**Red Flags** and **Verification** are more defensible — they encode observable signals and checkable outputs. But the `≥3` threshold is arbitrary and forces padding: a skill with two genuine red flags must invent a third to pass CI.

### 4. Effort went into metadata the runtime ignores, and not into the field it reads

52 skills maintain a `triggers:` list — 15 entries in `explore-feature` alone. Nothing in the repository reads this field; `install.sh` only inspects `related:`. Claude Code selects skills from `name` and `description`.

Meanwhile **69 of 74 descriptions omit any "when to use" clause**. Compare:

```yaml
# current — what, but not when
description: "Implement approved OpenSpec proposal with tiered execution (coordinated / local-parallel / sequential)"

# rightsized — what and when, which is what selection actually keys on
description: "Implements an approved OpenSpec change: sets up a worktree, works the task list
  test-first, and opens a PR. Use when a proposal exists at openspec/changes/<id>/ and the user
  asks to implement, build, or start work on it."
```

The tiering detail in the current description is invisible to the user asking "build the auth feature" and does no selection work. The trigger list is a hand-maintained approximation of what the description should have said in the first place.

### 5. Tests assert shape, not behaviour

`skills/tests/` is larger than the skills it tests, and its core invariants are `assert_frontmatter_parses`, `assert_required_keys_present`, `assert_references_resolve`, `assert_related_resolve`, `assert_tail_block_present`. Only the reference-resolution checks catch real bugs; the rest enforce a house style.

This is the mechanism that makes every change expensive. Rewording a skill can fail CI for reasons unrelated to whether the skill works. And because the tests never execute a skill, a skill can be structurally perfect and behaviourally broken.

The repo already owns the right tool for this — `gen-eval` and `gen-eval-scenario` — and doesn't point it at the skills themselves.

## Recommendations, in leverage order

### R1. Collapse the mechanical preamble into one tool call

Replace steps 0/0a/2/3/3z of `implement-feature` (and their near-duplicates in `plan-feature`, `validate-feature`, `iterate-on-*`, `autopilot`) with a single command returning structured state:

```bash
uv run skills session-start <change-id> --json
```

```json
{
  "tier": "coordinated",
  "tier_rationale": "coordinator reachable; discover/queue/lock capabilities present",
  "worktree_path": "/…/worktrees/add-auth",
  "worktree_branch": "openspec/add-auth--agent-3",
  "feature_branch": "openspec/add-auth",
  "worker_vendor": "claude",
  "seeded_tasks": 12,
  "warnings": []
}
```

The skill prose reduces to: *"Run `skills session-start <change-id> --json` and `cd` to `worktree_path`. It selects the tier, prepares the worktree, and records the worker vendor. If `tier` is `sequential`, work the task list yourself; otherwise dispatch per work package."*

Roughly 150 lines of markdown deleted per large skill, one implementation to test instead of six transcriptions to keep in sync, and — critically — the coordinator-detection and tier-selection logic becomes unit-testable Python instead of a pseudocode `if/else` ladder in a markdown file.

**This is the change that most directly addresses "every change takes longer."** Today, tier-selection logic has seven copies.

### R2. Give the script layer a real interface

Add console entry points in `skills/pyproject.toml` so cross-skill calls become discoverable commands rather than relative paths:

```toml
[project.scripts]
skills-worktree = "skills.worktree.cli:main"
skills-coord    = "skills.coordination_bridge.cli:main"
skills-review   = "skills.parallel_infrastructure.cli:main"
```

Requirements per criterion 3: every command takes `--json`, exits non-zero with an actionable message on failure, and documents itself through `--help`. Currently only 43 of 329 scripts emit JSON and 99 use `argparse`.

This eliminates all 243 `<skill-base-dir>` placeholders, all 13 `sys.path.insert` lines in prose, and the "run it BARE — do not pipe" class of warning. A self-describing interface means the skill doesn't have to teach the model how to call it.

### R3. Delete the Rationalizations block; keep Verification where it's real

- Remove **Common Rationalizations** from `references/skill-tail-template.md` and from all 20 skills. Remove `assert_tail_block_present`'s check for it.
- Keep **Verification**, but only where the items are machine-checkable outputs (a file path, a passing command, a PR link). Drop the `≥3` floor — two real checks beat three padded ones.
- Keep **Red Flags** only where they name a failure this codebase has actually seen. A red flag that has never fired is a guardrail for a model that no longer exists.

Recovers ~578 lines and removes a merge gate from every future skill.

### R4. Rewrite frontmatter to what the runtime reads

- Delete `triggers:` from all 52 skills — dead metadata.
- Keep `category`, `tags`, and `related` only if something consumes them (`install.sh` reads `related`; audit the others).
- Rewrite all 74 `description` fields to include both *what* and *when*, third person, with the concrete nouns a user would say.

This is the single cheapest change with a measurable payoff: skill selection accuracy is a function of `description` quality, and 93% of descriptions currently underspecify it.

### R5. Apply progressive disclosure to the 11 oversized skills

The pattern for `validate-feature` (887 lines, 21 numbered steps, 10 phases, zero sibling references):

```
validate-feature/
├── SKILL.md            # ~150 lines: phases, gate semantics, when to skip what
└── reference/
    ├── deploy.md       # docker-compose bring-up, DEBUG logging
    ├── security.md     # scan config and triage rules
    ├── e2e.md          # Playwright setup and selectors
    └── spec-compliance.md
```

One level deep, per the docs — nested references get partially read. A validation run that skips E2E then never loads `e2e.md`, and the tokens go to the actual diff instead.

Same treatment for `plan-feature` (756), `merge-pull-requests` (756), `autopilot` (699), `iterate-on-plan` (628), `implement-feature` (625), `test-driven-development` (606), `cleanup-feature` (605), `iterate-on-implementation` (595), `api-and-interface-design` (531), `performance-optimization` (509).

### R6. Cut rules that restate ordinary competence

`implement-feature`'s "Implementation Rules (0–5)" spans Rule 0 *Simplicity First*, Rule 0.5 *Scope Discipline*, Rule 1 *One Thing at a Time*, Rule 2 *Keep It Compilable*, Rule 3 *Feature Flags*, Rule 4 *Safe Defaults*, Rule 5 *Rollback-Friendly*.

Rules 0, 0.5, 1, and 2 describe how a competent engineer works by default; a frontier model does not need to be told that a commit mixing a feature and a typo fix is two commits. Rules 3, 4, and 5 are **project policy** — they encode a choice this repo made that the model cannot infer — and should be kept, moved to `CLAUDE.md` where they apply to all work, and stated once.

Apply the same test everywhere: **does this sentence encode a decision specific to this project, or does it describe competence?** Delete the second category. That test is what got Anthropic to an 80% cut.

### R7. Replace content-invariant tests with behavioural evals

Keep from `skills/tests/`: frontmatter parsing, reference resolution (both catch real breakage), and all unit tests of `*/scripts/*.py` (those test code).

Delete: tail-block presence, minimum-row thresholds, section-ordering assertions.

Add, using the existing `gen-eval-scenario` machinery: three scenarios per user-invocable skill, asserting outcomes — *"given fixture repo X and change-id Y, `/implement-feature` produces a branch whose tests pass and a PR whose description references the spec deltas."* Criterion 8: evals are the source of truth, and they're also the only way to safely make cuts R1–R6, because they tell you if a deletion regressed anything.

**Sequence matters: land a thin eval harness before the large deletions**, so the 80%-cut experiment is measurable rather than hopeful.

### R8. Use `/doctor` for the cost side of the ledger

`/doctor` is a bundled prompt-based skill in Claude Code (v2.1.205+, previously a built-in command). It is a **static rightsizing pass, not an eval** — worth being precise about, because its scope is narrower than the name suggests. Per the [commands reference](https://code.claude.com/docs/en/commands), the parts that apply here are:

- **Skill-listing context cost.** Every skill's `name` + `description` is preloaded into every session. With 74 skills that is a permanent tax on every turn, paid whether or not a skill is used. `/doctor` estimates the listing's total cost and names its biggest contributors — a direct, quantifiable measure of R4's payoff.
- **Unused skills, MCP servers, and plugins versus their context cost.** Produces the deletion-candidate list for skills that have never triggered.
- **`CLAUDE.md` trimming**, using this keep/cut heuristic: cut what the model could derive from the codebase (directory layouts, dependency lists, architecture overviews); keep pitfalls, rationale, and conventions that differ from tool defaults. Migrate always-loaded guidance into skills and nested `CLAUDE.md` files that load on demand.
- **Slow hooks.** This repo runs `SessionStart` hooks (`coord-env`, `register_agent`) on every session.

It reports findings first and asks before changing anything.

What it will **not** do: rewrite `SKILL.md` bodies. Its skill-related work targets the always-loaded listing and whether a skill is used at all — not the 887 lines inside `validate-feature`. It will not touch the 104 hard-coded script paths, the tail blocks, or `skills/tests/`. Those remain R1–R7, done by hand.

The reusable artifact is the heuristic. *"Cut what the model could derive; keep pitfalls, rationale, and conventions that differ from defaults"* is Anthropic's own operationalisation of criterion 4, and it is the same test R6 applies to `SKILL.md` bodies. Apply it manually where the tool cannot reach.

**How it relates to the eval gate.** `/doctor` measures context cost — the input side. Evals measure whether behaviour survived — the output side. A deletion is only accepted when both move the right way: cost down, eval scores flat or better. `/doctor` alone can tell you a skill is expensive; it cannot tell you that removing it broke something.

## Sequencing

| Phase | Work | Unblocks |
|---|---|---|
| 0 | R8 (`/doctor` baseline), then R4 (frontmatter/descriptions) | Establishes the context-cost baseline; R4 is cheap, isolated, and immediately improves selection |
| 1 | R7 eval harness — 3 scenarios for the 12 `user_invocable` skills | Makes every later deletion measurable |
| 2 | R2 (CLI entry points), then R1 (`session-start`) | Removes 104 path couplings and 7 copies of tier logic |
| 3 | R3, R6 (delete rationalizations and competence-restating rules) | ~700 lines, verified by phase-1 evals |
| 4 | R5 (progressive disclosure for the 11 oversized skills) | Per-run context drops toward what the task needs |

Expected shape after: `SKILL.md` total from ~17,900 lines to roughly 6,000–8,000, with the difference either deleted as unnecessary or promoted into tested Python and on-demand reference files. Test volume falls as shape-assertions are replaced by a smaller number of behavioural scenarios.

## What this does not change

- The tiered execution model (coordinated / local-parallel / sequential) is a genuine architectural decision and stays. What changes is that the model reads one JSON field instead of re-deriving a four-branch condition.
- Low-freedom, exact-script instruction stays wherever the operation is genuinely fragile: merge/rebase sequences, worktree teardown, anything irreversible. Criterion 5 keeps guardrails on narrow bridges — it just removes them from open fields.
- Vendor-neutral dispatch stays. It should move behind the `skills-review` interface rather than being re-explained in seven `SKILL.md` preambles.

## Sources

- [The new rules of context engineering for Claude 5 generation models](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models) — Anthropic
- [Thariq Shihipar, "The new rules of context engineering for Claude 5 models"](https://x.com/trq212/article/2080710971228918066)
- [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) — Claude Platform Docs
- [Lessons from building Claude Code: How we use skills](https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills)
