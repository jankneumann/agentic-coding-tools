# Architecture Analysis Tooling
#
# Generates, validates, and manages architecture artifacts in docs/architecture-analysis/
# from the agent-coordinator codebase (Python, TypeScript, Postgres).
#
# Usage:
#   make architecture                     # Full generation pipeline (in place)
#   make architecture-refresh             # Deterministic staged refresh + provenance
#   make architecture-check               # Read-only content-based freshness check
#   make architecture-diff BASE_SHA=abc123  # Compare to baseline
#   make architecture-feature FEATURE="src/locks.py,src/db.py"
#   make architecture-validate            # Validate existing graph
#   make architecture-views               # Regenerate views only
#   make architecture-clean               # Remove generated artifacts
#   make help                             # Show this help

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# All source directories are env-configurable. Defaults assume the Makefile
# lives at the repo root and agent-coordinator is a subdirectory.
ARCH_DIR         ?= docs/architecture-analysis
VIEWS_DIR        := $(ARCH_DIR)/views
SCRIPTS_DIR      ?= skills/refresh-architecture/scripts
PYTHON_SRC_DIR   ?= agent-coordinator/src
# TypeScript sources live under apps/ (apps/kanban-viz). The previous default
# `web` has never existed in this repository, which is why the committed
# ts_analysis.json records zero modules, functions and components.
TS_SRC_DIR       ?= apps
# Migrations moved to database/migrations when the coordinator left Supabase for
# ParadeDB; the supabase path no longer exists, so the postgres analyzer failed
# with "Migrations directory not found" on every run.
MIGRATIONS_DIR   ?= agent-coordinator/database/migrations

GRAPH_FILE     := $(ARCH_DIR)/architecture.graph.json
SUMMARY_FILE   := $(ARCH_DIR)/architecture.summary.json
DIAG_FILE      := $(ARCH_DIR)/architecture.diagnostics.json
ZONES_FILE     := $(ARCH_DIR)/parallel_zones.json

# Tree-sitter enrichment outputs
ENRICHMENT_FILE  := $(ARCH_DIR)/treesitter_enrichment.json
COMMENT_FILE     := $(ARCH_DIR)/comment_insights.json
PATTERN_FILE     := $(ARCH_DIR)/pattern_insights.json
QUERIES_DIR      := $(SCRIPTS_DIR)/treesitter_queries
# Interpreter for the optional tree-sitter stages. Resolved by the same module
# the shell pipeline and the provenance record use, so all three agree on
# whether the tool is available; an empty value means it is not (issue #378).
#
# This was `$(SCRIPTS_DIR)/.venv/bin/python` — a per-skill venv that does not
# exist here and that nothing creates — so `make architecture` skipped the
# enrichment, comment-linker and pattern-reporter stages on every run, silently,
# while still reporting success.
SCRIPTS_PYTHON   ?= $(shell $(PYTHON) $(SCRIPTS_DIR)/arch_utils/interpreters.py 2>/dev/null)

# Intermediate per-language outputs
PY_ANALYSIS    := $(ARCH_DIR)/python_analysis.json
TS_ANALYSIS    := $(ARCH_DIR)/ts_analysis.json
PG_ANALYSIS    := $(ARCH_DIR)/postgres_analysis.json

# Accept BASE_SHA for diff target, FEATURE for feature-slice target
# These are set via the command line: make architecture-diff BASE_SHA=abc123

# Python interpreter.
#
# The architecture producers and the context-drift gate MUST run under the same
# interpreter. `optional_tools` in architecture.provenance.json records whether
# tree-sitter was importable when the artifacts were produced, and the gate
# compares that against what *it* can import. A refresh under bare `python3` and
# a gate under `skills/.venv/bin/python` therefore disagree by construction, and
# report permanent, unfixable drift.
#
# Prefer this repository's declared toolchain (pinned by skills/uv.lock) when it
# is installed; fall back to `python3` so a bare checkout still works.
PYTHON         ?= $(if $(wildcard skills/.venv/bin/python),skills/.venv/bin/python,python3)

# ---------------------------------------------------------------------------
# Phony targets
# ---------------------------------------------------------------------------

.PHONY: architecture architecture-setup scripts-setup architecture-diff architecture-feature \
        architecture-validate architecture-views architecture-report architecture-clean \
        gen-eval gen-eval-augmented \
        help _analyze-python _analyze-postgres _analyze-typescript \
        _compile _validate _views _parallel-zones _report \
        _enrich-treesitter _comment-linker _pattern-reporter

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
	@echo "  PYTHON_SRC_DIR=<path>  Python source directory (default: agent-coordinator/src)"
	@echo "  TS_SRC_DIR=<path>      TypeScript source directory (default: apps)"
	@echo "  MIGRATIONS_DIR=<path>  SQL migrations directory (default: agent-coordinator/database/migrations)"
	@echo "  ARCH_DIR=<path>        Output directory (default: docs/architecture-analysis)"
	@echo "  BASE_SHA=<sha>         Git SHA for baseline diff comparison"
	@echo "  FEATURE=<glob>         File list or glob for feature slice extraction"
	@echo "  PYTHON=<path>          Python interpreter (default: python3)"
	@echo ""
	@echo "Examples:"
	@echo "  make architecture"
	@echo "  make architecture-diff BASE_SHA=abc123"
	@echo '  make architecture-feature FEATURE="src/locks.py,src/db.py"'
	@echo "  make gen-eval"
	@echo "  make gen-eval GENEVAL_CATEGORIES=lock-lifecycle"
	@echo "  make gen-eval-augmented"
	@echo ""

# ---------------------------------------------------------------------------
# architecture-setup — install dependencies for the analysis pipeline
# ---------------------------------------------------------------------------

scripts-setup: ## Install scripts/ venv with tree-sitter and analysis dependencies
	@echo "=== Setting up scripts/ virtual environment ==="
	@cd $(SCRIPTS_DIR) && uv sync
	@echo "Scripts venv ready at $(SCRIPTS_DIR)/.venv"

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
	@$(PYTHON) $(SCRIPTS_DIR)/run_architecture.py \
		--target-dir . \
		--python-src-dir $(PYTHON_SRC_DIR) \
		--ts-src-dir $(TS_SRC_DIR) \
		--migrations-dir $(MIGRATIONS_DIR) \
		--arch-dir $(ARCH_DIR) \
		--python $(PYTHON)

architecture-refresh: ## Deterministic staged refresh: stage -> validate -> promote -> write provenance
	@$(PYTHON) $(SCRIPTS_DIR)/run_architecture.py \
		--target-dir . \
		--python-src-dir $(PYTHON_SRC_DIR) \
		--ts-src-dir $(TS_SRC_DIR) \
		--migrations-dir $(MIGRATIONS_DIR) \
		--python $(PYTHON) \
		--staged

architecture-check: ## Read-only, mtime-independent freshness check via architecture provenance
	@$(PYTHON) $(SCRIPTS_DIR)/run_architecture.py --target-dir . --check

# ---------------------------------------------------------------------------
# Individual pipeline stages (used internally and for partial runs)
# ---------------------------------------------------------------------------

_analyze-python:
	@echo "--- Python analyzer ---"
	@mkdir -p $(ARCH_DIR)
	@$(PYTHON) $(SCRIPTS_DIR)/analyze_python.py \
		$(PYTHON_SRC_DIR) \
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
			$(TS_SRC_DIR) \
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

_enrich-treesitter:
	@echo "--- Tree-sitter enrichment ---"
	@if [ -x "$(SCRIPTS_PYTHON)" ] && $(SCRIPTS_PYTHON) -c "import tree_sitter" 2>/dev/null; then \
		$(SCRIPTS_PYTHON) $(SCRIPTS_DIR)/enrich_with_treesitter.py \
			--python-src $(PYTHON_SRC_DIR) \
			--ts-src $(TS_SRC_DIR) \
			--graph $(GRAPH_FILE) \
			--queries $(QUERIES_DIR) \
			--output $(ENRICHMENT_FILE); \
	else \
		echo "[INFO] tree-sitter not available — skipping enrichment"; \
	fi

_comment-linker:
	@echo "--- Comment linker ---"
	@if [ -f "$(ENRICHMENT_FILE)" ] && [ -x "$(SCRIPTS_PYTHON)" ]; then \
		$(SCRIPTS_PYTHON) $(SCRIPTS_DIR)/insights/comment_linker.py \
			--input-dir $(ARCH_DIR) \
			--output $(COMMENT_FILE); \
	else \
		echo "[INFO] No enrichment data — skipping comment linker"; \
	fi

_pattern-reporter:
	@echo "--- Pattern reporter ---"
	@if [ -f "$(ENRICHMENT_FILE)" ] && [ -x "$(SCRIPTS_PYTHON)" ]; then \
		$(SCRIPTS_PYTHON) $(SCRIPTS_DIR)/insights/pattern_reporter.py \
			--input-dir $(ARCH_DIR) \
			--output $(PATTERN_FILE); \
	else \
		echo "[INFO] No enrichment data — skipping pattern reporter"; \
	fi

architecture-enrichment: ## Run tree-sitter enrichment pass (requires scripts venv)
	@echo "=== Tree-sitter Architecture Enrichment ==="
	@$(MAKE) _enrich-treesitter
	@$(MAKE) _comment-linker
	@$(MAKE) _pattern-reporter
	@echo "Enrichment complete."

_report:
	@echo "--- Architecture report ---"
	@$(PYTHON) $(SCRIPTS_DIR)/reports/architecture_report.py \
		--input-dir $(ARCH_DIR) \
		--output $(ARCH_DIR)/architecture.report.md

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
# architecture-report — generate Markdown report from Layer 2 artifacts
# ---------------------------------------------------------------------------

architecture-report: ## Generate architecture.report.md from Layer 2 artifacts
	@echo "=== Generating Architecture Report ==="
	@if [ ! -f $(GRAPH_FILE) ]; then \
		echo "ERROR: $(GRAPH_FILE) not found. Run 'make architecture' first."; \
		exit 1; \
	fi
	@$(MAKE) _report
	@echo "Report written to $(ARCH_DIR)/architecture.report.md"

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
		$(ARCH_DIR)/architecture.report.md \
		$(ARCH_DIR)/cross_layer_flows.json \
		$(ARCH_DIR)/high_impact_nodes.json \
		$(ARCH_DIR)/parallel_zones.json \
		$(ARCH_DIR)/treesitter_enrichment.json \
		$(ARCH_DIR)/comment_insights.json \
		$(ARCH_DIR)/pattern_insights.json \
		$(ARCH_DIR)/views \
		$(ARCH_DIR)/tmp
	@echo "Cleaned. Committed artifacts in $(ARCH_DIR)/ may remain (e.g., README.md)."

# ---------------------------------------------------------------------------
# Gen-Eval — generator-evaluator testing
# ---------------------------------------------------------------------------

GENEVAL_DIR        ?= agent-coordinator
GENEVAL_DESCRIPTOR ?= $(GENEVAL_DIR)/evaluation/gen_eval/descriptors/agent-coordinator.yaml
GENEVAL_PYTHON     ?= $(GENEVAL_DIR)/.venv/bin/python
GENEVAL_OUTPUT     ?= .
GENEVAL_MODE       ?= template-only
GENEVAL_PARALLEL   ?= 5
GENEVAL_CATEGORIES ?=

gen-eval: ## Run gen-eval in template-only mode (fast, no LLM)
	@if [ ! -f "$(GENEVAL_DESCRIPTOR)" ]; then \
		echo "ERROR: Descriptor not found at $(GENEVAL_DESCRIPTOR)"; \
		echo "  Set GENEVAL_DESCRIPTOR=<path> or create one with /gen-eval-scenario"; \
		exit 1; \
	fi
	@echo "=== Gen-Eval ($(GENEVAL_MODE)) ==="
	@cd $(GENEVAL_DIR) && $(GENEVAL_PYTHON) -m evaluation.gen_eval \
		--descriptor $(patsubst $(GENEVAL_DIR)/%,%,$(GENEVAL_DESCRIPTOR)) \
		--mode $(GENEVAL_MODE) \
		--parallel $(GENEVAL_PARALLEL) \
		--no-services \
		--report-format both \
		--output-dir $(GENEVAL_OUTPUT) \
		$(if $(GENEVAL_CATEGORIES),--categories $(GENEVAL_CATEGORIES),) \
		--verbose

gen-eval-augmented: ## Run gen-eval with CLI-augmented LLM generation (subscription-covered)
	@$(MAKE) gen-eval GENEVAL_MODE=cli-augmented

# ---------------------------------------------------------------------------
# decisions — regenerate per-capability decision index from session-log tags
# ---------------------------------------------------------------------------
#
# Walks openspec/changes/ for session-log.md files, extracts Decision bullets
# tagged `architectural: <capability>`, and writes one markdown file per
# capability under docs/decisions/. Idempotent — safe to re-run.
#
# CI runs this target and fails if `git diff docs/decisions/` is non-empty,
# catching stale indices caused by missing regeneration after new tags land.

.PHONY: decisions
decisions: ## Regenerate docs/decisions/ from architectural tags in session-logs
	@$(PYTHON) skills/explore-feature/scripts/archive_index.py \
		--emit-decisions \
		--archive-root openspec/changes \
		--decisions-output-dir docs/decisions \
		--capabilities-root openspec/specs

.PHONY: context-refresh context-refresh-check
context-refresh: ## Regenerate all deterministic context producers (documentation, contracts, decisions)
	@$(PYTHON) skills/project-context-refresh/scripts/cli.py generate-all

context-refresh-check: ## Read-only, mtime-independent drift check for all context producers (exit 2 = drift)
	@$(PYTHON) skills/project-context-refresh/scripts/cli.py check-all

.PHONY: refresh-project-context refresh-project-context-check
refresh-project-context: ## Orchestrate every configured context producer into one durable operation + emit the manifest (ri-07)
	@$(PYTHON) skills/project-context-refresh/scripts/cli.py refresh

refresh-project-context-check: ## Read-only orchestrated refresh drift check (exit 0 fresh / 2 drift / 1 failed)
	@$(PYTHON) skills/project-context-refresh/scripts/cli.py refresh-check

# Composed deterministic context drift gate (ri-10)
#
# The local reproduction of the blocking CI check, and the only thing CI runs --
# so a failed build is reproduced verbatim here rather than approximated. It
# composes the deterministic producers, architecture freshness against committed
# provenance, and work-package context-impact validation scoped to the diff
# against CONTEXT_GATE_BASE.
#
# Exit codes come from ri-10's classification, not from the refresh outcome:
#   0  fresh, or only informational drift / absent optional owners
#   2  blocking drift -- committed managed output is stale
#   1  a producer failed, or the gate's apparatus could not run
#
# `--strict-legacy` is deliberately never passed: most work-package files predate
# the context_impact contract, and ri-08's progressive enforcement keyed on
# whether a declaration block exists is the intended migration path.
#
# CONTEXT_GATE_EVENT is the triggering event the run answers for. CI passes
# `github.event_name`; a local run leaves it EMPTY, which selects the strict
# rule -- every blocking finding fails the gate. That default is deliberate: it
# is the verdict this target gave before the event axis existed, so every caller
# that predates it (a developer at a shell, main_convergence's drift check) is
# unchanged. Passing `--event pull_request` reproduces the more permissive CI
# rule, under which drift inherited from CONTEXT_GATE_BASE is reported without
# failing. The flag is omitted rather than passed empty, because an empty event
# name is not a rule the gate has -- it is an error, and would exit 1.

CONTEXT_GATE_BASE ?= main
CONTEXT_GATE_EVENT ?=

.PHONY: context-drift-gate
context-drift-gate: ## Composed deterministic context drift gate (exit 0 fresh / 2 blocking drift / 1 failure)
	@$(PYTHON) skills/project-context-refresh/scripts/cli.py gate --base $(CONTEXT_GATE_BASE) \
		$(if $(CONTEXT_GATE_EVENT),--event $(CONTEXT_GATE_EVENT))

# Enablement Consistency Gate (ri-13)
#
# Asks one build-time question: is the semantic-context injection default this
# tree declares authorized by the evidence this tree carries? It compares the
# single `INJECTION_DEFAULT_ENABLED` declaration in
# skills/context-engineering/scripts/semantic_context.py against the recorded
# evaluation report at docs/evaluation/semantic-context/report.json, applying
# design decision D12's expiry conditions. A failure names every condition
# it found unmet.
#
#   0  authorized, or nothing is claimed (the default is disabled)
#   1  the gate could not read what it needed to decide
#   2  the evidence is current and schema-valid, and its verdict is not a pass
#   3  the evidence is absent or has expired
#
# Those are the gate's own codes. `make` collapses any recipe failure to its own
# exit 2, printing the real one as `Error <n>`, so a caller that needs to tell 2
# from 3 runs the module directly rather than through this target.
#
# It adds NOTHING at runtime. ri-12's per-request fallbacks are already total and
# already fail closed; this gate operates on the justification for the default,
# which the runtime cannot see. See docs/evaluation/semantic-context/README.md.
#
# EMBEDDING_CONTRACT is the JSON EmbeddingContract the tree is configured with.
# It is optional only because the default is off: with the default enabled, an
# unsupplied contract is an unmet condition rather than a waived one, because an
# unchecked embedding fingerprint is not a matching one.

EMBEDDING_CONTRACT ?=

.PHONY: semantic-enablement-gate
semantic-enablement-gate: ## Enablement consistency gate: injection default vs. its evidence (0 ok / 2 fail / 3 no evidence / 1 failure)
	@PYTHONPATH=packages/context-eval/src $(PYTHON) -m context_eval.enablement_gate \
		--repository-root . \
		$(if $(EMBEDDING_CONTRACT),--embedding-contract $(EMBEDDING_CONTRACT),)
# ---------------------------------------------------------------------------
# atlas — interactive HTML view of the architecture graph
# ---------------------------------------------------------------------------

.PHONY: atlas atlas-check
atlas: ## Render docs/architecture-analysis/atlas/index.html from the architecture graph
	@$(PYTHON) skills/codebase-atlas/scripts/build_atlas.py

atlas-check: ## Read-only freshness check for the rendered atlas (exit 2 = stale)
	@$(PYTHON) skills/codebase-atlas/scripts/build_atlas.py --check
