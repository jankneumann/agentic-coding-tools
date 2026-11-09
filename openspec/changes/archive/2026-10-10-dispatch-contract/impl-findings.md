# Implementation Findings: dispatch-contract

IMPL_ITERATE, threshold `medium`. Review was single-vendor (`claude_code`), under the
cloud-container quorum policy (`single_vendor_review`).

## Iteration 1

| # | Type | Criticality | Description | Fix | Commit |
|---|------|-------------|-------------|-----|--------|
| 1 | security | high | `_resolve_capability_park` re-evaluated the posture whenever a fingerprint's member listing differed from a human rejection's record, so a posture flip to `auto` could clear an operator's rejection | Reuse a human-provenance blocked subject without consulting the posture; the entry lists the current members | 9c52005 |
| 2 | bug | high | Child `gate-check` treated a human rejection as final forever. After the operator resumed the run, the gate could never be asked again, and a caller outside `ESCALATE` got exit 4 with the loop left where it was | The rejection stays in force until a later human `escalate_resume` proceed (a posture-derived resume does not end it). While it is in force, `gate-check` enters `ESCALATE` | 6892017 |
| 3 | security | high | `redact_command` kept short credentials that the sanitizer passes: URL userinfo, `curl -u user:pw`, `--password x`, `--token=x`, `*_secret_access_key x` | Added URL-userinfo, user-flag and keyed-secret redaction before `sanitize()` | af0817f |
| 4 | bug | medium | Cross-host reinitialize took over a pre-go claim whose lease had not expired, bumping the generation while a live child on the other host still held it | Reinitialize a claimed attempt only after its lease has expired, the same rule `child_start`/`reissue` use | a3330ff |
| 5 | bug | medium | `apply` did not re-derive the result from loop state. A composed v2 result could complete an item whose goal gate was abandoned or refused, or park on the wrong gate or missing-lane set | `apply` re-derives native v2 results through `result_from_loop_state` and refuses any outcome, handoff, kind, gate or fingerprint mismatch (v1 is still tolerated) | 8b76939 |
| 6 | edge-case | medium | The closure enumeration read any kind/gate node that is not a const or enum as `null` alone, so loosening a gate would still pass the closure test | Non-enumerable nodes raise `DispatchContractError` naming the branch | 609aff1 |

Supervisor-requested follow-ups (tasks 7.6, 7.7): `converge(base_ref=)` pass-through
(9cdc27d), and converge's own `.review-ledger/` and `.review-cache/` writes left out of the
post-fix scope check (9805527).

## Iteration 2

| # | Type | Criticality | Description | Fix | Commit |
|---|------|-------------|-------------|-----|--------|
| 7 | bug | medium | Regression from fix 1: after the operator approved a rejected fingerprint, the stale rejection was still the latest blocked subject, so a new park on that fingerprint stayed blocked. Members that joined after the rejection were also not resumed by the approval | A subject answered by a later proceed is no longer the prior record. `answer_escalation` resumes current fingerprint members that the subject's listing predates | 4cc15ae |

## IMPL_REVIEW (converge, targeted fixes)

`converge()` ran with `review_type=implementation`, `fix_mode=targeted`, `min_quorum=1`
from `resolve_quorum_policy` (policy `cloud-container-single-vendor-2026-10-09`), and
`base_ref=origin/openspec/roadmap-multiplayer-collaboration`. Review was single-vendor
(`claude_code`), degradation `single_vendor_review`. Blocking trend per round: `[5, 0]`.
Converged in round 2.

| Ledger | Type | Criticality | Description | Fix | Commit |
|---|---|---|---|---|---|
| 16, 17 | security | medium | A dispatched child's `gate-answer` checked only `--approval-ref` against the marker, so a matching reference could record an approval the supervisor had rejected, or answer another gate | `--gate` and `--decision` must also equal the marker's `gate_answer` (exit 2, nothing recorded), with tests | 5b28e32 |
| 18, 19 | security | medium | `apply_delegated_batch` persisted a `permission_blocked` result's `parked.command` verbatim into the tracked checkpoint (attempt and journal); only the router's record was re-sanitized | The command is passed through `redact_command` right after validation, before binding, journaling and persistence, with an apply-level test | b34c6af |
| 20 | correctness | low | Auth-header redaction was not idempotent (a second pass rewrote an already-redacted header) | The lookahead skips leading whitespace | bad6de9 |

Advisory (low) added in IMPL_REVIEW: `_resolve_capability_park`'s proceed path indexes
`records[0]` when the attempt is not among its fingerprint's parked members, which
raises `IndexError` instead of a `GateRefusalError`.

## Remaining (below threshold)

- low: in a dispatched child whose posture digest has drifted, a `notify_with_timeout` gate can still take its posture-derived timeout default. The spec forbids only `auto` here; parking would follow the supervisor-authority intent more closely.
- low: `emit-result` does not cross-check `--dispatch-id`/`--generation` against the launch marker. The supervisor's identity check still rejects a mismatch at `apply`.
- low: rebind accepts a post-go attempt that has no recorded evidence when only a worktree for its branch exists on this host. The evidence conditions hold vacuously.
- open question: once a human has rejected `escalate_resume` itself, gate-check can never re-ask it. Recovery is the `abandoned` edge or an operator edit.

## VAL_REVIEW (converge, targeted fixes)

`converge()` ran with `review_type=implementation`, `fix_mode=targeted`, `min_quorum=1`
from `resolve_quorum_policy` (policy `cloud-container-single-vendor-2026-10-09`), and
`base_ref=origin/openspec/roadmap-multiplayer-collaboration`. Review was single-vendor
(`claude_code`), degradation `single_vendor_review`. Blocking trend per round: `[5, 0]`.
Converged in round 2. The critique checked whether `validation-report.md` proves each ri-21 outcome.

| Ledger | Type | Criticality | Description | Fix | Commit |
|---|---|---|---|---|---|
| 25 | spec_gap | medium | Outcome 6 claimed CI gitleaks as the real-binary check, but `security.yml` runs only for `main`, so this change's PR (base: roadmap branch) never triggers it; the local check ports one default rule | Report states the one-rule proxy and that the first real scan is PR #662's Security job | a179b24 |
| 26 | spec_gap | medium | Outcome 4: no test cleared a posture-derived capability-fingerprint block after a posture flip without a human answer | `test_a_posture_derived_capability_block_clears_after_a_posture_flip` | 843ad77 |
| 27 | spec_gap | medium | Outcome 7: hosts A and B shared one repo root, so a leaked absolute path could not be detected | `test_a_checkpoint_checked_out_at_another_root_rebinds_without_host_a_paths` | df3b98e |
| 28 | spec_gap | medium | Outcome 5 "end to end" was proven only piecewise | `test_profile_and_degradations_travel_the_whole_chain` | 843ad77 |
| 29 | spec_gap | low | Report citations omitted the fingerprint, dispatched-child, apply-time refusal and wrong-token tests | Citations and counts corrected | a179b24 |

## PR #667 review

- P1 provenance: `answer_escalation` resumed fingerprint members that parked after the subject was recorded; an approval now resumes only the durable subject's `dispatch_ids`, and a member joining a human rejection extends the subject durably and re-projects it before it can be answered (765f9d8).
- P1 cloud workers: `harness_provided` isolation at the repo root became `worktree_ref: null`, so `child_start` could not resolve it; the repo root now round-trips as `.` (b35e544).
- P2 single-flight: capability/permission park resolution and `answer_escalation` now run under the subject lock keyed by workspace + dedupe fingerprint; a resolver whose attempt a concurrent winner resumed reports that proceed (this also closes the IMPL_REVIEW `records[0]` advisory) (43a9b11).
