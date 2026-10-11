# Design — migrate-ci-to-self-hosted-gx10-runners

Selected approach: **A** (proposal.md). It combines four parts:
- a lane manifest;
- an inline canonical `runs-on` expression that defaults to the hosted lane and excludes forks;
- host-minted JIT runners in rootless podman containers;
- a systemd user template unit.

## Context and constraints

- **Host.** The GX10 runs linux/aarch64, Ubuntu 24.04 class, systemd 255, podman 4.9.3, rootless.
  There is no Docker daemon.
- **Rootless networking.** Podman 4.9 uses `slirp4netns` with `allow_host_loopback=false` by
  default. A container therefore cannot reach host loopback services: the coordinator API and
  Postgres on `:54322`.
- **Current workflows.** `ci.yml` has 25 jobs and `security.yml` has 3, all on `ubuntu-latest`.
  The triggers are `push` (main), `pull_request`, and `merge_group`.
- **Other services on the host.** The host also carries the ri-08 dispatcher daemon and the
  vendor CLIs. Runner containers must not exhaust its resources or reach its credentials.
- **Implementation boundary (proposal.md § Hard boundary).** The implementation must not:
  - register runners;
  - mint tokens;
  - change repository settings or variables;
  - install, enable or start units or containers;
  - touch `main`.

## Decisions

### D1 — A machine-readable lane manifest is the single source of routing truth

`.github/runner-lanes.yaml` (schema `.github/runner-lanes.schema.json`, drafted in
`contracts/schemas/runner-lanes.schema.json`) holds the following:

```yaml
schema_version: 1
routing:
  repository_variable: CI_RUNNER_LANE   # unset or anything but "self-hosted" => hosted
  dispatch_input: runner_lane           # workflow_dispatch choice: auto | hosted | self-hosted
  self_hosted_labels: [self-hosted, linux, ARM64, gx10]
  hosted_label: ubuntu-latest
workflows:
  ci.yml:
    jobs:
      test: { lane: routed }
      test-integration:
        lane: hosted
        reason_code: container-engine
        reason: "services: paradedb container needs a container engine; none is exposed inside runner containers (D6)."
      # ... every job, no omissions
  security.yml:
    jobs: { ... }
```

**Rationale.** The manifest is an auditable record of which jobs run on which lane and why. It
also lets tests check the workflows against the manifest instead of hard-coding job names.
Without it, the hosted pin is a bare `ubuntu-latest` string, and nothing distinguishes "pinned
on purpose" from "never migrated".

**Closed `reason_code` set:**

| Code | Meaning |
|---|---|
| `container-engine` | The job needs `services:`, a Docker build, or podman |
| `amd64-only` | The job uses an image, binary or validated artifact that exists only for amd64, or fails on arm64 |
| `privileged-token` | The job holds a write-scoped `GITHUB_TOKEN` |
| `measured-slower` | The operator moved the job back after measurement |

### D2 — Initial job classification

| Workflow | Job | Lane | Reason |
|---|---|---|---|
| ci | test-openbao-credentials, test, test-infra-skills, test-skills, skill-audit-freshness, validate-specs, context-drift-gate, contract-breaking-change-gate, coverage-ratchet, check-docker-imports, formal-coordination, gen-eval-tests, code-search-tests, system-one-decisions-tests, agent-scenarios-tests, requirement-traceability-sweep, context-eval, semantic-enablement-gate, validate-context-producers, test-codebase-atlas | routed | — |
| ci | test-openbao-live | hosted | `container-engine`: `run_live_matrix.sh` starts an OpenBao container through podman or docker |
| ci | test-integration, gen-eval | hosted | `container-engine`: `services:` Postgres (paradedb) and `sudo apt-get` |
| ci | docker-smoke-import | hosted | `container-engine` (buildx with the `type=gha` cache). The image it validates is the amd64 production image (Railway), so arm64 would also check the wrong architecture |
| ci | dependency-update-remediation | hosted | `privileged-token`: it holds `contents: write` and pushes. Write tokens stay off the shared host |
| security | secret-scan, dependency-audit-coordinator, dependency-audit-skills | routed | — |

`check-docker-imports` is routed because it is a static Python import check and needs no engine.

Arm64 risk for `secret-scan` (gitleaks-action binary download) and `formal-coordination` (Java)
is resolved by the operator dry run (O6). A failure there produces a manifest move to
`amd64-only`, not a workaround.

### D3 — Canonical inline `runs-on` expression (no routing job)

Every routed job uses exactly this string. The tests compare it after whitespace normalization:

```yaml
runs-on: ${{ (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) && ((github.event_name == 'workflow_dispatch' && inputs.runner_lane != 'auto') && inputs.runner_lane || vars.CI_RUNNER_LANE) == 'self-hosted' && fromJSON('["self-hosted","linux","ARM64","gx10"]') || 'ubuntu-latest' }}
```

**Evaluation table.** This table is the spec for the tests' reference evaluator (task 2.1):

| Event | Fork? | dispatch input | `vars.CI_RUNNER_LANE` | Result |
|---|---|---|---|---|
| pull_request | yes | — | any | `ubuntu-latest` |
| pull_request | no | — | unset / `hosted` / other | `ubuntu-latest` |
| pull_request | no | — | `self-hosted` | GX10 labels |
| push / merge_group | — | — | `self-hosted` | GX10 labels |
| push / merge_group | — | — | unset | `ubuntu-latest` |
| workflow_dispatch | — | `self-hosted` | any | GX10 labels |
| workflow_dispatch | — | `hosted` | any | `ubuntu-latest` |
| workflow_dispatch | — | `auto` | follows variable | follows variable |

**Rejected: routing job (Approach B).** It adds a serial hosted hop in front of every job,
which costs wall-clock time.

**Rejected: YAML anchors.** GitHub Actions supports anchors, but `actionlint` and some
downstream parsers in this repository do not handle them uniformly. Repeating the expression
and enforcing it with a test is the safer option.

The labels inside `fromJSON(...)` must equal `routing.self_hosted_labels` in the manifest. A
test checks this.

### D4 — Defense in depth: in-job fork guard and trigger allowlist

Each routed job's **first** step:

```yaml
- name: Refuse fork code on self-hosted runner
  if: runner.environment == 'self-hosted' && github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name != github.repository
  shell: bash
  working-directory: ${{ github.workspace }}
  run: |
    echo "::error::Fork pull requests must never execute on self-hosted runners; routing expression bypassed."
    exit 1
```

`working-directory` is overridden so that jobs with `defaults.run.working-directory` do not fail
on a directory that has not been checked out yet.

Trigger allowlist for both workflows: `push`, `pull_request`, `merge_group`,
`workflow_dispatch`. A test fails if either workflow gains any of the following, because they
run with base-repo privileges on fork-supplied input:
- `pull_request_target`
- `workflow_run`
- `issue_comment`

**Repository setting (operator-only, O5).** Set *Require approval for all external
contributors* through the `fork-pr-contributor-approval` API. Approval only lets a fork run
start. Under D3 that run still lands on `ubuntu-latest`.

### D5 — Host-minted JIT config; credentials never enter the container

`deploy/gx10-runner/mint-jitconfig.sh <instance>` runs as the unit's `ExecStartPre` on the host.
It works in four steps:

1. It reads the credential from `$CREDENTIALS_DIRECTORY/github-token` (systemd
   `LoadCredential=`), falling back to `GX10_RUNNER_TOKEN_FILE`. It refuses any credential file
   whose mode is wider than 0600.
2. It calls
   `POST /repos/{owner}/{repo}/actions/runners/generate-jitconfig` with:
   - `name=gx10-<hostname>-<instance>-<epoch>`
   - `runner_group_id=1`
   - `labels` = manifest `self_hosted_labels`, read from the env file that the install docs
     generate
   - `work_folder=_work`
3. It writes `ACTIONS_RUNNER_INPUT_JITCONFIG=<encoded>` and the runner id into
   `$XDG_RUNTIME_DIR/gx10-runner/<instance>.env`, with umask 077.
4. On API failure it retries with exponential backoff (per-attempt delay capped at 300 s) inside
   a **total retry budget** `GX10_MINT_MAX_ELAPSED` (default 600 s), then exits non-zero so
   systemd restarts it. The budget must stay below the unit's `TimeoutStartSec=` (D7), or
   systemd kills the script mid-backoff, restarts it after `RestartSec`, and the backoff never
   takes effect (the API is hammered every ~10 s instead). A test pins
   `GX10_MINT_MAX_ELAPSED < TimeoutStartSec`.

The container receives only the single-use encoded JIT config, through `--env-file`. A job that
reads it gains nothing, because the config is consumed by the runner it already belongs to.

**Credential choice.** A fine-grained PAT scoped to this repository with
*Administration: read and write*, expiring in 90 days or less (A3).

**Rejected: registration token plus `config.sh --ephemeral` inside the container.** Either the
long-lived credential or a reusable registration token would sit inside the PR-code container.

**Deferred: GitHub App.** It gives short-lived installation tokens, but needs JWT signing on the
host. It is recorded as the upgrade path in the runbook.

`cleanup-runner.sh <instance>` runs as `ExecStopPost`. If the JIT runner id from the env file
is still registered and offline, it deletes the registration. Deletion is best-effort and
always exits 0.

### D6 — Container hardening and isolation

The `podman run` invocation in the unit (`ExecStart`) MUST include:
- `--rm`
- `--pull=never` (the image is the locally built `localhost/gx10-runner:<sha>` from O3; a start
  must never pull a different image from a registry)
- `--network slirp4netns:allow_host_loopback=false` (explicit, see below)
- `--name gx10-runner-%i`
- `--env-file %t/gx10-runner/%i.env`
- `--security-opt no-new-privileges`
- `--cap-drop ALL`
- `--pids-limit`
- `--cpus` and `--memory`, from the env file (default 2 CPU / 8 GiB per instance)
- `--tmpfs /tmp`
- one named volume for the uv cache (`gx10-runner-uv-cache:/home/runner/.cache/uv`)

It MUST NOT include any of the following:
- `--privileged`
- `--network host`
- a mounted podman or docker socket (`*.sock`)
- any bind mount of the host user's home directory

**Network is pinned explicitly, not inherited from the podman default.** Podman 4.9 (the GX10
today) defaults rootless networking to `slirp4netns` with `allow_host_loopback=false`, which
makes host loopback services (coordinator API, Postgres on `:54322`) unreachable. Podman 5.x
changes the default to `pasta`, which by default maps the gateway address to the host and
would expose those services to PR code after a routine host upgrade. The unit therefore passes
`--network slirp4netns:allow_host_loopback=false` and a test requires that exact option. If the
host later moves to podman 5 and the operator prefers `pasta`, the equivalent is
`--network pasta:--no-map-gw`, which is a reviewed unit change, not a default. O4 verifies
isolation on the host.

**Shared uv cache trade-off.** A cache shared across jobs speeds up `uv sync`. It is also a
poisoning vector: a same-repository PR job can write arbitrary files into a cache that a later
`main` push job reads, and uv does not re-hash cached entries on reuse. Lockfile hash checking
does **not** mitigate this: it applies at download time only, and several jobs run
`uv sync --all-extras` without `--locked`, `uv run --with pytest-cov` or `uv pip install
pip-audit`, which resolve outside the lockfile. The risk is accepted (assumption A10) because:
- forks never route here (D3 and D4), so only same-repository branches can reach the cache;
- pushing a same-repository branch already requires write access to the repository, and this
  is a single-principal repository in solo mode, so every cache writer is already a trusted
  principal;
- the cache can be dropped at any time.

The operator can disable the cache with `GX10_RUNNER_UV_CACHE=off`, which drops the volume. If
the repository gains collaborators who are not fully trusted (team mode), the runbook directs
the operator to set `GX10_RUNNER_UV_CACHE=off` as part of that transition.

The operator can disable the cache with `GX10_RUNNER_UV_CACHE=off`, which drops the volume. The
setup-* toolcache stays inside the container, because concurrent writers would race on a
shared toolcache.

**Runner image.** `deploy/gx10-runner/Containerfile` is built
`FROM ghcr.io/actions/actions-runner:<version>@sha256:<digest>`, a multi-arch image that is
pinned with no `latest`. It adds a baseline toolchain declared in
`deploy/gx10-runner/toolchain.txt`:
- `git`, `curl`, `jq`, `make`, `build-essential`
- `unzip`, `xz-utils`, `zstd`, `ca-certificates`, `python3`

The entrypoint is `/home/runner/run.sh` with the JIT config from the environment. The runner
user stays non-root, and sudo is not granted to it.

### D7 — systemd user template unit, dedicated lingering user

`deploy/gx10-runner/systemd/gx10-runner@.service` is installed as a **user** unit for a
dedicated `ghrunner` account (A4). It has these properties:
- `Restart=always` and `RestartSec=10`. The container exits after its single job, and systemd
  starts a fresh one. This is the per-job ephemerality mechanism.
- `StartLimitIntervalSec=0` in the **`[Unit]`** section (that is where systemd ≥ 230 reads it;
  in `[Service]` it is ignored with a warning), because restarts after normal jobs are frequent
  and expected. Back-off on persistent API failure lives in `mint-jitconfig.sh`, not in the
  start limit.
- `TimeoutStartSec=900`, which bounds `ExecStartPre` and must exceed the mint script's total
  retry budget `GX10_MINT_MAX_ELAPSED` (D5). The default of 90 s would kill the script in the
  middle of its backoff.
- `ExecStartPre` is the mint script.
- `ExecStart` is `podman run …` (D6).
- `ExecStopPost` is the cleanup script.
- `TimeoutStopSec=90`.
- `[Install] WantedBy=default.target`.

Reboot survival comes from `loginctl enable-linger ghrunner`, an operator-only step (O1). It
starts the user manager at boot without a login, and the user manager starts enabled
`default.target` units.

`deploy/gx10-runner/install-units.sh` is a script for the **operator** to run. It copies the
units and scripts into `<prefix>/.config/systemd/user` and `<prefix>/.local/lib/gx10-runner`.
`--prefix` defaults to the `ghrunner` home directory. The script then prints the
`loginctl enable-linger` and `systemctl --user enable --now` commands. It never executes
`systemctl`, `loginctl` or `podman`. The implementation tests it only with
`--prefix <tmpdir>`, and never runs it against a real home directory.

**Initial instance count.** 8 (A9). The operator tunes it against O8.

**Rejected: a system unit running rootful podman.** It gives a larger blast radius on container
escape.

**Rejected: rootless podman under the operator's own account.** That account holds vendor CLI
credentials and SSH keys.

### D8 — Measurement and verification tooling is pure over JSON

`scripts/ci/ci_wallclock.py` provides:
- `median_wallclock(runs, *, conclusion="success")`. It computes `run_started_at → updated_at`
  seconds over successful runs and excludes cancelled and failed runs.
- `compare(baseline, candidate, *, threshold=0.85, min_n=5)`. It returns pass/fail plus the
  numbers. Pass requires `candidate_median ≤ threshold × baseline_median` and `n ≥ min_n` on
  both sides (A6).
- `verify_run(jobs, manifest, workflow, *, expected_lane="self-hosted")`. It returns one
  violation per job in these cases:
  - with `expected_lane="self-hosted"`, a routed job did not run on a runner labelled `gx10`;
    with `expected_lane="hosted"`, a routed job ran on a self-hosted runner (the O12 rollback
    check);
  - a hosted job ran on a self-hosted runner;
  - a job concluded anything other than `success` or `skipped` (`continue-on-error` jobs are
    reported as warnings, not violations);
  - a job concluded `skipped` although its workflow definition has **no** job-level `if:`
    (an unconditional job can only be skipped by an upstream failure, which is a violation);
  - a manifest job is missing from the run's jobs list.

  A job that concluded `skipped` **and** has a job-level `if:` is not a violation, and its
  runner placement is not checked, because a skipped job is never assigned a runner. This is
  the normal case for `dependency-update-remediation`, whose `if:` limits it to Dependabot pull
  requests: it is skipped on every dispatch, push and ordinary PR run. Without this rule every
  O6, O7, O11 and O12 check would report a false violation.

A run's lane is derived from where its routed jobs actually ran, using the runner labels in the
jobs API. It is not derived from dispatch inputs, because the runs API does not expose them.
`compare --baseline-lane hosted --candidate-lane self-hosted` groups runs on that basis.

Run selection for `median` and `compare` is explicit, so that the A6 measurement is reproducible:
- `--workflow <file>` (required);
- `--head-sha <sha>` restricts to runs of one commit, which is how the paired O8 dispatch runs
  are selected;
- `--event <name>` (for example `workflow_dispatch` for O8, `pull_request` for the corroborating
  window);
- `--since` / `--until` (ISO dates) bound the before/after window;
- `--limit` (default 200) caps the number of runs fetched, so a paginated fetch is bounded.

The CLI wrappers (`median`, `compare`, `verify-run`) shell out to `gh api` only when the
**operator** runs them. The tests use JSON fixtures only, with no network access.

### D9 — Hosted fallback is operator-switched; automatic fallback deferred

When `CI_RUNNER_LANE=self-hosted` and no GX10 runner is online, routed jobs queue. GitHub's
queue limit is 24 h, and `timeout-minutes` does not cover queue time.

The documented fallback works in three steps:
1. `gh variable set CI_RUNNER_LANE --body hosted`, or `gh variable delete CI_RUNNER_LANE`.
2. Cancel the queued runs.
3. Re-run them.

The runbook gives a detection command that counts runs queued for more than 10 minutes.

Automatic fallback needs a token that can list runners. That is either a routing job (Approach
B, rejected for latency) or a host-side watchdog that changes repository variables, which is
outside this change's boundary. It is filed as a follow-up candidate for the ri-18 operator
status surface.

### D10 — Tool parity for routed jobs

Some routed jobs call tools that `ubuntu-latest` preinstalls but the runner image does not, for
example `npm` in `validate-specs`. Each such job either:
- gains an explicit setup action (`actions/setup-node` pinned to the same major version the
  repository uses elsewhere), or
- uses a tool listed in `toolchain.txt`.

A static test scans the `run:` blocks of routed jobs for a fixed list of commands that are
hosted-only. It matches a command only in **command position**: at the start of a line or after
`;`, `&&`, `||`, `|`, `$(`, `sudo ` or `env `, followed by whitespace or end of line. A
substring such as `scripts/check_docker_imports.py` therefore never matches `docker`. The
commands are:
- `npm`, `npx`, `node`, `java`, `go`
- `docker`, `podman`, `sudo`, `apt-get`

For every hit, the job must have the matching setup action, or must be hosted. `docker`,
`podman`, `sudo` and `apt-get` are always disallowed in routed jobs. The test keeps an
allowlist mechanism (each entry: workflow, job, command and a comment) for a future justified
exception; it starts **empty**, because command-position matching already ignores the
`check_docker_imports.py` script path.

**Known limit.** The scan sees only `run:` text. A command invoked indirectly, from inside a
script the step calls (as `run_live_matrix.sh` does with podman), is invisible to it. The O6
self-hosted dry run is the backstop for that class, and any job it catches moves to `hosted`
through the manifest.

## Operator-only steps (summary; the full runbook is in `docs/guides/self-hosted-ci-runners.md`)

O1–O12 are listed in tasks.md § 7, each with its verification command. None is an
implementation task, and nothing in the implementation phases performs them.

## Risks

| Risk | Mitigation |
|---|---|
| A routed job fails on arm64 | O6 dry run with `verify-run`. Move the job to `amd64-only` through the manifest |
| Lower concurrency (8 vs ~20 hosted) lengthens the critical path | Measure in O8. Tune the instance count, or move jobs back with `measured-slower` |
| PAT leak from the host | 0600 file or systemd credential; dedicated user; 90-day expiry; minimum scope; App upgrade path |
| Host down with lane=self-hosted | D9 manual flip plus the queued-run detection command |
| New jobs added by concurrent changes | Manifest completeness test fails until they are classified |
| Podman upgrade changes the rootless network default to `pasta` and exposes host loopback | Explicit `--network slirp4netns:allow_host_loopback=false` in the unit, pinned by a test (D6) |
| Mint script killed mid-backoff by the start timeout, hammering the API | Explicit `TimeoutStartSec` above the bounded `GX10_MINT_MAX_ELAPSED` budget, pinned by a test (D5, D7) |
| Cache poisoning by a same-repository PR job | Accepted in solo mode (A10); `GX10_RUNNER_UV_CACHE=off` switch, mandated on a move to team mode |
| A routed job invokes a container engine indirectly through a script | O6 dry run backstop; the static scan only sees `run:` text (D10) |
