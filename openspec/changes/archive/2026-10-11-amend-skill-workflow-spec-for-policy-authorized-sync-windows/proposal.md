# Proposal: Policy-Authorized Sync Windows

Change ID: `amend-skill-workflow-spec-for-policy-authorized-sync-windows`
Roadmap: `roadmap-always-on-agent-automation`, item `ri-11` (depends on `ri-04`, the trust posture contract)

## Why

The `skill-workflow` requirement "Main Receives Work Through PR Sync Points"
says that any sync-point skill touching main (`/merge-pull-requests`,
`/update-specs`, the main-touching part of `/cleanup-feature`) **MUST be
explicitly user-invoked**. That rule is correct for an interactive repository.
It also rules out the always-on roadmap's later items:

- `ri-12` adds a headless mode to `/merge-pull-requests`.
- `ri-13` adds a quiet-window drain protocol.

Both need a scheduled sync point that runs with no prompt, and no spec text
permits one.

This change relaxes the rule on purpose, and only as far as the trust posture
allows:

- A sync-point skill MAY run on a schedule only under a **sync window** that the
  repository's trust posture (`TRUST_POSTURE.md`) explicitly declares.
- The window declares its cadence, the sync-point skills it covers, the PR
  sources it may act on, and the highest kind of PR it may merge unattended
  (its auto-merge ceiling).
- Without such a declaration nothing changes: user invocation stays the only
  path.
- The clean-tree check, the active-agent guard and the validation gates stay
  exactly as they are.

## What Changes

1. **Spec amendment (`skill-workflow`).** MODIFY "Main Receives Work Through PR
   Sync Points":
   - User invocation stays the documented default.
   - A scheduled invocation is permitted only when it names a sync window that
     the trust posture declares and that window lists the skill.
   - New scenarios state that the active-agent guard, the clean-tree check and
     the validation gates are unchanged.
   - A scheduled run MUST NOT use the force escape hatch.
   - A scheduled run acts only on PRs from the window's allowed sources and
     never merges a PR above the window's auto-merge ceiling.
   - A scheduled trigger must name a window and observe its cadence, and the
     skill must pass the authorization check before any other work.
   - A window is necessary but not sufficient: it never changes a trust
     posture gate disposition. Which gates apply to a scheduled action is
     defined by the change that adds the scheduled caller (`ri-12`, `ri-13`).
   - Also MODIFY "Merge Conductor Invokes Iterate Skills", whose sentence "The
     merge skill remains the user-invoked sync-point" would otherwise contradict
     the amended requirement.
2. **Spec addition (`trust-posture`).** ADD "Sync Window Declarations":
   - The posture front matter gains an optional `sync_windows` list. Each entry
     has `id`, `cadence`, `skills`, `allowed_sources` and `auto_merge_ceiling`.
   - The list is closed-set validated and fails closed: if it is absent or
     empty, no window exists.
   - The posture digest covers the declared windows. A posture that declares
     none hashes exactly as it does today.
3. **Posture contract code.** Extend `skills/shared/trust_posture.py`:
   - parse and validate `sync_windows`
   - add a `SyncWindow` value type and a `MergeCeiling` ordering
   - add an `authorize_sync_window(posture, window_id, skill)` check that later
     scheduled callers (`ri-12`, `ri-13`) must pass before they run
   - mirror the shape in `openspec/schemas/trust-posture.schema.json`
4. **Origin vocabulary export.** Add an exported `PR_ORIGINS` frozenset to
   `skills/shared/github_classifier.py`, the module that actually emits PR
   origins. Today the set exists only as scattered string literals, so nothing
   could pin the window vocabulary against it.
5. **Template documentation.** Document the `sync_windows` block, commented
   out, in `TRUST_POSTURE.template.md`.
6. **Tests** in `skills/shared/tests/` for the parser, the validator, the
   digest stability, the authorization check, the schema mirror, and the
   vocabulary parity with `github_classifier` and `classify_kind`.

### Out of scope

- Any scheduler, cron job, or headless merge execution (`ri-12` and `ri-13`).
- Any change to the effective settings of this repository's live
  `TRUST_POSTURE.md`. No window is declared here, so this repository's
  behaviour, and its posture digest, are unchanged.
- Any change to the `merge` gate disposition. That gate still governs
  autopilot's SUBMIT_PR → DONE edge.

## Approaches Considered

### Approach 1: Spec-only amendment

- **What it is:** Amend the requirement text and describe the posture fields in
  prose. Leave the schema and loader for `ri-12`.
- **Pros:** smallest diff. No code.
- **Cons:**
  - "Requires an explicit posture declaration" cannot be checked, because
    nothing parses the declaration.
  - `ri-12` would have to invent the field names and validation under time
    pressure.
  - Today the loader silently ignores unknown top-level keys, so a mis-typed
    window would look declared.
- **Effort:** XS

### Approach 2: Spec amendment plus posture-contract extension (Recommended)

- **What it is:** Amend the spec and add a validated `sync_windows` section to
  the trust posture contract (loader, schema, template, tests), along with a
  pure `authorize_sync_window` check.
- **Pros:**
  - The acceptance outcome becomes machine-checkable.
  - Field names are fixed once, in the `ri-04` contract that later items
    already read.
  - Fails closed, and the digest of every existing posture is unchanged.
- **Cons:**
  - Touches shared governance code.
  - Adds a small amount of contract surface before any consumer uses it.
- **Effort:** S

### Approach 3: Separate `SYNC_WINDOWS.md` contract

- **What it is:** Declare windows in their own file, with their own loader.
- **Pros:** Keeps the gate contract narrow.
- **Cons:**
  - Contradicts the roadmap's decision that every unattended behaviour reads its
    authorization from the trust posture.
  - Creates two digests that the supervisor would have to pin.
  - Splits governance across two files.
- **Effort:** M

### Selected Approach

**Approach 2.** The recorded roadmap approval for `ri-11` authorized this
direction (`gate-decision:2d683b7a-2f39-4b59-96d9-3abdf22f8a8f`), and the
`proposal_approval` gate is `auto` under that scope. Approach 1 fails
acceptance outcome 2 in practice, because no artifact enforces the
declaration. Approach 3 contradicts the roadmap's single-contract rationale.

## Assumptions (no interactive discovery: supervised child run)

- **A1.** Window cadence is a five-field cron expression in UTC. Interpreting it
  (next-fire computation) is left to the scheduler (`ri-13`). This change
  validates only the expression's shape.
- **A2.** `allowed_sources` uses the existing PR origin vocabulary that
  `skills/shared/github_classifier.classify_pr` emits (and that
  `discover_prs.py` passes through): `openspec`, `sentinel`, `bolt`, `palette`,
  `jules`, `codex`, `dependabot`, `renovate`, `other`. The detailed origins are
  used, not the folded PR-card origins, so a window can admit `sentinel`
  without admitting every Jules PR.
- **A3.** `auto_merge_ceiling` uses the PR kinds of
  `skills/merge-pull-requests/scripts/classify_kind.py` (`automation` < `plan` <
  `implementation`), plus `none`. A window with ceiling `none` may triage and
  notify but never merges unattended.
- **A4.** A scheduled run MUST NOT use the active-agent guard's force escape
  hatch. Only a human may force.
- **A5.** A sync window authorizes *starting* a sync point unattended; it does
  not authorize any gated action. Gate dispositions (notably `merge`) still
  apply. This is the fail-closed reading; the opposite reading (a window
  implies `auto` for the actions it covers) would let one window silently widen
  a gate, and is rejected.
- **A6.** Declared windows are covered by the single posture digest. Declaring
  or editing a window therefore re-evaluates digest-pinned decisions exactly as
  any gate edit does today (see design Risks).

## Impact

- Specs: `skill-workflow` (two MODIFIED requirements: "Main Receives Work
  Through PR Sync Points" and "Merge Conductor Invokes Iterate Skills"),
  `trust-posture` (one ADDED requirement)
- Code: `skills/shared/trust_posture.py`,
  `skills/shared/github_classifier.py` (exported `PR_ORIGINS` only; no behaviour
  change), `openspec/schemas/trust-posture.schema.json`
- Docs: `TRUST_POSTURE.template.md`
- Tests: `skills/shared/tests/test_trust_posture_sync_windows.py`,
  `skills/tests/merge-pull-requests/test_classify.py` (origin-set coverage)
- Runtime behaviour of this repository: unchanged. No window is declared, and
  the posture digest is unchanged.
