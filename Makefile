# Architecture Analysis Tooling
#
# Generates, validates, and manages architecture artifacts in .architecture/
# from the agent-coordinator codebase (Python, TypeScript, Postgres).
#
# Usage:
#   make architecture                     # Full generation pipeline
#   make architecture-diff BASE_SHA=abc123  # Compare to baseline
#   make architecture-feature FEATURE="agent-coordinator/src/locks.py,agent-coordinator/src/db.py"
#   make architecture-validate            # Validate existing graph
#   make architecture-views               # Regenerate views only
#   make architecture-clean               # Remove generated artifacts
#   make help                             # Show this help

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ARCH_DIR       := .architecture
VIEWS_DIR      := $(ARCH_DIR)/views
SCRIPTS_DIR    := scripts
PYTHON_SRC     := agent-coordinator/src
TS_SRC         := web/
MIGRATIONS_DIR := agent-coordinator/supabase/migrations

GRAPH_FILE     := $(ARCH_DIR)/architecture.graph.json
SUMMARY_FILE   := $(ARCH_DIR)/architecture.summary.json
DIAG_FILE      := $(ARCH_DIR)/architecture.diagnostics.json
ZONES_FILE     := $(ARCH_DIR)/parallel_zones.json

# Intermediate per-language outputs
PY_ANALYSIS    := $(ARCH_DIR)/python_analysis.json
TS_ANALYSIS    := $(ARCH_DIR)/ts_analysis.json
PG_ANALYSIS    := $(ARCH_DIR)/postgres_analysis.json

# Accept BASE_SHA for diff target, FEATURE for feature-slice target
# These are set via the command line: make architecture-diff BASE_SHA=abc123

# Python interpreter
PYTHON         ?= python3

# ---------------------------------------------------------------------------
# Phony targets
# ---------------------------------------------------------------------------

.PHONY: architecture architecture-setup architecture-diff architecture-feature \
        architecture-validate architecture-views architecture-clean \
        help _analyze-python _analyze-postgres _analyze-typescript \
        _compile _validate _views _parallel-zones

# ---------------------------------------------------------------------------
# help — display available targets
# ---------------------------------------------------------------------------

help: ## Show available make targets with descriptions
	@echo ""
	@echo "Architecture Analysis Targets"
	@echo "============================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-28s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Variables:"
	@echo "  BASE_SHA=<sha>    Git SHA for baseline diff comparison"
	@echo "  FEATURE=<glob>    File list or glob for feature slice extraction"
	@echo "  PYTHON=<path>     Python interpreter (default: python3)"
	@echo ""
	@echo "Examples:"
	@echo "  make architecture"
	@echo "  make architecture-diff BASE_SHA=abc123"
	@echo '  make architecture-feature FEATURE="agent-coordinator/src/locks.py,agent-coordinator/src/db.py"'
	@echo ""

# ---------------------------------------------------------------------------
# architecture-setup — install dependencies for the analysis pipeline
# ---------------------------------------------------------------------------

architecture-setup: ## Install Python (and optionally Node.js) deps for the analysis pipeline
	@echo "=== Installing architecture analysis dependencies ==="
	@$(PYTHON) -m pip install -e "agent-coordinator/[analysis]" --quiet
	@if command -v npm >/dev/null 2>&1; then \
		echo "Installing TypeScript analyzer deps..."; \
		npm install --no-save ts-morph typescript ts-node 2>/dev/null || \
			echo "[WARN] npm install failed — TypeScript analyzer will be skipped"; \
	else \
		echo "[INFO] npm not found — TypeScript analyzer will be skipped"; \
	fi
	@echo "Setup complete."

# ---------------------------------------------------------------------------
# architecture — full generation pipeline
# ---------------------------------------------------------------------------

architecture: ## Full generation: analyzers -> compiler -> validator -> views
	@$(SCRIPTS_DIR)/refresh_architecture.sh

# ---------------------------------------------------------------------------
# Individual pipeline stages (used internally and for partial runs)
# ---------------------------------------------------------------------------

_analyze-python:
	@echo "--- Python analyzer ---"
	@mkdir -p $(ARCH_DIR)
	@$(PYTHON) $(SCRIPTS_DIR)/analyze_python.py \
		$(PYTHON_SRC) \
		--output $(PY_ANALYSIS) \
	|| { echo "[WARN] Python analyzer failed"; exit 1; }

_analyze-postgres:
	@echo "--- Postgres analyzer ---"
	@mkdir -p $(ARCH_DIR)
	@$(PYTHON) $(SCRIPTS_DIR)/analyze_postgres.py \
		$(MIGRATIONS_DIR) \
		--output $(PG_ANALYSIS) \
	|| { echo "[WARN] Postgres analyzer failed"; exit 1; }

_analyze-typescript:
	@echo "--- TypeScript analyzer ---"
	@mkdir -p $(ARCH_DIR)
	@if command -v npx >/dev/null 2>&1; then \
		npx ts-node $(SCRIPTS_DIR)/analyze_typescript.ts \
			$(TS_SRC) \
			--output $(TS_ANALYSIS) \
		|| { echo "[WARN] TypeScript analyzer failed (ts-morph may not be installed)"; exit 1; }; \
	else \
		echo "[WARN] npx not found — skipping TypeScript analyzer"; \
		exit 1; \
	fi

_compile:
	@echo "--- Graph compiler ---"
	@$(PYTHON) $(SCRIPTS_DIR)/compile_architecture_graph.py \
		--input-dir $(ARCH_DIR) \
		--output-dir $(ARCH_DIR)

_validate:
	@echo "--- Flow validator ---"
	@$(PYTHON) $(SCRIPTS_DIR)/validate_flows.py \
		--graph $(GRAPH_FILE) \
		--output $(DIAG_FILE)

_views:
	@echo "--- View generator ---"
	@mkdir -p $(VIEWS_DIR)
	@$(PYTHON) $(SCRIPTS_DIR)/generate_views.py \
		--graph $(GRAPH_FILE) \
		--output-dir $(VIEWS_DIR)

_parallel-zones:
	@echo "--- Parallel zone analyzer ---"
	@$(PYTHON) $(SCRIPTS_DIR)/parallel_zones.py \
		--graph $(GRAPH_FILE) \
		--output $(ZONES_FILE)

# ---------------------------------------------------------------------------
# architecture-diff — baseline comparison
# ---------------------------------------------------------------------------

architecture-diff: ## Baseline comparison: compare graph to BASE_SHA version
	@if [ -z "$(BASE_SHA)" ]; then \
		echo "ERROR: BASE_SHA is required. Usage: make architecture-diff BASE_SHA=<sha>"; \
		exit 1; \
	fi
	@echo "=== Architecture Diff: comparing to $(BASE_SHA) ==="
	@mkdir -p $(ARCH_DIR)/tmp
	@# Extract the baseline graph from the given commit
	@git show $(BASE_SHA):$(GRAPH_FILE) > $(ARCH_DIR)/tmp/baseline_graph.json 2>/dev/null \
		|| { echo "ERROR: Could not retrieve $(GRAPH_FILE) from commit $(BASE_SHA)"; \
		     echo "Make sure the baseline commit has architecture artifacts."; \
		     rm -rf $(ARCH_DIR)/tmp; exit 1; }
	@# Regenerate current graph if it doesn't exist
	@if [ ! -f $(GRAPH_FILE) ]; then \
		echo "Current graph not found — generating..."; \
		$(MAKE) architecture; \
	fi
	@# Run the diff comparison
	@$(PYTHON) $(SCRIPTS_DIR)/diff_architecture.py \
		--baseline $(ARCH_DIR)/tmp/baseline_graph.json \
		--current $(GRAPH_FILE) \
		--output $(ARCH_DIR)/architecture.diff.json \
	&& echo "Diff report written to $(ARCH_DIR)/architecture.diff.json" \
	|| echo "[WARN] Diff script not yet implemented — compare manually with: git diff $(BASE_SHA) -- $(GRAPH_FILE)"
	@rm -rf $(ARCH_DIR)/tmp

# ---------------------------------------------------------------------------
# architecture-feature — feature slice extraction
# ---------------------------------------------------------------------------

architecture-feature: ## Feature slice: extract subgraph for given files (FEATURE=<glob or file list>)
	@if [ -z "$(FEATURE)" ]; then \
		echo "ERROR: FEATURE is required. Usage: make architecture-feature FEATURE=\"file1.py,file2.py\""; \
		exit 1; \
	fi
	@echo "=== Feature Slice: $(FEATURE) ==="
	@if [ ! -f $(GRAPH_FILE) ]; then \
		echo "Graph not found — generating..."; \
		$(MAKE) architecture; \
	fi
	@mkdir -p $(VIEWS_DIR)
	@$(PYTHON) $(SCRIPTS_DIR)/generate_views.py \
		--graph $(GRAPH_FILE) \
		--output-dir $(VIEWS_DIR) \
		--feature-files "$(FEATURE)" \
	&& echo "Feature slice written to $(VIEWS_DIR)/" \
	|| echo "[WARN] Feature slice extraction failed — ensure generate_views.py supports --feature-files"

# ---------------------------------------------------------------------------
# architecture-validate — run validator on existing graph
# ---------------------------------------------------------------------------

architecture-validate: ## Run the schema and flow validators on the existing graph
	@echo "=== Architecture Validation ==="
	@if [ ! -f $(GRAPH_FILE) ]; then \
		echo "ERROR: $(GRAPH_FILE) not found. Run 'make architecture' first."; \
		exit 1; \
	fi
	@echo "--- Schema validation ---"
	@$(PYTHON) $(SCRIPTS_DIR)/validate_schema.py $(GRAPH_FILE)
	@echo ""
	@echo "--- Flow validation ---"
	@$(PYTHON) $(SCRIPTS_DIR)/validate_flows.py \
		--graph $(GRAPH_FILE) \
		--output $(DIAG_FILE) \
	&& echo "Diagnostics written to $(DIAG_FILE)" \
	|| echo "[WARN] Flow validator not yet available"

# ---------------------------------------------------------------------------
# architecture-views — regenerate views only
# ---------------------------------------------------------------------------

architecture-views: ## Regenerate views from the existing graph
	@echo "=== Regenerating Architecture Views ==="
	@if [ ! -f $(GRAPH_FILE) ]; then \
		echo "ERROR: $(GRAPH_FILE) not found. Run 'make architecture' first."; \
		exit 1; \
	fi
	@$(MAKE) _views
	@$(MAKE) _parallel-zones
	@echo "Views regenerated in $(VIEWS_DIR)/"

# ---------------------------------------------------------------------------
# architecture-clean — remove generated artifacts
# ---------------------------------------------------------------------------

architecture-clean: ## Remove all generated architecture artifacts
	@echo "=== Cleaning Architecture Artifacts ==="
	@rm -rf $(ARCH_DIR)/python_analysis.json \
		$(ARCH_DIR)/ts_analysis.json \
		$(ARCH_DIR)/postgres_analysis.json \
		$(ARCH_DIR)/architecture.graph.json \
		$(ARCH_DIR)/architecture.summary.json \
		$(ARCH_DIR)/architecture.diagnostics.json \
		$(ARCH_DIR)/architecture.diff.json \
		$(ARCH_DIR)/parallel_zones.json \
		$(ARCH_DIR)/views \
		$(ARCH_DIR)/tmp
	@echo "Cleaned. Committed artifacts in $(ARCH_DIR)/ may remain (e.g., README.md)."
