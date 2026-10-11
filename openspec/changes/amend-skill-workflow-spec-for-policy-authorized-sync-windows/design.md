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
- `allowed_sources`: the origins that `discover_prs.py` emits.
- `auto_merge_ceiling`: `none` < `automation` < `plan` < `implementation`. The
  last three are the kinds that `classify_kind.py` emits. `MergeCeiling.permits(kind)`
  is a rank comparison, and an unknown kind is never permitted (fail-closed).

The trust posture module defines its own frozen sets. It does not import from
`merge-pull-requests`, so the shared contract stays free of dependencies on any
single skill. A test pins the sets equal to the merge skill's constants, so the
two vocabularies cannot drift apart unnoticed.

### D4: Cadence shape only

`cadence` must be exactly five whitespace-separated fields, each matching
`[0-9*/,-]+`. Named months and days, `@daily` macros and six-field forms are
rejected.

Computing the next fire time is the scheduler's job (`ri-13`), so this module
does not depend on a cron library. Times are interpreted as UTC, and the
template documents that.

### D5: Digest stability

`posture_digest` keeps hashing exactly the current canonical gates map when no
windows are declared. When windows are declared, it hashes:

```
{"gates": <gates map>, "sync_windows": [<canonical window>, ...]}
```

Canonical windows keep their declared order, and list fields are sorted inside
each window. As a result:

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

This is the check that the amended `skill-workflow` scenarios require of any
scheduled caller. No skill calls it yet; `ri-12` wires it in.

### D7: The live posture is untouched

`TRUST_POSTURE.md` effective settings are not edited. Windows are documented
only in `TRUST_POSTURE.template.md`, as a commented-out example, so validating
the template still declares no window.

## Risks

- **A future consumer forgets to call `authorize_sync_window`.**
  - Mitigation: the spec requires the call, and `ri-12`'s acceptance tests
    exercise refusal.
  - This change cannot enforce the call, because no scheduled caller exists yet.
- **The vocabularies drift from the merge skill.**
  - Mitigation: the parity test in D3.
