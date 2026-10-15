# Make expedite fail closed on missing validation

> Parent roadmap: `verification-enforcement-discipline` (item `ri-02`)
> Change ID: `make-expedite-fail-closed-on-missing-validation`
> Effort: S
> Priority: 1

## Why

`/expedite` is the pre-merge readiness check: READY means it is safe to run
`/cleanup-feature` or `/merge-pull-requests`. Today a change with **no**
`validation-report.md` is READY:

- `skills/expedite/scripts/expedite.py:101-105` — `check_validation_report(None)`
  returns `status="skip"`.
- `expedite.py:171` — `ready = all(c.status != "fail" ...)`, so a skip rolls up
  to READY.
- `skills/expedite/SKILL.md:59-65` lists "`validation_report` (no file) → Run
  `/validate-feature` first." as a **blocker**, and line 67 then says a `skip`
  "does not block". The table and the code disagree, and nothing tests either.

This is the clearest instance in the repo of *absence treated as a pass*: the
one check whose job is "was this verified?" answers yes when nobody looked.

`gate_logic` already has the opposite invariant. `ALWAYS_REQUIRED_PHASES`
(`skills/validate-feature/scripts/gate_logic.py:57-61`) requires "Spec
Compliance" for every change, deployable or not, with the comment "A missing
validation-report.md still fails". expedite bypasses that rule by never calling
`pre_merge_gate` when the report is missing.

## What Changes

- A missing validation report makes `check_validation_report` return `fail`.
  The `detail` names the probed paths, and the `action` is "run /validate-feature".
- **expedite gets a recorded operator override,** `--accept-missing-validation "<reason>"`:
  - The check returns `pass`, and its detail starts with
    `OVERRIDE — no validation report accepted: <reason>`. This follows the
    `FORCED OVERRIDE —` precedent in `gate_logic.pre_merge_gate:767-773`.
  - The JSON verdict gains an `overrides` list naming each overridden check and
    its reason.
  - An empty or whitespace-only reason is rejected with exit 2.
- `check_validation_report` takes `change_id` and `repo_root`, so the change
  directory comes from `openspec/changes/<id>` rather than from the report's
  parent directory. Today, when the report sits under `reports/` or in a
  worktree, the change dir is silently lost and the gate cannot read a declared
  `deployable` flag.
- **SKILL.md updates:**
  - The status table and the `skip` sentence are corrected: `skip` remains only
    for the rework report.
  - The new flag is documented.
- A drift test asserts that the SKILL.md table and the code's check→status
  mapping agree. It fails if either side changes alone.
- Runtime mirrors under `.claude/skills/expedite` and `.agents/skills/expedite`
  are re-synced.

## Approaches Considered

### Selected Approach

**Approach A: strict fail-closed with a recorded override**, selected at
Gate 1 without modification.

- A missing report always blocks.
- READY without a report is reachable only through
  `--accept-missing-validation "<reason>"`. The override is printed in text
  output and recorded under `overrides` in JSON.
- This matches `gate_logic`'s `ALWAYS_REQUIRED_PHASES` invariant, so there is
  one rule rather than two.
- It adds no declaration surface that the change's own author could use to
  exempt themselves.
- The diff stays confined to `skills/expedite/`.
- **Accepted cost:** docs-only and skills-only changes must either run
  `/validate-feature` or pass the override with a reason.

### Rejected alternatives

- **B: declared `validation_exempt: <reason>`** in proposal frontmatter or
  work-packages. Rejected because it is self-certification: the author of the
  change writes its exemption. It would also widen the shared `gate_logic`
  module for one consumer.
- **C: derive the exemption from the deployable surface.** Rejected because it
  reopens absence-as-pass for every skills/docs change. It also depends on a
  `git diff main...HEAD` that is empty when run from main, and it contradicts
  `ALWAYS_REQUIRED_PHASES`.

## Correction to the roadmap item

The roadmap outcome reads: "READY remains reachable for a change that
gate_logic declares validation-exempt." **`gate_logic` has no
validation-exempt rule.** The non-deployable classification drops only the
Smoke, Security and E2E phases, and Spec Compliance is always required.

Under the selected approach the outcome becomes: *READY remains reachable
without a report only through the recorded operator override, and a change
with a passing report is READY regardless of its deployable surface.*

## Impact

- **Code:**
  - `skills/expedite/scripts/expedite.py`
  - `skills/expedite/SKILL.md`
  - `skills/expedite/scripts/tests/test_expedite.py`
  - a new drift test, `skills/expedite/scripts/tests/test_skill_md_drift.py`,
    placed in the directory `skills/pyproject.toml` already collects
  - mirrors under `.claude/skills/expedite/` and `.agents/skills/expedite/`
- **Behaviour:**
  - Any caller that relied on a report-less READY now gets BLOCKED (exit 1).
    There are no code consumers of `expedite.py`; it is referenced only in docs.
  - Existing tests that flip:
    - `TestValidationReportCheck.test_skip_when_path_none` (:142)
    - `TestExpedite.test_ready_when_skips_only` (:247)
- **Docs:** `docs/mental-models.md:252-267` describes expedite. Its "28 tests"
  count is updated if it becomes wrong.

## Non-Goals

- Changing `gate_logic.pre_merge_gate` or the deployable classification.
- Gating a missing report in `merge_pr.py` (`_check_pre_merge_gate` runs only
  when `--validation-report` is given). That is merge-path work owned by ri-01
  and ri-03.
- Making the rework-report `skip` blocking. The SKILL already says that some
  changes legitimately have no rework report.

## Acceptance Outcomes

- `expedite <id>` exits 1 (BLOCKED) when no validation report exists at any
  probed path, and the `validation_report` check reports `fail`.
- `expedite <id> --accept-missing-validation "<reason>"` exits 0. Its text
  output contains `OVERRIDE`, and its JSON carries the reason under `overrides`.
- `--accept-missing-validation ""` exits 2.
- A test parses the SKILL.md status table and fails if the table and
  `expedite.py`'s check→status mapping disagree.
