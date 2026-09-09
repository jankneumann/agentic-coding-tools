# Validation Report — factory-missions-architecture-alignment

**Run**: 2026-09-08, GX10 (linux/arm64), rootless podman 4.9.3, Playwright chromium 153.0.8010.12
**Task**: 8.1 "Run full `validate-feature` end-to-end on the sample frontend"

This report records the first live end-to-end run of this change. It was
deferred at implementation time for want of Docker and Playwright browser
binaries; both are available here, and the run found five defects that stubbed
unit tests could not reach. Each was fixed with a regression test verified to
fail without the fix (PR #498, commit `ae0cdef0`).

## Deploy

- **Status**: pass
- Stack started via `stack_launcher.py` against `agent-coordinator/docker-compose.yml`
  on podman. `docker_stack.py`'s runtime detection already preferred a live
  podman over a dead docker (issue #433) and needed no change; the
  Docker-compatible API socket (`podman.socket`) had to be started.
- **Defects found and fixed**:
  - `compose up` never passed `--profile api`, so `coordinator-api` never
    started and the stack reported healthy with nothing on the API port.
  - The allocated `api_port` was never handed to compose (the file reads
    `AGENT_COORDINATOR_REST_PORT`), so the API bound the fixed default 8081
    while `.test-env` advertised the allocated port — and two concurrent stacks
    would collide on 8081, which is what allocating a port is for.
  - `down` omitted the profile too, leaking `coordinator-api` between runs.
- **Evidence**: API bound the allocated port (18215) and `/health` returned
  `{"status":"ok","db":"connected","version":"0.2.0"}`.

## Smoke

- **Status**: pass — **11/11** (was 0/11 before the deploy fixes, then 10/11)
- **Defect found and fixed**: the launcher configured `COORDINATION_API_KEYS`
  but published no `API_KEY`, while the smoke fixture defaults to
  `e2e-test-key`. The two never agreed, so `test_valid_credentials_accepted`
  received a 401 from a correctly configured stack. Probed directly:
  `dev-key-001` → 422 (auth passed), `e2e-test-key` → 401.

## gen-eval (Playwright path)

- **Status**: pass — **2/2 scenarios** against real chromium on the live fixture
- **Defect found and fixed**: the default `--test-dir` was
  `test-results/generated/`, which is Playwright's own `outputDir`. Playwright
  clears it before each run, so it deleted the specs it was about to execute,
  ran zero tests, exited 0 and wrote an empty findings file — indistinguishable
  from a genuine clean pass. Default moved to `.generated/`.
- **Falsifiability confirmed**: with a seeded defect (`'Welcome, '` →
  `'Hello, '`) the validator emitted exactly one `behavioral_failure` finding,
  attributed to the right scenario, with the source ref traced to
  `sample.spec.md:16-23`; scenario 2 correctly still passed. Both findings
  files validate against `openspec/schemas/review-findings.schema.json`.
- Also corrected: `sample-descriptor.yaml`'s `startup_cwd` still pointed at the
  pre-extraction `evaluation/gen_eval/fixtures/sample-frontend`.

## Security

- **Status**: DEGRADED (permitted — the phase is non-critical and was run with
  `--allow-degraded-pass`)
- At the time of this run, `run_zap_scan.sh` started its container without host
  networking and so could not reach a `localhost` target; ZAP itself ran
  correctly under podman when invoked directly (66 PASS / 1 WARN).
  dependency-check could not resolve its unqualified image name under podman.
- **Both since fixed** in PR #499 (`e9aec674`) and PR #500 (`0b179e78`): the
  security phase now returns 12 findings (2 medium, 6 low, 4 info) from a live
  target, and dependency-check reports its real blocker (an unseeded NVD
  database) rather than an opaque exit code.
- Artifact from this run: `security-review-report.md` in this directory.

## E2E

- **Status**: pass — **20/20** (`agent-coordinator/tests/e2e -m e2e`) against the
  live podman-backed ParadeDB.

## Rollout

**Not applicable.** This change ships skills, CI wiring and validation tooling.
It has no traffic-serving surface, no feature flag and no user-facing request
path, so the staged-rollout stages (5% → 25% → 50% → 100%) and their traffic
thresholds have nothing to measure. Recording them as "checked" would assert
observations nobody made. The equivalent guard for this class of change is the
test suite and the CI gates, both green on `main`.
