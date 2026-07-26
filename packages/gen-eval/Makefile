# gen-eval package targets.
#
# The root Makefile's `gen-eval` target runs the framework against the
# *coordinator's* descriptor. These targets are for the package itself.

GEN_EVAL_REPORTS ?= evaluation/.reports

.PHONY: help dogfood test lint contracts

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

dogfood: ## Run gen-eval against its own CLI surface
	@# Sync first: the scenarios drive the *installed console script*
	@# resolved from PATH, not the source tree. Without the install this
	@# evaluates whatever stale `gen-eval` happens to be on PATH — or
	@# nothing at all.
	@#
	@# --all-extras is not needed by the CLI itself, but a bare `uv sync`
	@# would *uninstall* the extras from the shared .venv and break the
	@# test suite's mcp/sdk/db imports on the next run.
	@uv sync --all-extras --quiet
	@# --fail-threshold 1.0: every scenario must pass. This is a contract
	@# suite, not a sampling — a single regression should fail the gate.
	@# No --no-services flag: evaluation/descriptor.yaml has no startup
	@# block (UP-4), so passing one would mask a regression that made the
	@# block mandatory again.
	uv run gen-eval \
		--descriptor evaluation/descriptor.yaml \
		--output-dir $(GEN_EVAL_REPORTS) \
		--fail-threshold 1.0 \
		--verbose

test: ## Run the unit suite (excludes slow build/install tests)
	uv run pytest -q -m "not slow"

lint: ## ruff over every Python tree in the package
	uv run ruff check src/ tests/ scripts/

contracts: ## Regenerate the published JSON Schema contract
	uv run python scripts/generate_contract_schemas.py
