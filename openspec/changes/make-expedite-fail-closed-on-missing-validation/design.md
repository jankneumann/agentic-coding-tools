# Design: Make expedite fail closed on missing validation

> Change ID: `make-expedite-fail-closed-on-missing-validation`
> Roadmap item: `ri-02` (`verification-enforcement-discipline`)
> Selected approach: **A — strict fail-closed with a recorded override**

## Context

`expedite.py` turns "no validation report" into a `skip` that its roll-up treats
as READY (`expedite.py:101-105`, `:171`). Its own SKILL.md table lists the same
condition as a blocker, and `gate_logic.ALWAYS_REQUIRED_PHASES` already encodes
"a missing report still fails" for the merge-time gate. This change makes
expedite agree with both.

## Decisions

### D1 — A missing report is `fail`, never `skip`

`check_validation_report` returns `fail` when no report is found. The rework
report's `skip` is unchanged (proposal Non-Goals). The `ready` roll-up
(`all(status != "fail")`) is **not** changed: making `skip` blocking globally
would also block the legitimate no-rework-report case. The fix lives at the
check, where the meaning of absence is known.

*Rejected:* treating `skip` as blocking in the roll-up (wrong granularity), and
Approaches B/C from the proposal (self-declared or derived exemptions).

### D2 — Override format follows the `FORCED OVERRIDE —` precedent

`--accept-missing-validation "<reason>"` produces `status="pass"` with
`detail="OVERRIDE — no validation report accepted: <reason>"`, mirroring
`gate_logic.pre_merge_gate`'s `FORCED OVERRIDE —` prefix (`gate_logic.py:767-773`)
so that a grep for `OVERRIDE —` finds both. The verdict gains
`overrides: list[{check, reason}]`, always serialized (empty by default) so
consumers never have to distinguish "absent" from "none".

- The reason is validated in `main()` before any check runs: `reason.strip()`
  empty → `argparse` error → exit 2. Validating in the CLI rather than in
  `expedite()` keeps the library function total and lets tests call it with a
  reason directly.
- The override applies **only** when no report exists. A failing report is not
  maskable by this flag; that is what `--force` at merge time is for, and it
  already records its own `FORCED OVERRIDE`.

### D3 — `change_dir` is derived from the change id

`check_validation_report(report_path, *, change_id, repo_root, accept_missing=None)`.
`change_dir = repo_root / "openspec" / "changes" / change_id` when that directory
exists, else `None` (an absent change directory means no declared metadata
applies; `pre_merge_gate` already treats `change_dir=None` that way). Today `change_dir` is `report_path.parent`, which is wrong
for the `reports/` and `.git-worktrees/` probe locations, so `pre_merge_gate`
silently loses a declared `deployable` flag there.

The function keeps `report_path` as its first positional parameter so the
existing direct-call tests change only by keyword arguments.

### D4 — The drift test lives beside the existing suite

The drift test is `skills/expedite/scripts/tests/test_skill_md_drift.py`, not a
new `skills/tests/expedite/` directory. `skills/expedite/scripts/tests` is already
in `skills/pyproject.toml` `testpaths`; a new directory would need its own
registration and the `ci_coverage` guard, for no gain.

The test derives the code side by **running** each check against fixtures (no
report, failing report, passing report, each rework action) and collecting the
statuses each check can return, rather than parsing `expedite.py` source. It
then parses the SKILL.md `| Check fail | Resolution |` table and asserts:

1. the set of check names in the table equals the set `expedite()` emits
   (both directions, so a check added on either side alone fails the test);
2. a `validation_report` (no file) row exists;
3. `rework_report` is the only check observed to return `skip`;
4. no SKILL.md sentence matching `skip` … `does not block` mentions the
   validation report.

## Risks

- **Friction for docs/skills-only changes.** Accepted at Gate 1; the override
  exists for exactly this and leaves a reason on record.
- **Callers relying on report-less READY.** None in code (`expedite.py` has no
  importers outside its tests); documentation only.
