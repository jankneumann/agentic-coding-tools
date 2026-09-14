# Round 6 implementation-review dispositions

- Dispatch: all five configured vendor harnesses received the verified repository-local prompt. Claude, Codex, and Grok returned schema-valid reviews, satisfying quorum. Antigravity returned an empty wrapper despite the required JSON mode; Pi emitted protocol NDJSON and a separate schema-invalid reviewer file, preserved byte-for-byte as out-of-band raw evidence.
- Codex 1 (high): fixed. Migration 039 now records projection ownership in work_queue_projection_ownership, a database-owned registry keyed by task UUID. An ordinary issue at the exact tuple fails closed even if its input_data spoofs the former marker; submit and reconcile preserve the row and projection head.
- Codex 2 / Claude 3: fixed by restoring the non-empty round-5 disposition ledger.
- Claude 1: fixed. Same-generation replay resets only cancelled/completed/failed canonical rows; claimed or running rows keep lifecycle state while their exact owned labels are repaired.
- Claude 2: fixed. projection_key_collision is classified as HTTP 409 and covered by a focused mapper regression.
- Claude 4-5: accepted as bounded operational notes; retry history preserves generation correctness, and static review limitations do not weaken the recorded executable validation.
- Claude 6-20, Codex 3-7, and Grok findings: accepted as positive verification or non-blocking advisory observations. No further behavioral gap was identified in those findings.
- Verification: focused live Postgres tests cover spoofed ownership, submit/reconcile collision atomicity, active-state preservation, and terminal reactivation; the mapper regression covers the 409 contract. Full validation and a post-fix review follow on the final source commit.
