# Tasks — Extract gen-eval into a reusable package

> Test-first ordering within each phase. Each implementation task lists the test task it depends on. Spec / contract / design references are listed inline.

## 1. Package scaffold

- [ ] 1.1 Write smoke test for empty package import — confirms `import gen_eval` resolves to the new package, not the legacy location. **(S)**
  **Spec scenarios**: gen-eval-framework.canonical-module-name
  **Design decisions**: D1, D2
  **Dependencies**: None
- [ ] 1.2 Create `packages/gen-eval/` skeleton: `pyproject.toml`, `src/gen_eval/__init__.py` (empty re-exports), `README.md` stub, `tests/__init__.py`, `examples/` placeholder. Verify with task 1.1 that `cd packages/gen-eval && uv sync && uv run python -c "import gen_eval"` succeeds. **(S)**
  **Spec scenarios**: gen-eval-framework.distributable-python-package (the relative-path-install scenario)
  **Design decisions**: D1, D2
  **Dependencies**: 1.1
- [ ] 1.3 Configure `packages/gen-eval/pyproject.toml` with the four optional extras (`mcp`, `sdk`, `db`, `all`), the `gen-eval` console script entry point, and the `uv_build` backend per D2. **(S)**
  **Design decisions**: D2, D4
  **Dependencies**: 1.2

- [ ] 1.C **Checkpoint**: `cd packages/gen-eval && uv sync && uv run pytest -q` green; `uv build` produces a wheel.

## 2. Framework code move

- [ ] 2.1 Write parity test: pick three representative public APIs (e.g., `gen_eval.run_evaluation`, `gen_eval.openspec_seed.parse_openspec_change`, `gen_eval.evaluator.Evaluator`) and assert they exist + have the expected signatures after the move. **(M)**
  **Spec scenarios**: gen-eval-framework.canonical-module-name, gen-eval-framework.module-discovery-and-import-boundary
  **Design decisions**: D1, D3
  **Dependencies**: 1.3
- [ ] 2.2 Move all 23 `.py` files from `agent-coordinator/evaluation/gen_eval/` (excluding `mcp_service.py` and `clients/mcp_client.py`) to `packages/gen-eval/src/gen_eval/`. Update `gen_eval/__init__.py` to re-export the existing public API. Use `git mv` to preserve history. **(L — flagged, but splitting wouldn't reduce risk; single atomic move keeps imports consistent)**
  **Spec scenarios**: gen-eval-framework.canonical-module-name
  **Design decisions**: D1
  **Dependencies**: 2.1
- [ ] 2.3 Move `mcp_service.py` and `clients/mcp_client.py` and wrap their `fastmcp` imports in a try/except per D4 (raise `ImportError` with `[mcp]` install hint). **(S)**
  **Spec scenarios**: gen-eval-framework.optional-mcp-service-extra
  **Design decisions**: D4
  **Dependencies**: 2.2
- [ ] 2.4 **Surgical extraction of `GenEvalMetrics`.** Cut the `GenEvalMetrics` dataclass out of `agent-coordinator/evaluation/metrics.py` and paste it into a new file `packages/gen-eval/src/gen_eval/metrics.py`. Leave the remaining 10 classes (`TimingMetric`, `TokenUsage`, `CorrectnessMetrics`, `CoordinationMetrics`, `SafetyMetrics`, `ParallelizationMetrics`, `TaskMetrics`, `AggregatedMetrics`, `TrialMetrics`, `MetricsCollector`) and `compute_effect_size` in place — they are coordinator-domain, consumed by `evaluation/ablation.py`, `evaluation/reports/generator.py`, and four coordinator test files. Update `gen_eval/reports.py` import from `from evaluation.metrics import GenEvalMetrics` to `from gen_eval.metrics import GenEvalMetrics`. Verify no other coordinator imports break with `cd agent-coordinator && uv run pytest tests/test_evaluation/ -m "not e2e and not integration"`. **(S)**
  **Spec scenarios**: gen-eval-framework.module-discovery-and-import-boundary (framework has zero imports from agent-coordinator)
  **Design decisions**: D3
  **Dependencies**: 2.2
- [ ] 2.4.1 **Surface test**: add `packages/gen-eval/tests/test_metrics_surface.py` asserting `gen_eval.metrics` exposes exactly `{"GenEvalMetrics"}` (plus dunder names). Guards against re-importing unrelated coordinator metrics classes during future refactors. **(XS)**
  **Spec scenarios**: gen-eval-framework.module-discovery-and-import-boundary
  **Design decisions**: D3
  **Dependencies**: 2.4
- [ ] 2.5 Move package-shipped data: `schemas/`, `dtu/` (templates only — drop `dtu/*/fidelity-report.json`), and `evaluation/gen_eval/descriptors/sample-frontend.yaml` → `packages/gen-eval/tests/fixtures/sample-descriptor.yaml`. **(S)**
  **Spec scenarios**: gen-eval-framework.framework-consumer-data-split
  **Design decisions**: D1, D7
  **Dependencies**: 2.2

- [ ] 2.C **Checkpoint**: parity test 2.1 passes; `grep -rE "from (agent_coordinator|src\.coordination_)" packages/gen-eval/src/` is empty; `grep -r "from evaluation.gen_eval" packages/gen-eval/src/` is empty.

## 3. Package tests + CI

- [ ] 3.1 Relocate gen-eval's 29 existing unit-test files from `agent-coordinator/tests/test_evaluation/test_gen_eval/` (the actual path — note the `test_` prefix on each segment) into `packages/gen-eval/tests/`. Adjust imports from `evaluation.gen_eval.*` to `gen_eval.*` and `evaluation.metrics import GenEvalMetrics` to `gen_eval.metrics import GenEvalMetrics`. Delete the now-empty `agent-coordinator/tests/test_evaluation/test_gen_eval/` directory. Update `wp-package-tests.scope.write_allow` to include this source path so the relocation is in-scope. **(M)**
  **Design decisions**: D1
  **Dependencies**: 2.5
- [ ] 3.2 Write a test that asserts `from gen_eval.mcp_service import GenEvalMCPService` raises `ImportError` in a venv where `fastmcp` is NOT installed (use a subprocess + a clean venv, or a `unittest.mock` import-blocker). **(M)**
  **Spec scenarios**: gen-eval-framework.optional-mcp-service-extra (base-install-lacks-mcp-dependencies)
  **Design decisions**: D4
  **Dependencies**: 2.3
- [ ] 3.3 Write a test that asserts a built sdist (`uv build`) contains `schemas/`, `dtu/`, `tests/fixtures/`, `examples/` AND does NOT contain `descriptors/agent-coordinator.yaml` or any file under `manifests/`. **(S)**
  **Spec scenarios**: gen-eval-framework.framework-consumer-data-split (package-does-not-ship-coordinator-specific-descriptors)
  **Design decisions**: D7
  **Dependencies**: 2.5
- [ ] 3.4 Add a new CI job `gen-eval-tests` to `.github/workflows/ci.yml` per D10 (uv sync, ruff, mypy, pytest excluding e2e/integration). **(S)**
  **Design decisions**: D10
  **Dependencies**: 3.1, 3.2, 3.3

- [ ] 3.C **Checkpoint**: `cd packages/gen-eval && uv run pytest -v` is green; CI job runs and passes on a draft PR.

## 4. agent-coordinator migration

- [ ] 4.1 Write a failing test in `agent-coordinator/tests/` that confirms `from gen_eval.mcp_service import get_gen_eval_service` resolves AND that the existing `/gen-eval/list-scenarios` endpoint returns at least one scenario. Test must use a started coordinator process or its TestClient. **(M)**
  **Spec scenarios**: gen-eval-framework.optional-mcp-service-extra (agent-coordinator-installs-the-mcp-extra)
  **Design decisions**: D5, D6
  **Dependencies**: 2.C (checkpoint)
- [ ] 4.2 Update `agent-coordinator/pyproject.toml`: replace the existing `gen-eval = [...]` optional-deps stub with a path-dep `gen-eval[mcp]` under `[project.dependencies]` and `[tool.uv.sources]` per D5. **(S)**
  **Spec scenarios**: gen-eval-framework.distributable-python-package (agent-coordinator-consumes-the-package)
  **Design decisions**: D5
  **Dependencies**: 4.1
- [ ] 4.3 Rewrite all `from evaluation.gen_eval` imports in `agent-coordinator/src/` to `from gen_eval`. Confirmed sites: `src/coordination_api.py` (4 lazy imports), `src/coordination_mcp.py` (6 lazy imports), and any others surfaced by `grep -rn 'evaluation\.gen_eval' agent-coordinator/src/`. Update `evaluation/__init__.py` to remove the `from . import gen_eval` re-export. **Also update** `agent-coordinator/tests/test_check_docker_imports.py` — it embeds two literal `"from evaluation.gen_eval import mcp_service\n"` strings as test fixtures (lines 54 and 210); both need to become `"from gen_eval import mcp_service\n"`. **Also update** `agent-coordinator/CLAUDE.md` line 122 reference (`evaluation.gen_eval.mcp_service` → `gen_eval.mcp_service`). **(S)**
  **Spec scenarios**: gen-eval-framework.canonical-module-name (import-path-migration)
  **Design decisions**: D6
  **Dependencies**: 4.2
- [ ] 4.4 Relocate per-project data per D7: `agent-coordinator/evaluation/gen_eval/descriptors/` → `agent-coordinator/evaluation/descriptors/`; `manifests/` → one level up; `scenarios/` → one level up. Delete the now-empty `agent-coordinator/evaluation/gen_eval/` directory. Update any scenario-discovery code that hardcoded the old path. **(M)**
  **Spec scenarios**: gen-eval-framework.framework-consumer-data-split
  **Design decisions**: D7
  **Dependencies**: 4.3
- [ ] 4.5 Update `agent-coordinator/Dockerfile` per D8 **Option B (wheel install)**. Specifically: (a) add `COPY dist/gen_eval-*.whl /tmp/wheels/` and `ENV UV_FIND_LINKS=/tmp/wheels` before the `uv sync` step; (b) **add `--no-sources` to the Dockerfile's `uv sync` invocation** (or set `UV_NO_SOURCES=1`) so `[tool.uv.sources]` (which points at `../packages/gen-eval`, unreachable from the Docker context) is bypassed and the wheel from `UV_FIND_LINKS` is the resolved source; (c) move the `COPY evaluation/` line *after* `uv sync` for layer-cache hygiene; (d) keep the existing `context: agent-coordinator` everywhere (Railway service root unchanged, ci.yml docker-build context unchanged, docker-compose.yml unchanged). Add an `agent-coordinator/Makefile` target `build-image` that runs `cd ../packages/gen-eval && uv build --out-dir ../../agent-coordinator/dist` before the docker build. Add `dist/` to `agent-coordinator/.gitignore`. **Update `agent-coordinator/railway.toml`** to add a `[build]` section with a `buildCommand` that runs the gen-eval wheel build before the Docker build (Railway has no pre-build hook by default; the buildCommand is the supported entry point). Document the new `make build-image` workflow AND the Railway buildCommand in `agent-coordinator/README.md` and explain that the path-dep is editable locally but installs as a wheel inside Docker. **(M)**
  **Design decisions**: D8
  **Dependencies**: 4.4
- [ ] 4.6 Run the full `agent-coordinator` test suite locally: `cd agent-coordinator && uv sync --all-extras && uv run pytest -m "not e2e and not integration"`. All must pass. **(S)**
  **Dependencies**: 4.5

- [ ] 4.C **Checkpoint**: agent-coordinator tests green; `grep -r "from evaluation.gen_eval" agent-coordinator/` is empty; coordinator boots locally and `/gen-eval/list-scenarios` responds.

## 5. Skill invocation updates (parallel-safe with section 4)

- [ ] 5.1 Update `skills/gen-eval/SKILL.md`: replace every `python -m evaluation.gen_eval` with `python -m gen_eval`. Verify the surrounding context (PYTHONPATH assumptions, descriptor-discovery hints) is also updated. **(S)**
  **Design decisions**: D9
  **Dependencies**: 2.C
- [ ] 5.2 Update `skills/validate-feature/SKILL.md` phase 4b. Two changes required:
  - Replace the `python -m evaluation.gen_eval` invocation (line 322) with `python -m gen_eval`.
  - **Update the descriptor-discovery glob (line 295)** from `find "$PROJECT_ROOT" -path "*/evaluation/gen_eval/descriptors/*.yaml"` to `find "$PROJECT_ROOT" -path "*/evaluation/descriptors/*.yaml"` so it matches the relocated consumer-side descriptors at `agent-coordinator/evaluation/descriptors/` (per D7). The old glob silently produces zero matches after relocation, which would silently skip gen-eval coverage in /validate-feature. **(S)**
  **Design decisions**: D7, D9
  **Dependencies**: 2.C
- [ ] 5.3 Update playwright-validator's Python scripts and SKILL.md per D9. Specifically:
  - `skills/playwright-validator/scripts/cli.py:141`: change `from evaluation.gen_eval.openspec_seed import parse_openspec_change` to `from gen_eval.openspec_seed import parse_openspec_change`. Remove the `sys.path.insert(0, agent-coordinator/)` workaround above the import — once gen-eval is a real installed package, that hack is no longer needed. Retain the `_minimal_parse` fallback (it's now defensive robustness, not legacy compat).
  - `skills/playwright-validator/scripts/findings.py:112`: update the docstring reference `agent_coordinator.evaluation.gen_eval.findings_emitter.BehavioralFinding` → `gen_eval.findings_emitter.BehavioralFinding`. **(S)**
  **Design decisions**: D9
  **Dependencies**: 2.C
- [ ] 5.3.1 Update `skills/gen-eval-scenario/SKILL.md`: line 172 contains `from evaluation.gen_eval.models import Scenario` in an embedded Python validation snippet. Change to `from gen_eval.models import Scenario`. (The MCP-tool invocations elsewhere in this skill are unchanged.) **(S)**
  **Design decisions**: D9
  **Dependencies**: 2.C
- [ ] 5.4 Run `bash skills/install.sh --mode rsync --deps none --python-tools none` to regenerate `.claude/skills/` and `.agents/skills/` runtime mirrors. Verify no `evaluation.gen_eval` strings remain anywhere in `skills/`, `.claude/skills/`, or `.agents/skills/` (including under `skills/playwright-validator/scripts/` and `skills/gen-eval-scenario/`). **(S)**
  **Design decisions**: D9
  **Dependencies**: 5.1, 5.2, 5.3, 5.3.1

- [ ] 5.C **Checkpoint**: BOTH greps must return zero matches across `skills/`, `.claude/skills/`, and `.agents/skills/`:
  - `grep -rn "evaluation\.gen_eval" skills/ .claude/skills/ .agents/skills/` — dotted Python import form.
  - `grep -rn "evaluation/gen_eval" skills/ .claude/skills/ .agents/skills/` — slash path form (catches things like the validate-feature descriptor-discovery glob and any shell-level path references that the dotted grep would miss).
  Excluded: the historical docstring in `findings.py` if it has already been updated to `gen_eval.findings_emitter`.

## 6. Examples + adoption docs (parallel-safe with sections 4 and 5)

- [ ] 6.1 Write `packages/gen-eval/examples/agentic-assistant-quickstart.md` per spec: complete walkthrough including `uv add` command, descriptor template at `evaluation/descriptors/agentic-assistant.yaml`, optional `[mcp]` install reasoning, and one scenario run end-to-end with expected output. **(M)**
  **Spec scenarios**: gen-eval-framework.documented-consumer-adoption-contract
  **Design decisions**: D1
  **Dependencies**: 2.C
- [ ] 6.2 Write `packages/gen-eval/examples/descriptor-template.yaml` — annotated minimal descriptor any consumer can copy + adapt. **(S)**
  **Dependencies**: 6.1
- [ ] 6.3 Write `packages/gen-eval/README.md`: public API summary, two install profiles (base and `[mcp]`), pointer to the quickstart, link to spec. **(S)**
  **Spec scenarios**: gen-eval-framework.documented-consumer-adoption-contract
  **Dependencies**: 6.1
- [ ] 6.4 Write an ADR in `docs/decisions/` documenting the `packages/` convention and the gen-eval extraction (Context / Decision / Consequences). **(S)**
  **Dependencies**: 6.3

- [ ] 6.C **Checkpoint**: a human follows the quickstart end-to-end on a clean clone and produces a working descriptor + one passing scenario.

## Parallelizability summary

After 2.C the DAG forks. The four packages below have no write-scope overlap and can run in parallel agents:

```
wp-package-scaffold → wp-framework-move ──┬─→ wp-package-tests       (CI workflow, package tests)
                                          ├─→ wp-coordinator-migrate (coordinator pyproject, src, Dockerfile, data move, leftover test fixes)
                                          ├─→ wp-skills-update       (skills/*, playwright-validator scripts, gen-eval-scenario, runtime mirrors)
                                          └─→ wp-examples-doc        (packages/gen-eval/README, examples/, docs/decisions/)
                                              ↓
                                          wp-integration            (validate + docker smoke; converge)
```

- Independent: 4 packages (post-2.C).
- Sequential chains: 1 (scaffold → move → integration).
- Max parallel width: 4.
- File-overlap check: post-D8-Option-B, `.github/workflows/ci.yml` is touched only by `wp-package-tests` (adds the gen-eval test matrix job *and* the pre-build wheel step required by Option B). `wp-coordinator-migrate` no longer needs to edit ci.yml because the Docker context is unchanged. `agent-coordinator/Makefile` and `.gitignore` are exclusively in `wp-coordinator-migrate`.

## 7. Integration

- [ ] 7.1 Run `openspec validate extract-gen-eval-package --strict` from the repo root. **(XS)**
  **Dependencies**: 1.C, 2.C, 3.C, 4.C, 5.C, 6.C
- [ ] 7.2 Run `make architecture` to refresh `docs/architecture-analysis/` artifacts (gen-eval's component now lives under `packages/`, not `agent-coordinator/`). **(XS)**
  **Dependencies**: 4.C
- [ ] 7.3 Run `/validate-feature extract-gen-eval-package` (full validation pass: spec, evidence, deploy smoke, security, e2e). **(M)**
  **Dependencies**: 7.1, 7.2
- [ ] 7.4 Manually verify the docker build with the **same context Railway uses** (`agent-coordinator/`, per D8 Option B): first run `make -C agent-coordinator build-image` (which builds the wheel into `agent-coordinator/dist/`), then `docker build -f agent-coordinator/Dockerfile -t agent-coordinator:gen-eval-test agent-coordinator/`. The `agent-coordinator/` build context is what makes `COPY dist/gen_eval-*.whl /tmp/wheels/` resolve and proves the Railway-compatible build path. **(S)**
  **Design decisions**: D8
  **Dependencies**: 4.5
- [ ] 7.5 Run one end-to-end gen-eval scenario inside the built container against a started coordinator to confirm `/gen-eval/run` works. **(S)**
  **Dependencies**: 7.4

- [ ] 7.C **Checkpoint**: all validate-feature phases green; CI green on the PR; coordinator container runs and serves gen-eval requests.
