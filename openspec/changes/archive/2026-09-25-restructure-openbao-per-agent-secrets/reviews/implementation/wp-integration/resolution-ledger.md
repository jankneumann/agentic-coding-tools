# wp-integration review disposition

Review target: `f5c50e86`; integrated tip: `73500e9c`. Antigravity, Claude Code, and Grok produced schema-valid findings (3/4); Pi did not. The pinned live OpenBao matrix passed 8 tests after the followup, with no PostgREST dependency. The independent final audit found no blockers.

| Consensus IDs | Disposition on integrated tip |
| --- | --- |
| 2, 5 | Fixed: a synchronized two-process live test starts from one protected bundle. It verifies one unwrap/login and reuse of the same cached token by the other process. |
| 4 | Fixed: `agent-coordinator/CLAUDE.md` qualifies `COORDINATION_API_KEYS` as a non-Bao rollback lever only. |
| 6 | Fixed: the dedicated runner fails when pytest reports zero passed tests, including an all-skipped suite. The worker checked this with an injected skip plugin. |
| 14 | Fixed: agent and service policy tests explicitly deny reads from `secret/coordinator`. |
| 15 | Fixed: each periodic renewal extends the lease beyond the previous renewal, and the same token remains usable past the tuned auth-mount max TTL. |
| 16, 21 | Fixed: live identity test checks recovery to ready after repairing documents and tests that static keys cannot bypass Bao identity; disabled state remains covered by coordinator unit tests. |
| 17 | Fixed in a feature-level followup: canonical `skills/bao-vault/SKILL.md` now documents `BAO_INTERNAL_ROLE_ID` and `BAO_INTERNAL_SECRET_ID`. |
| 18 | Fixed: unused role-name argument removed from the live reader helper. |
| 20 | Fixed: live tests clean up temporary AppRoles and policy. |
| 1, 3, 7–12, 22 | Positive findings; no change requested. |
| 13 | Accepted: the image extraction guard is intentionally coupled to the current Compose layout and fails loudly if formatting prevents a match. |
| 19 | Accepted operational trade-off: the immutable image digest is duplicated deliberately and equality-checked; upgrades require updating both Compose and the runner. The operator guide names the pinned matrix. |

No `context_impact` block is declared for this package; its context-impact status is **unmigrated**.
