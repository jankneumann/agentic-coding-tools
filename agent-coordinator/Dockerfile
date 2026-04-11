# =============================================================================
# Multi-stage production Dockerfile for the Coordination API
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build — install production dependencies via uv
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

WORKDIR /app

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency manifests (layer caching)
COPY pyproject.toml uv.lock* ./

# hatchling requires README.md for metadata validation even with --no-install-project
RUN touch README.md && uv sync --all-extras --no-dev --no-install-project

# ---------------------------------------------------------------------------
# Stage 2: Runtime — lean image with only venv + source
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

WORKDIR /app

# Copy the virtual environment from the build stage
COPY --from=builder /app/.venv /app/.venv

# Copy application source code and runtime config assets loaded from disk.
COPY src/ /app/src/
COPY profiles/ /app/profiles/
COPY cedar/ /app/cedar/
# Evaluation module is imported by src/coordination_api.py for the
# /gen-eval/* endpoints (list_scenarios, validate_scenario, create_scenario,
# run_gen_eval). Without this COPY those routes return 500 at runtime.
COPY evaluation/ /app/evaluation/
COPY agents.yaml /app/agents.yaml
COPY teams.yaml /app/teams.yaml

# Create non-root user and switch to it
RUN groupadd --system appuser && \
    useradd --system --gid appuser --no-create-home appuser && \
    chown -R appuser:appuser /app
USER appuser

# Default environment
ENV DB_BACKEND=postgres \
    PYTHONPATH=/app

# Expose the API port (Railway overrides via $PORT)
EXPOSE 8081

# Run uvicorn — use $PORT for Railway, 0.0.0.0 so Railway proxy/healthcheck can reach us
CMD ["/bin/sh", "-c", "/app/.venv/bin/python -m uvicorn src.coordination_api:create_coordination_api --factory --host 0.0.0.0 --port ${PORT:-8081}"]
