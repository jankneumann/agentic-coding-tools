# Validation Report: derive-agent-identity-from-registry

**Date**: 2026-08-16
**Commit**: 509ff07
**Branch**: claude/coordination-api-keys-harnesses-1eby78 (operator override; not `openspec/<change-id>`)
**Environment**: cloud harness — no container runtime, no live services, no PR

## Phase Results

○ **Deploy**: deferred — no container runtime (`docker ps` unavailable). Not run, not passed.
○ **Smoke**: deferred — depends on Deploy.
○ **E2E**: deferred — depends on Deploy.
○ **CI/CD**: deferred — no PR exists for this branch.
⚠ **Security (scanners)**: **INCONCLUSIVE**, reported as PASS by the gate. Both scanners were
  `unavailable` — `dependency-check` has no binary and no container runtime; ZAP had no target.
  The gate's own reason field reads "Degraded execution allowed by policy; no threshold findings
  detected". Zero findings over zero scanning is not evidence, and this row must not be read as
  a pass.
✗→✓ **Security (adversarial code review)**: **FAIL on first pass**, now remediated. This was the
  only real security signal in the run. See below.
✓ **Spec Compliance**: 7/7 requirements traced with evidence; task-drift gate PASS (0 unchecked
  boxes against 17 commits). Trust scale verified empirically across all three consumers
  (module 0–4, `AGENTS_SCHEMA` 0–4, migration 031 CHECK 0–4) and the migration-022 merge-op
  boundary (`trust >= 3`) reproduced exactly for all seven registry agents.
⚠ **Architecture**: flow validation reported 0 findings but checked **0 entrypoints** — the
  changed files do not map to entrypoints in the graph. Nothing to check, not "verified".
✓ **Work-package structure**: schema, DAG acyclicity, lock-key canonicalization, scope overlap
  and lock overlap all pass.
✓ **Unit suite / types / lint**: 2312 passed, 11 skipped, 0 failed; `mypy --strict` clean
  (77 files); `ruff` clean.

## Security review findings

Ten findings. Every claim spot-checked against source before acting; all verified.

**Fixed in this change** (each with a test proven to fail when the fix is reverted):

| # | Sev | Finding |
|---|---|---|
| 1 | HIGH | Retiring an agent **escalated** it. The success branch preceded the not-in-registry branch, so a decommissioned agent kept resolving via the `agent_type` fallback to a surviving sibling — `codex-remote` → `codex_local` at trust 3, crossing `MIN_ADMIN_TRUST`. Introduced by D11's assignment deletion. |
| 2 | HIGH | The gate compared nothing: `registry_entry.profile` was never checked against `profile.name`, so a registry agent resolving to a different, higher-trust profile was accepted silently — the same weaker claim the CI invariant had just been rewritten to reject. |
| 3 | MED | Two registry entries could share a `profile`; the second silently overwrote the first (an entry squatting `claude_code_local` at trust 4 promoted `claude-local` to ADMIN). |
| 4 | MED | Insert-failure fallback retried *any* exception as an UPDATE; a zero-row UPDATE raises nothing, so RLS/FK failures reported phantom writes and emitted audit events for rows that do not exist. |
| 6 | MED | `work_queue.py` carried a verbatim pre-change copy of the resolver, still failing open — denied 500 on the HTTP path, silently granted trust 2 on the queue path. |
| 9 | LOW | `synced_from_registry_at` was never written, making migration 031's comment about operator forensics false. |
| — | MED | A **third** fail-open resolver in `policy_engine.py`, found while fixing F6 and fixed in the same pass. Most dangerous of the three: its result feeds the suspension check, so a projection failure promoted a suspended agent (trust 0) to the default and un-suspended it. |

**Filed as follow-ups** (coordinator issues, not fixed here):

- **MED** `docker-compose.yml` sets `COORDINATION_API_KEY_IDENTITIES` to a literal `"{}"`, which
  is truthy — the shipped deployment never consults the registry, and any dev-key holder can
  assert an arbitrary `agent_id`. Pre-existing; the change's premise depends on it.
- **MED** Registry load failure silently unbinds every key when `COORDINATION_API_KEYS` is set.
- **MED** `ProfilesService.check_operation` fails open when no profile resolves.
- **LOW** The `agent_type` fallback is nondeterministic, not oldest-wins: migration 007 seeds five
  profiles in one INSERT, so `created_at` is identical across them. Orphan disabling also shifts
  the surviving candidates upward.

## Result

**PASS with stated limitations** — the code-level gates are green and every HIGH/MEDIUM finding
in the change's own surface is fixed and regression-tested.

Two honest caveats, neither resolvable in this environment:

1. **Nothing was executed against a running system.** Deploy, smoke, E2E, CI, and both security
   scanners were unavailable. All evidence is unit-level plus static analysis plus code reading.
   The startup sync in particular has never run against a real Postgres — its behavior against
   the live table is verified only through fakes.
2. **The remediation has not been independently re-reviewed.** The fixes are verified by
   revert-testing (each new test fails without its fix), but the adversarial reviewer has not
   examined the fixed code. A second review pass before merge would be proportionate given that
   two HIGH findings landed in the first one.

**Recommended next step**: re-run the adversarial review against `509ff07`, then deploy to an
environment with Postgres and run the startup sync for real before archiving. `/cleanup-feature`
should wait for both.
