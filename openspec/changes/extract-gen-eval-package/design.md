# Design — Extract gen-eval into a reusable package

## Context

`gen-eval` is a ~6.5 KLOC generator-evaluator framework that today lives only inside `agent-coordinator/evaluation/gen_eval/` with no `pyproject.toml`. The change extracts it to `packages/gen-eval/` as a pip-installable package, migrates `agent-coordinator` to consume it as a path dependency, and updates all skills that invoke it via `python -m evaluation.gen_eval`. This design captures the load-bearing implementation decisions; the proposal captures the *why* and the rejected alternatives.

## Decisions

### D1 — Package layout (`packages/gen-eval/` with `src/` layout)

```
packages/gen-eval/
  pyproject.toml
  README.md
  src/
    gen_eval/
      __init__.py          # public API exports
      __main__.py          # CLI entry point (was: evaluation/gen_eval/__main__.py)
      evaluator.py
      semantic_judge.py
      fidelity.py
      generator.py
      cli_generator.py
      sdk_generator.py
      hybrid_generator.py
      llm_generator_base.py
      openspec_seed.py
      change_detector.py
      dtu_scaffold.py
      orchestrator.py
      coordinator.py
      config.py
      models.py
      descriptor.py
      manifest.py
      reports.py
      findings_emitter.py
      feedback.py
      metrics.py           # moved from agent-coordinator/evaluation/metrics.py
      mcp_service.py       # conditionally importable; requires [mcp] extra
      clients/
        __init__.py
        base.py
        http_client.py
        mcp_client.py      # conditionally importable; requires [mcp] extra
        cli_client.py
        db_client.py
        wait_client.py
      schemas/
        lock_responses.json
        memory_responses.json
        work_responses.json
      dtu/
        github/descriptor.seed.yaml
        transports/descriptor.seed.yaml
  tests/
    __init__.py
    fixtures/
      sample-descriptor.yaml         # moved from evaluation/gen_eval/descriptors/sample-frontend.yaml
      sample-fixtures/...            # moved from evaluation/gen_eval/fixtures/
    test_evaluator.py
    test_generator.py
    test_orchestrator.py
    ... (existing unit tests, relocated)
  examples/
    agentic-assistant-quickstart.md
    descriptor-template.yaml
```

**Rationale.** `src/` layout (rather than flat) is the modern uv/PEP 621 default — it prevents accidental imports from a non-installed copy during development and matches what `uv init` produces. The `gen_eval` underscore-form is the canonical Python module name; the directory `packages/gen-eval/` uses kebab-case for filesystem readability (consistent with the package's distribution name on PyPI in the future).

### D2 — `pyproject.toml` shape

```toml
[project]
name = "gen-eval"
version = "0.1.0"
description = "Generator-evaluator framework for agentic system testing"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.13",
    "pyyaml>=6.0",
    "jinja2>=3.1",
    "jsonpath-ng>=1.6",
    "httpx>=0.28",
]

[project.optional-dependencies]
mcp = ["fastmcp>=2.0"]
sdk = ["anthropic>=0.94", "openai>=1.50"]
db = ["asyncpg>=0.29"]
all = ["gen-eval[mcp,sdk,db]"]

[project.scripts]
gen-eval = "gen_eval.__main__:main"

[build-system]
requires = ["uv_build>=0.9,<0.10"]
build-backend = "uv_build"

[dependency-groups]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.6", "mypy>=1.13"]
```

**Rationale.** Four optional-extras (mcp, sdk, db, all) match the four lazy-import boundaries in the existing code. `[project.scripts]` adds a `gen-eval` console script as a convenience over `python -m gen_eval`. `uv_build` matches the convention agentic-assistant already uses.

### D3 — Resolving the `evaluation.metrics` reverse coupling

Today: `agent-coordinator/evaluation/metrics.py` defines `GenEvalMetrics`; `gen_eval/reports.py:206` imports it.

**Decision: Move `metrics.py` into the package as `gen_eval/metrics.py`.**

Considered alternatives:
- *Shim with Protocol injection* — would require gen-eval to define a `MetricsProtocol` and accept it via DI. Theoretically more decoupled but no other consumer needs metrics-of-a-different-shape; YAGNI.
- *Stub with no-op default* — package ships a no-op `GenEvalMetrics`, consumer can override. Adds indirection for zero gain since the real metrics live in gen-eval territory anyway (`GenEvalMetrics` literally has gen-eval in the name).
- *Leave in agent-coordinator, expose via callback* — adds a callback parameter to every reports.py call site. Same shape as DI but worse ergonomics.

Moving it in is the only option where the package becomes truly self-contained.

### D4 — Optional `[mcp]` extra wiring

`gen_eval/mcp_service.py` currently does `from fastmcp import …` at module top. After the extraction:

```python
# packages/gen-eval/src/gen_eval/mcp_service.py
try:
    from fastmcp import …
except ImportError as e:
    raise ImportError(
        "gen_eval.mcp_service requires the [mcp] extra. "
        "Install with: uv add 'gen-eval[mcp]'"
    ) from e
```

Same pattern for `gen_eval/clients/mcp_client.py` (uses fastmcp Client). All other modules in the package SHALL NOT import from `fastmcp` at all, so the base install is genuinely mcp-free.

`gen_eval/__init__.py` SHALL NOT re-export anything from `mcp_service` or `mcp_client` at top level — consumers who want them must explicitly `from gen_eval.mcp_service import …`. This keeps `import gen_eval` cheap and dependency-free.

### D5 — agent-coordinator dependency declaration

```toml
# agent-coordinator/pyproject.toml
[project]
dependencies = [
    # ... existing
    "gen-eval[mcp]",  # was: gen-eval = ["jinja2>=3.1.6", "jsonpath-ng>=1.6.0"]
]

[tool.uv.sources]
gen-eval = { path = "../packages/gen-eval", editable = true }
```

`editable = true` is important: this is a monorepo, the coordinator and the package evolve together, and editable installs mean code changes in `packages/gen-eval/src/` are immediately visible in the coordinator's venv without a re-sync.

### D6 — Lazy import sites in `coordination_api.py` and `coordination_mcp.py`

Today (rough sketch):
```python
def get_handler():
    from evaluation.gen_eval.mcp_service import get_gen_eval_service
    return get_gen_eval_service()
```

After:
```python
def get_handler():
    from gen_eval.mcp_service import get_gen_eval_service
    return get_gen_eval_service()
```

Mechanical s/`evaluation.gen_eval.`/`gen_eval.`/g across the coordinator's `src/` tree. The lazy-import pattern is preserved — it's important because (a) it lets the coordinator boot in environments where the `[mcp]` extra isn't installed (e.g., minimal smoke-test containers) and (b) it keeps gen-eval's startup cost out of FastAPI app bootstrap.

### D7 — Data relocation inside agent-coordinator

| Today | After |
|---|---|
| `agent-coordinator/evaluation/gen_eval/descriptors/agent-coordinator.yaml` | `agent-coordinator/evaluation/descriptors/agent-coordinator.yaml` |
| `agent-coordinator/evaluation/gen_eval/manifests/*.manifest.yaml` | `agent-coordinator/evaluation/manifests/*.manifest.yaml` |
| `agent-coordinator/evaluation/gen_eval/scenarios/**` | `agent-coordinator/evaluation/scenarios/**` |
| `agent-coordinator/evaluation/gen_eval/dtu/*/fidelity-report.json` | DELETED (these are generated artifacts; rebuild on demand) |
| `evaluation/gen_eval/descriptors/sample-frontend.yaml` (at repo root, currently the canonical empty home) | MOVED to `packages/gen-eval/tests/fixtures/sample-descriptor.yaml` |
| `evaluation/gen_eval/fixtures/**` (at repo root) | MOVED to `packages/gen-eval/tests/fixtures/` (if anything actually exists there) |
| `evaluation/gen_eval/` (the repo-root carved home) | DELETED entirely once contents relocated |

**Constraint:** the relocation INSIDE `agent-coordinator/evaluation/` (gen_eval/descriptors/ → descriptors/) must happen in a single commit that also updates any descriptor-discovery logic in the coordinator's tests/CI. Otherwise the coordinator's existing gen-eval invocations would still try to find descriptors at the old path.

### D8 — Dockerfile update

`agent-coordinator/Dockerfile:38` today:
```dockerfile
COPY evaluation/ /app/evaluation/
```

After the change, `evaluation/` contains only the relocated `descriptors/`, `manifests/`, `scenarios/` directories — no Python code. The framework arrives via `uv sync` from the path dependency. The `COPY` line stays (for the data) but should be moved AFTER the `uv sync` step so the layer cache invalidates correctly when scenarios change but dependencies don't.

We also need to add `COPY ../packages/gen-eval /workspace/packages/gen-eval` (or arrange the Docker build context so the package is reachable). Likely cleanest: change `docker build` context to the repo root rather than `agent-coordinator/`, with `-f agent-coordinator/Dockerfile`. This is a build-pipeline change and should be documented in the cleanup-feature merge plan.

### D9 — Skill invocation updates

| Skill | Before | After |
|---|---|---|
| `skills/gen-eval/SKILL.md` | `python -m evaluation.gen_eval --descriptor …` | `python -m gen_eval --descriptor …` |
| `skills/validate-feature/SKILL.md` (phase 4b) | same | same |
| `skills/playwright-validator/SKILL.md` | `from evaluation.gen_eval.openspec_seed import parse_openspec_change` (with fallback parser) | `from gen_eval.openspec_seed import parse_openspec_change` (fallback parser can stay as defensive code for environments without gen-eval installed) |
| `skills/gen-eval-scenario/SKILL.md` | `mcp__coordination__create_scenario` | unchanged (MCP tool name is stable; only the underlying service module path changes) |

All `skills/` edits are in **canonical** sources only; runtime mirrors regenerate via `bash skills/install.sh --mode rsync --deps none --python-tools none`.

### D10 — CI changes

Today's `.github/workflows/ci.yml` runs ruff/mypy/pytest scoped to `agent-coordinator/` and infra `skills/`. After this change, we add a third matrix job:

```yaml
gen-eval-tests:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v5
    - run: cd packages/gen-eval && uv sync --all-extras
    - run: cd packages/gen-eval && uv run ruff check
    - run: cd packages/gen-eval && uv run mypy src/
    - run: cd packages/gen-eval && uv run pytest -m "not e2e and not integration"
```

The agent-coordinator job needs to learn about the path dep: `cd agent-coordinator && uv sync --all-extras` already works for path deps, but the working directory and the order of repo checkout matter. Should be a single-line change.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Strangler: `gen_eval/__init__.py` re-exports from `agent_coordinator.evaluation.gen_eval` | Would require `gen-eval` to depend on `agent-coordinator` — inverts the dependency graph. The package should not depend on the service that consumes it. |
| Two-package split (`gen-eval-core` + `gen-eval-mcp`) | Adds a second `pyproject.toml`, second release surface, second test job for marginal benefit. Optional extras give the same install-time flexibility with one package. |
| Keep `evaluation/gen_eval/` at repo root as the package home | Namespace ambiguity during cutover (`evaluation/gen_eval/` at root vs. `agent-coordinator/evaluation/gen_eval/`), and the directory name forces a different convention for the next extraction anyway. |
| Defer the metrics.py move; keep it in agent-coordinator with an injected interface | `GenEvalMetrics` is named for gen-eval and only used inside gen-eval's `reports.py`. No other consumer needs it. Moving it in is the only choice with zero loss of flexibility. |

## Trade-offs

| Accepted | Over | Reason |
|---|---|---|
| Single atomic change (~30 file moves + Dockerfile + skills + pyproject) | Phased two-change rollout | No drift window; the convention is set the moment the change lands. The phased approach saves no work — it just defers half of it. |
| New top-level `packages/` directory | Reusing `evaluation/gen_eval/` at root | Establishes the convention that other planned extractions (Hoverfly, prompt opt, vendor packages) will follow. Convention-cost is paid once. |
| Path-only install in the immediate term | PyPI publishing in this change | PyPI is real release infrastructure (CI publish workflow, version-bump policy, namespace claim, trusted publisher setup). Worth a dedicated change after the first external consumer (agentic-assistant) proves the path-install works. |
| Examples doc as the agentic-assistant adoption proof | Cross-repo PR to agentic-assistant | Real cross-repo PRs cost coordination overhead (separate CI, separate review cycle). The quickstart doc is verifiable inside this repo. If it turns out to be wrong, the agentic-assistant adoption will surface it; cost is one bug-fix change vs. one cross-repo PR. |

## Open Questions

1. **Should we set up a uv workspace** (`packages/*` listed in a root `pyproject.toml` as workspace members) **as part of this change?** Useful when ≥2 packages exist. Recommendation: defer until the second extraction lands; revisit then. Tracking note: when Hoverfly/prompt-opt/etc. land, the second extraction PR should introduce the workspace pyproject.
2. **Should `gen_eval.coordinator` (the optional HTTP integration back to agent-coordinator) be its own extra (`[coordinator]`)?** Currently it's in core (no third-party deps required beyond httpx, which is already core). Lean toward leaving it in core — no install cost, no consumer harm.
3. **CI matrix order**: should agent-coordinator's CI run *after* gen-eval's, since the coordinator now depends on the package? Technically uv resolves path deps fine in any order; ordering matters only for tighter failure attribution. Defer to implementation.

## Verification (how `/validate-feature` will check this)

- **Spec compliance**: `openspec validate extract-gen-eval-package --strict` passes.
- **Static**: zero `from agent_coordinator` or `from src.coordination_` imports in `packages/gen-eval/src/`. Zero `from evaluation.gen_eval` imports anywhere in the repo after the change.
- **Build**: `cd packages/gen-eval && uv build` produces a wheel + sdist; the sdist content matches the data-split requirement (no agent-coordinator-specific descriptors).
- **Coordinator**: `cd agent-coordinator && uv sync --all-extras && uv run pytest` — full coordinator suite green with the package installed via path dep.
- **MCP smoke**: with agent-coordinator running locally, `curl http://localhost:8000/gen-eval/list-scenarios` returns a non-empty response.
- **CLI smoke**: `python -m gen_eval --descriptor packages/gen-eval/tests/fixtures/sample-descriptor.yaml --mode template-only` exits 0.
- **Skills**: all updated SKILL.md invocations reference `python -m gen_eval`; runtime mirrors regenerated; no `evaluation.gen_eval` strings remain in `skills/`.
- **Docker**: `docker build` from the new context produces a working image; `/gen-eval/*` endpoints respond inside the container.
