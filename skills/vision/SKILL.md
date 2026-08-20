---
name: vision
description: >
  Draft and stress-test a VISION.md for a repository, then iterate with the author
  until they approve it. Mines the repo's real decision record — OpenSpec specs and
  archived change proposals, capability-timeline ADRs, merged PRs, git history — for
  evidence, drafts the vision as a testable acceptance policy, and stress-tests it
  with fault-line hypotheticals only the author can answer. Use on /vision, or when
  asked to write, refine, or stress-test a project vision, a statement of what a
  project refuses to become, or contribution-acceptance criteria.
category: Documentation
tags:
  - vision
  - acceptance-policy
  - evidence-mining
  - openspec
  - adr
  - stress-test
  - review-board
  - project-identity
triggers:
  - "write a vision"
  - "VISION.md"
  - "project vision"
  - "stress-test the vision"
  - "what does this project refuse to become"
  - "acceptance criteria for contributions"
user_invocable: true
related:
  - documentation-and-adrs
  - update-specs
  - worktree
---

# /vision

You are running the **vision** skill. Produce a VISION.md the author can approve: an
acceptance policy for the project's future, grounded in what they actually build, and
sharpened by hypotheticals they answer on a review board.

This is not a writing exercise. Follow this file top to bottom.

## Provenance

Adapted from the upstream [`kunchenguid/vision`](https://github.com/kunchenguid/vision)
Agent Skill (MIT). The pipeline, hard rules, output anatomy, and the review-board
house style are upstream. Three things are localized to this repo and are the reason
this is a first-class skill rather than a `vendor-manifest.json` entry — the vendor
fetcher overwrites files in place and would clobber all three:

1. **Evidence ladder** (Step 3) — mines this repo's decision artifacts (OpenSpec specs
   and archived proposals, `docs/decisions/` capability timelines, merge logs) ahead of
   PR titles, rather than treating merged-PR history as the primary source.
2. **Review-loop transport** (Step 6) — verdicts return through `AskUserQuestion`, this
   repo's established human-gate tool, instead of `npx -y lavish-axi`. No external
   service and no npm dependency sit between the author and their own vision.
3. **Repo conventions** — house frontmatter keys, the `<skill-base-dir>` path rule, the
   worktree mutation guard, and the tail-block contract enforced by
   `skills/tests/vision/`.

When syncing upstream improvements, re-adapt these three; do not overwrite them.

## Hard rules

1. **Evidence over vibes.** Every principle in the draft must be traceable to concrete
   evidence: a named spec requirement, archived proposal, ADR entry, PR, commit, file,
   or the author's recorded answers. Generic engineering virtues ("we value quality")
   are banned unless the history demonstrates them specifically.
2. **Check for an existing VISION.md first.** If one exists on the default branch,
   switch to delta mode: treat it as the approved baseline, propose line-level candidate
   changes from evidence newer than it, and never write a competing document.
3. **The author owns the vision.** You draft, stress-test, and fold in their verdicts;
   you never approve, never soften a hypothetical to please, and never fold in a
   principle they did not state or demonstrate.
4. **A vision is an acceptance policy.** Write testable accept/resist criteria in
   declarative present tense, with explicit non-goals, so a future reader — human or
   agent — can apply them to a concrete change.
5. **No softball hypotheticals.** Each one must sit on a genuine fault line where yes
   and no are both defensible, with both sides steelmanned. If you can predict the
   author's answer, replace the hypothetical.
6. **The review board is built from the shipped template, and verdicts come back
   through the host.** The board is the shipped template with only its slots filled,
   never restyled or restructured; verdicts return via `AskUserQuestion`, never by you
   reading an answer into the record yourself. Mechanics in Step 6.
7. **Iterate in batches, trace every edit.** Each author verdict maps to a named edit in
   a changelog; the author must be able to see exactly how their answer changed the text.
8. **Formatting of the VISION.md output.** One sentence per line. Plain hyphens, never
   em dashes. No roadmap, no feature list, no marketing voice. (This rule governs the
   drafted VISION.md only, not this skill file or your chat replies.)

## Pipeline

### Step 0 - Parse target and author

- Target repo: current working directory by default, or an explicit `owner/repo`.
- Author: the person whose vision this is; default to the repo owner. Their merged work
  is the evidence base.
- Ask one short question via `AskUserQuestion` if the target or author is genuinely
  ambiguous. Do not ask if the default is obvious.

### Step 0b - Claim a work surface [mutating skill]

This skill writes `VISION.md` and an answers file. Where they land depends on the
target resolved in Step 0:

- **Target is the current repo** (the default): the launcher invariant applies — never
  mutate the shared checkout in local CLI execution.

  ```bash
  python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup vision
  python3 "<skill-base-dir>/../shared/checkout_policy.py" require-mutation
  ```

  In cloud-harness environments both calls short-circuit to success — the container
  already provides isolation. Full rules: `docs/guides/worktree-management.md` in the
  consumer project.

- **Target is an external `owner/repo`**: the write surface is a clone of the *target*,
  never this repo's checkout or worktree. Clone the target, work there, and skip the
  worktree/guard calls above — they govern this repo only. If the target clone is
  read-only (no push access), still draft there and deliver the files to the author
  instead of pushing.

Everywhere below, "the work surface" means whichever of these Step 0b resolved.

### Step 1 - Learn the pattern

A VISION.md has a stable anatomy; hold the draft to it:

- Identity opener: "X exists so that ...", who it serves, and "It owns exactly one
  thing: ...".
- 3-6 principle sections with short declarative headings, each a set of testable
  present-tense commitments and refusals.
- Explicit non-goals, named concretely ("it is not a CI system, not a ...").
- A closing pair of tests: "A change aligns when ..." and "A change should be resisted
  when ...", concrete enough to apply to a real PR.
- Voice: declarative, present tense, zero marketing; length 40-70 lines.

If the author names exemplar visions, read them; note shape, voice, length.

### Step 2 - Existing-vision check

- If the default branch has a `VISION.md`: delta mode (hard rule 2). Diff its age
  against the history and propose only evidence-backed candidate additions or edits,
  as a numbered list, each independently acceptable.
- If not: from-scratch mode.

### Step 3 - Mine the evidence

Work down this ladder. **Tier A is the primary source in this repo** — a merged PR
title tells you what was built; an archived proposal with its rejected alternatives
tells you what was *chosen over what*, which is the raw material of an acceptance
policy. Skip a tier only when its artifacts do not exist.

If **no** tier yields readable history, **stop** and say so. Never fabricate the
author's values, PR titles, proposals, or evidence. A vision built on invented
evidence is worse than no vision.

#### Tier A - Decision artifacts (OpenSpec repos)

| Source | What it reveals |
|---|---|
| `openspec/project.md` | Stated purpose, stack, conventions. Test these claims against behavior; where they diverge, the behavior is the value. |
| `openspec/specs/<capability>/spec.md` | Standing commitments the project holds itself to. Requirements are already written as testable criteria — the vision's closest existing relative. |
| `openspec/changes/archive/*/proposal.md` | What was accepted, and the stated why. The strongest revealed-value signal in the repo. |
| `openspec/changes/archive/*/design.md` | Trade-offs weighed and **alternatives rejected**. A rejected alternative is a refusal with reasoning attached — mine these hardest. |
| `docs/decisions/<capability>.md` | Capability timelines with `active` / `superseded` status and `Supersedes` links. A superseded decision is a value the project *changed its mind about*; the reversal is evidence. |
| `docs/guides/*.md` | Conventions codified enough that someone wrote them down. |
| `docs/lessons-learned.md`, `docs/mental-models.md` | Values the author articulated explicitly. Quote, do not paraphrase into generics. |
| `docs/merge-logs/` | Merge-session decision records: what got integrated, what got held back. |
| `CLAUDE.md` and `docs/guides/*` | Standing instructions to agents. These are non-negotiables stated in the imperative — near-vision text already. |

Read broadly, then read deep: scan 30-60 archived proposal titles, then read 8-15 full
`proposal.md` + `design.md` pairs spread across the date range.

#### Tier B - Merged pull requests

```bash
gh pr list --author <owner> --state merged --limit 100 --json number,title,body,closedAt
```

One call returns titles and bodies together — scan 30-100 titles, then read 8-15 full
bodies spread across the range from the same payload; no per-PR `gh pr view` round
trips.

#### Tier C - Commit history

```bash
git log --author=<owner> --no-merges --format='%h %ad %s%n%b' --date=short
```

Titles and messages still reveal what the author builds. This repo uses conventional
commits, so `feat(scope):` prefixes cluster the work by capability for free.

#### Output of Step 3

- Extract recurring revealed values: what gets built, what gets refused, what class of
  bug gets fixed at the root, what the author writes in intent statements, and **what
  got reversed** (superseded ADRs, rejected alternatives, reverted changes).
- Produce a private evidence sheet: `value -> supporting specs, proposals, ADR entries,
  PRs, commits, or files`. This sheet is the source of truth for every drafted line.

### Step 4 - Draft

- Follow the Step 1 anatomy and the output template below.
- Every line must map to the evidence sheet. Length target: 40-70 lines.
- In delta mode, keep the baseline untouched and emit the numbered candidate list
  Step 2 defines.

### Step 5 - Design the hypotheticals

- 8-12 concrete change proposals per vision, aimed at the draft's fault lines. Draw from
  this taxonomy:
  - tempting-but-off-mission features the author will plausibly be asked for;
  - principle collisions (simplicity vs capability, safety vs speed, generality vs
    focus, cost vs quality);
  - slippery slopes, where one reasonable step normalizes the next;
  - scope expansions (new users, new content types, new hosts, teams);
  - identity questions the draft leaves open.
- Format per hypothetical: id, title, the concrete proposal (2-4 sentences), the
  principle it tests (quote the draft), and why the answer is non-obvious (steelman both
  sides).
- Quality gate: delete and replace any hypothetical whose answer you can predict.

In an OpenSpec repo, the archive is a hypothetical generator. A proposal that was
accepted *narrowly*, or a `design.md` whose rejected alternative still looks defensible,
marks a fault line the author has already stood on once.

### Step 6 - Review loop

The board is the **reading surface**; `AskUserQuestion` is the **verdict channel**. Both
are required: the board carries the full draft and both steelmen, which a question
prompt cannot hold; the question tool carries the verdict back to you, which a static
file cannot.

#### 6a. Build the board

Copy `<skill-base-dir>/assets/review-template.html` and `assets/review.css` next to each
other on the work surface, then fill only the template's marked slots: `{{PROJECT}}`,
`{{RUN_NOTE}}`, `{{DRAFT_MARKDOWN}}` (the full latest VISION.md text), and the `CARDS`
array — one object per hypothetical: `{ id, title, body, tests, why }`.

Change nothing else. The template already carries the house structure: full draft on the
left, one card at a time on the right, the steelman in full view. No boilerplate gets
rewritten and no run gets restyled.

#### 6b. Hand the board to the author

Write the board to `VISION-review.html` on the work surface. Do not launch a server,
install a package, or route the board through an external service. How the author
reaches it depends on where this session runs:

- **Local session**: give the author the path; the file opens in a browser directly.
- **Remote session** (cloud harness, container): a container-local path is unreachable
  from the author's browser, so a bare path is never the handoff. Deliver the file
  through the host's file-delivery mechanism (send/attach it for inline rendering), or
  commit it to the working branch and hand the author the hosted file link.

The board's own verdict buttons record a local ledger the author can read back — treat
that ledger as a convenience, never as the channel of record.

#### 6c. Collect verdicts

Ask through `AskUserQuestion`, in batches of 2-3 hypotheticals, one question per card:

- **question**: the card's title plus a one-line restatement of the proposal.
- **header**: the card id (`H-7`).
- **options**: `In vision` / `Off mission` / `Conditional`, each `description` naming the
  concrete consequence for the draft if chosen.
- **multiSelect**: `false`.

Include one open-ended reasoning question in the **same call** — the reasoning, not the
verdict, is what the vision gets rebuilt from. The tool takes at most 4 questions per
call, which is why a batch is 2-3 cards, never 4: the reasoning slot must always fit.
Authors can also attach reasoning per card via each question's free-form "Other" path;
harvest both.

If `AskUserQuestion` is unavailable in the current runtime, present the batch as a
numbered list in regular output and ask the author to respond inline, matching the
fallback convention `plan-feature` uses.

#### 6d. Fold in and reply

On each batch: record the verdicts verbatim in a durable answers file
(`VISION-answers.md`), distill the principles they reveal, fold every verdict into the
draft, rebuild the board in place with the new draft text and remaining cards, and reply
with a changelog line per verdict:

```
H-7 Off mission -> authority section now opens with "the author approves; the tool never does"
```

Continue until the author approves or ends the session. Do not approve on their behalf;
do not treat silence as approval.

### Step 7 - Finish

- Deliver: the approved `VISION.md` text (or approved delta), the full hypothetical set
  with recorded verdicts and reasoning, and the changelog.
- The answers file is durable calibration material; keep `VISION-answers.md` next to the
  vision and commit both.
- Commit and push per the consumer project's `docs/guides/git-conventions.md`; the work
  is not complete until `git push` succeeds. On a read-only external target (Step 0b),
  delivery of the files to the author replaces the push — say which happened.

## Output template (from-scratch mode)

    # Vision

    `{project}` exists so that {the one-sentence reason the project exists}.
    It serves {the named user}, and it {what it turns their input into}.
    It owns exactly one thing: {the single owned surface}.

    ## {Principle section, 3-6 of these}

    {Declarative, testable, present-tense lines; one sentence per line.}
    {Explicit boundaries: what is welcome, what is refused, and why.}

    ## Scope

    {What this project is not, named concretely.}
    {Where personal/private material stays, if applicable.}
    {How the repo holds itself to its own standard, if applicable.}

    A change aligns when {testable positive criteria}.
    A change should be resisted when {testable negative criteria}.

## Pre-flight checklist (before drafting)

- [ ] Target repo and author resolved
- [ ] Work surface claimed (worktree setup + mutation guard, or cloud short-circuit)
- [ ] Existing VISION.md checked (mode chosen)
- [ ] Evidence sheet built from real artifacts at the highest available tier (no invented
      evidence)

## Pre-approval checklist (before the author signs off)

- [ ] Every drafted line traces to the evidence sheet or a recorded verdict
- [ ] 8-12 hypotheticals, none predictable, both sides steelmanned
- [ ] Every author verdict folded in with a traced changelog line
- [ ] Answers file saved next to the vision

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "The README already says what this project is — I can draft from that" | A README states intent; the archive states what was actually chosen when intent collided with reality. Drafting from the README reproduces the marketing voice rule 8 bans. |
| "I know what the author would say to this hypothetical, so I'll record it and move on" | Rule 3 makes the author the only approver. A predicted answer is an invented one, and rule 5 requires you to *replace* any hypothetical you can predict, not answer it. |
| "PR history is unreadable here, so I'll infer values from the code structure" | Structure shows what exists, not what was refused. Tier C (`git log`) is the floor; below it the skill stops rather than infers. |
| "The board collects verdicts, so I can read them off the ledger" | The in-page ledger is a convenience for the author. Verdicts of record arrive through `AskUserQuestion` (6c); reading the ledger back means you never confirmed the author committed to it. |
| "This vision is generic because the project is generic" | Generic principles mean the evidence sheet is thin, not that the project lacks values. Go back to Tier A rejected alternatives and superseded ADRs. |

## Red Flags

- A drafted principle has no entry in the evidence sheet, or its entry cites the draft
  itself.
- The vision contains a roadmap, a feature list, or the word "world-class".
- Every hypothetical resolved `In vision` — the fault lines were softballs (rule 5).
- `VISION.md` changed but `VISION-answers.md` did not, or a changelog line names no
  verdict id.
- The skill reported an approved vision without a recorded author verdict on approval.
- The board was restyled, restructured, or replaced with a different review surface.
- Evidence citations are all from one month of history, or all from one capability.

## Verification

1. Every line of the delivered `VISION.md` maps to a named entry in the evidence sheet
   (spec requirement, archived proposal, ADR entry, PR, commit, or recorded verdict).
2. The hypothetical set numbers 8-12, and each carries a quoted draft principle plus a
   two-sided steelman.
3. `VISION-answers.md` exists beside `VISION.md`, and every verdict in it has a matching
   changelog line naming the edit it produced.
4. The board file was generated from `assets/review-template.html` with only the four
   slots filled — `diff` against the shipped template shows changes confined to
   `{{PROJECT}}`, `{{RUN_NOTE}}`, `{{DRAFT_MARKDOWN}}`, and `CARDS`.
5. The author's approval is recorded explicitly; no step inferred it from silence.
