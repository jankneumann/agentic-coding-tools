# Contract: .test-env File Format

The `.test-env` file is the handoff artifact between `phase_deploy.py` and `phase_smoke.py`.
Written by deploy, read by smoke. Dotenv format (parseable by `python-dotenv` or shell `source`).

## Required Fields

| Key | Type | Description |
|-----|------|-------------|
| `TEST_ENV_TYPE` | `docker` \| `neon` | Which environment backend is running |
| `POSTGRES_DSN` | connection string | Full PostgreSQL connection string |
| `API_BASE_URL` | URL | Base URL for coordination API (e.g., `http://localhost:10003`) |
| `SEED_STRATEGY` | `dump_restore` \| `migrations` | How seed data was applied |
| `STARTED_AT` | ISO 8601 timestamp | When the environment was started |

## Optional Fields (Docker-specific)

| Key | Type | Description |
|-----|------|-------------|
| `COMPOSE_PROJECT_NAME` | string | Docker Compose project name for cleanup |
| `COMPOSE_FILE` | path | Path to docker-compose.yml used |
| `DB_PORT` | integer | Allocated PostgreSQL port |
| `API_PORT` | integer | Allocated API port |

## Optional Fields (Neon-specific)

| Key | Type | Description |
|-----|------|-------------|
| `NEON_BRANCH_ID` | string | Neon branch identifier for cleanup |
| `NEON_PROJECT_ID` | string | Neon project containing the branch |
| `NEON_HOST` | string | Neon connection hostname |

## Example (Docker)

```bash
TEST_ENV_TYPE=docker
POSTGRES_DSN=postgresql://postgres:postgres@localhost:10000/postgres
API_BASE_URL=http://localhost:10003
COMPOSE_PROJECT_NAME=ac-a1b2c3d4
COMPOSE_FILE=/path/to/agent-coordinator/docker-compose.yml
DB_PORT=10000
API_PORT=10003
SEED_STRATEGY=migrations
STARTED_AT=2026-03-31T20:00:00Z
```

## Example (Neon)

```bash
TEST_ENV_TYPE=neon
POSTGRES_DSN=postgresql://user:pass@ep-cool-name-123.us-east-2.aws.neon.tech/neondb
API_BASE_URL=https://ep-cool-name-123.us-east-2.aws.neon.tech
NEON_BRANCH_ID=br-abc123
NEON_PROJECT_ID=proj-xyz789
NEON_HOST=ep-cool-name-123.us-east-2.aws.neon.tech
SEED_STRATEGY=dump_restore
STARTED_AT=2026-03-31T20:00:00Z
```
