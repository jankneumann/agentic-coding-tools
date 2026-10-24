# Add why mode to explain-code with epistemic tiers

> Parent roadmap: `verification-enforcement-discipline` (item `ri-09`)
> Change ID: `add-why-mode-to-explain-code-with-epistemic-tiers`
> Effort: M
> Priority: 4

## Why

No tool in this repository answers "why is this code like this?" from the decision
record. The record exists:

- `git blame` gives the commit that last touched a line.
- Commit subjects carry PR numbers (`(#123)` for squash merges, `Merge pull request #N
  from <owner>/openspec/<id>` for merge commits).
- Commits on OpenSpec branches touch `openspec/changes/<id>/` (or, after archival,
  `openspec/changes/archive/<date>-<id>/`).
- A change's `session-log.md` carries `architectural:`-tagged Decision bullets.
  `skills/explore-feature/scripts/decision_index.py` (`extract_decisions`, line 110)
  already parses them into `TaggedDecision` records. The same records feed the
  `docs/decisions/<capability>.md` timelines.

Today an agent asked "why" either reads these by hand, inconsistently, or answers from
the code's shape alone. In both cases its answer reads the same whether a claim was
quoted from a record or invented to fit. Two failure modes follow:

1. **A missing record is hidden by a plausible guess.** When no decision covers a line,
   the honest answer is "no record covers this". The usual answer is a fluent rationale
   that nobody wrote down.
2. **The question's own hypothesis becomes the premise.** "This retry was added for the
   flaky coordinator, right?" gets confirmed rather than checked.

Review findings have the same gap. `evidence_class` (`deterministic | judgment`) says
how a finding was *established*. It does not say how strongly the finding's claim is
backed by what the reviewer actually saw. A shared tier vocabulary lets explain-code
answers and review findings describe their own calibration in the same words.

## What Changes

- **A read-only `why_trace` script.** New file:
  `skills/explain-code/scripts/why_trace.py`. Given `<path>:<line>`, it emits one
  deterministic JSON document with the chain `blame → commit → PR → change-id →
  decisions`.
  - **Reuse, not a second parser.** It imports `extract_decisions` and the supersession
    resolver from `skills/explore-feature/scripts/decision_index.py` rather than
    re-parsing session logs.
  - **Read-only.** It runs only read-only git commands (`blame`, `show`, `log`), reads
    files, writes nothing and makes no network calls.
  - **The null result is explicit.** When no decision record covers the line,
    `decisions` is `[]` and `null_result` names which link of the chain broke:
    `uncommitted`, `history_truncated` (the line blames to a shallow-clone boundary),
    `no_change_id` or `no_decision_record`. It exits `0`, because a null
    result is an answer, not an error.
- **A "why" mode in explain-code.** It is a new catalogue form, the *why chain*, with
  its own `references/why.md`. No standalone `/why` skill is added (roadmap
  out-of-scope, and the operator decision "Extend explain-code").
- **SKILL.md documents three things:**
  - the five-tier vocabulary — Direct, Supported, Inferred, Speculative, Unknown;
  - the **null-result rule**: "no decision record covers this line" is reported as the
    finding, tagged Unknown, and never replaced by an inferred rationale;
  - the **embedded-hypothesis rule**: a reason asserted in the question is restated as
    a claim and tested against the trace, never adopted as a premise.
- **`review-findings.schema.json` gains one optional finding property.** The new
  `evidence_level` property has the enum `direct | supported | inferred | speculative |
  unknown`. It is added to the canonical schema and to its byte-identical
  install-assets mirror.
  - It is not required and has no default, so every existing emitter and every
    committed findings document validates unchanged.
  - The schema diff is limited to that one property.
  - It reaches `review_findings_schema.prompt_contract()` automatically, because that
    function derives enums from the schema.
- **Prompt consumers name the new optional field.** Two prompt builders hand-render a
  vocabulary block, and the existing schema-agreement test
  (`skills/tests/merge-pull-requests/test_vendor_review_prompt.py::test_enum_values_match_the_schema`)
  requires every non-readOnly enum value to appear in the vendor prompt. Each builder
  gains one line, marked OPTIONAL, under its existing `if "<field>" in enums:` pattern:
  - `prompt_contract_block()` in `review_findings_schema.py`;
  - `build_review_prompt()` in `skills/merge-pull-requests/scripts/vendor_review.py`.
- **Distribution wiring.**
  - `skills/install-manifest.json` declares `explore-feature` as a cross-skill
    dependency of `explain-code`. `why_trace` imports from the co-installed
    `explore-feature` at `<skill-base-dir>/../explore-feature/scripts`.
  - The runtime copies under `.claude/skills/` and `.agents/skills/` are re-synced by
    `skills/install.sh`.

## Approaches Considered

### Selected approach (assumed — pending the proposal-approval gate)

**Approach A: extend explain-code with a why-chain form and a deterministic trace
script; tiers live in the reply contract, not in the script.**

- `why_trace` assembles records and pointers only. It never assigns a tier, because
  tiering a claim is a judgement about the answer, not a property of a record.
- The script provides the facts that make tiering checkable:
  - a `pointer` per record (`git:<sha>`, `<session-log path>#<phase-slug>/D<n>`);
  - a `mentions_target` flag per decision, true when the decision text names the file
    or the requested symbol.
- Direct claims must cite a pointer. Linking a decision to *this line* is Direct only
  when `mentions_target` is true, and Inferred otherwise.
- **Accepted cost:** PR numbers come only from local commit text. A rebase-merged PR
  with no PR marker in any commit subject yields `pr: null` with a stated reason,
  rather than a GitHub lookup.

### Rejected alternatives

- **B: a standalone `/why` skill.** Explicitly out of scope in the roadmap proposal. It
  would also duplicate explain-code's grounding and brevity contract.
- **C: let the script assign tiers.** A record cannot know which claim an answer makes
  from it, so a script-assigned tier would be false precision. The tier vocabulary
  would also drift between the script and the review schema.
- **D: query GitHub for PR metadata.** It is non-deterministic, needs credentials and a
  network, and breaks fixture-repo testing. Local commit text covers squash and merge
  commits, which are the repository's two PR-bearing merge shapes.
- **E: re-implement session-log parsing inside explain-code.** That creates a second
  parser of the Decision-bullet grammar that would drift from `decision_index.py`.

## Assumptions (stated conservatively; the discovery questions are human decisions)

1. The requirements belong to the `skill-workflow` capability. That is where the
   existing explain-code requirements and the review-findings schema requirements live.
   The roadmap scaffold's `verification-enforcement-discipline` capability directory
   was a placeholder.
2. Target granularity is `<path>:<line>`. A symbol is resolved to its definition line by
   the skill (from `build_atlas.py --tree` output, or by reading the source) before
   `why_trace` runs. `--symbol` only feeds the `mentions_target` check.
3. The tier names in the schema are lowercase, matching every other enum in the schema.
   SKILL.md shows them capitalised in prose.
4. `evidence_level` is informational. The consensus synthesizer and the blocking rules
   do not read it, so no gate behaviour changes. An invalid value never costs the
   finding: ingest coercion normalises a case variant or removes the field, and records
   a coercion note.
5. The why-chain reply keeps explain-code's existing grounding contract. It is a
   non-call-tree form, so it ends with
   `Grounding: source read, unverified (form not graph-backed)`. The disclosure
   requirement is not modified.

## Non-goals

- Mining or ranking decisions across the whole repository; that is `explore-feature`.
- Changing `docs/decisions/` generation or the Decision-bullet grammar.
- Migrating any emitter to populate `evidence_level`.
- A GitHub/PR API client or any network access from `why_trace`.
- Writing files, HTML or browser output from explain-code. The no-side-effect rule
  stands.

## Dependencies

- None (roadmap `depends_on: []`).
- Four other active changes edit `review-findings.schema.json`, so this change keeps
  its edit to one additive property.

## Acceptance Outcomes

- `why_trace` returns the blame, commit, change-id and decision chain for a fixture
  repository, and an explicit empty result when no decision record covers the line.
- The explain-code SKILL documents the tier vocabulary and the null-result and
  embedded-hypothesis rules; no standalone /why skill is added.
- `evidence_level` is optional in `review-findings.schema.json`, appears in the prompt
  contract derived by `review_findings_schema.prompt_contract`, and every existing
  emitter still validates; the schema diff is limited to that one field.
