# Design: Policy-Authorized Sync Windows

## Context

`skill-workflow` requires every sync point that touches main to be explicitly
user-invoked. Roadmap items `ri-12` (headless merge) and `ri-13` (quiet-window
drain) need a scheduled sync point. The roadmap requires that every unattended
behaviour read its authorization from the trust posture contract (`ri-04`,
`skills/shared/trust_posture.py`). This change records that authorization
surface and amends the spec. It runs nothing on a schedule.

## Decisions

### D1: Windows live in the trust posture front matter, not in a separate file

`sync_windows` is an optional top-level key beside `gates`.

- One contract file and one loader.
- One digest that the supervisor already pins in launch markers.
- Rejected: a separate `SYNC_WINDOWS.md` (Approach 3). It would split governance
  and need a second digest.

### D2: Fail closed, as gates do

If `sync_windows` is absent, `null` or `[]`, the posture declares no windows,
and `authorize_sync_window` fails for every id and skill. This mirrors the
absent-file → all-`block` invariant for gates.

A present but malformed window is a validation error. It is never silently
dropped, because a dropped window would look declared to an operator who reads
the file.

### D3: Closed vocabularies reuse the merge skill's existing classifications

- `skills`: `merge-pull-requests`, `update-specs`, `cleanup-feature`. These are
  the three sync points that the amended requirement names.
- `allowed_sources`: the detailed origins that
  `skills/shared/github_classifier.classify_pr` emits (`discover_prs.py` only
  passes them through). That module has no exported set today, so this change
  adds `PR_ORIGINS` there, plus a test in
  `skills/tests/merge-pull-requests/test_classify.py` that every origin
  `classify_pr` returns is in `PR_ORIGINS` and that `to_pr_card_origin` folds
  every member. The detailed origins are chosen over the folded PR-card origins
  so a window can admit `sentinel` without admitting every Jules PR.
- `auto_merge_ceiling`: `none` < `automation` < `plan` < `implementation`. The
  last three are the kinds that `classify_kind.py` emits. `MergeCeiling.permits(kind)`
  is a rank comparison, and an unknown kind is never permitted (fail-closed).

The trust posture module defines its own frozen sets. It does not import from
`merge-pull-requests` or `github_classifier`, so the posture contract stays a
leaf module with no dependency on any skill. Parity tests pin
`SYNC_SOURCES == github_classifier.PR_ORIGINS` and the ranked kinds equal to
`set(classify_kind.KIND_TO_SKILL)`, and a schema test pins the JSON schema enums
equal to the same Python sets, so the three copies cannot drift apart
unnoticed.

### D4: Cadence shape only

`cadence` must be exactly five fields separated by ASCII spaces (no tabs, no
leading or trailing whitespace), each matching `[0-9*/,-]+`. The loader and the
JSON schema use the same pattern, so the two validators accept the same strings.
Named months and days, `@daily` macros and six-field forms are rejected. This is deliberately a cron-*shaped* string, not a full cron grammar:
`99 * * * *` or `*/0 * * * *` pass the loader; refusing a cadence it cannot
schedule is the scheduler's obligation, specified by `ri-13`, not by this change.

Computing the next fire time is the scheduler's job (`ri-13`), so this module
does not depend on a cron library. Times are interpreted as UTC, and the
template documents that.

### D5: Digest stability

`posture_digest` keeps hashing exactly the current canonical gates map when no
windows are declared. When windows are declared, it hashes:

```
{"gates": <gates map>, "sync_windows": [<canonical window>, ...]}
```

Canonical windows are sorted by `id`, and list fields are sorted inside each
window. This matches the existing invariant that front-matter key order does
not change the digest: windows have unique ids, so declaration order carries no
meaning. As a result:

- The digest of this repository's live posture, which declares no windows, is
  byte-identical to today's. Existing launch markers and recorded gate
  decisions are not invalidated.
- Any declared change to a window does change the digest. A widened window
  therefore forces the posture-derived decisions that depend on it to be
  re-evaluated.

### D6: `authorize_sync_window(posture, window_id, skill)` is the single entry check

- Returns the `SyncWindow` when the window is declared and lists the skill.
- Otherwise raises `SyncWindowNotAuthorized`, whose message names either the
  missing window or the missing skill.
- An unknown skill name raises `ValueError`, because the skill set is closed.
- It accepts the absent-posture value that `load_posture` returns when no
  contract file exists (`present=False`, no windows), and also `None`, as
  `posture_digest` does, and fails for both.

This is the check that the amended `skill-workflow` scenarios require of any
scheduled caller, **before any other work** (discovery, remediation, branch
writes), not merely before touching main. No skill calls it yet; `ri-12` wires
it in. The check does not consult `cadence`: observing the cadence is the
trigger's obligation (the scheduler, `ri-13`), which the spec states and
`ri-13` tests.

**Verification boundary.** No scheduled caller exists in this change, so the
`skill-workflow` scheduled-invocation scenarios cannot be exercised end to end
here. This change verifies the part it owns: the authorization check and the
ceiling ordering, through unit tests. The scenarios are the acceptance contract
that `ri-12` (headless merge) and `ri-13` (drain) MUST test at their call sites.
How a scheduled invocation names its window (for example a `--sync-window <id>`
argument) is `ri-12`'s choice; the spec constrains only that a non-user trigger
must name one and the skill must check it.

### D7: The live posture is untouched

`TRUST_POSTURE.md` effective settings are not edited. Windows are documented
only in `TRUST_POSTURE.template.md`, as a commented-out example, so validating
the template still declares no window.

### D8: A window is necessary, never sufficient

A sync window authorizes starting a sync-point skill without a user. It does
not change any gate disposition. A scheduled `/merge-pull-requests` run still
evaluates every gate that applies to the action it is about to take, and a
`block` stops it.

- Rejected: treating a window as an implicit `auto` for the `merge` gate. One
  posture edit would then widen two independent controls at once, and an
  operator reading `gates.merge: block` would be misled.
- `authorize_sync_window` therefore returns the window and nothing else; it
  does not consult or return gate dispositions.

## Risks

- **A future consumer forgets to call `authorize_sync_window`.**
  - Mitigation: the spec requires the call, and `ri-12`'s acceptance tests
    exercise refusal.
  - This change cannot enforce the call, because no scheduled caller exists yet.
- **The vocabularies drift from the merge skill.**
  - Mitigation: the parity tests in D3.
- **Declaring a window re-evaluates digest-pinned decisions.** Because the
  digest covers windows (D5), declaring or editing one is, to the supervisor,
  a posture change like any gate edit:
  - recorded `posture_block` decisions are re-evaluated
    (`skills/supervise/scripts/gate_router.py`);
  - in-flight children whose worktree posture predates the edit no longer match
    the supervisor's launch-marker digest, so they take no `auto` disposition
    until rebased (`skills/supervise/scripts/execution.py`, D5 of the dispatch
    contract).
  - Accepted: this is the fail-closed direction. The alternative, a separate
    window digest, would let a widened window go unnoticed by every existing
    digest check. Operators should declare windows while no supervised run is
    in flight; the template says so.
- **`show` output grows.** `python -m shared.trust_posture show` gains a
  `sync_windows:` section. It is printed after the gates, so existing readers
  of the gate lines are unaffected; a test pins the format.
