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
    summary" in the requirement. Step 11 opens with "Skip this step if
    `VENDOR_REVIEW=false`", and an `11.5` heading sitting under it reads as
    part of the skipped block — which would disable the audit on exactly the
    runs that skip vendor review. The step's first line therefore states the
    always-run rule outright ("This step is NOT gated by `VENDOR_REVIEW`; it
    runs on every converged iteration, including runs that skipped Step 11"),
    and task 3.7 asserts that wording is present.
  - `validate-feature`: the human decision point is the **Step 11 Validation
    Report** plus the **After Validation** prompt that presents it. Choices are
    a `Choices:` row in the existing Phase Results block, echoed once more
    under After Validation when any `needs-user` entry is open.
  - `cleanup-feature`: new **Step 5.5 "Surface open `needs-user` choices"**
    anchored immediately before the `### 6. Archive OpenSpec Proposal`
    heading. (The skill's Step 5 region carries the label `5c` twice — once
    as `#### 5c. Mark original tasks.md` inside Step 5 and once as
    `### 5c. Pre-Launch Checklist` — plus a `5d` staged-rollout block;
    anchoring on Step 6 is the only unambiguous position.)
    **The Step 5a early exit must be retargeted.** `#### 5a. Detect open
    tasks` ends with "If **all tasks are checked** (`- [x]`), skip to Step
    6" — the common happy path, and it would jump straight over 5.5, so a
    fully-completed change would archive without ever surfacing its open
    `needs-user` entries. That line is retargeted to Step 5.5, which is why
    task 3.3 edits two places in the file and task 3.7 asserts the skip
    target. This is the same region where open tasks are surfaced and the
    last moment before archive freezes the ledger. Not Step 2 (PR approval — too early, the ledger may
    not exist yet) and not 2.5a (a hard gate; adding anything there reads as
    a new gate).
  - *Alternative rejected*: hooking validate-feature at Step 7.0 (the drift
    prompt). That prompt only fires on drift; the ledger must surface on every
    run.

- **F2: Step 11.5 commits the ledger pair, comparing entries and not bytes.**
  The loop's last commit is Step 10; an audit after it would leave
  `choices.json`/`choices.md` untracked, and both gates read the ledger from
  the branch (validate-feature) or the change directory that archive moves
  (cleanup-feature). Step 11.5 therefore stages **both paths under the change
  directory**:

  ```bash
  git add "openspec/changes/$CHANGE_ID/choices.json" \
          "openspec/changes/$CHANGE_ID/choices.md"
  ```

  (An earlier draft wrote `git add openspec/changes/$CHANGE_ID/choices.json
  choices.md`, where the second path resolves against the working directory
  and stages a repo-root `choices.md` that does not exist — committing half
  the pair. The pathspec is spelled out for both files for that reason.)

  **The "commit only when changed" test is on `entries` alone.**
  A byte comparison always differs: `choices_ledger.make_header` stamps a
  fresh `generated_at` and `run_id` every run, `render_markdown` prints
  `generated_at` into `choices.md`, `header.git_sha` moves with every commit,
  and `audited_range.head_sha` moves with it — and D3 idempotence (stable
  `stable_id`s across runs) says nothing about byte-stability. Subtracting
  only the two obviously per-run header fields is not enough; `git_sha` and
  `audited_range` are equally volatile and equally uninteresting.

  The comparison is therefore positive rather than subtractive, and it names
  its two keys by their real location in the document. `build_document`
  produces `{header, change_id, audited_range, entries[, auditor]}`, so the
  six header fields are nested under `header` and are *not* document-root
  keys. Step 11.5 parses both JSON documents and compares exactly two things:
  the `entries` array and `header.schema_version`. `entries` is canonically
  ordered by `rank_entries` at write time, so equal entry sets compare equal;
  `header.schema_version` is included so a schema bump is never silently
  dropped. Every other field is ignored **by name**: `header.generated_at`,
  `header.run_id`, `header.git_sha`, `header.generator`,
  `header.event_kind`, and the root-level `change_id`, `audited_range` and
  `auditor`. Comparing `header` as a whole would always differ; looking for a
  root-level `schema_version` would find nothing.

  When the change has no committed `choices.json` yet, there is nothing to
  compare and the pair always commits — `git show` failing on an unknown path
  is the first-audit case, not an error to warn about. Otherwise, when
  `entries` and `schema_version` are unchanged, Step 11.5 restores the
  committed pair (`git checkout -- <both paths>`) and commits nothing;
  otherwise it commits `chore(choices): audit ledger for <change-id>`. Every
  re-audit of an unchanged diff is a commit-wise no-op, which is what F2
  always intended and what a byte test could not deliver.

  The staging, the comparison and the commit are all inside the
  warn-and-continue guard.
  - *Alternative rejected*: leave the pair uncommitted for the user. Silent
    loss at the first `git stash`/worktree teardown, and the gates never see
    it.
  - *Alternative rejected*: amend the last iteration commit. The repo's
    reconcile rule is "new commit, do NOT amend" (validate-feature 7.0).
  - *Alternative rejected*: commit on every successful audit. One
    content-free commit per `iterate-on-implementation` run, on every change,
    purely to restamp a timestamp.

- **F3: One shared reader, `skills/audit-choices/scripts/needs_user.py`.**
  CLI: `--change-id`, `--repo-root` (default `.`), `--format text|json`
  (default `text`). **The reader does not distinguish "no ledger" from "a
  ledger with nothing open" — it is silent for both, deliberately, so that a
  caller can pipe it without branching.** Scenario `skill-workflow.11`
  requires the *gates* to tell those two cases apart, and they do it
  themselves: each hook tests for `openspec/changes/<id>/choices.json` before
  calling the reader and picks its own wording (`○ Choices: no ledger` vs
  `✓ Choices: 0 needs-user` in validate-feature; `no choices
  ledger` vs `no open choices` in cleanup-feature). Keeping the branch in the
  two callers rather than in the reader costs one `test -f` each and leaves
  the reader's contract — print the open entries, nothing else, exit 0 — as
  narrow as F3 intends. Loads `openspec/changes/<change-id>/choices.json`, keeps
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
  `validate-feature/scripts/gate_logic.py` computes pass/fail by looking up a
  fixed allow-list of phase headings — `ALWAYS_REQUIRED_PHASES`
  (`Spec Compliance`) plus `REQUIRED_PHASES` (`Smoke Tests`, `Security`,
  `E2E Tests`) when the surface is deployable, plus `Architecture` in blocking
  mode — and reading each one's `**Status**` line. An unrecognized
  `## Choices` section is never consulted, so it could not become a gate input
  without also editing those dicts. The row form is not chosen because a
  section would be dangerous today; it is chosen because it leaves no heading
  for a future allow-list edit to pick up by accident, and because choices
  belong inside the presentation the human already reads. The row form —
  `○ Choices: no ledger` / `✓ Choices: 0 needs-user` /
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
  - *Partial pair*: `choices_ledger.write_ledger_pair` writes `choices.json`
    and then renders `choices.md` as a second, separate operation, so an
    interruption between them leaves the JSON on disk with no rendering. The
    step therefore checks that **both** files exist and are non-empty before
    staging anything; if only one is present it treats the run as a failure
    and takes the skip line. Discarding the orphan needs two cases, because
    `git checkout -- <path>` restores a tracked file but silently does
    nothing for an untracked one: a path that `git ls-files --error-unmatch`
    knows is restored with `git checkout --`, and a path it does not know —
    the first-audit case, where no ledger was ever committed — is removed
    with `rm -f`. A single `git checkout --` for both would leave a
    first-run orphan sitting in the worktree while the design claimed it was
    discarded. This is the hook-level guarantee behind the spec's
    "SHALL NOT commit a partial ledger pair"; the driver itself is not made
    atomic, because the proposal forbids driver changes.
  - In every case Step 11.5 emits exactly one line —
    `audit-choices: skipped (<reason>) — continuing to summary` — records the
    reason in the Step 12 summary under a `Choices audit:` line, and proceeds.
    Nothing in Step 11.5 may `exit 1`, `set -e`-abort, or return a failing
    outcome to autopilot.

- **F8: `audit-choices` gains an optional `--run-id` argument.**
  `run_audit.py` has required `--run-id` since Phase 2, but
  `skills/audit-choices/SKILL.md` documents only two argument forms,
  `<change-id>` and `<base-sha>..<head-sha>`. F2 prescribes
  `run_id=iterate-on-implementation-<UTC ISO timestamp>` so a ledger can be
  traced back to the run that produced it, and there is no documented way to
  pass it. The skill's Arguments section gains an optional trailing
  `--run-id <id>` (documentation only — the driver already accepts it), and
  the skill keeps choosing its own id when the caller omits it. Together with
  the F3 reader, this is the whole of what the change touches inside
  `audit-choices`: one new read-only script and one documented argument.
  Neither adds a writer — the read-only posture and its mechanical test are
  untouched.
  - *Alternative rejected*: drop the prescribed `run_id` and let the skill
    pick one. Then no ledger names the workflow step that produced it, and
    the `Choices audit:` summary line cannot cite a correlatable id.

- **F7: Scenario ordinals follow the parent's document order, and the key
  table is the authority.** The carried-forward tasks inherited ordinals that
  did not survive checking: the archived parent's spec delta has **seven**
  scenarios, all seven merged into `openspec/specs/skill-workflow/spec.md`,
  and an earlier draft of the key table listed six of them in an order that
  matched neither document. Ordinals are therefore assigned by the parent
  delta's own document order — `skill-workflow.1` through `.7` canonical,
  `.8` through `.12` for this delta's five scenarios in their document order —
  and `tasks.md` carries the table that resolves each one to a title and a
  location. Renumbering the task references was preferred over patching the
  table in place: an ordinal that resolves to two different scenarios
  depending on which document you open is worse than a diff.

## Risks / Trade-offs

- **Ledger text is untrusted.** Entries are LLM output that already passed
  schema validation, but headlines are free text. The reader prints plain
  text; the hooks never interpolate entry text into a shell command, a
  template, or a commit message. Gate-presenting agents treat the lines as
  data.
- **Standalone `range:` form writes to an odd path.** With `change_id =
  "range:<base>..<head>"`, the driver writes under
  `openspec/changes/range:<base>..<head>/`. Scenario `skill-workflow.12`
  asserts only the recorded `change_id` and the exit code; the location is
  out of scope here
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
