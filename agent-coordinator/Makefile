# agent-coordinator/Makefile — Coordinator lifecycle management
# Usage: cd agent-coordinator && make <target>
#    or: make -C agent-coordinator <target>

.DEFAULT_GOAL := help
SHELL := /bin/bash

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_PORT          ?= $(or $(AGENT_COORDINATOR_DB_PORT),54322)
API_PORT         ?= 8081
MCP_SSE_PORT     ?= 8082
COMPOSE          := docker compose
UV               := uv
UV_RUN           := $(UV) run
LOG_DIR          := .logs

# Activate the local deployment profile by default so the profile loader
# sets DB_BACKEND=postgres and POSTGRES_DSN from profiles/local.yaml.
export COORDINATOR_PROFILE ?= local

# ---------------------------------------------------------------------------
# Phase: Setup
# ---------------------------------------------------------------------------

.PHONY: install
install: ## Install all dependencies (uv sync --all-extras)
	$(UV) sync --all-extras

.PHONY: git-setup
git-setup: ## Configure git for parallel development (rerere, zdiff3, etc.)
	bash $(CURDIR)/../scripts/git-parallel-setup.sh

.PHONY: setup-env
setup-env: ## Copy .env.example → .env (will not overwrite existing .env)
	@if [ -f .env ]; then \
		echo ".env already exists — skipping (delete it first to regenerate)"; \
	else \
		cp .env.example .env; \
		echo "Created .env from .env.example — edit it to fill in your values"; \
	fi

# ---------------------------------------------------------------------------
# Phase: Infrastructure
# ---------------------------------------------------------------------------

.PHONY: db-up
db-up: ## Start ParadeDB (docker compose up -d)
	AGENT_COORDINATOR_DB_PORT=$(DB_PORT) $(COMPOSE) up -d

.PHONY: db-down
db-down: ## Stop ParadeDB (docker compose down)
	$(COMPOSE) down

.PHONY: db-logs
db-logs: ## Tail ParadeDB logs
	$(COMPOSE) logs -f postgres

.PHONY: db-reset
db-reset: ## Destroy and recreate the database (requires FORCE=1)
	@if [ "$(FORCE)" != "1" ]; then \
		echo "This will DELETE all data. Run with FORCE=1 to confirm:"; \
		echo "  make db-reset FORCE=1"; \
		exit 1; \
	fi
	$(COMPOSE) down -v
	AGENT_COORDINATOR_DB_PORT=$(DB_PORT) $(COMPOSE) up -d
	@echo "Database reset — waiting for healthy…"
	@$(MAKE) --no-print-directory _wait-for-db

.PHONY: db-status
db-status: ## Check database health (pg_isready)
	@pg_isready -h localhost -p $(DB_PORT) -U postgres && echo "Database is ready" || echo "Database is not ready"

.PHONY: db-shell
db-shell: ## Open psql shell to the running database
	psql postgresql://postgres:postgres@localhost:$(DB_PORT)/postgres

# ---------------------------------------------------------------------------
# Phase: Services
# ---------------------------------------------------------------------------

.PHONY: mcp-serve
mcp-serve: ## Run MCP server (stdio transport — for manual testing)
	$(UV_RUN) coordination-mcp

.PHONY: mcp-serve-sse
mcp-serve-sse: ## Run MCP server (SSE on :8082 — for browser/debug)
	$(UV_RUN) coordination-mcp --transport=sse --port=$(MCP_SSE_PORT)

.PHONY: api-serve
api-serve: ## Run HTTP API server on :8081
	$(UV_RUN) coordination-api --port=$(API_PORT)

# ---------------------------------------------------------------------------
# Phase: Claude Code Integration
# ---------------------------------------------------------------------------

.PHONY: claude-mcp-setup
claude-mcp-setup: ## Print the mcp.json snippet for ~/.claude/mcp.json
	@echo ""
	@echo "Add the following to ~/.claude/mcp.json (or .claude/mcp.json in your project):"
	@echo ""
	@echo '{'
	@echo '  "mcpServers": {'
	@echo '    "coordination": {'
	@echo '      "type": "stdio",'
	@echo '      "command": "uv",'
	@echo '      "args": ["run", "coordination-mcp"],'
	@echo '      "cwd": "$(CURDIR)"'
	@echo '    }'
	@echo '  }'
	@echo '}'
	@echo ""

# ---------------------------------------------------------------------------
# Phase: Quality
# ---------------------------------------------------------------------------

.PHONY: test
test: ## Run unit tests (excludes e2e and integration)
	$(UV_RUN) pytest -m "not e2e and not integration"

.PHONY: test-all
test-all: ## Run all tests (requires db-up)
	$(UV_RUN) pytest

.PHONY: test-integration
test-integration: ## Run integration tests only (requires db-up)
	$(UV_RUN) pytest -m integration

.PHONY: test-e2e
test-e2e: ## Run e2e tests only (requires db-up + services running)
	$(UV_RUN) pytest -m e2e

.PHONY: lint
lint: ## Run ruff linter
	$(UV_RUN) ruff check .

.PHONY: format
format: ## Run ruff formatter
	$(UV_RUN) ruff format .

.PHONY: typecheck
typecheck: ## Run mypy strict type checking
	$(UV_RUN) mypy --strict src/

.PHONY: check
check: lint typecheck test ## Run lint + typecheck + test (CI parity)

# ---------------------------------------------------------------------------
# Phase: Compound
# ---------------------------------------------------------------------------

.PHONY: dev
dev: install db-up _wait-for-db api-serve ## Full dev setup: install + db + api server (foreground)

.PHONY: dev-bg
dev-bg: install db-up _wait-for-db ## Full dev setup: install + db + api server (background)
	@mkdir -p $(LOG_DIR)
	@echo "Starting API server on :$(API_PORT) (log: $(LOG_DIR)/api.log)…"
	@nohup $(UV_RUN) coordination-api --port=$(API_PORT) > $(LOG_DIR)/api.log 2>&1 & echo $$! > $(LOG_DIR)/api.pid
	@echo "PID $$(cat $(LOG_DIR)/api.pid) — stop with: make stop"

.PHONY: stop
stop: ## Stop all services (db + background API)
	@if [ -f $(LOG_DIR)/api.pid ]; then \
		pid=$$(cat $(LOG_DIR)/api.pid); \
		if kill -0 $$pid 2>/dev/null; then \
			kill $$pid && echo "Stopped API server (PID $$pid)"; \
		else \
			echo "API server (PID $$pid) not running"; \
		fi; \
		rm -f $(LOG_DIR)/api.pid; \
	fi
	$(COMPOSE) down

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

.PHONY: _wait-for-db
_wait-for-db:
	@echo "Waiting for database on port $(DB_PORT)…"
	@for i in $$(seq 1 30); do \
		pg_isready -h localhost -p $(DB_PORT) -U postgres -q 2>/dev/null && break; \
		sleep 1; \
	done
	@pg_isready -h localhost -p $(DB_PORT) -U postgres -q 2>/dev/null \
		&& echo "Database is ready" \
		|| (echo "ERROR: Database did not become ready within 30s" && exit 1)
