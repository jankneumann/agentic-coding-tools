# Plan Review Round 1 Dispositions

Real quorum: 4/4 schema-valid reviewers (Antigravity, Claude Code, Codex, Grok). Pi was excluded from quorum because its raw output used the invalid `testability` axis; both the raw output and manifest error are retained.

| Consensus ID | Status | Disposition | Plan response |
|---|---|---|---|
| 1 | disagreement | fixed | D1/D6 and the failure scenario now make route a separate retry-only cleanup step and prohibit apply/dispatch replay. |
| 2 | disagreement | fixed | D2 defines one workspace lock and an already-locked resume helper, preventing nested `flock`. |
| 3 | unconfirmed critical | fixed | D3 and the second-exhaustion scenario key `escalate_resume` reuse by dispatch plus lease generation. |
| 4 | confirmed critical | fixed | Contract/spec now state only `route_parked_escalations` returns resolutions; `apply` is unchanged. |
| 5 | disagreement | fixed | D2 resolves both concurrency and reentrancy concerns with stable ordering and one lock. |
| 6 | confirmed high | fixed | D7 and the end-to-end test clear the old application journal before the next generation applies. |
| 7 | confirmed high | fixed | D8 and tasks define mirror-first rehydrate and the next normal supervisor handoff. |
| 8 | unconfirmed medium | fixed | D9 documents synchronous per-attempt timeout and cumulative batch latency. |
| 9 | unconfirmed medium | fixed | D2 forbids saving the scan snapshot and requires a fresh durable re-read before each resolution. |
| 10 | unconfirmed medium | fixed | Tasks 3.1/3.4 preserve the prose-free gate-name protocol invariant. |
| 11 | unconfirmed medium | fixed | Task 3.4 makes host apply/route sequencing executable rather than documentation-only. |
| 12 | confirmed medium | fixed | D5 requires fixed bounded policy-pause reason text and excludes raw child reason from notification context. |
| 13 | unconfirmed medium | fixed | D1/D5/D6 and the retry scenario define `already_routed` without a second resume. |
| 14 | unconfirmed low | fixed | `contracts/README.md` now assigns the exact output to the route method. |
| 15 | unconfirmed positive | accepted | Transcript-free bounded reporting remains a desired property and is strengthened in D5. |
| 16 | unconfirmed positive | accepted | Structural exclusion of non-policy-pause states remains unchanged in D4. |
| 17 | unconfirmed low | accepted with guard | Canonical install remains required; task 4.6 requires scope verification so only allowlisted supervise mirror changes can land. |
| 18 | unconfirmed low | fixed | Proposal Out of Scope explicitly retains manual reconcile for earlier batches. |
| 19 | confirmed positive | accepted | Existing persistence, exclusion, and mirror schema seams remain the foundation. |
| 20 | unconfirmed FYI | fixed | D9 and task 3.1 explicitly document synchronous notification polling cost. |
| 21 | unconfirmed positive | accepted | The implementation continues composing existing persistence and approval seams. |

No round-1 blocking or disagreement finding was waived. Round 2 must independently confirm the revised plan before implementation.
