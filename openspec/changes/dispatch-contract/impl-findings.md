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

## Remaining (below threshold)

- low: in a dispatched child whose posture digest has drifted, a `notify_with_timeout` gate can still take its posture-derived timeout default. The spec forbids only `auto` here; parking would follow the supervisor-authority intent more closely.
- low: `emit-result` does not cross-check `--dispatch-id`/`--generation` against the launch marker. The supervisor's identity check still rejects a mismatch at `apply`.
- low: rebind accepts a post-go attempt that has no recorded evidence when only a worktree for its branch exists on this host. The evidence conditions hold vacuously.
- open question: once a human has rejected `escalate_resume` itself, gate-check can never re-ask it. Recovery is the `abandoned` edge or an operator edit.
