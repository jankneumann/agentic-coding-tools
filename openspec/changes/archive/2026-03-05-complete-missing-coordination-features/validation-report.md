# Validation Report: complete-missing-coordination-features

**Date**: 2026-02-14
**Commit**: 0f2f8fc
**Branch**: main (feature commits present)

## Phase Results

⚠ Deploy: Default local probing from sandbox could not reach Docker-host ports, but elevated checks confirmed Docker daemon and containers are healthy.
- Docker access required elevated execution in this environment.
- Brought up stack with alternate host ports to avoid clashes:
  - Postgres: `55432`
  - PostgREST: `13000`
  - Realtime: `14000`

✓ E2E: Passed against remapped PostgREST port.
- Command: `BASE_URL=http://localhost:13000 uv run pytest -q tests/e2e`
- Result: `2 passed`

✓ Unit/Integration (non-e2e):
- Command: `uv run pytest -q tests -k 'not e2e'`
- Result: `278 passed, 29 skipped, 2 deselected`

✓ Spec Compliance (structural):
- Command: `openspec validate complete-missing-coordination-features --strict`
- Result: valid

○ CI/CD: Not evaluated in this pass (no branch/PR alignment for `openspec/complete-missing-coordination-features` from current `main` branch context).

## Port Remap Procedure

1. Create override file:

```yaml
services:
  postgres:
    ports:
      - "55432:5432"
  rest:
    ports:
      - "13000:3000"
  realtime:
    ports:
      - "14000:4000"
```

2. Start stack:

```bash
docker compose -f agent-coordinator/docker-compose.yml -f /tmp/agent-coordinator.compose.override.yml -p agentcoord up -d
```

3. Run e2e with remapped base URL:

```bash
BASE_URL=http://localhost:13000 uv run pytest -q tests/e2e
```

## Result

**PASS (with environment note)** — Feature validation succeeded when running on non-conflicting host ports.
