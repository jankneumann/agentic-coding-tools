# PCA-02 post-merge validation — 2026-09-28

Source: `fcc0e542cd0cf128c50330fcda71ee82b36bd10b` (`origin/main` at validation start). The feature landed in [PR #629](https://github.com/jankneumann/agentic-coding-tools/pull/629), merge commit `31b8a93dd9cdc41c9bf8c82d67ec096c0b4b39b0`.

## Results

| Check | Result | Evidence |
| --- | --- | --- |
| Local deployment | Pass | Isolated Podman Compose project `pca02val` built the coordinator API and started PostgreSQL plus the pinned OpenBao image. `/health` returned `200` with `db: connected`; OpenBao `/v1/sys/health` reported initialized and unsealed. |
| HTTP smoke | Pass | `skills/validate-feature/scripts/smoke_tests`: 11 passed against `127.0.0.1:18081`. Auth rejection, health, readiness, CORS, and error sanitization were checked. |
| Coordinator E2E | Pass | `agent-coordinator/tests/e2e`: 21 passed against the isolated PostgreSQL service. |
| OpenBao live matrix | Pass | `skills/bao-vault/scripts/tests/integration`: 8 passed against the pinned OpenBao service, including principal path isolation, wrapped bootstrap, coordinator identity rotation/readiness, and token renewal. |
| ZAP baseline | Pass at the configured high-severity threshold | The live scan parsed one informational “Storable and Cacheable Content” alert on 404 responses. No medium, high, or critical findings were reported. |
| OWASP Dependency-Check | Inconclusive | The local NVD database was 17 days old, exceeding the required 7-day freshness limit. `NVD_API_KEY` was unavailable, so no current CVE scan ran. The security gate returned `INCONCLUSIVE`, not pass. |
| Merge CI | Pass | PR #629 shows successful `test-openbao-live`, `secret-scan`, dependency-audit, integration, Docker import, and other configured checks. |

The deployed API used its development static-key configuration; `/ready` returned `identity: disabled`. The separate live OpenBao matrix exercised Bao-backed identity rotation and readiness directly. This run does not establish a full HTTP deployment with Bao-backed authentication, nor does it establish production rollout readiness.

## Runtime log findings

The coordinator container stayed healthy, but startup/runtime logs showed three nonfatal errors:

- `refresh_rpc_client.is_graph_stale`: `No module named rpc_server`; the merge train fell back to a full test suite.
- Watchdog stale-agent sweep: relation `agent_discovery` does not exist (already tracked by [issue #634](https://github.com/jankneumann/agentic-coding-tools/issues/634)).
- Watchdog vendor-health sweep: `'NoneType' object has no attribute '__dict__'`.

These errors were observed in the isolated dev stack. They were not attributed to PCA-02 by this validation run.

The RPC and vendor-health errors are tracked by [issue #644](https://github.com/jankneumann/agentic-coding-tools/issues/644).

## Remaining validation

Refresh the NVD database and rerun Dependency-Check. A deployment using Bao-backed coordinator authentication should be smoke-tested before production cutover. Preserve the OpenBao migration and bootstrap procedure in `docs/openbao-secret-management.md`; the dev server and synthetic keys used here are not production credentials.

The remaining PCA-02 validation is tracked by [issue #642](https://github.com/jankneumann/agentic-coding-tools/issues/642).
