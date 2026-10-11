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
runs-on: ${{ (github.event_name == 'push' || github.event_name == 'workflow_dispatch' || (github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository)) && ((github.event_name == 'workflow_dispatch' && inputs.runner_lane != 'auto') && inputs.runner_lane || vars.CI_RUNNER_LANE) == 'self-hosted' && fromJSON('["self-hosted","linux","ARM64","gx10"]') || 'ubuntu-latest' }}
```

**Evaluation table.** This table is the spec for the tests' reference evaluator (task 2.1):

| Event | Fork? | dispatch input | `vars.CI_RUNNER_LANE` | Result |
|---|---|---|---|---|
| pull_request | yes | — | any | `ubuntu-latest` |
| pull_request | no | — | unset / `hosted` / other | `ubuntu-latest` |
| pull_request | no | — | `self-hosted` | GX10 labels |
| push | — | — | `self-hosted` | GX10 labels |
| push | — | — | unset | `ubuntu-latest` |
| merge_group | — | — | any | `ubuntu-latest` |
| any other event | — | — | any | `ubuntu-latest` |
| workflow_dispatch | — | `self-hosted` | any | GX10 labels |
| workflow_dispatch | — | `hosted` | any | `ubuntu-latest` |
| workflow_dispatch | — | `auto` | follows variable | follows variable |

**Event eligibility is an allowlist, not a fork test.** Only three event shapes can reach the
GX10: `push` (to `main`, i.e. code already merged), `workflow_dispatch` (started by a user with
write access, on a ref of this repository) and a same-repository `pull_request`. Everything
else resolves to `ubuntu-latest`. In particular, **`merge_group` always runs hosted**: a merge
queue builds a temporary merge commit that can contain an approved *fork* PR's code, and the
`merge_group` payload carries no reliable head-repository field to tell fork from same-repo
entries. Routing it would let fork code execute on the host after a maintainer enqueues it,
which the fork requirement forbids. The cost is that merge-queue runs keep hosted wall-clock
time; the post-merge `push` run on `main` still routes. A later change may route `merge_group`
only if fork provenance of every queued PR can be established safely.

**Rejected: routing job (Approach B).** It adds a serial hosted hop in front of every job,
which costs wall-clock time.

**Rejected: YAML anchors.** GitHub Actions supports anchors, but `actionlint` and some
downstream parsers in this repository do not handle them uniformly. Repeating the expression
and enforcing it with a test is the safer option.

The labels inside `fromJSON(...)` must equal `routing.self_hosted_labels` in the manifest, the
`vars.<name>` reference must name `routing.repository_variable`, and the `inputs.<name>`
references must name `routing.dispatch_input`. A test checks all three, so no field of the
manifest's routing block is decorative.

### D4 — Defense in depth: in-job fork guard and trigger allowlist

Each routed job's **first** step:

```yaml
- name: Refuse ineligible events on self-hosted runner
  if: runner.environment == 'self-hosted' && !(github.event_name == 'push' || github.event_name == 'workflow_dispatch' || (github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository))
  shell: bash
  working-directory: ${{ github.workspace }}
  run: |
    echo "::error::Only push, workflow_dispatch and same-repository pull_request runs may execute on self-hosted runners (fork PRs and merge_group never); routing expression bypassed."
    exit 1
```

The guard condition is `runner.environment == 'self-hosted'` combined with the **negation of
the D3 event-eligibility clause**, character for character, so a fork `pull_request` and every
`merge_group` run fail the job if they ever land on a self-hosted runner. A test pins the
guard's clause to the clause inside the canonical expression.

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
start. Under D3 that run still lands on `ubuntu-latest`, and so does any `merge_group` run that
later carries the fork PR's code.

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
   - `labels` = the **custom** labels only: manifest `self_hosted_labels` minus the labels the
     runner assigns itself (`self-hosted`, `Linux`, `ARM64`, compared case-insensitively),
     i.e. `["gx10"]` today, read from the env file. The API documents `labels` as custom
     labels, so sending the defaults risks a 422; the effective label set is defaults ∪
     requested, which must equal the manifest set (case-insensitively)
   - `work_folder=_work`
3. It writes `ACTIONS_RUNNER_INPUT_JITCONFIG=<encoded>` and the runner id into
   `$XDG_RUNTIME_DIR/gx10-runner/<instance>.env`, with umask 077.
4. On API failure it retries with exponential backoff (per-attempt delay capped at 300 s) inside
   a **total retry budget** `GX10_MINT_MAX_ELAPSED` (default 600 s), then exits non-zero so
   systemd restarts it. The budget must stay below the unit's `TimeoutStartSec=` (D7), or
   systemd kills the script mid-backoff, restarts it after `RestartSec`, and the backoff never
   takes effect (the API is hammered every ~10 s instead). A test pins
   `GX10_MINT_MAX_ELAPSED < TimeoutStartSec`.

The container receives only the single-use encoded JIT config, through `--env-file`. That value
is not inert: it encodes the runner's identity and Actions-service credentials, and because it
is in the runner's environment every job step inherits it, so PR code could act as that runner
against the Actions service (read its own job message, post status) **while the job runs**.
Ephemerality bounds this to one job on one single-use registration that cannot be reused after
the job, and it grants nothing on the host or on other jobs. This residual is **accepted**. A
narrower option, deferred, is an entrypoint wrapper that reads the variable, `unset`s it and
passes it as `--jitconfig` (at the cost of the value appearing briefly in `ps`).

**Credential choice.** A fine-grained PAT scoped to this repository with
*Administration: read and write*, expiring in 90 days or less (A3).

**Rejected: registration token plus `config.sh --ephemeral` inside the container.** Either the
long-lived credential or a reusable registration token would sit inside the PR-code container.

**Deferred: GitHub App.** It gives short-lived installation tokens, but needs JWT signing on the
host. It is recorded as the upgrade path in the runbook.

`cleanup-runner.sh <instance>` runs as `ExecStopPost`. If the JIT runner id from the env file
is still registered and offline, it deletes the registration. Deletion is best-effort and
always exits 0.

`ExecStopPost` does not run after a power loss or hard reboot, so never-used registrations can
survive it. Before minting, `mint-jitconfig.sh <instance>` therefore **sweeps** stale
registrations: it lists the repository's runners (read-only GET, bounded by `per_page=100`)
and deletes every **offline** runner whose name starts with `gx10-<hostname>-<instance>-`
(the instance's own prefix, so it never touches another instance's or another host's runners).
The sweep is best-effort: a failure is logged and does not consume the mint retry budget.

**Host DNS must stay reachable for `ghrunner`.** The mint script resolves `api.github.com`
through the host resolver; on Ubuntu 24.04 that is systemd-resolved's stub at `127.0.0.53`, a
local address. The D6 nftables control therefore exempts the resolver (see D6).

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
- the word `$GX10_RUNNER_CACHE_ARGS`, unbraced and standing alone, which systemd splits on
  whitespace into zero or more arguments. It is empty by default (no cache volume); the only
  opted-in value is `--volume gx10-runner-uv-cache:/home/runner/.cache/uv` (see the uv cache
  trade-off below)

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
`--network pasta:--no-map-gw`, which is a reviewed unit change, not a default.

**What the pin does not cover: services bound to non-loopback host addresses.**
`allow_host_loopback=false` only removes the `10.0.2.2 → 127.0.0.1` mapping. slirp4netns still
NATs container traffic through the host's network stack as the `ghrunner` user, so any host
service listening on `0.0.0.0` or on the host's LAN or Tailscale address (a compose-published
`0.0.0.0:54322` Postgres is the common case; the coordinator API and the ri-08 daemon may also
bind non-loopback) stays reachable from PR code through the host's real IP. Isolation of host
services therefore rests on one of two operator-enforced controls, and O4 must prove it:
1. **Preferred — an nftables egress rule for the runner user**: in an `output` hook chain,
   first accept DNS to the host stub resolver
   (`meta skuid ghrunner ip daddr 127.0.0.53 udp dport 53 accept` and the same for `tcp`), then
   drop every other packet whose socket owner is `ghrunner` and whose destination is a local
   host address (`meta skuid ghrunner fib daddr type local drop`). Because slirp4netns runs as
   `ghrunner`, this blocks every host-local service regardless of how it binds, while leaving
   internet egress and name resolution intact (both for the mint script and for container DNS,
   which slirp4netns forwards through the host resolver). Without the DNS exemption the mint
   script cannot resolve `api.github.com`, burns its retry budget on every start, and no
   instance ever comes online. Installing the rule is operator-only.
2. **Fallback — loopback-only binding**: every host service the runners must not reach binds to
   `127.0.0.1` only (compose ports published as `127.0.0.1:54322:5432`), checked with
   `ss -ltnp`.

O4's verification probes the coordinator API port and `:54322` on **each** host address
(`10.0.2.2`, the LAN address and the Tailscale address, from `hostname -I`) from inside a
runner container and requires every **TCP connect** to be refused or to time out. The probe is
transport-level (`timeout 3 bash -c 'exec 3<>/dev/tcp/<addr>/<port>'`), not an HTTP request:
`curl` against a non-HTTP service such as Postgres fails *after* connecting, which would report
"unreachable" exactly when the port is reachable. A probe of `10.0.2.2` alone is not sufficient
evidence. O4 also confirms DNS still works for `ghrunner` (`getent hosts api.github.com`).

**Shared uv cache trade-off: off by default, explicit operator opt-in.** A cache shared across
jobs speeds up `uv sync`. It is also a cross-trust poisoning vector: a same-repository PR job
can write arbitrary files into a cache that a later `main` push job reads, and uv does not
re-hash cached entries on reuse. Lockfile hash checking does **not** mitigate this: it applies
at download time only, and several jobs run `uv sync --all-extras` without `--locked`,
`uv run --with pytest-cov` or `uv pip install pip-audit`, which resolve outside the lockfile.

"Every same-repository branch author is a trusted human" is **not** true here. Same-repository
branches are also pushed by automation — Dependabot (whose PRs carry freshly bumped third-party
packages) and the agent PR sources the `merge-pull-requests` skill accepts (Jules, Codex and
other agent branches) — and by any holder of a leaked collaborator credential. Pushing a branch
is also weaker than merging to protected `main`. With a shared writable cache, such a branch
could influence a later `main` job before any human has reviewed its diff.

Per-trust-tier volumes are not available: the container starts before the job is assigned, so
the unit cannot choose a volume by event. The design therefore makes the cache **opt-in**:
- `gx10-runner.env.example` ships `GX10_RUNNER_CACHE_ARGS=` (empty), so a default install
  mounts no shared cache and every job starts with an empty in-container cache.
- Enabling it is an operator decision recorded as an explicit risk acceptance (assumption A10,
  runbook step O4): the operator sets
  `GX10_RUNNER_CACHE_ARGS=--volume gx10-runner-uv-cache:/home/runner/.cache/uv`, and records
  in the runbook's acceptance line who accepted the risk and on what date, having confirmed that
  every same-repository writer (humans and automation) is acceptable as a cache writer.
- Disabling it again is the same variable set back to empty, plus
  `podman volume rm gx10-runner-uv-cache`. A move to team mode requires disabling it.
- A trust-split follow-up (a separate cache-holding pool selected by label for `push` runs
  only) is the upgrade path if the cache is needed without the shared-writer risk.

When the cache is on, routed jobs must actually use it: the container sets
`UV_CACHE_DIR=/home/runner/.cache/uv`, and routed jobs that use `astral-sh/setup-uv` pass
`cache-local-path: /home/runner/.cache/uv` so the action does not redirect the cache to
`$RUNNER_TEMP`. The setup-* toolcache stays inside the container, because concurrent writers
would race on a shared toolcache.

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
- `EnvironmentFile=%h/.config/gx10-runner/env`: the operator's copy of
  `gx10-runner.env.example`. It supplies the repository slug, image reference, CPU and memory
  limits, labels, `GX10_MINT_MAX_ELAPSED` and `GX10_RUNNER_CACHE_ARGS` to `ExecStartPre` and
  `ExecStart`; without it they are all unset. It is distinct from the per-instance container
  env file `%t/gx10-runner/%i.env` that the mint script writes (JIT config and runner id only).
- `LoadCredential=github-token:%h/.config/gx10-runner/token`: the registration credential (O2
  stores it at that path, mode 0600). systemd exposes it to `ExecStartPre` as
  `$CREDENTIALS_DIRECTORY/github-token`, the mint script's primary source;
  `GX10_RUNNER_TOKEN_FILE` remains only as a fallback for running the script by hand and is
  not set in the env file.
- `ExecStartPre` is the mint script.
- `ExecStart` is `podman run --replace …` (D6). `--replace` removes a leftover container of the
  same name (from an unclean stop or a crash before `--rm` cleanup) instead of failing on the
  name conflict, which would otherwise make `Restart=always` retry every 10 s forever while the
  instance silently drops out of the pool.
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
  - a job concluded anything other than `success` or `skipped` (a job declared
    `continue-on-error: true` is reported as a **warning**, not a violation; the result model is
    `{violations: [...], warnings: [...]}` and the CLI exits non-zero only on violations);
  - a job concluded `skipped` although its workflow definition has **no** job-level `if:`
    (an unconditional job can only be skipped by an upstream failure, which is a violation);
  - a manifest job is missing from the run's jobs list.

  A job that concluded `skipped` **and** has a job-level `if:` is not a violation, and its
  runner placement is not checked, because a skipped job is never assigned a runner. This is
  the normal case for `dependency-update-remediation`, whose `if:` limits it to Dependabot pull
  requests: it is skipped on every dispatch, push and ordinary PR run. Without this rule every
  O6, O7, O11 and O12 check would report a false violation.

**Job correlation contract.** The jobs API returns each job's display `name`, not its YAML job
id. `verify_run` maps a manifest job id to API job entries by deriving the expected display
name from the workflow definition:
- a job with no `name:` key is displayed as its job id; a job with a literal `name:` is
  displayed as that string;
- a job with a `strategy.matrix` expands to one API entry per combination, displayed as
  `<display name> (<v1>, <v2>, …)`; `verify_run` matches the prefix `<display name> (` and
  checks every expansion individually (each must meet the lane and conclusion rules, and at
  least one expansion must be present);
- a `name:` that contains an expression (`${{`) is rejected by the manifest completeness test,
  because it cannot be resolved statically.

`verify-run` reads the workflow definition **at the run's `head_sha`**, fetched read-only with
`gh api repos/{owner}/{repo}/contents/.github/workflows/<file>?ref=<head_sha>` (or from a local
file passed with `--workflow-file`, which the tests use), never from the local checkout, so a
run of an older or newer commit is judged against the job-level `if:`, `name:`,
`strategy.matrix` and `continue-on-error` it actually ran with.

Today no job in `ci.yml` or `security.yml` sets `name:` or `strategy.matrix`, so every display
name equals its job id. The completeness test (task 2.2) asserts that derived display names are
unique within each workflow, so the mapping is one-to-one; an API entry that matches no
manifest job is reported as a violation ("unknown job"), which also catches a renamed job.

A run's lane is derived from where its routed jobs actually ran, using the runner labels in the
jobs API. It is not derived from dispatch inputs, because the runs API does not expose them.
`compare --baseline-lane hosted --candidate-lane self-hosted` groups runs on that basis. A run
is classified only when **all** its routed jobs that were assigned a runner ran on the same
lane. A run with mixed placement, or with no routed job assigned a runner, is **excluded** from
both samples and listed in a diagnostic (`excluded_runs` with a reason), so it cannot distort
the ratio.

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
| PR code reaches a host service bound to `0.0.0.0` or a LAN/Tailscale address through slirp4netns NAT | Operator nftables rule dropping `ghrunner`-owned traffic to local addresses, or loopback-only binding; O4 probes every host address (D6) |
| Mint script killed mid-backoff by the start timeout, hammering the API | Explicit `TimeoutStartSec` above the bounded `GX10_MINT_MAX_ELAPSED` budget, pinned by a test (D5, D7) |
| Cache poisoning by a same-repository PR job (human, Dependabot or agent branch) | Cache off by default; enabling it is a recorded operator risk acceptance (A10); disabled again by emptying `GX10_RUNNER_CACHE_ARGS`, mandated on a move to team mode |
| A routed job invokes a container engine indirectly through a script | O6 dry run backstop; the static scan only sees `run:` text (D10) |
