# wp-seeding review disposition

Review target: pre-fix tip `90d46525`; integrated tip: `56dabf90`. Antigravity, Claude Code, and Grok supplied valid findings (3/4); Pi did not. An independent final audit passed, 30 focused tests passed, and live OpenBao 2.6.2 seeding and cutover smokes passed.

| Consensus IDs | Disposition on integrated tip |
| --- | --- |
| 1, 8 | Fixed: bare legacy role aliases matching the migration-map contract are accepted, covered by preflight and retirement tests. |
| 2, 5 | Fixed: schema lookup resolves active and archived OpenSpec change directories; tests cover both. |
| 3, 17 | Fixed: Makefile forwards explicit cutover arguments and checks required inputs before starting the dev container. |
| 11 | Fixed: internal handoff policy and read proof honor validated `BAO_SECRET_PATH`. |
| 12 | Fixed: schema error reporting omits offending values. |
| 13 | Fixed: newly issued one-use SecretIDs expire after 600 seconds; wrapping expires after 300 seconds. |
| 15 | Fixed: absent/null KV mount options fail preflight with a controlled error. |
| 19 | Fixed: the seeder module header documents the new CLI. |
| 4, 10 | Positive findings; no change requested. |
| 6, 18 | Accepted for this release: audit events identify the identity-reader principal for internal policy and auth-mount operations because the frozen event contract has no separate internal principal or mount resource. This attribution should be made more precise in a follow-up contract revision. |
| 7 | Accepted with operator cutover sequencing: already issued internal tokens may retain the retired policy until re-login. The integration guide must require draining/restarting consumers after installing the isolated role and before final policy retirement. |
| 9, 16 | Accepted with follow-up: legacy callable helpers remain for compatibility, but the CLI no longer invokes them; documentation migration belongs to `wp-integration`. |
| 14 | Accepted as recoverable partial apply: managed state writes after successful reconciliation; a failed apply should be retried against the same registry before any retirement, and operator docs must say so. |
| 20 | Deferred to live integration matrix: rejected wrapping creation path and sanitized audit are covered there. |

The `make bao-dev` flow intentionally does not copy retained internal values into `secret/coordinator`: design D3 forbids the principal seeder from mutating unrelated internal data. The integration guide must explain explicit internal-secret staging for a fresh dev Bao server. The package has no `context_impact` declaration, so its status is **unmigrated**.
