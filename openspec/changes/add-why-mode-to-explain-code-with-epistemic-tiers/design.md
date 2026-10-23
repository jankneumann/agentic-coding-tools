# Design: Add why mode to explain-code with epistemic tiers

## Context

`explain-code` is a prompt-only skill: a catalogue of five visual forms, a grounding
contract, and no scripts. This change adds a sixth form, the **why chain**. It also
adds the skill's first script, `why_trace.py`, which assembles the evidence a why answer
cites. The tier vocabulary that answers use is also added to `review-findings.schema.json`
as an optional per-finding `evidence_level`.

## Decisions

### D1 — Capability: `skill-workflow`

The existing explain-code requirements are in `openspec/specs/skill-workflow/spec.md`:

- Visual Code Explainer Skill
- Explainer Grounding and Coverage Disclosure
- Explainer Frontmatter Without Triggers
- Explainer Distribution Wiring

So is Review Findings Schema Extension. The delta therefore targets `skill-workflow`:

- **ADDED:** the why-trace script, the why-chain reply contract, and the evidence-level
  field.
- **MODIFIED:** two existing requirements, so the spec no longer calls the skill
  "prompt-only" and the manifest dependency list includes `explore-feature`.

### D2 — `why_trace` is a record assembler; tiers belong to the reply

The script emits records and pointers and never assigns a tier.

- A tier qualifies a *claim*, and a claim is made in the answer. The same commit message
  can back a Direct claim ("the commit says X") and an Inferred one ("so the line exists
  for Y").
- Two facts make the reply's tiering checkable rather than free-form:
  - **Pointers.** Every record carries a stable pointer:
    - `git:<sha>` for blame and commit records;
    - `git:<sha>` of the PR-bearing commit for PR records;
    - `<session-log relpath>#<phase-slug>/D<n>` for decisions. This is the same ref
      grammar that `supersedes:` uses in `decision_index.py`.
  - **`mentions_target`.** For each decision, true when its title or rationale contains
    the target's repo-relative path, its basename, or the `--symbol` value. Only then
    may a reply say *as Direct* that the decision explains the line. Otherwise the link
    from decision to line is Inferred.

### D3 — Chain resolution is local and deterministic

| Link | Source | Absent → |
|---|---|---|
| blame | `git blame --porcelain -w -M -L n,n -- <path>` against the working tree (no revision argument, so uncommitted lines report the all-zero sha) | an all-zero sha → `status: uncommitted` |
| commit | `git show -s --format=…` plus `git show --name-only --format= <sha>` | — |
| PR | 1. `(#N)` at the end of the commit subject; 2. `Merge pull request #N` in the subject; 3. the oldest merge commit on `git log --ancestry-path --merges <sha>..HEAD` whose subject carries a PR marker | `pr: null`, `pr_reason` given |
| change-id | 1. paths the commit touches under `openspec/changes/<id>/` or `openspec/changes/archive/<date>-<id>/`; 2. `openspec/<id>` in the commit or PR-merge subject or body | `status: no_change_id` |
| change dir | `openspec/changes/<id>` if it is a directory, otherwise the lexically last `openspec/changes/archive/<YYYY-MM-DD>-<id>` whose name matches exactly (so `-demo-change` never matches `…-other-demo-change`) | `change_dir: null` |
| decisions | `decision_index.extract_decisions(<change_dir>/session-log.md)` | `status: no_decision_record` |
| superseded_by | `decision_index._build_supersession_map` over every `openspec/changes/**/session-log.md` | `null` |
| index path | `docs/decisions/<capability>.md` if the file exists | `null` |

The line-range check uses the working-tree file length, matching the blame target.

Resolving archive paths at read time follows the path-stability rule. A commit made
while the change was active still resolves after archival.

`extract_decisions` takes the change id from the session log's parent directory name,
so for an archived change it reports `<date>-<id>`. `why_trace` reports the canonical
`<id>` in its own `change_id` field. For supersession it looks a decision up under both
the extracted directory name and the canonical id, because a `supersedes:` reference may
have been written with either one.

`_build_supersession_map` is private to `decision_index.py`, but it is the only correct
implementation of the phased and legacy `supersedes:` grammar. Reusing it is the
roadmap's instruction and avoids a second resolver. A drift in its signature fails the
`why_trace` fixture tests.

### D4 — Output shape and exit codes

The output is one JSON object on stdout, with `schema_version: 1` and these keys:

- `target` — `{path, line, symbol}`
- `status` — one of `traced`, `no_decision_record`, `no_change_id`, `uncommitted`
- `blame`
- `commit`
- `pr`
- `pr_reason`
- `change_ids` — `[{change_id, source, change_dir}]`
- `decisions` — `[{change_id, capability, phase, date, index, title, rationale,
  supersedes, superseded_by, pointer, index_path, mentions_target}]`
- `null_result` — `null` when `status` is `traced`, otherwise `{reason, message}`

Lists are sorted deterministically: change ids in discovery order, then decisions by
`(change_id, phase date, index)`. When the trace cannot complete, `decisions` is always
present as `[]`.

| Exit | Meaning |
|---|---|
| `0` | A trace was produced, including all three null results |
| `1` | Git failure: not a repository, or git cannot be spawned |
| `2` | Invalid input: malformed target, path not tracked, line out of range |

A null result exits `0` because it is a finding, not a failure. Collapsing it into an
error would make "no record" indistinguishable from "could not look" — the
absence-is-not-a-pass theme of this roadmap.

### D5 — Tier vocabulary and reply rules

| Tier | Use when |
|---|---|
| Direct | The claim restates one record in the trace; it cites that record's pointer |
| Supported | Two or more independent records in the trace agree on the claim; it cites both |
| Inferred | The claim follows from trace records by reasoning, but no record states it |
| Speculative | The claim is plausible but not derived from the trace |
| Unknown | The trace has no evidence either way |

- **Tag format.** Each claim sentence ends with its tier in brackets, for example
  `[Direct git:1a2b3c4]`.
- **Null-result rule.** When `null_result` is non-null, the reply leads with
  `No decision record covers <path>:<line> (<reason>)` tagged `[Unknown]`. It must not
  present a rationale as the answer. At most one further sentence may offer an Inferred
  or Speculative reading, tagged as such.
- **Embedded-hypothesis rule.** A reason asserted in the question is restated as a
  claim. The reply gives it one verdict:
  - *confirmed* — tier Direct or Supported, with a pointer;
  - *contradicted* — with a pointer to the contradicting record;
  - *untested* — tier Unknown.

  It is never used as the premise of the answer.
- **Form.** The why chain is one fenced chain such as
  `src/app.py:42 → 1a2b3c4 → #123 → <change-id> → D2 (<capability>)`, whose first node carries the file location, plus at most three tagged
  sentences. The reply ends with the existing non-call-tree disclosure line,
  `Grounding: source read, unverified (form not graph-backed)`. The grounding
  requirement is untouched.

### D6 — `evidence_level` is one optional property, informational only

```json
"evidence_level": {
  "type": "string",
  "enum": ["direct", "supported", "inferred", "speculative", "unknown"],
  "description": "…same vocabulary as explain-code's why mode…"
}
```

- **Placement and scope.** It goes in `findings.items.properties`. It is not added to
  `required`, it has no `default` and it is not `readOnly`, so the vendor is asked to
  supply it. Both schema copies are edited identically. The diff is exactly that one
  property in each copy.
- **No consumer change.** The consensus synthesizer, the coercion table and blocking
  logic do not read it. `evidence_class` stays the only field that affects blocking.
- **Prompt builders.** Both gain an OPTIONAL line using their existing
  `if "<field>" in enums:` pattern:
  - `prompt_contract_block()`;
  - `vendor_review.build_review_prompt()`.

  `test_vendor_review_prompt.py::test_enum_values_match_the_schema` enforces this for
  the vendor prompt. `vendor_review._FALLBACK_ENUMS`, the offline copy used when the
  schema cannot be read, also gains the `evidence_level` tuple, because
  `test_fallback_matches_the_schema` requires every schema enum to appear there.
- **Single vocabulary.** A new test asserts that the tier list in explain-code's
  `references/why.md`, lowercased, equals the schema enum. The vocabulary cannot
  silently fork.
- **Emitter regression check.** Another test asserts that the new property adds no
  validation error to any committed per-vendor findings document
  (`openspec/changes/**/findings-*.json`): the error set under the current schema must
  be a subset of the error set under the schema with `evidence_level` removed. Many
  historical documents predate other required fields, so asserting "all valid" would
  test the wrong thing. This is the "every existing emitter still validates" property.

### D7 — Distribution

- **Manifest.** `skills/install-manifest.json` →
  `cross_skill_dependencies["explain-code"]` gains `"explore-feature"`, which is already
  `portable`.
- **Import path.** `why_trace.py` puts
  `Path(__file__).resolve().parents[2] / "explore-feature" / "scripts"` on `sys.path`.
  This is the same pattern `project-context-refresh/scripts/producer_decisions.py`
  uses. It resolves to `<skill-base-dir>/../explore-feature/scripts` in both the
  canonical tree and the runtime copies.
- **Invocation.** SKILL.md invokes the script as
  `python3 "<skill-base-dir>/scripts/why_trace.py" <path>:<line>`.
- **Detectable sibling reference.** The manifest validator recognises sibling references
  only in the textual form `<skill-base-dir>/../<skill>`, not in a `parents[2]`
  expression. `why_trace.py` therefore names
  `<skill-base-dir>/../explore-feature/scripts` in its module docstring, so the
  validator's coverage check sees the dependency. The SKILL.md frontmatter `related`
  list also gains `explore-feature`.
- **No bytecode writes.** `why_trace.py` sets `sys.dont_write_bytecode = True` before it
  imports `decision_index`. Otherwise the import could write `__pycache__` into the
  sibling skill directory, which would break the "SHALL NOT write any file" rule.

## Risks

- **Rebase-merged PRs have no PR marker,** so `pr` is null. This is accepted and
  disclosed through `pr_reason`. The change-id link usually still resolves, because
  OpenSpec branch commits touch the change dir.
- **Blame on a line moved by a later refactor points at the refactor commit.** That is
  correct blame semantics. The reply's Unknown or Inferred tiers carry the uncertainty.
  `-w -M` is passed so that whitespace and moved-line noise is reduced
  deterministically.
- **`_build_supersession_map` is private.** It is pinned by the fixture tests (D3).

## Open questions (for the proposal-approval gate; assumptions in proposal.md)

- Should `why_trace` accept a symbol directly rather than requiring the skill to resolve
  it first? Assumed no (proposal assumption 2).
