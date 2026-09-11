# Design: followup-add-decision-choices-ledger

## Context

The parent change `add-decision-choices-ledger` (archived at
`openspec/changes/archive/2026-09-10-add-decision-choices-ledger/`) shipped the
schema, the evidence collector, the ledger writer/renderer, the audit driver and
the `audit-choices` skill. Its design decisions D1–D8 stand unchanged and are
referenced here by number; this document does not restate them. Two are
load-bearing for this change:

- **D5** — cross-reference-only linkage; the auditor never writes to
  `session-log.md` or `docs/decisions/`. The positioning note in the generated
  decision-index README (task 3.5) is edited at its producer,
  `skills/explore-feature/scripts/decision_index.py::emit_readme`, never in
  the generated file.
- **D6** — non-blocking by construction; `needs-user` verdicts reach humans
  only through existing gates, reusing the open-task surfacing pattern. No new
  gate.

This change is wiring: three SKILL.md hooks, one small read-only reader, two
documentation edits, and the tests that pin them. It changes nothing about the
schema, ledger format, driver, or the skill's read-only posture.

## Goals / Non-Goals

**Goals**

- `iterate-on-implementation` produces (and commits) a ledger for every change
  it converges, without ever failing because of the audit.
- `validate-feature` and `cleanup-feature` show a human the open `needs-user`
  entries at the point they already make a decision, with zero change to what
  that decision means.
- The wiring is pinned by tests so a future SKILL.md rewrite cannot silently
  drop a hook.

**Non-Goals**

- No lifecycle for `needs-user` entries: `cleanup-feature` surfaces them, it
  does not migrate them into the follow-up proposal, mark them addressed, or
  refuse to archive. The ledger is archived with the change directory as-is.
- No change to `run_audit.py`, `collect_evidence.py`, `choices_ledger.py`, or
  the schema. The one code addition (F3) is a reader that opens no file for
  writing.
- No fix for the standalone `range:<base>..<head>` ledger location (see
  Risks); that is a Phase 2 quirk and gets its own follow-up.

## Decisions

- **F1: Hook placement — one named step per skill.**
  - `iterate-on-implementation`: new **Step 11.5 "Audit Choices
    (non-blocking)"** between 11c (vendor-review remediation) and 12 (Present
    Summary). This is "after its converged review step and before its final
    summary" in the requirement; it runs whether or not Step 11 was skipped
    (`VENDOR_REVIEW=false`).
  - `validate-feature`: the human decision point is the **Step 11 Validation
    Report** plus the **After Validation** prompt that presents it. Choices are
    a `Choices:` row in the existing Phase Results block, echoed once more
    under After Validation when any `needs-user` entry is open.
  - `cleanup-feature`: new **Step 5.5 "Surface open `needs-user` choices"**
    after Step 5 (Migrate Open Tasks) and before Step 6 (Archive). This is the
    same place open tasks are surfaced and the last moment before archive
    freezes the ledger. Not Step 2 (PR approval — too early, the ledger may
    not exist yet) and not 2.5a (a hard gate; adding anything there reads as
    a new gate).
  - *Alternative rejected*: hooking validate-feature at Step 7.0 (the drift
    prompt). That prompt only fires on drift; the ledger must surface on every
    run.

- **F2: Step 11.5 commits the ledger pair.** The loop's last commit is Step
  10; an audit after it would leave `choices.json`/`choices.md` untracked, and
  both gates read the ledger from the branch (validate-feature) or the change
  directory that archive moves (cleanup-feature). Step 11.5 therefore runs
  `git add openspec/changes/$CHANGE_ID/choices.json choices.md` and commits
  `chore(choices): audit ledger for <change-id>` **only when the pair changed**
  (a no-diff re-audit — D3 idempotence — commits nothing). The commit itself
  is inside the warn-and-continue guard.
  - *Alternative rejected*: leave the pair uncommitted for the user. Silent
    loss at the first `git stash`/worktree teardown, and the gates never see
    it.
  - *Alternative rejected*: amend the last iteration commit. The repo's
    reconcile rule is "new commit, do NOT amend" (validate-feature 7.0).

- **F3: One shared reader, `skills/audit-choices/scripts/needs_user.py`.**
  CLI: `--change-id`, `--repo-root` (default `.`), `--format text|json`
  (default `text`). Loads `openspec/changes/<change-id>/choices.json`, keeps
  entries with `verdict == "needs-user"`, orders them with
  `choices_ledger.rank_entries` (least-confident first), prints one line per
  entry in text mode (`<stable_id[:12]>  <confidence>  <choice headline>`) or
  the JSON array in json mode. Prints nothing and exits 0 when the ledger is
  absent, unreadable, or has no `needs-user` entries; never raises; opens no
  file for writing (the SKILL.md invariant "nothing else in scripts/ opens a
  file for writing" holds). Both gate hooks call it — ranking and filtering
  live in one place.
  - *Alternative rejected*: inline `python3 -c`/`jq` snippets in two SKILL.md
    files. Two copies of the ranking rule that drift independently, and no
    unit test can pin markdown.
  - *Alternative rejected*: a function in `choices_ledger.py` only. The gates
    are shell steps in SKILL.md; they need a CLI entry point.

- **F4: Choices are a Phase Results row, never a `## Choices` section.**
  `validate-feature/scripts/gate_logic.py` parses `## <heading>` sections with
  a `**Status**` line to compute pass/fail for required phases. A `## Choices`
  section would be one heading away from becoming a gate input. The row form —
  `○ Choices: no ledger` / `✓ Choices: 5 entries, 0 needs-user` /
  `⚠ Choices: 2 needs-user entries (choices.md)` followed by the reader's
  lines — is invisible to that parser, so "approve/reject semantics otherwise
  unchanged" is true by construction rather than by discipline. The `⚠`
  symbol is already defined as "passed with warnings" and never flips Result.

- **F5: Task 3.6's fixture is a synthetic repo seeded from the archive, not
  the archive itself.** `run_audit.py` resolves `change_dir` as
  `openspec/changes/<change-id>/` with no archive lookup, so auditing the
  archived parent id in the real repo would create a phantom active change
  directory (`choices.json` beside no `proposal.md`) and break
  `openspec validate --all`. The e2e test builds a `tmp_path` git repo (the
  `test_readonly_posture.fixture_repo` pattern), copies the archived parent's
  `proposal.md`, `design.md` and `session-log.md` into
  `openspec/changes/<id>/` as data, makes one base and one implementing
  commit, and drives `run_audit.run_audit()` with a canned candidate set
  containing one `sound`, one `unsound` and one `needs-user` entry (one of
  them matching a session-log Decision bullet so `self_reported` resolves both
  ways). "Archived-change fixture" therefore means *archived artifacts as
  fixture data*, which is what the parent's Migration Plan intended.

- **F6: What "fails or is unavailable" means, and what the guard does.**
  - *Unavailable*: `skills/audit-choices/` is not installed in the runtime
    skill directory; the harness exposes no sub-agent dispatch tool
    (`/audit-choices` cannot dispatch its independent auditor); or dispatch
    returns no parseable candidate array.
  - *Fails*: `run_audit.py` exits non-zero (it never should), prints an
    `audit-choices: WARNING` line (driver `ok=False`), or any command in the
    step raises.
  - In every case Step 11.5 emits exactly one line —
    `audit-choices: skipped (<reason>) — continuing to summary` — records the
    reason in the Step 12 summary under a `Choices audit:` line, and proceeds.
    Nothing in Step 11.5 may `exit 1`, `set -e`-abort, or return a failing
    outcome to autopilot.

- **F7: Scenario ordinals are retained and keyed.** Tasks keep the parent's
  `skill-workflow.N` references so the parent's dependency graph reads
  unchanged; `tasks.md` carries a key table resolving each ordinal to a
  scenario title and its location (canonical spec for 1–6, this delta for
  7–11). New scenarios added by this iteration continue the sequence.

## Risks / Trade-offs

- **Ledger text is untrusted.** Entries are LLM output that already passed
  schema validation, but headlines are free text. The reader prints plain
  text; the hooks never interpolate entry text into a shell command, a
  template, or a commit message. Gate-presenting agents treat the lines as
  data.
- **Standalone `range:` form writes to an odd path.** With `change_id =
  "range:<base>..<head>"`, the driver writes under
  `openspec/changes/range:<base>..<head>/`. Scenario 11 asserts only the
  recorded `change_id` and the exit code; the location is out of scope here
  and is recommended as follow-up `fix-audit-choices-range-ledger-path`.
- **Audit cost per convergence.** Step 11.5 adds one sub-agent dispatch to
  every `iterate-on-implementation` run. Accepted: the parent deferred
  multi-vendor consensus for exactly this reason, and the step is skippable by
  the same "unavailable" path if an operator removes the skill.
- **Runtime-copy drift.** Canonical edits in `skills/` reach `.claude/skills/`
  only via `install.sh`; a hook that exists canonically but not at runtime is
  invisible. The checkpoints run `install.sh --check` and the resync.

## Migration Plan

Additive. Rollout order matches task dependencies: reader (3.0), hooks
(3.1–3.3), docs (3.4–3.5), tests (3.6–3.7). Rollback is deleting the three
hook blocks; ledgers already committed remain valid standalone artifacts and
the reader is inert without callers.
