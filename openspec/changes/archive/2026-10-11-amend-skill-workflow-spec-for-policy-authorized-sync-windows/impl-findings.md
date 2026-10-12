# Implementation Findings

## IMPL_REVIEW (autopilot, multi-vendor `converge()`)

`converge(review_type="implementation", min_quorum=2, fix_mode="targeted", base_ref="origin/main")`
with an IMPL_FIX `fix_callback` bound to the lead implementer (`claude_code`).

**Attempt 1 (quorum lost).** The packet was 136,738 bytes. `codex`, `pi` and
`antigravity` take the prompt as one argv element, and Linux caps a single
argument at 128 KiB (`MAX_ARG_STRLEN`), so all three failed with
`E2BIG: Argument list too long`. `grok` failed because its CLI is too old (HTTP 426).
Only `claude_code` succeeded, so quorum was 1/2. The manifest is kept as
`.review-cache/round-1/impl-attempt1-review-manifest.json`.

**Attempt 2 (converged in round 1).** For this run only, autopilot bookkeeping
files were excluded from the packet diff: `.review-ledger/**`, `loop-state.json`,
`session-log.md`, `plan-findings.md` and `.phase-resolution-cache.json`. The
packet came to 104 KB. Open ledger items still reach reviewers through the
packet's own section. Results:

- `claude_code` and `codex` succeeded, meeting quorum 2/2.
- `antigravity` timed out at 240s.
- `pi` failed with `auth_required`.
- `grok` failed with HTTP 426 again.

Consensus was 11 unique findings: 0 confirmed, 11 unconfirmed, 0 blocking.
`codex` emitted string ids and no `file_path`, so its findings did not anchor.
Two of its findings say the same thing as `claude_code` findings, but the
synthesizer could not match them.

The plan round's `review-manifest.json`, `review-packet.meta.json` and
`fact-check-claude_code.json` share the `round-1/` directory, and this round
overwrote them. They are kept as `plan-*.json` beside the new files.

### Orchestrator adjudication, applied as IMPL_FIX

| Ledger | Source | Criticality | Finding | Disposition |
|--------|--------|-------------|---------|-------------|
| 15, 21 | claude_code#3 + codex#2 | low/medium | The loader split `cadence` on any whitespace, but the schema allows only spaces. A tab-separated or padded cadence loaded but failed the schema. | Fixed. The loader now uses `_CADENCE_PATTERN`, which is character-identical to the schema pattern. The spec, design D4 and template now say "space-separated, no leading or trailing whitespace". New tests: malformed cases for tab and padded cadences, schema rejection cases, and `test_cadence_loader_and_schema_agree`, which checks the pattern is identical and the verdicts match. |
| 14, 22 | claude_code#2 + codex#3 | medium | `TestPrOriginsVocabulary` only asserted `seen ⊆ PR_ORIGINS`. The plain-`jules` fixture used an author that is not in `JULES_AUTHORS`, so it classified as `other`. | Fixed. The fixture author is now `jules[bot]`, and the test asserts `seen == gc.PR_ORIGINS` (exhaustive in both directions). |
| 13 | claude_code#1 | medium | The template still said a scheduled merge "evaluates the `merge` gate", which assumes a gate mapping the spec delegates to ri-12/ri-13. | Fixed. The template now says "every gate that its scheduled caller's change declares applicable". D8 already said this. |
| 20 | codex#1 | medium | The trust-posture spec had a SHALL on the scheduler with no scenario that tests it. | Fixed. The clause is now informative: refusing an unschedulable cadence belongs to ri-13's spec. D4 is aligned. |
| 16 | claude_code#4 | low | The live digest literal has no refresh guidance. | Fixed with a comment on `LIVE_DIGEST`. |
| 17 | claude_code#5 | low | The schema description's em-dash was rewritten as `—`. | Fixed. The literal character is restored, so the schema diff now contains only the `sync_windows` additions. |
| — | attempt-1 claude_code#4 | low | Duplicate-id detection ignored ids of windows that were rejected for other reasons. | Fixed. The id is recorded once it is valid kebab-case. New test: `test_duplicate_of_invalid_window_still_reported`. |
| 1-5 | plan ledger | medium/low | Fixed by PLAN_FIX. This round's review confirmed each as resolved. | Marked addressed. |
| 6, 7, 18, 19, 23 | plan ledger, re-verified | low | Labels the README with the `openapi` sub-type. Makes sources and ceiling mandatory for non-PR skills. | Accepted, no change (low; recorded decisions). |
| 8-12 | plan ledger | low | Stale loop-state gate signals. Task 1.1 wording. D4 shape-only. `@daily` deferred. Single package. | Accepted, no change. |

Post-fix checks:

- `pytest skills/shared/tests skills/tests/merge-pull-requests`: 481 passed.
- The autopilot posture/gate tests: 63 passed.
- `ruff`: clean.
- `openspec validate --strict`: valid.
- `trust_posture.py validate` on the live `TRUST_POSTURE.md`: valid. Its digest is unchanged.

Ledger after the fix: 0 blocking, 0 adjudication items, 10 open (all low).

**Infrastructure follow-ups (not in this change's scope):**

- Argv-prompt vendors break at 128 KiB. They need stdin or file delivery.
- `codex` review output has no `file_path` and uses string ids.
- The `grok` CLI needs to be upgraded.
- `pi` failed with `auth_required`.
- Plan and implementation reviews share `.review-cache/round-N/`.
