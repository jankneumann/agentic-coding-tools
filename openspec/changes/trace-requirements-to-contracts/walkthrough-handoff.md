# Handoff — start the cite-requirements walkthrough (Track A)

Written 2026-08-08 for a fresh session. Everything a clean context needs to
run the guided traceability walkthrough; nothing here requires the prior
conversation.

## Objective

Execute **Track A** of `human-tasks.md` (same directory) via the
`cite-requirements` skill: tasks 4.1 / 4.2 / 4.2b — cite or exclude each of
the 17 CLI contract flags, then triage the 34 effective requirements. The
operator (Jan) makes every selection; the session scribes, annotates, and
writes files. Read these two files FIRST:

1. `skills/cite-requirements/SKILL.md` — the full protocol, including the
   quote/interpretation contract (load-bearing; do not paraphrase inside the
   verbatim zone).
2. `openspec/changes/trace-requirements-to-contracts/human-tasks.md` — the
   work plan and its warnings.

## Where

- Worktree: `.git-worktrees/trace-requirements-to-contracts/` (work here,
  never the shared checkout)
- Branch: `openspec/trace-requirements-to-contracts`, synced with origin;
  PR **#342** (14/14 CI green as of last check)
- The skill is committed at `skills/cite-requirements/` but NOT yet synced
  to `.claude/skills/` (that happens at cleanup per repo convention) —
  follow its SKILL.md directly from `skills/`.

## Exact starting state (verify, don't trust)

```bash
WALK="uv run --project packages/gen-eval python skills/cite-requirements/scripts/walkthrough.py"
$WALK status --change trace-requirements-to-contracts
```

Expected: `flags 0/17 decided | requirements 0/34 accounted | reverse
switch (exclusions file): absent`. If it differs, a previous session made
decisions — read `traceability-decisions.yaml` (journal) before continuing;
never redo a journalled decision without the operator asking.

Uncommitted files that are NOT yours to touch: `loop-state.json`
(autopilot bookkeeping, phase = IMPLEMENT/complete) and untracked
`openspec/schemas/context-*.json` (a different change's artifacts).

## Session plan

1. **PREPARE** (once): build the annotation prompt (all 17 flag entries
   verbatim + all 34 requirement ids/headings/bodies) and dispatch it to
   two models — `Agent(model="haiku")` and
   `codex exec -m gpt-5.6-luna "<prompt>"`. Merge into
   `openspec/changes/trace-requirements-to-contracts/traceability-annotations.json`,
   then `$WALK annotations-validate <file>`. Annotations are interpretation
   ONLY; a vendor failing is non-fatal — proceed and say so on every card.
2. **Flags, one card at a time** (suggested order: contract order,
   `--print-contract-version` first):
   `$WALK card flag --subject=--print-contract-version --change trace-requirements-to-contracts`
   → append the fenced interpretation section → AskUserQuestion (Cite /
   Exclude flag / New requirement / Defer) → `$WALK apply-cite ...` or
   `$WALK apply-exclude-flag ...` (the `=` form for flag args: `--flag=--mode`).
3. **New requirements** (task 4.1 sub-flow): operator states intent →
   draft SHALL-first requirement into the spec delta → `openspec validate
   --strict --changes trace-requirements-to-contracts` → cite it.
4. **Reverse triage** after all flags are decided:
   `$WALK card requirement --subject=<id> ...` →
   `$WALK apply-exclude-requirement --id <id> --reason "..."`.
5. **Verify after each batch**: regenerate + `--check` the descriptor, run
   the gate, show `$WALK status`. All bare, never piped.

## Hard rules (from D1/D6/D13 — violations defeat the change)

- The operator selects; models and orchestrator only annotate, clearly
  fenced below the script's marker line.
- **One sitting for the forward half**: the FIRST citation opts the whole
  CLI document into forward enforcement (D6) — verified live: the gate
  exits 1 naming all undecided flags until the file is finished. Mid-red is
  normal during the session; do not stop with the branch in that state
  without telling the operator.
- The FIRST `apply-exclude-requirement` CREATES the exclusions file and
  flips reverse enforcement ON (D13). The script announces it; relay it.
  Overrun retreat = delete the file and defer, never placeholder reasons.
- Never flip tasks.md checkboxes 4.1/4.2/4.2b without operator
  confirmation; never flip 4.2b while any requirement is unaccounted.

## Numbers (measured, may have drifted — re-derive from `$WALK status`)

17 flags, 34 requirements (20 archived + 14 from this change's delta),
zero decided. Gate worklist = the `$WALK status` output; the gate's own
output is the progress bar — keep no parallel count.

## After Track A

- Commit contract + exclusions + annotations + journal + spec-delta edits
  together with explicit `-- <paths>` (prior staged work may exist).
- Track B (coordinator contract, tasks 5.1/5.2/5.3) is separate and also
  human — see human-tasks.md.
- When both tracks land: re-invoke `/autopilot trace-requirements-to-contracts`
  to pick up wp-wiring (5.6, 5.7, 5.8, 5.9), then human task 5.7c gates the
  merge. Autopilot state: IMPLEMENT/complete; next phases IMPL_ITERATE →
  IMPL_REVIEW → VALIDATE → VAL_REVIEW (enabled) → SUBMIT_PR.
