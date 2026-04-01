# Proposal: Live Service Testing Pipeline

**Change ID**: `live-service-testing`
**Status**: Proposed
**Created**: 2026-03-31

## Why

Live service testing has silently dropped out of the validation pipeline. When validation phases were moved from `/validate-feature` to the implementation stages, only environment-safe phases (spec, evidence) were wired in. The Docker-dependent phases (deploy, smoke, security, e2e) specified in `validate-feature/SKILL.md` have **no implementing scripts** — they exist only as spec text.

This means:
- `/implement-feature` runs `--phase spec,evidence` — no live services touched
- `/cleanup-feature` runs `--phase deploy,smoke,security,e2e` — but warns and allows skip if Docker unavailable
- **No hard gate** prevents merging code that has never been tested against a running database or API

The consequence: regressions that only manifest with a live database (connection handling, migration ordering, asyncpg serialization edge cases) can reach main undetected.

Additionally, the Neon branching and data sync path from local dev to cloud has never been validated end-to-end, despite being a stated capability of the project.

## What Changes

### 1. Stack Launcher (`skills/validate-feature/scripts/stack_launcher.py`)
A Python script that orchestrates isolated test environments:
- Allocates ports via `port_allocator` (coordinator MCP or direct import)
- Starts a Docker/Podman Compose stack with allocated ports + unique `COMPOSE_PROJECT_NAME`
- Waits for health checks (pg_isready, API readiness)
- Returns connection details as environment variables
- Teardown: `docker compose down -v` + `release_ports`
- Supports both Docker and Podman runtimes (auto-detected via `docker-lifecycle` conventions)

### 2. Smoke Test Suite (`skills/validate-feature/scripts/smoke_tests/`)
Pytest-based smoke tests parametrized by `API_BASE_URL` and `POSTGRES_DSN`:
- `test_health.py` — `/health` and `/ready` return 2xx
- `test_auth.py` — no creds → 401, valid creds → 200, garbage → rejected
- `test_cors.py` — preflight headers correct
- `test_error_sanitization.py` — no stack traces, filesystem paths, or internal IPs in error responses
- Works against any stack (local Docker, Neon branch, Railway staging)

### 3. Neon Branch Integration (`skills/validate-feature/scripts/neon_branch.py`)
Two seeding strategies, selected by context:
- **pg_dump/pg_restore**: Snapshot local ParadeDB → restore into ephemeral Neon branch. For ad-hoc validation with real dev data.
- **Migrations + seed script**: Run 16 migration files on Neon branch, then apply `seed.sql` with representative fixtures. For CI and deterministic testing.
- **Neon → Neon branching**: Create branches from an existing Neon database (Neon's native branching). For cloud-to-cloud testing.
- Teardown: Delete ephemeral branch after tests complete.

### 4. DB Seed Data (`agent-coordinator/supabase/seed.sql`)
Representative test fixture data covering all 7 cleanable tables:
- Agent sessions, file locks, work queue items, memory entries, handoff documents
- Sufficient for smoke tests and integration validation
- Idempotent (uses `INSERT ... ON CONFLICT DO NOTHING`)

### 5. Mandatory Live-Test Gate
- **Soft gate** at end of `/implement-feature`: Run smoke tests if Docker/Neon available; warn if skipped
- **Hard gate** in `/cleanup-feature`: Smoke test pass required to proceed to merge. No skip allowed.
- Gate checks `validation-report.md` for evidence of smoke test pass
- Two paths satisfy the gate: Docker stack (local) or Neon branch (cloud/CI)

### 6. Validate-Feature Phase Scripts
Implement the `deploy` and `smoke` phase runner scripts that `validate-feature/SKILL.md` describes but never built:
- `scripts/phase_deploy.py` — Stack launcher integration, timeout handling, failure reporting
- `scripts/phase_smoke.py` — Smoke test runner, result collection, report generation

## Approaches Considered

### Approach A: Unified Stack Launcher (Recommended)

**Description**: A single `stack_launcher.py` that abstracts over Docker local stacks and Neon branches behind a common `TestEnvironment` interface. The smoke tests don't know or care which backend is providing services.

**Pros**:
- Single test suite works against both environments
- `TestEnvironment` protocol makes adding Railway/staging trivial later
- Port allocator already provides the env_snippet format that docker-compose expects
- Clean separation: launcher manages lifecycle, tests only see URLs

**Cons**:
- Slightly more abstraction upfront
- Neon and Docker have different readiness semantics (branch creation vs container startup)

**Effort**: M

### Approach B: Separate Docker and Neon Scripts

**Description**: Two independent scripts — `docker_stack.py` for local and `neon_branch.py` for cloud. Each has its own test runner invocation pattern.

**Pros**:
- Simpler individual scripts
- No abstraction overhead
- Can ship Docker path first, Neon later

**Cons**:
- Duplicate test invocation logic
- Smoke tests need environment-switching boilerplate
- Gate enforcement must check two different report formats
- Adding a third environment (Railway) means a third script

**Effort**: M

### Approach C: Docker-Only with Neon as Follow-up

**Description**: Build only the Docker stack launcher and smoke tests now. Neon branching deferred entirely to a follow-up change.

**Pros**:
- Smallest scope, fastest delivery
- Unblocks the mandatory gate immediately
- No Neon CLI dependency to manage

**Cons**:
- Cloud/CI agents with no Docker still can't run live tests
- Neon sync validation (stated goal) not addressed
- Seed data still needs to be written for Docker anyway

**Effort**: S

### Selected Approach

**Approach A: Unified Stack Launcher** — selected because the `TestEnvironment` abstraction pays for itself immediately (the smoke tests are the same regardless of backend), and the user explicitly wants Neon sync validated end-to-end in this change, not deferred.

## Assumptions

1. `neonctl` CLI is available or installable on the development machine (needed for Neon branching)
2. The existing `port_allocator.py` singleton is importable from skills scripts (it's in `agent-coordinator/src/`)
3. Docker/Podman is available on at least one CI runner or dev machine (for the Docker path)
4. The Neon project/database for branching will be configured via environment variables (`NEON_PROJECT_ID`, `NEON_API_KEY`)
5. The existing 16 migrations are sufficient to create a testable schema on Neon (no ParadeDB-specific extensions blocking Neon compatibility)

## Risks

- **ParadeDB extensions on Neon**: pg_search and pgvector are used in docker-compose. Neon supports pgvector but may not support pg_search. Mitigation: migration scripts should gracefully skip ParadeDB-specific extensions when running on Neon.
- **Neonctl availability in CI**: GitHub Actions would need neonctl installed. Mitigation: the soft/hard gate model allows Docker-only CI with Neon for local dev validation.
