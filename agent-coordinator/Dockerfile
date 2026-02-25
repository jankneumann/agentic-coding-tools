# =============================================================================
# Multi-stage production Dockerfile for the Coordination API
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build — install production dependencies via uv
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency manifests first (layer caching)
COPY pyproject.toml uv.lock* ./

# Install production dependencies (all extras, no dev deps)
RUN uv sync --all-extras --no-dev

# ---------------------------------------------------------------------------
# Stage 2: Runtime — lean image with only venv + source
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy the virtual environment from the build stage
COPY --from=builder /app/.venv /app/.venv

# Copy application source code
COPY src/ /app/src/

# Create non-root user and switch to it
RUN groupadd --system appuser && \
    useradd --system --gid appuser --no-create-home appuser && \
    chown -R appuser:appuser /app
USER appuser

# Default environment
ENV DB_BACKEND=postgres

# Expose the API port
EXPOSE 8081

# Run uvicorn from the venv
ENTRYPOINT ["/app/.venv/bin/python", "-m", "uvicorn", "src.coordination_api:create_coordination_api", "--factory", "--host", "0.0.0.0", "--port", "8081"]
