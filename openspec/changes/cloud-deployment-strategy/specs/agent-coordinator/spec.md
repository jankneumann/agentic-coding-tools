# Delta Spec: agent-coordinator (cloud-deployment-strategy)

## ADDED Requirements

### Requirement: Production Container Image

The agent-coordinator MUST provide a production Dockerfile that builds the coordination HTTP API into a container image with multi-stage build, using `uv` for dependency installation and `uvicorn` as the ASGI server.

#### Scenario: Build container image successfully
- **WHEN** `docker build -t coordination-api agent-coordinator/` is run
- **THEN** the image SHALL build successfully with a non-root runtime user
- **AND** the image SHALL be less than 200MB
- **AND** the image SHALL expose port 8081

#### Scenario: Run container with required environment
- **WHEN** the container is started with `POSTGRES_DSN`, `DB_BACKEND=postgres`, and `COORDINATION_API_KEYS` set
- **THEN** the coordination API SHALL be accessible on port 8081
- **AND** the `/health` endpoint SHALL return `{"status": "ok"}`

---

### Requirement: Railway Deployment Configuration

The agent-coordinator MUST include a Railway deployment configuration that specifies the build method, health check endpoint, and required environment variables.

#### Scenario: Deploy two-service project to Railway
- **WHEN** the repository is connected to Railway with two services configured
- **THEN** Service 1 (ParadeDB Postgres) SHALL be accessible on the private network
- **AND** Service 2 (Coordination API) SHALL build from the Dockerfile
- **AND** the health check SHALL poll `GET /health` every 30 seconds
- **AND** the API service SHALL be accessible via Railway-provided HTTPS URL

---

### Requirement: Production Server Settings

The coordination API MUST support production uvicorn configuration via environment variables for worker count, keep-alive timeout, and access logging.

#### Scenario: Configure production workers
- **WHEN** `API_WORKERS=4` is set in the environment
- **THEN** uvicorn SHALL start 4 worker processes
- **AND** the default worker count SHALL be 1

#### Scenario: Configure access logging
- **WHEN** `API_ACCESS_LOG=true` is set in the environment
- **THEN** uvicorn SHALL emit access log entries for each request

---

### Requirement: Health Check with Database Connectivity

The `/health` endpoint MUST include a database connectivity check that reports both API and database status.

#### Scenario: Database is reachable
- **WHEN** a GET request is made to `/health` and the database is responsive
- **THEN** the response SHALL be `{"status": "ok", "db": "connected"}` with HTTP 200

#### Scenario: Database is unreachable
- **WHEN** a GET request is made to `/health` and the database is not responsive within 2 seconds
- **THEN** the response SHALL be `{"status": "degraded", "db": "unreachable"}` with HTTP 503

---

### Requirement: ParadeDB Local Development Environment

The local docker-compose MUST use the ParadeDB Postgres image as a single database service, replacing the previous three-service Supabase stack.

#### Scenario: Start local development database
- **WHEN** `docker compose up -d` is run in the agent-coordinator directory
- **THEN** a single ParadeDB Postgres container SHALL start on port 54322
- **AND** all existing migrations SHALL be applied automatically
- **AND** the `pg_search` and `vector` extensions SHALL be available

#### Scenario: Connect with asyncpg
- **WHEN** `DB_BACKEND=postgres` and `POSTGRES_DSN=postgresql://postgres:postgres@localhost:54322/postgres` are set
- **THEN** the coordination MCP server and HTTP API SHALL connect successfully via asyncpg

---

### Requirement: Cloud Deployment Guide

A deployment guide MUST document Railway two-service setup, ParadeDB Postgres configuration, environment setup, API key provisioning, migration execution, and verification steps.

#### Scenario: Follow deployment guide to production
- **WHEN** a developer follows `docs/cloud-deployment.md` from start to finish
- **THEN** they SHALL have a working Railway deployment with ParadeDB Postgres and coordination API
- **AND** cloud agents SHALL be able to call `/health` and receive a 200 response

#### Scenario: Database migration execution
- **WHEN** the guide's migration section is followed
- **THEN** all migration files SHALL be applied to the Railway Postgres instance
- **AND** at least one automated migration method SHALL be documented (psql script or GitHub Actions)

---

### Requirement: Setup-Coordinator Cloud Support

The setup-coordinator skill MUST include instructions for configuring cloud agent access to the deployed coordination API.

#### Scenario: Configure cloud agent endpoint
- **WHEN** a cloud agent runs the setup-coordinator skill with `--mode web`
- **THEN** it SHALL verify connectivity to the `COORDINATION_API_URL` endpoint
- **AND** it SHALL confirm API key authentication works

---

### Requirement: SSRF Allowlist Documentation

The coordination bridge MUST document how to configure `COORDINATION_ALLOWED_HOSTS` for cloud deployment URLs beyond the default localhost allowlist.

#### Scenario: Cloud URL in SSRF allowlist
- **WHEN** `COORDINATION_ALLOWED_HOSTS` includes the Railway deployment hostname
- **THEN** the coordination bridge SHALL allow HTTP requests to that host
- **AND** requests to unlisted hosts SHALL still be blocked
