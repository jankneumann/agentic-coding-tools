# wp-coordinator review disposition

Review target: `424cd958`; integrated tip: `5cbe43df`. Antigravity, Claude Code, and Grok produced schema-valid findings (3/4); Pi did not. The independent final audit passed, and 236 focused package tests passed.

| Consensus IDs | Disposition on integrated tip |
| --- | --- |
| 1 | Fixed: missing or malformed internal KV-v2 document raises a sanitized error; mixed-type entries remain warning-and-filter per CFG-21. |
| 2 | Fixed: grace expiry emits one schema-valid `openbao.identity.snapshot_expired` event. |
| 3 | Fixed: missing/malformed/duplicate candidate errors log only affected canonical principal IDs and a typed code, while emitting one sanitized failure event. |
| 11 | Fixed: Langfuse attribution uses the same installed Bao snapshot and API header precedence/stripping as coordinator authorization. |
| Claude Code 3 (unmatched) | Fixed: keys with surrounding whitespace are rejected before snapshot install. |
| 5–9, 15 | Positive findings; no change requested. |
| 4 | Accepted: unexpected non-adapter loader errors map to `CONFIGURATION_INVALID` without exposing exception details. Source-specific diagnostics are a follow-up observability improvement. |
| 10 | Deferred to the live integration matrix: denial/error taxonomy is preserved by the adapter; live permission denial still needs an executable assertion. |
| 12 | Accepted rollout constraint: `BAO_ADDR` enables both internal loader and identity reader, so deployment must provide both internal AppRole inputs and identity-reader bootstrap before enabling it. Integration docs cover this. |
| 13 | Accepted follow-up: interprocess bootstrap lock acquisition is unbounded. A bounded lock wait should be designed separately without weakening single-use unwrap serialization. |
| 14 | Reviewer environment limitation: vendor sandbox could not run tests; the worker and orchestrator passed the focused suite, and the wider suite's 32 Cedar failures reproduce on the parent baseline. |

No `context_impact` block is declared for this package; its context-impact status is **unmigrated**.
