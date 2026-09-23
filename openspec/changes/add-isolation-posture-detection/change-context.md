# Change Context: add-isolation-posture-detection

| Requirement | Design | Implementation | Verification |
|---|---|---|---|
| Independent dimensions | D1, D3 | `skills/shared/environment_profile.py` | truth-table tests |
| Boolean compatibility | D2 | compatibility property/constructor | compatibility tests |
| Cloud detection | D3 | exact Claude/Codex markers | marker and precedence tests |
| Worktree filesystem reads | D4 | worktree and merge entrypoints | inverse-dimension tests |

Architecture refresh was attempted but cannot analyze this skills-only repository because
its configured `src/` root does not exist; committed artifacts were untouched.

The reproduced Codex harness exposed `CODEX_CI=1`,
`CODEX_PERMISSION_PROFILE=:workspace`, and
`CODEX_SANDBOX_NETWORK_DISABLED=1` while none of the legacy filesystem markers
matched. These are treated as exact empirical heuristics rather than stable public
provider contracts; generic `CODEX_CI`, session IDs, and permission/network markers
alone do not assert filesystem isolation.
