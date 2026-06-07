# =============================================================================
# Multi-stage production Dockerfile for the Coordination API
#
# Build context: repo root (not agent-coordinator/).
# Required by D8 Strategy A: gen-eval lives at packages/gen-eval/, a sibling
# of agent-coordinator/, so the Docker build must see both trees.
#
# Build with:
#   docker build -f agent-coordinator/Dockerfile -t agent-coordinator:latest .
#
# docker-compose.yml: context=.. dockerfile=agent-coordinator/Dockerfile
# Railway dashboard: Source > Root Directory = /  (one-time prerequisite)
#                    Build > Dockerfile Path = agent-coordinator/Dockerfile
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build — install production dependencies via uv
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

# Build tools needed to compile native deps (e.g. asyncpg, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends gcc libffi-dev && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy the gen-eval sibling package so the path-dep in
# agent-coordinator/pyproject.toml resolves at uv-sync time. The path is
# `{ path = "../packages/gen-eval" }` relative to the pyproject.toml dir.
# We put pyproject.toml at /app, so `../packages/gen-eval` resolves to
# /packages/gen-eval — gen-eval must live there, not under /workspace.
COPY packages/gen-eval/ /packages/gen-eval/

WORKDIR /app

# Copy dependency manifests (layer caching — only reinstall when these change)
COPY agent-coordinator/pyproject.toml agent-coordinator/uv.lock* ./

# hatchling requires README.md for metadata validation even with --no-install-project
RUN touch README.md && uv sync --all-extras --no-dev --no-install-project

# ---------------------------------------------------------------------------
# Stage 2: Runtime — lean image with only venv + source
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

WORKDIR /app

# Copy the virtual environment from the build stage.
# gen-eval is installed as a non-editable wheel inside .venv — the
# /workspace/packages/gen-eval/ source tree is NOT present in this stage,
# which is intentional: the runtime image stays minimal.
COPY --from=builder /app/.venv /app/.venv

# Copy application source code and runtime config assets loaded from disk.
COPY agent-coordinator/src/ /app/src/
COPY agent-coordinator/profiles/ /app/profiles/
COPY agent-coordinator/cedar/ /app/cedar/
# Evaluation module is imported by src/coordination_api.py for the
# /gen-eval/* endpoints (list_scenarios, validate_scenario, create_scenario,
# run_gen_eval). Without this COPY those routes return 500 at runtime.
# The gen_eval Python package itself is installed in .venv (copied above);
# what lives here is the coordinator's per-project data: descriptors/,
# manifests/, scenarios/.
COPY agent-coordinator/evaluation/ /app/evaluation/
# Database migrations — required by src/migrations.py auto-runner at startup.
COPY agent-coordinator/database/ /app/database/
COPY agent-coordinator/agents.yaml /app/agents.yaml
COPY agent-coordinator/teams.yaml /app/teams.yaml
# archetypes.yaml is read at runtime by src/agents_config.py:load_archetypes_config
# (`Path(__file__).parent.parent / "archetypes.yaml"`). It powers per-phase
# archetype resolution at POST /archetypes/resolve_for_phase. Without this
# COPY the endpoint returns 404 for every phase because phase_mapping never
# loads. Same Dockerfile contract as agents.yaml/teams.yaml above.
COPY agent-coordinator/archetypes.yaml /app/archetypes.yaml

# IMPL_REVIEW live-smoke Finding B: pre-create a writable workdir that
# COORDINATOR_WORKDIR_ROOT points at. Without this, the kanban-viz
# saved-view and audit endpoints try to write under /docs/... (the
# fallback when WORKDIR_ROOT is unset OR when it's set but the parent
# doesn't exist with write permissions for the unprivileged user).
RUN mkdir -p /app/workdir/docs/kanban-viz

# Create non-root user and switch to it
RUN groupadd --system appuser && \
    useradd --system --gid appuser --no-create-home appuser && \
    chown -R appuser:appuser /app
USER appuser

# Default environment
ENV DB_BACKEND=postgres \
    PYTHONPATH=/app \
    # Prepend the venv to PATH so `python` (and other installed entry points)
    # resolve to /app/.venv/ instead of the base image's /usr/local/bin/python.
    # Without this, ad-hoc invocations like `docker run --entrypoint python ...`
    # silently use system Python and report `ModuleNotFoundError: gen_eval`,
    # even though gen_eval is correctly installed in the venv. The CMD below
    # hard-codes the venv python so runtime is unaffected either way; this ENV
    # only fixes operator/debug ergonomics and tightens the 7.4.1 import gate.
    PATH=/app/.venv/bin:$PATH \
    # Point gen_eval.mcp_service at the coordinator's per-project data.
    # Resolves relative to the process cwd (/app at runtime).
    GEN_EVAL_DATA_DIR=/app/evaluation

# Expose the API port (Railway overrides via $PORT)
EXPOSE 8081

# Run uvicorn — use $PORT for Railway, 0.0.0.0 so Railway proxy/healthcheck can reach us
CMD ["/bin/sh", "-c", "/app/.venv/bin/python -m uvicorn src.coordination_api:create_coordination_api --factory --host 0.0.0.0 --port ${PORT:-8081}"]
