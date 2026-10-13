# Validation Review Findings

## VAL_REVIEW (autopilot, multi-vendor `converge()`)

`converge(review_type="implementation", min_quorum=2, max_rounds=3, fix_mode="targeted", base_ref="origin/main")`.
The VAL_FIX `fix_callback` was `phase_fixer.apply_phase_fixes` bound to the lead
implementer (`claude_code`). A `post_fix_validator` ran the sync-window, posture
and classifier tests plus `openspec validate --strict`. The IMPL_REVIEW
bookkeeping exclusions were reused: `.review-ledger/**`, `loop-state.json`,
`session-log.md`, `plan-findings.md`, `impl-findings.md` and
`.phase-resolution-cache.json`. They were applied in-process, and no
`.review-rules.json` was written.

The IMPL_REVIEW checkpoint was moved to `.review-cache/impl-review-round-1/`
before this run, because both reviews write to `.review-cache/round-1/` with the
same filenames.

**Round 1 dispatch:**

- `claude_code` (fable) succeeded with 5 findings.
- `codex` (gpt-5.6-sol) succeeded with 3 findings.
- `antigravity` timed out at 240s.
- `grok` failed with HTTP 426 because its CLI is outdated.
- `pi` failed with `auth_required`.

Quorum was 2/2. The loop returned `adjudication_required` with no blocking
items. One judgment finding was rated `high` and reported by a single vendor.
VAL_FIX did not run inside the loop because the loop stopped for adjudication
before reaching its fix step.

### Orchestrator adjudication

| Ledger | Source | Criticality | Finding | Disposition |
|--------|--------|-------------|---------|-------------|
| 28 | codex#1 | high → low | The schema's `uniqueItems` does not enforce unique window `id`s. | Downgraded. JSON Schema 2020-12 cannot express uniqueness by a member property. The schema's `sync_windows` description already names the Python loader as the authoritative validator "including unique ids across entries". The spec also puts duplicate-id rejection on the loader, and `test_duplicate_id_rejected` covers it. This is a documented limitation, not a contract violation. |
| 29 | codex#2 | medium → low | Under Python's `jsonschema`, the schema's `$` accepts a trailing newline that the loader rejects. | Downgraded. With JSON Schema's ECMA-262 semantics, `$` means absolute end, so the contract agrees with the loader. Only the Python validator diverges, and `test_cadence_loader_and_schema_agree` already records that. |
| 30 | codex#3 | medium | The validation report claimed the tests cover every spec scenario, but the design and tasks defer the scheduled-invocation scenarios to ri-12/ri-13. | **Fixed (VAL_FIX).** The Spec Compliance section of `validation-report.md` now states the verification boundary from design D6. |
| 24 | claude_code#1 | low | The cadence pattern `( +...)` accepts runs of internal spaces, so equivalent cadences produce different digests. | Accepted, no change. The digest change is fail-closed. Tightening the pattern would also change the schema and is better left to a follow-up. |
| 25, 26 | claude_code#2, #3 | low | Live-digest tripwire coupling. Dead `repr(item)` fallback in `_check_list_field`. | Accepted, no change. |
| 27 | claude_code#4/#5 | low | Re-verified ledger 6/7/18/19/23. | Still low, no change. |

**Evidence re-check:**

- The sync-window, posture, scope and classify tests passed: 166 tests.
- `agent-coordinator` `test_github_classifier.py` passed: 29 tests.
- `openspec validate --strict` reported the change as valid.

**Ledger after adjudication:** 0 blocking items, 0 adjudication items, 16 open items (all low).
