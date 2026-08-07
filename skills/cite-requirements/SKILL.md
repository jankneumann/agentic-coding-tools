# Cite Requirements

Walk the operator through requirement-traceability judgement calls one at a
time — flag citations (forward, D6) and requirement exclusions (reverse,
D13) — then transcribe each decision into the contract YAML, the exclusions
file, and a decisions journal. Built for the `[human]` tasks of
`trace-requirements-to-contracts` (4.1, 4.2, 4.2b); parameterised by
capability so later retrofits reuse it.

**What this skill is NOT.** It does not decide. D1 of
`trace-requirements-to-contracts` (quoted verbatim):

> **Decision.** An operation's requirement citations are written into the
> contract. Nothing infers them from names, paths, or prose similarity.
> […] **Consequence.** Retrofitting is manual. That is a cost, not a
> defect: the cost is one human decision per operation, and the decision is
> the artifact.

The skill sequences the decisions, quotes the evidence, records the call,
and writes the files. The selection is the operator's on every card.

## Arguments

`<change-id>` — the active OpenSpec change whose spec delta shadows the
archive (D11). Optional flags:

- `--capability <name>` — default `gen-eval-framework`
- `--contract <path>` — default `openspec/contracts/gen-eval-framework/cli/gen-eval.yaml`
- `--skip-annotations` — run without the model-annotation phase

## Sub-agent authorization

Invoking this skill **is** the operator's request to dispatch the two
annotation sub-agents in Step 2 (they are part of the skill's defined
execution model, same contract as the orchestrator skills in CLAUDE.md).
No other dispatch is authorized by this skill.

## The quote/interpretation contract (load-bearing)

Every decision card has two zones, and the boundary is **structural**, not
stylistic:

1. **Verbatim zone** — produced exclusively by `scripts/walkthrough.py`,
   which can only print bytes it read from files, each slice labelled with
   its `file:line` provenance. Ends at the literal marker line the script
   prints ("*Everything above is verbatim file content…*").
2. **Interpretation zone** — appended by the orchestrating agent below that
   marker, under the heading `## Interpretation — NOT from any file`. Model
   annotations appear here labelled per model; the orchestrator's own
   reading appears here labelled as its own. Nothing in this zone may be
   presented as file content, and nothing from it is ever written into an
   artifact except by an explicit operator decision.

Never paraphrase inside the verbatim zone; never quote inside the
interpretation zone without repeating the provenance label.

## Runtime

The helper needs the gen-eval venv (it reuses the gate's own parser —
`gen_eval.traceability` — rather than growing a drifting reimplementation):

```bash
WALK="uv run --project packages/gen-eval python skills/cite-requirements/scripts/walkthrough.py"
```

Run it BARE, never piped ahead of an exit-code check.

## Steps

### 0. Detect and gate

Skip with an explicit message when `packages/gen-eval/` or the contract
file is absent (consumer repos): print
`[cite-requirements] SKIP: <missing path>` and stop. Work in the change's
worktree, never the shared checkout.

### 1. Inventory

```bash
$WALK status --change <change-id>
$WALK inventory --change <change-id>   # JSON, for the loop below
```

Report progress (`flags N/17 decided | requirements M/34 accounted`) and
whether the reverse switch (exclusions file) already exists — its creation
flips enforcement ON (D13), so the operator must always know which side of
that line they are on.

### 2. PREPARE — multi-model semantic annotations (once per session)

Purpose: populate the interpretation zone with **independent semantic
readings from two cheap models of different vendors**, so the operator sees
where models agree, disagree, or find nothing — without any single
plausible-looking match anchoring the card (D1's stated failure mode).

Build one annotation prompt containing (a) every undecided flag's verbatim
contract entry and (b) every effective requirement's id, heading, and body
(from `$WALK card flag <any> …`'s requirement section, or `inventory` plus
the spec files). Ask each model to return STRICT JSON:
`{"flags": {"--x": [{"requirement": "<id>", "note": "<one line>"}]}}`,
with an empty list where nothing is semantically related. Explicitly
instruct: name ONLY ids from the provided list; do not rank; omit rather
than stretch.

Dispatch the same prompt to two models (tiers are defaults — resolve
against `agent-coordinator/agents.yaml` archetypes when available rather
than hardcoding):

- **claude / haiku**: `Agent(prompt=<annotation prompt>, model="haiku")`
- **codex / gpt-5.6-luna**: `codex exec -m gpt-5.6-luna "<annotation prompt>"`

Merge into `openspec/changes/<change-id>/traceability-annotations.json`:

```json
{"generated": "<iso>", "models": [{"label": "haiku", "vendor": "claude"},
                                   {"label": "gpt-5.6-luna", "vendor": "codex"}],
 "flags": {"--mode": [{"model": "haiku", "requirement": "…", "note": "…"}]}}
```

Validate the shape: `$WALK annotations-validate <file>` (structure only —
content is interpretation and is deliberately not judged). If a vendor is
unavailable or returns unparseable output, proceed with the models that
responded and say so on every card; a card with zero annotations is still
valid, because the verbatim zone is sufficient to decide from. Never
re-prompt a model to "fix" its opinion — re-dispatch stricter on format
only.

The annotations file is committed: it is provenance for what the operator
was shown. Its entries NEVER flow into the contract mechanically.

### 3. WALKTHROUGH — one flag at a time

For each flag the inventory lists as `undecided`:

1. `$WALK card flag --subject=<name> --change <change-id>` → show the card
   verbatim (`--subject=--mode` — the `=` form is required, since flag names
   themselves begin with `--`).
2. Below the script's marker, append `## Interpretation — NOT from any
   file`: each model's annotations for this flag (labelled), a one-line
   agreement summary ("both name X", "haiku only", "neither model found a
   related requirement"), and the orchestrator's own reading if it has one
   (labelled as such).
3. Ask via AskUserQuestion. Options: **Cite requirement(s)** /
   **Exclude this flag** (needs a written reason) / **New requirement
   needed** (task 4.1 sub-flow) / **Defer**. Where the annotation models
   named ≤3 distinct candidates, list them as multiSelect options *plus*
   "Other" — the card's full list means any id can be typed; annotated
   candidates are a convenience, never the menu.
4. Transcribe:

```bash
$WALK apply-cite --flag <name> --require <id> [--require <id2>] \
  --note "<operator's stated reasoning>" --change <change-id>
# or
$WALK apply-exclude-flag --flag <name> --reason "<operator's reason>" --change <change-id>
```

The script fails closed: unresolvable ids, double-decisions (without
`--replace`), empty reasons, and malformed post-edit YAML are hard errors.
Revisions go through `--replace`, which journals again — the journal is
append-only history, not current state.

### 3b. NEW REQUIREMENT sub-flow (task 4.1)

When the operator picks "New requirement needed":

1. Operator states the intent in their own words (journalled verbatim as
   `note`).
2. Draft the requirement for the spec delta
   (`openspec/changes/<change-id>/specs/<capability>/spec.md`, `## ADDED
   Requirements`): first line leads with SHALL (only the first line is
   strict-checked), one `#### Scenario:` minimum. Show the draft for
   line-edit or veto — the operator's edit is the decision.
3. Write it with the Edit tool, then `openspec validate --strict --changes
   <change-id>` — must pass before proceeding.
4. Cite it: the id is `<capability>.<slug>`; `apply-cite` will fail closed
   if the heading slugifies differently than expected, which is the check.

### 4. REVERSE triage — remaining requirements (task 4.2b)

Only after every flag is decided. For each `unaccounted` requirement:

1. `$WALK card requirement --subject=<id> --change <change-id>` → show
   verbatim.
2. Append interpretation: which flags the models related to this
   requirement (reverse view of the same annotations), labelled as before.
3. Ask: **Excuse with reason** / **Cite from an existing flag** (loops
   back to `apply-cite --replace` on that flag) / **Defer**.
4. `$WALK apply-exclude-requirement --id <id> --reason "…" --change <change-id>`

**The first excusal creates the exclusions file and flips reverse
enforcement ON (D13).** The script announces this; relay it. If the triage
overruns the operator's appetite, the designed retreat is deleting the
file and deferring reverse opt-in to a follow-up change — never
placeholder reasons, which parse fine and reproduce exactly the
unfalsifiable green this gate exists to eliminate.

### 5. VERIFY — after each batch and at the end

```bash
uv run --project packages/gen-eval python packages/gen-eval/scripts/generate_tool_descriptor.py
uv run --project packages/gen-eval python packages/gen-eval/scripts/generate_tool_descriptor.py --check
uv run --project packages/gen-eval python packages/gen-eval/scripts/check_traceability.py \
  --scope capability --change <change-id> --repo-root .
$WALK status --change <change-id>
```

Each command bare. Report the worklist delta ("34 → 21 unaccounted"). The
gate's own output is the progress bar; the walkthrough never keeps a
parallel count that could drift from it.

### 6. Land

Show the journal (`openspec/changes/<change-id>/traceability-decisions.yaml`)
as the session summary. Committing is the operator's call; suggest staging
contract + exclusions + annotations + journal + any spec-delta edits
together, with explicit `-- <paths>`. Task checkboxes 4.1/4.2/4.2b are
`[human]` — propose flipping them only when the operator confirms the
phase is genuinely complete, and never flip 4.2b while any requirement is
`unaccounted`.

## Failure modes

- **Undo** is `git checkout -- <file>` plus a journal entry noting the
  reversal; the journal is never rewritten.
- A `card` for a flag that already carries a decision is fine (review
  mode); `apply-*` without `--replace` is what fails.
- If `$WALK` cannot import `gen_eval`, the invocation forgot
  `--project packages/gen-eval` — that is the fix, not sys.path surgery.

## Related

- `/validate-feature` — runs the change-scoped gate this skill feeds
  (task 5.6, once wired).
- `parallel-infrastructure/scripts/review_dispatcher.py` — vendor probing
  if `codex` availability needs checking before Step 2.
- `openspec/changes/trace-requirements-to-contracts/human-tasks.md` — the
  work plan this skill executes Track A of.
