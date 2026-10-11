# Migrate CI to self-hosted GX10 runners

> Parent roadmap: `roadmap-always-on-agent-automation` · Roadmap item `ri-20`
> Change ID: `migrate-ci-to-self-hosted-gx10-runners`
> Effort: M · Priority: 2 · Depends on: none
> Planned by: autopilot PLAN phase (non-interactive, archetype `architect`). There was no human
> in the loop, so every discovery answer below is an **explicit assumption** (§ Assumptions),
> and Gate 2 is replaced by the supervisor-owned `proposal_approval` gate.

## Why

CI wall-clock time sets how often merge sync windows can run. Every job in `ci.yml` (25 jobs)
and `security.yml` (3 jobs) runs on `ubuntu-latest`. Each run starts from a cold VM: it
installs Python through `uv`, resolves the whole lockfile again, and pays for queueing on the
hosted runners. The always-on GX10 host is a linux/aarch64 machine of the NVIDIA DGX Spark
class. It already holds the vendor CLIs, a warm `uv` cache and podman, and it is idle for most
of the day. Moving the jobs that are compatible to ephemeral, containerized self-hosted runners
on that host should shorten the CI critical path and stop CI from depending on hosted-runner
queueing.

A self-hosted runner that executes pull-request code is a code-execution surface on that host.
For that reason the roadmap treats fork-PR safety and aarch64 parity as first-class
requirements, not as hardening to add later.

## What Changes

1. **Lane manifest (new, `.github/runner-lanes.yaml`).** This file records how every job in
   `ci.yml` and `security.yml` is routed, in a form a machine can read. Each job is either
   `routed`, meaning it follows the lane selector, or `hosted`, meaning it is pinned to
   `ubuntu-latest`. A hosted job carries a `reason_code` from a closed set and a written reason.
   The file also holds the self-hosted label set, the repository variable name and the
   dispatch input name. A JSON Schema (`.github/runner-lanes.schema.json`) validates it.
2. **Workflow routing (`ci.yml` and `security.yml`, on this branch only).**
   - Every `routed` job gets the same canonical `runs-on` expression. It selects the GX10
     label set only when both of these hold:
     - The event is not a fork pull request.
     - The lane resolves to `self-hosted`. The lane comes from the `runner_lane`
       `workflow_dispatch` input, or else from the `CI_RUNNER_LANE` repository variable.
   - In every other case, including when the variable is unset (the default), the expression
     evaluates to `ubuntu-latest`. Merging this change therefore changes no CI behaviour until
     an operator sets the variable.
   - Every routed job's first step is an in-job guard. It fails the job if a fork pull request
     ever reaches a self-hosted runner.
   - Hosted-pinned jobs keep a literal `runs-on: ubuntu-latest`. Each has a justification in
     the manifest. The pinned jobs are the container-engine jobs (`test-integration`,
     `gen-eval`, `test-openbao-live`), `docker-smoke-import` (production image architecture is
     amd64, and it needs a container engine), and the write-token job
     `dependency-update-remediation`.
   - Both workflows gain a `workflow_dispatch` trigger with a `runner_lane` choice input
     (`auto` | `hosted` | `self-hosted`). It is used for A/B measurement and for dry runs.
   - Routed jobs that rely on tools preinstalled on `ubuntu-latest` (for example `npm` in
     `validate-specs`) get an explicit setup step, or rely on the runner image baseline.
3. **Runner host kit (new, `deploy/gx10-runner/`).** This is written and tested, but it is
   never installed by this change. It contains:
   - A pinned arm64 `Containerfile` built on the official `actions-runner` image.
   - A host-side `mint-jitconfig.sh`. It mints a single-use just-in-time runner configuration
     with a host-held credential, so the credential never enters the container.
   - A `cleanup-runner.sh` that removes a runner registration that was never used.
   - A systemd **user** template unit, `gx10-runner@.service`. It runs one `podman run --rm`
     container per instance with `Restart=always`, so each job gets a fresh container. The
     unit is meant to run as a dedicated lingering host user, so the runners start again after
     a reboot.
   - An example environment file.
4. **Measurement and verification tooling (new, `scripts/ci/ci_wallclock.py`).** These are
   pure functions over `gh api` JSON, with a thin CLI:
   - `median` computes the median wall-clock time of successful runs per lane and time window.
   - `compare` applies the acceptance threshold.
   - `verify-run` checks one workflow run against the manifest: each routed job ran on a
     `gx10` runner, each hosted job ran on a GitHub-hosted runner, and every job succeeded.
5. **Operator runbook (new, `docs/guides/self-hosted-ci-runners.md`).** It covers each
   operator-only step with a concrete verification command: host user and linger, credential,
   image build, enabling the units, the fork-approval repository setting, the A/B dry run,
   flipping the variable, measuring wall-clock time, checking ephemerality, checking reboot
   survival, the fork-PR test and rollback.
6. **Tests (new, `skills/tests/ci_runners/`).** Static tests over the workflow YAML, the
   manifest, the systemd unit, the container and host scripts, and the measurement functions.

### Hard boundary (applies to every task and package)

The implementation **may** write workflow YAML on this branch, systemd unit files, container
and runner scripts, docs and tests. It **must not**:
- Register runners or mint registration or JIT tokens.
- Change repository or organization settings or variables.
- Install, enable or start systemd units or containers on any host.
- Push to, or edit workflows on, `main`.

Every outcome that needs one of those actions is an **operator-only step** (tasks.md § 7). It
is not an implementation task.

## Approaches Considered

### Approach A — Lane manifest, inline canonical `runs-on` expression, host-minted JIT runners under systemd user units (**Recommended**)

**Description:** A checked-in manifest classifies every job. Routed jobs carry one canonical
`runs-on` expression that defaults to hosted and excludes forks. That expression appears
verbatim in each job, and a test enforces it. The runners are rootless podman containers, one
job per container. A systemd template unit restarts them. The unit's `ExecStartPre` mints a
single-use JIT config on the host.

- **Pros:**
  - The default is safe: when the variable is unset the result is `ubuntu-latest`, so merging
    is a no-op.
  - It adds no serial routing job, so the critical path does not grow.
  - The manifest is an auditable, machine-readable record of why each job is pinned.
  - The routing credential never enters the container that runs PR code.
  - JIT configs are inherently one job per registration.
  - Per-job tuning after measurement is a one-line manifest change.
- **Cons:**
  - The routing expression is long and repeated about 23 times. A test pins it, but humans
    will find it noisy.
  - Falling back to hosted when the host is down is manual: the operator flips the variable.
  - Container-engine jobs stay hosted in v1.
- **Effort:** M

### Approach B — Routing job (`route`) that computes `runs-on` once, consumed via `needs.route.outputs`

**Description:** A small job on `ubuntu-latest` evaluates lane, fork status and runner
availability (through a token that can list runners), then emits a JSON label array. Every
other job `needs: route` and uses `runs-on: ${{ fromJSON(needs.route.outputs.runs_on) }}`.

- **Pros:**
  - The expression lives in one place.
  - With a token that can list runners, the job could fall back to hosted automatically when
    no GX10 runner is online.
- **Cons:**
  - It adds a serial hosted job of about 15 to 30 s, including queueing, in front of every
    job. That works directly against outcome 2.
  - Every job gains a `needs:` edge, which touches the existing dependency structure and the
    tests that parse it.
  - An automatic availability probe needs a token with administration read scope inside a
    workflow that runs PR code.
- **Effort:** M

### Approach C — actions-runner-controller (ARC) on a single-node k3s cluster on the GX10

**Description:** Run GitHub's Kubernetes runner scale sets on the host, which provide
autoscaled ephemeral pods and container-mode jobs.

- **Pros:**
  - It is the upstream-supported autoscaling and ephemeral model.
  - Container mode could also serve `services:` jobs.
- **Cons:**
  - It brings in Kubernetes as a new operational dependency on a box that runs podman and
    systemd today.
  - It has far more moving parts to secure and keep running.
  - Its scale-set listener needs a GitHub App installed with broader scope.
  - Its value only shows at concurrency levels a single host does not need.
- **Effort:** L

### Selected Approach

**Approach A.** The autopilot PLAN phase chose it at Gate 1 with no human present. It
preserves outcome 2, because it adds no serial routing hop. It keeps merge risk at zero,
because hosted is the default. It satisfies the "auditable over minimal diff" preference
through the manifest. It keeps the trust boundary narrow, because the credential stays on the
host and the container has no engine socket.

Approach B's single source of truth comes back cheaply through the test-enforced canonical
expression. Its automatic fallback is deferred as a follow-up (see design.md D9). Approach C is
recorded as the path to take if engine-backed jobs or multi-host scaling are later required.

## Assumptions (discovery answered by the planner, not by a human)

- **A1. Repository visibility is treated as public (worst case).** Fork PRs must never route to
  self-hosted, even after approval. Approval only lets a fork run start; it then runs on
  `ubuntu-latest`.
- **A2. Runners are registered at repository scope**, not organization scope. They use the
  default runner group, so no other repository can schedule jobs on them.
- **A3. The registration credential is a fine-grained PAT** scoped to this one repository with
  *Administration: read and write* only. It is held on the host as a 0600 file or a systemd
  credential. A GitHub App is the documented upgrade path (design.md D5).
- **A4. The runners run under a dedicated unprivileged host user** (`ghrunner`), never the
  operator's own account, which holds vendor CLI credentials, SSH keys and the coordinator
  stack.
- **A5. Container-engine jobs stay hosted in v1.** These are `services:` containers, Docker
  builds and the podman-driven OpenBao matrix. No container engine socket is exposed inside a
  container that runs PR code.
- **A6. "Measurably drops" means** the median wall-clock time of successful CI runs on the
  self-hosted lane is at most 0.85 × the hosted median. That is a reduction of at least 15 %,
  over at least 5 paired `workflow_dispatch` runs per lane on the same commit, with at least
  20 PR runs per lane in the before/after window as a corroborating measure.
- **A7. The hosted fallback is operator-switched**, by setting `CI_RUNNER_LANE` to `hosted` or
  deleting it. An unset variable means hosted. Automatic fallback is deferred (D9).
- **A8. aarch64 Python compatibility is not a blocker.** The planning host is itself aarch64,
  and both `uv` venvs resolve and run here. Any routed job that fails on arm64 during the
  operator dry run is moved to `hosted` with `reason_code: amd64-only` through a manifest
  change. That decision is recorded, not hidden.
- **A9. Initial runner concurrency is 8 instances**, configurable. The operator tunes it
  against the wall-clock measurement. The ri-08 dispatcher daemon shares the host, so per-
  container CPU and memory limits are mandatory.

## Impact

- **New capability:** `ci-runner-infrastructure`.
- **Files written:**
  - `.github/runner-lanes.yaml`
  - `.github/runner-lanes.schema.json`
  - `.github/workflows/ci.yml` and `.github/workflows/security.yml` (routing only)
  - `deploy/gx10-runner/**`
  - `scripts/ci/ci_wallclock.py`
  - `docs/guides/self-hosted-ci-runners.md`
  - `skills/tests/ci_runners/**`
  - `skills/pyproject.toml` (registers the test path)
- **Interactions:**
  - Several active changes add jobs to `ci.yml`, including
    `gate-drift-with-mirrors-hooks-and-blocking-ci`, `assert-generated-artifacts-validate-in-ci`
    and `enforce-fork-policies-in-ci-worktrees-and-sync-points`.
  - The manifest completeness test fails for any job that is not classified. Whichever change
    merges second must add its jobs to the manifest. That is the intended forcing function.
  - The tests that already parse `ci.yml` (`skills/tests/ci_coverage/`,
    `skills/tests/project-context-refresh/`) must stay green. Only `runs-on`, a guard step,
    `workflow_dispatch` and setup steps change.
- **Not changed:**
  - Branch-protection required-check names, because job ids are unchanged.
  - `concurrency` semantics.
  - Job `permissions`.
