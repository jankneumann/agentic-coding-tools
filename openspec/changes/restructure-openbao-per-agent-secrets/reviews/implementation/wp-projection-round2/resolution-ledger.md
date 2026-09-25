# wp-projection review disposition

Review target: earlier projection tip `efd85f99`; final integrated tip: `31fbdb0c`.
Quorum: Antigravity, Claude Code, and Grok produced schema-valid findings (3/4); Pi output was invalid. Independent final audit passed at `31fbdb0c`.

| Consensus ID | Disposition on final tip | Evidence |
| --- | --- | --- |
| 1 | Fixed | `_bootstrap` clears stale client token for lookup, puts the wrapping token in the header for `sys.unwrap()` without a body token, and clears it before AppRole login. Live OpenBao 2.6.2 reproduction showed this exact header pattern succeeds. |
| 2, 5 | Fixed | Wrapping lookup/unwrap 400/401/403 map to `BOOTSTRAP_INVALID`; rejected AppRole login maps to `AUTHENTICATION_FAILED`. |
| 3 | Fixed | Setup cloud registry fixture includes explicit credential vendor catalog; the expanded coordinator suite passed 157 tests. |
| 4, 10 | Fixed | `lookup_self` server TTL drives renewal at half the periodic lease; a ten-minute cadence is covered by an adapter test. |
| 6 | Fixed | `test-openbao-credentials` CI job runs package tests. |
| 7 | Fixed | KV-v2 read explicitly sets `raise_on_deleted_version=True`. |
| 8 | Accepted as staged rollout constraint | Fail-closed identity map remains empty until `wp-coordinator` installs the accepted-key snapshot; Bao must not be enabled on an intermediate deployment. |
| 9, 11 | Positive findings | No changes requested. |

The package declares no `context_impact` block; its context-impact status is **unmigrated**. The live scoped policy/bootstrap/rotation matrix remains assigned to `wp-integration`.
