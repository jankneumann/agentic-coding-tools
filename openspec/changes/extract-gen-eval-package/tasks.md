# Tasks — Extract gen-eval into a reusable package

> Test-first ordering within each phase. Each implementation task lists the test task it depends on. Spec / contract / design references are listed inline.

## 1. Package scaffold

- [x] 1.1 Write smoke test for empty package import — confirms `import gen_eval` resolves to the new package, not the legacy location. **(S)**
  **Spec scenarios**: gen-eval-framework.canonical-module-name
  **Design decisions**: D1, D2
  **Dependencies**: None
- [x] 1.2 Create `packages/gen-eval/` skeleton: `pyproject.toml`, `src/gen_eval/__init__.py` (empty re-exports), `README.md` stub, `tests/__init__.py`, `examples/` placeholder. Verify with task 1.1 that `cd packages/gen-eval && uv sync && uv run python -c "import gen_eval"` succeeds. **(S)**
  **Spec scenarios**: gen-eval-framework.distributable-python-package (the relative-path-install scenario)
  **Design decisions**: D1, D2
  **Dependencies**: 1.1
- [x] 1.3 Configure `packages/gen-eval/pyproject.toml` with the four optional extras (`mcp`, `sdk`, `db`, `all`), the `gen-eval` console script entry point, and the `uv_build` backend per D2. **(S)**
  **Design decisions**: D2, D4
  **Dependencies**: 1.2

- [x] 1.C **Checkpoint**: `cd packages/gen-eval && uv sync && uv run pytest -q` green; `uv build` produces a wheel.

## 2. Framework code move

- [x] 2.1 Write parity test: pick three representative public APIs (e.g., `gen_eval.run_evaluation`, `gen_eval.openspec_seed.parse_openspec_change`, `gen_eval.evaluator.Evaluator`) and assert they exist + have the expected signatures after the move. **(M)**
  **Spec scenarios**: gen-eval-framework.canonical-module-name, gen-eval-framework.module-discovery-and-import-boundary
  **Design decisions**: D1, D3
  **Dependencies**: 1.3
- [x] 2.2 Move all 23 `.py` files from `agent-coordinator/evaluation/gen_eval/` (excluding `mcp_service.py` and `clients/mcp_client.py`) to `packages/gen-eval/src/gen_eval/`. Update `gen_eval/__init__.py` to re-export the existing public API. Use `git mv` to preserve history. **(L — flagged, but splitting wouldn't reduce risk; single atomic move keeps imports consistent)**
  **Spec scenarios**: gen-eval-framework.canonical-module-name
  **Design decisions**: D1
  **Dependencies**: 2.1
- [x] 2.3 Move `mcp_service.py` and `clients/mcp_client.py` and wrap their `fastmcp` imports in a try/except per D4 (raise `ImportError` with `[mcp]` install hint). **(S)**
  **Spec scenarios**: gen-eval-framework.optional-mcp-service-extra
  **Design decisions**: D4
  **Dependencies**: 2.2
- [x] 2.4 **Surgical extraction of `GenEvalMetrics`.** Cut the `GenEvalMetrics` dataclass out of `agent-coordinator/evaluation/metrics.py` and paste it into a new file `packages/gen-eval/src/gen_eval/metrics.py`. Leave the remaining 10 classes (`TimingMetric`, `TokenUsage`, `CorrectnessMetrics`, `CoordinationMetrics`, `SafetyMetrics`, `ParallelizationMetrics`, `TaskMetrics`, `AggregatedMetrics`, `TrialMetrics`, `MetricsCollector`) and `compute_effect_size` in place — they are coordinator-domain, consumed by `evaluation/ablation.py`, `evaluation/reports/generator.py`, and four coordinator test files. Update `gen_eval/reports.py` import from `from evaluation.metrics import GenEvalMetrics` to `from gen_eval.metrics import GenEvalMetrics`. Verify no other coordinator imports break with `cd agent-coordinator && uv run pytest tests/test_evaluation/ -m "not e2e and not integration"`. **(S)**
  **Spec scenarios**: gen-eval-framework.module-discovery-and-import-boundary (framework has zero imports from agent-coordinator)
  **Design decisions**: D3
  **Dependencies**: 2.2
- [x] 2.4.1 **Surface test**: add `packages/gen-eval/tests/test_metrics_surface.py` asserting the exact public surface of `gen_eval.metrics`. Use an explicit allowlist rather than a `_`-prefix filter so the assertion fails loudly if any unrelated symbol is reintroduced: `assert {n for n in dir(gen_eval.metrics) if not n.startswith("_")} == {"GenEvalMetrics"}, f"unexpected public names: {sorted(n for n in dir(gen_eval.metrics) if not n.startswith('_'))}"`. The test message lists the unexpected names so the failure is self-diagnosing. Guards against re-importing unrelated coordinator metrics classes during future refactors. **(XS)**
  **Spec scenarios**: gen-eval-framework.module-discovery-and-import-boundary
  **Design decisions**: D3
  **Dependencies**: 2.4
- [x] 2.5 Move package-shipped data: `schemas/`, `dtu/` (templates only — drop `dtu/*/fidelity-report.json`), and `evaluation/gen_eval/descriptors/sample-frontend.yaml` → `packages/gen-eval/tests/fixtures/sample-descriptor.yaml`. **(S)**
  **Spec scenarios**: gen-eval-framework.framework-consumer-data-split
  **Design decisions**: D1, D7
  **Dependencies**: 2.2

- [x] 2.C **Checkpoint**: parity test 2.1 passes; `grep -rE "from (agent_coordinator|src\.coordination_)" packages/gen-eval/src/` is empty; `grep -r "from evaluation.gen_eval" packages/gen-eval/src/` is empty.

## 3. Package tests + CI

- [x] 3.1 Relocate gen-eval's 29 existing unit-test files from `agent-coordinator/tests/test_evaluation/test_gen_eval/` (the actual path — note the `test_` prefix on each segment) into `packages/gen-eval/tests/`. Adjust imports from `evaluation.gen_eval.*` to `gen_eval.*` and `evaluation.metrics import GenEvalMetrics` to `gen_eval.metrics import GenEvalMetrics`. Delete the now-empty `agent-coordinator/tests/test_evaluation/test_gen_eval/` directory. Update `wp-package-tests.scope.write_allow` to include this source path so the relocation is in-scope. **(M)**
  **Design decisions**: D1
  **Dependencies**: 2.5
- [x] 3.2 Write a test that asserts `from gen_eval.mcp_service import GenEvalMCPService` raises `ImportError` in a venv where `fastmcp` is NOT installed (use a subprocess + a clean venv, or a `unittest.mock` import-blocker). **(M)**
  **Spec scenarios**: gen-eval-framework.optional-mcp-service-extra (base-install-lacks-mcp-dependencies)
  **Design decisions**: D4
  **Dependencies**: 2.3
- [x] 3.3 Write a test that asserts a built sdist (`uv build`) contains `schemas/`, `dtu/`, `tests/fixtures/`, `examples/` AND does NOT contain `descriptors/agent-coordinator.yaml` or any file under `manifests/`. **(S)**
  **Spec scenarios**: gen-eval-framework.framework-consumer-data-split (package-does-not-ship-coordinator-specific-descriptors)
  **Design decisions**: D7
  **Dependencies**: 2.5
- [x] 3.4 Add a new CI job `gen-eval-tests` to `.github/workflows/ci.yml` per D10 (uv sync, ruff, mypy, pytest excluding e2e/integration). **(S)**
  **Design decisions**: D10
  **Dependencies**: 3.1, 3.2, 3.3

- [x] 3.C **Checkpoint**: `cd packages/gen-eval && uv run pytest -v` is green; CI job runs and passes on a draft PR.

## 4. agent-coordinator migration

- [x] 4.1 Write a failing test at `agent-coordinator/tests/test_gen_eval_extraction.py` (pinned name for scope hygiene — wp-coordinator-migrate's scope explicitly allows this file rather than the broader `agent-coordinator/tests/**` glob, which would overlap with wp-package-tests' relocation deletes). The test SHALL assert that (a) `from gen_eval.mcp_service import get_gen_eval_service` resolves and (b) the existing `/gen-eval/list-scenarios` endpoint returns at least one scenario. Test must use a started coordinator process or its TestClient. **(M)**
  **Spec scenarios**: gen-eval-framework.optional-mcp-service-extra (agent-coordinator-installs-the-mcp-extra)
  **Design decisions**: D5, D6
  **Dependencies**: 2.C (checkpoint)
- [x] 4.2 Update `agent-coordinator/pyproject.toml`: replace the existing `gen-eval = [...]` optional-deps stub with a path-dep `gen-eval[mcp]` under `[project.dependencies]` and `[tool.uv.sources]` per D5. **(S)**
  **Spec scenarios**: gen-eval-framework.distributable-python-package (agent-coordinator-consumes-the-package)
  **Design decisions**: D5
  **Dependencies**: 4.1
- [x] 4.3 Rewrite all `from evaluation.gen_eval` imports in `agent-coordinator/src/` to `from gen_eval`. Confirmed sites: `src/coordination_api.py` (4 lazy imports), `src/coordination_mcp.py` (6 lazy imports), and any others surfaced by `grep -rn 'evaluation\.gen_eval' agent-coordinator/src/`. Update `evaluation/__init__.py` to remove the `from . import gen_eval` re-export **AND** remove the `"gen_eval"` entry from the module's `__all__` list (if present). Leaving the name in `__all__` after deleting the import would trigger linter warnings (F401/F405) and produce an `AttributeError` for any consumer that does `from evaluation import *`. **Also update** `agent-coordinator/tests/test_check_docker_imports.py` — it embeds two literal `"from evaluation.gen_eval import mcp_service\n"` strings as test fixtures (lines 54 and 210); both need to become `"from gen_eval import mcp_service\n"`. **Also update** `agent-coordinator/CLAUDE.md` line 122 reference (`evaluation.gen_eval.mcp_service` → `gen_eval.mcp_service`). **(S)**
  **Spec scenarios**: gen-eval-framework.canonical-module-name (import-path-migration)
  **Design decisions**: D6
  **Dependencies**: 4.2
- [x] 4.4 Relocate per-project data per D7: `agent-coordinator/evaluation/gen_eval/descriptors/` → `agent-coordinator/evaluation/descriptors/`; `manifests/` → one level up; `scenarios/` → one level up. Delete the now-empty `agent-coordinator/evaluation/gen_eval/` directory. Update any scenario-discovery code that hardcoded the old path. **(M)**
  **Spec scenarios**: gen-eval-framework.framework-consumer-data-split
  **Design decisions**: D7
  **Dependencies**: 4.3
- [x] 4.5 Update `agent-coordinator/Dockerfile` and the surrounding docker-build surfaces per D8 **Strategy A (repo-root build context)**. Five subtasks; all five must land in the same commit because they redefine the Docker build context together:
  - (a) **Dockerfile path updates**. The build context is now repo root, so every `COPY` source path in `agent-coordinator/Dockerfile` SHALL be prefixed with `agent-coordinator/` (e.g. `COPY pyproject.toml uv.lock ./` → `COPY agent-coordinator/pyproject.toml agent-coordinator/uv.lock ./`; `COPY evaluation/ /app/evaluation/` → `COPY agent-coordinator/evaluation/ /app/evaluation/`; same for `src/`, etc.). Add `COPY packages/gen-eval/ /workspace/packages/gen-eval/` BEFORE the `uv sync` step so the `[tool.uv.sources]` path-dep `{ path = "../packages/gen-eval" }` resolves inside the image. Move the `COPY agent-coordinator/evaluation/` line *after* `uv sync` for layer-cache hygiene.
  - (b) **`.github/workflows/ci.yml` coordinator docker-build step**: change `context: agent-coordinator` → `context: .` and `file: Dockerfile` → `file: agent-coordinator/Dockerfile`. **Owned by wp-integration (task 7.6), not this package** — the CI step repoint depends on the Dockerfile changes here being in place first, so it lands after wp-coordinator-migrate completes; wp-package-tests independently adds the gen-eval-tests matrix job (task 3.4). The CI file is therefore touched by three packages but on disjoint stanzas; wp-integration's scope is the merge boundary. The Dockerfile change in subtask (a) and the CI step change are coupled: do not merge wp-coordinator-migrate alone without queuing wp-integration's CI step, or CI will fail (Dockerfile expects repo-root context but CI still passes `context: agent-coordinator`).
  - (c) **`agent-coordinator/docker-compose.yml`**: for the coordinator service, change `build.context` from `.` to `..` (parent dir, which is the repo root from the file's location) and add `build.dockerfile: agent-coordinator/Dockerfile`. Other services in the compose file that don't depend on the gen-eval package keep their existing context.
  - (d) **`agent-coordinator/railway.toml`**: add a top-of-file comment block documenting that the Railway dashboard must be configured with **Source > Root Directory = `/`** and **Build > Dockerfile Path = `agent-coordinator/Dockerfile`** (the dashboard setting takes precedence; the file alone cannot override Source > Root Directory). Add a `dockerfilePath = "agent-coordinator/Dockerfile"` entry that takes effect once the dashboard root is at repo root. Do NOT add a `[build] buildCommand` — under the Dockerfile builder Railway silently ignores `buildCommand`, and Strategy A doesn't need one (the package is in-context).
  - (e) **`agent-coordinator/README.md`**: add a `## Deployment` section documenting (1) the Railway dashboard change as a one-time prerequisite when adopting this version; (2) the rationale (gen-eval lives at `packages/gen-eval/`, a sibling of `agent-coordinator/`, so the Docker build needs to see both); (3) the rollback path if the dashboard change can't be made (revert this change's commit on the deployed branch). Also remove any pre-existing prose that references the old `context: agent-coordinator` build path.
  - Do NOT add an `agent-coordinator/Makefile build-image` target, do NOT add `dist/` to `.gitignore`, do NOT add `--no-sources` to `uv sync`, do NOT add `UV_FIND_LINKS` — these were Option B artifacts that Strategy A obsoletes. **(M)**
  **Design decisions**: D8
  **Dependencies**: 4.4
- [x] 4.6 Run the full `agent-coordinator` test suite locally: `cd agent-coordinator && uv sync --all-extras && uv run pytest -m "not e2e and not integration"`. All must pass. **(S)**
  **Dependencies**: 4.5

- [x] 4.C **Checkpoint**: agent-coordinator tests green; `grep -r "from evaluation.gen_eval" agent-coordinator/` is empty; coordinator boots locally and `/gen-eval/list-scenarios` responds.

## 5. Skill invocation updates (parallel-safe with section 4)

- [x] 5.1 Update `skills/gen-eval/SKILL.md`: replace every `python -m evaluation.gen_eval` with `python -m gen_eval`. Verify the surrounding context (PYTHONPATH assumptions, descriptor-discovery hints) is also updated. **(S)**
  **Design decisions**: D9
  **Dependencies**: 2.C
- [x] 5.2 Update `skills/validate-feature/SKILL.md` phase 4b. Two changes required:
  - Replace the `python -m evaluation.gen_eval` invocation (line 322) with `python -m gen_eval`.
  - **Update the descriptor-discovery glob (line 295)** from `find "$PROJECT_ROOT" -path "*/evaluation/gen_eval/descriptors/*.yaml"` to `find "$PROJECT_ROOT" -path "*/evaluation/descriptors/*.yaml"` so it matches the relocated consumer-side descriptors at `agent-coordinator/evaluation/descriptors/` (per D7). The old glob silently produces zero matches after relocation, which would silently skip gen-eval coverage in /validate-feature. **(S)**
  **Design decisions**: D7, D9
  **Dependencies**: 2.C
- [x] 5.3 Update playwright-validator's Python scripts and SKILL.md per D9. Specifically:
  - `skills/playwright-validator/scripts/cli.py:141`: change `from evaluation.gen_eval.openspec_seed import parse_openspec_change` to `from gen_eval.openspec_seed import parse_openspec_change`. Remove the `sys.path.insert(0, agent-coordinator/)` workaround above the import — once gen-eval is a real installed package, that hack is no longer needed. Retain the `_minimal_parse` fallback (it's now defensive robustness, not legacy compat).
  - `skills/playwright-validator/scripts/findings.py:112`: update the docstring reference `agent_coordinator.evaluation.gen_eval.findings_emitter.BehavioralFinding` → `gen_eval.findings_emitter.BehavioralFinding`. **(S)**
  **Design decisions**: D9
  **Dependencies**: 2.C
- [x] 5.3.1 Update `skills/gen-eval-scenario/SKILL.md`: line 172 contains `from evaluation.gen_eval.models import Scenario` in an embedded Python validation snippet. Change to `from gen_eval.models import Scenario`. (The MCP-tool invocations elsewhere in this skill are unchanged.) **(S)**
  **Design decisions**: D9
  **Dependencies**: 2.C
- [x] 5.4 Run `bash skills/install.sh --mode rsync --deps none --python-tools none` to regenerate `.claude/skills/` and `.agents/skills/` runtime mirrors. Verify no `evaluation.gen_eval` strings remain anywhere in `skills/`, `.claude/skills/`, or `.agents/skills/` (including under `skills/playwright-validator/scripts/` and `skills/gen-eval-scenario/`). **(S)**
  **Design decisions**: D9
  **Dependencies**: 5.1, 5.2, 5.3, 5.3.1

- [x] 5.C **Checkpoint**: BOTH greps must return zero matches across `skills/`, `.claude/skills/`, and `.agents/skills/`:
  - `grep -rn "evaluation\.gen_eval" skills/ .claude/skills/ .agents/skills/` — dotted Python import form.
  - `grep -rn "evaluation/gen_eval" skills/ .claude/skills/ .agents/skills/` — slash path form (catches things like the validate-feature descriptor-discovery glob and any shell-level path references that the dotted grep would miss).
  Excluded: the historical docstring in `findings.py` if it has already been updated to `gen_eval.findings_emitter`.

- [x] 5.5 **Repo-wide stale-reference sweep.** After tasks 4.3 and 5.4 land, the import-rewrite work is complete inside `agent-coordinator/`, `skills/`, and the runtime mirrors — but prose elsewhere in the repo may still reference the legacy paths. Run both greps below at the repo root and update every match (the union — not just the dotted form):
  - `grep -rn "evaluation\.gen_eval" CLAUDE.md README.md docs/ .github/ apps/ 2>/dev/null` — dotted Python import form in prose.
  - `grep -rn "evaluation/gen_eval" CLAUDE.md README.md docs/ .github/ apps/ 2>/dev/null` — slash path form (catches docs that quote shell commands or file paths).
  Update each hit to `gen_eval` / `packages/gen-eval/` as appropriate (the same rewrites tasks 4.3, 5.1–5.4 use inside their respective scopes). Specifically check: top-level `CLAUDE.md`, top-level `README.md`, `docs/parallel-agentic-development.md`, `docs/skills-workflow.md`, `docs/lessons-learned.md`, `.github/PULL_REQUEST_TEMPLATE.md` (if present), `.github/ISSUE_TEMPLATE/*` (if present). **(S)**
  **Design decisions**: D9
  **Dependencies**: 4.3, 5.4

## 6. Examples + adoption docs (parallel-safe with sections 4 and 5)

- [x] 6.1 Write `packages/gen-eval/examples/agentic-assistant-quickstart.md` per spec: complete walkthrough including `uv add` command, descriptor template at `evaluation/descriptors/agentic-assistant.yaml`, optional `[mcp]` install reasoning, and one scenario run end-to-end with expected output. **(M)**
  **Spec scenarios**: gen-eval-framework.documented-consumer-adoption-contract
  **Design decisions**: D1
  **Dependencies**: 2.C
- [x] 6.2 Write `packages/gen-eval/examples/descriptor-template.yaml` — annotated minimal descriptor any consumer can copy + adapt. **(S)**
  **Dependencies**: 6.1
- [x] 6.3 Write `packages/gen-eval/README.md`: public API summary, two install profiles (base and `[mcp]`), pointer to the quickstart, link to spec. **(S)**
  **Spec scenarios**: gen-eval-framework.documented-consumer-adoption-contract
  **Dependencies**: 6.1
- [x] 6.4 Write an ADR in `docs/decisions/` documenting the `packages/` convention and the gen-eval extraction (Context / Decision / Consequences). **(S)**
  **Dependencies**: 6.3

- [x] 6.C **Checkpoint**: a human follows the quickstart end-to-end on a clean clone and produces a working descriptor + one passing scenario.

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
- File-overlap check (post-Strategy-A):
  - `.github/workflows/ci.yml` is touched by exactly two packages on **disjoint stanzas**: `wp-package-tests` adds the new `gen-eval-tests` matrix job (task 3.4); `wp-integration` repoints the existing coordinator `docker-build` step's context + Dockerfile path AND rewrites the smoke-import line (task 7.6). The two stanzas don't collide; `wp-integration` runs after `wp-package-tests` per the DAG, so it picks up the matrix-job edit before adding its own.
  - `agent-coordinator/Dockerfile`, `agent-coordinator/docker-compose.yml`, `agent-coordinator/railway.toml`, `agent-coordinator/README.md` are touched only by `wp-coordinator-migrate` (Strategy A Docker pivot).
  - **No `agent-coordinator/Makefile` or `.gitignore` work in any package.** Those were Option B artifacts; Strategy A obsoletes them.
  - Repo-root prose files (`CLAUDE.md`, `README.md`, `docs/`, `apps/`) and `.github/` non-CI files are touched only by `wp-integration` under task 5.5 (repo-wide stale-reference sweep). `wp-skills-update` already scrubs `skills/`, `.claude/skills/`, `.agents/skills/`.

## 7. Integration

- [x] 7.1 Run `openspec validate extract-gen-eval-package --strict` from the repo root. **(XS)**
  **Dependencies**: 1.C, 2.C, 3.C, 4.C, 5.C, 6.C
- [x] 7.2 Run `make architecture` to refresh `docs/architecture-analysis/` artifacts (gen-eval's component now lives under `packages/`, not `agent-coordinator/`). **(XS)**
  **Dependencies**: 4.C
- [x] 7.3 Run `/validate-feature extract-gen-eval-package` (full validation pass: spec, evidence, deploy smoke, security, e2e). **(M)**
  **Dependencies**: 7.1, 7.2
- [x] 7.4 Manually verify the docker build with the **same context Railway uses after the dashboard change** (repo root, per D8 Strategy A): `docker build -f agent-coordinator/Dockerfile -t agent-coordinator:gen-eval-test .`. The repo-root build context is what makes `COPY packages/gen-eval/` and `COPY agent-coordinator/` both resolve and proves the Railway-compatible build path. **(S)**
- [x] 7.4.1 **In-container import smoke.** After 7.4 succeeds, run `docker run --rm --entrypoint python agent-coordinator:gen-eval-test -c "import gen_eval; import gen_eval.mcp_service; print(gen_eval.__file__)"`. This proves the non-editable path install survived the multi-stage Dockerfile (Codex round-3 finding: an editable install would leave a `.pth` pointing at `/workspace/packages/gen-eval/src/` which only exists in the builder stage, so `docker build` would exit 0 but `import gen_eval` would fail at runtime). The print statement SHALL emit a path under `/app/.venv/lib/python*/site-packages/gen_eval/__init__.py` — not a path under `/workspace/` and not a "module not found" error. **(S)**
  **Design decisions**: D5, D8
  **Dependencies**: 7.4
- [x] 7.5 Run one end-to-end gen-eval scenario inside the built container against a started coordinator to confirm `/gen-eval/run` works. **(S)**
  **Dependencies**: 7.4.1
- [x] 7.6 **CI docker-build step repoint** (owned by wp-integration to avoid scope collision with wp-package-tests on `.github/workflows/ci.yml`, per D8 Strategy A). Update the existing coordinator docker-build step in `.github/workflows/ci.yml`: (a) change `context: agent-coordinator` → `context: .` and `file: Dockerfile` → `file: agent-coordinator/Dockerfile`; (b) rewrite the smoke-import list in the same step from `import evaluation.gen_eval.mcp_service` (or any variant referencing the legacy module path) to `import gen_eval.mcp_service` — the legacy module is removed by task 4.3 and the CI smoke would break in lockstep if not updated. Run the CI workflow locally with `act` (or push a draft PR) to confirm the coordinator docker-build step succeeds with the new context AND the smoke-import resolves. **(S)**
  **Design decisions**: D8, D9
  **Dependencies**: 4.5, 5.4

- [x] 7.C **Checkpoint**: all validate-feature phases green; CI green on the PR; coordinator container runs and serves gen-eval requests.
