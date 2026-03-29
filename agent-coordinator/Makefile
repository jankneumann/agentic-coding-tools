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
# Phase: OpenBao
# ---------------------------------------------------------------------------

BAO_PORT         ?= $(or $(AGENT_COORDINATOR_BAO_PORT),8200)

.PHONY: bao-dev
bao-dev: ## Start OpenBao dev server + seed from .secrets.yaml
	AGENT_COORDINATOR_BAO_PORT=$(BAO_PORT) $(COMPOSE) --profile openbao up -d openbao
	@echo "Waiting for OpenBao on port $(BAO_PORT)…"
	@for i in $$(seq 1 15); do \
		curl -sf http://localhost:$(BAO_PORT)/v1/sys/health >/dev/null 2>&1 && break; \
		sleep 1; \
	done
	@curl -sf http://localhost:$(BAO_PORT)/v1/sys/health >/dev/null 2>&1 \
		&& echo "OpenBao is ready" \
		|| (echo "ERROR: OpenBao did not become ready within 15s" && exit 1)
	BAO_ADDR=http://localhost:$(BAO_PORT) BAO_TOKEN=dev-root-token \
		python ../scripts/bao_seed.py

.PHONY: bao-seed
bao-seed: ## Re-seed OpenBao from .secrets.yaml and agents.yaml
	BAO_ADDR=http://localhost:$(BAO_PORT) BAO_TOKEN=dev-root-token \
		python ../scripts/bao_seed.py

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
# Phase: MCP Integration
# ---------------------------------------------------------------------------

# Env vars shared across all MCP registrations
MCP_ENV_FLAGS := --env DB_BACKEND=postgres \
	--env "POSTGRES_DSN=postgresql://postgres:postgres@localhost:$(DB_PORT)/postgres" \
	--env AGENT_ID=claude-code-1 \
	--env AGENT_TYPE=claude_code

.PHONY: claude-mcp-setup
claude-mcp-setup: ## Register coordination MCP server with Claude Code
	claude mcp add-json --scope user coordination \
		'{"type":"stdio","command":"$(CURDIR)/.venv/bin/python","args":["-m","src.coordination_mcp"],"cwd":"$(CURDIR)","env":{"DB_BACKEND":"postgres","POSTGRES_DSN":"postgresql://postgres:postgres@localhost:$(DB_PORT)/postgres","AGENT_ID":"claude-code-1","AGENT_TYPE":"claude_code"}}'
	@echo "Coordination MCP server registered. Restart Claude Code to activate."

.PHONY: codex-mcp-setup
codex-mcp-setup: ## Register coordination MCP server with Codex CLI
	codex mcp add $(MCP_ENV_FLAGS) \
		coordination -- $(CURDIR)/.venv/bin/python -m src.coordination_mcp
	@echo "Coordination MCP server registered. Restart Codex to activate."

.PHONY: gemini-mcp-setup
gemini-mcp-setup: ## Register coordination MCP server with Gemini CLI
	gemini mcp add --scope user $(MCP_ENV_FLAGS) \
		coordination $(CURDIR)/.venv/bin/python -m src.coordination_mcp
	@echo "Coordination MCP server registered. Restart Gemini to activate."

.PHONY: mcp-setup
mcp-setup: claude-mcp-setup codex-mcp-setup gemini-mcp-setup ## Register coordination MCP server with all CLI agents

# ---------------------------------------------------------------------------
# Phase: Hooks & Notification Integration
# ---------------------------------------------------------------------------
# Hooks install at USER scope (~/.claude/, ~/.codex/) so they fire in ANY
# repo, not just this one.  The hook scripts use absolute paths back to
# this checkout so they find the coordinator Python modules.

SCRIPTS_ABS := $(CURDIR)/scripts

# JSON template used by claude-hooks-setup and codex-hooks-setup.
# Uses absolute paths so the hooks work from any working directory.
define HOOKS_JSON
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "python3 $(SCRIPTS_ABS)/register_agent.py"
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python3 $(SCRIPTS_ABS)/report_status.py"
      }
    ],
    "SessionEnd": [
      {
        "type": "command",
        "command": "python3 $(SCRIPTS_ABS)/deregister_agent.py"
      }
    ]
  }
}
endef
export HOOKS_JSON

.PHONY: claude-hooks-setup
claude-hooks-setup: ## Install coordinator hooks into Claude Code (user scope, works in any repo)
	@mkdir -p ~/.claude
	@echo "$$HOOKS_JSON" > ~/.claude/hooks.json
	@echo "Installed ~/.claude/hooks.json (user scope)"
	@echo "  Scripts point to: $(SCRIPTS_ABS)/"
	@echo "  Hooks: SessionStart, Stop, SessionEnd"

.PHONY: codex-hooks-setup
codex-hooks-setup: ## Install coordinator hooks into Codex CLI (user scope, works in any repo)
	@mkdir -p ~/.codex
	@echo "$$HOOKS_JSON" > ~/.codex/hooks.json
	@echo "Installed ~/.codex/hooks.json (user scope)"
	@echo "  Scripts point to: $(SCRIPTS_ABS)/"
	@echo "  Hooks: SessionStart, Stop, SessionEnd"

.PHONY: gemini-wrapper-install
gemini-wrapper-install: ## Install Gemini status wrapper (symlink gemini-coord to ~/.local/bin)
	@chmod +x $(SCRIPTS_ABS)/gemini_wrapper.sh
	@mkdir -p ~/.local/bin
	@ln -sf $(SCRIPTS_ABS)/gemini_wrapper.sh ~/.local/bin/gemini-coord
	@echo "Installed ~/.local/bin/gemini-coord -> $(SCRIPTS_ABS)/gemini_wrapper.sh"
	@echo ""
	@echo "Usage (from any repo):"
	@echo "  gemini-coord \"your prompt here\""
	@echo "  gemini-coord -p \"fix the test\" -y"
	@echo ""
	@echo "Ensure ~/.local/bin is in your PATH."
	@echo "Set env vars for coordinator connection:"
	@echo "  export COORDINATOR_URL=http://localhost:$(API_PORT)"
	@echo "  export AGENT_ID=gemini-1"
	@echo "  export AGENT_TYPE=gemini"

.PHONY: hooks-setup
hooks-setup: claude-hooks-setup codex-hooks-setup gemini-wrapper-install ## Install coordinator hooks/wrappers for ALL agents (user scope)
	@echo ""
	@echo "All agents configured for coordinator status reporting."
	@echo "  Claude Code: ~/.claude/hooks.json  (SessionStart, Stop, SessionEnd)"
	@echo "  Codex CLI:   ~/.codex/hooks.json   (SessionStart, Stop, SessionEnd)"
	@echo "  Gemini CLI:  ~/.local/bin/gemini-coord (wrapper script)"

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

.PHONY: api-stop
api-stop: ## Stop background API server (keeps DB running)
	@if [ -f $(LOG_DIR)/api.pid ]; then \
		pid=$$(cat $(LOG_DIR)/api.pid); \
		if kill -0 $$pid 2>/dev/null; then \
			kill $$pid && echo "Stopped API server (PID $$pid)"; \
		else \
			echo "API server (PID $$pid) not running"; \
		fi; \
		rm -f $(LOG_DIR)/api.pid; \
	else \
		echo "No API pid file found"; \
	fi

.PHONY: api-start
api-start: ## Start API server in background (assumes DB already running)
	@mkdir -p $(LOG_DIR)
	@echo "Starting API server on :$(API_PORT) (log: $(LOG_DIR)/api.log)…"
	@nohup $(UV_RUN) coordination-api --port=$(API_PORT) > $(LOG_DIR)/api.log 2>&1 & echo $$! > $(LOG_DIR)/api.pid
	@echo "PID $$(cat $(LOG_DIR)/api.pid) — stop with: make api-stop"

.PHONY: api-restart
api-restart: api-stop api-start ## Restart API server (keeps DB running)

.PHONY: stop
stop: api-stop ## Stop all services (db + background API)
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
