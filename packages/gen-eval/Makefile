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
	@# --min-coverage 1: a floor the contracted surface can actually reach,
	@# not the spec's 80% service figure. Dogfood exercises 10 of 17 flags
	@# (58.8%), so an 80% floor would make this target permanently red even
	@# with D11 completeness fully satisfied — a gate that can never pass is
	@# the mirror of one that can never fail. `1` catches the state that
	@# matters here: declared and tested vocabularies failing to connect at
	@# all, which reads as 0%.
	uv run gen-eval \
		--descriptor evaluation/descriptor.yaml \
		--output-dir $(GEN_EVAL_REPORTS) \
		--fail-threshold 1.0 \
		--min-coverage 1 \
		--verbose
	@# The acceptance gate (D11). Completeness, not a percentage: every
	@# contracted coverage unit is exercised by a scenario or carries a
	@# written reason in evaluation/coverage-exclusions.yaml. The percentage
	@# above is informative; this is what fails the build.
	uv run python scripts/check_coverage_completeness.py \
		--report $(GEN_EVAL_REPORTS)/gen-eval-report.json \
		--exclusions evaluation/coverage-exclusions.yaml

test: ## Run the unit suite (CI's selector, minus slow build/install tests)
	@# `not e2e and not integration` is CI's selector verbatim
	@# (.github/workflows/ci.yml, gen-eval-tests job). It has to match: a
	@# developer entry point that is red where CI is green gets ignored just
	@# as fast as a gate that can never fail, and the next real failure in it
	@# is then invisible. The integration tests resolve scenarios against a
	@# coordinator-repo path that does not exist in this package, so the
	@# previous `-m "not slow"` left this target permanently red on a clean
	@# tree while CI stayed green.
	@#
	@# `not slow` is the one deliberate difference, and it points the safe
	@# way: those build/install tests DO run in CI, so this target is a
	@# strict SUBSET of the CI gate. Green here does not prove green there;
	@# red here is always real. Run `uv run pytest -q -m "not e2e and not
	@# integration"` to reproduce the CI selector exactly.
	uv run pytest -q -m "not slow and not e2e and not integration"

lint: ## ruff over every Python tree in the package
	uv run ruff check src/ tests/ scripts/

contracts: ## Regenerate the published JSON Schema contract
	uv run python scripts/generate_contract_schemas.py
