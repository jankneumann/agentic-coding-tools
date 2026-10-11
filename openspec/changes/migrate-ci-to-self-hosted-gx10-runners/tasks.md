# Tasks — migrate-ci-to-self-hosted-gx10-runners

> Change ID: `migrate-ci-to-self-hosted-gx10-runners` · Roadmap item `roadmap-always-on-agent-automation/ri-20`

**Conventions**
- Sizes follow the plan-feature sizing table. No task is XL, and none is L.
- Ordering is TDD: every test task comes before the implementation task it verifies, and that
  implementation task depends on it.
- Spec scenario references use the form `ci-runner-infrastructure / "<scenario>"`.
- Design decisions are cited by D-number from `design.md`.
- All tests live in `skills/tests/ci_runners/`. Run them with
  `skills/.venv/bin/python -m pytest skills/tests/ci_runners -q`.
- No test may pin `openspec/changes/<id>/`. Tests read the promoted `.github/` copies only.

**HARD BOUNDARY — applies to every task in § 1–6.** Implementation tasks write files on this
branch only. They MUST NOT do any of the following:
- register runners;
- mint registration or JIT tokens;
- call a mutating GitHub API;
- set repository or organization settings or variables;
- run `systemctl`, `loginctl` or `podman run`/`podman build` against the host;
- push to `main`.

Everything of that kind is in § 7 (operator-only).

## Status

- [x] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## Phase 1 — Contracts: manifest schema, manifest, test package

- [x] 1.1 Write `skills/tests/ci_runners/test_manifest_schema.py` (S)
  - The promoted `.github/runner-lanes.schema.json` is valid Draft 2020-12.
  - `.github/runner-lanes.yaml` validates against it.
  - Negative fixtures are rejected:
    - a hosted job with no `reason_code`;
    - a hosted job with an empty `reason`;
    - an unknown `reason_code`;
    - `hosted_label` set to anything other than `ubuntu-latest`;
    - `self_hosted_labels` without `self-hosted`.

  **Spec scenarios**: ci-runner-infrastructure / "Hosted job without justification is rejected"
  **Contracts**: contracts/schemas/runner-lanes.schema.json
  **Design decisions**: D1
  **Dependencies**: none
- [x] 1.2 Promote the schema from the change's `contracts/schemas/` to
      `.github/runner-lanes.schema.json`, then author `.github/runner-lanes.yaml` (S)
  - The manifest classifies every current job of `ci.yml` (25) and `security.yml` (3) exactly
    as the design D2 table does.
  - The routing block is `CI_RUNNER_LANE` / `runner_lane` /
    `[self-hosted, linux, ARM64, gx10]` / `ubuntu-latest`.

  **Spec scenarios**: ci-runner-infrastructure / "Hosted job without justification is rejected"
  **Design decisions**: D1, D2
  **Dependencies**: 1.1
- [x] 1.3 Create the `skills/tests/ci_runners/` package skeleton and register it (XS)
  - Add `__init__.py`.
  - Add `conftest.py` with fixtures `repo_root`, `manifest` and `load_workflow(name)`.
  - Register the directory in the `testpaths` of `skills/pyproject.toml`, so that
    `skills/tests/ci_coverage/test_ci_test_coverage.py` stays green.

  **Dependencies**: none
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 2 — Workflow routing (`ci.yml`, `security.yml` on this branch)

- [x] 2.1 Write `test_routing_expression.py` (M)
  - It contains a minimal reference evaluator for the D3 expression grammar:
    - the `&&`/`||` value semantics of GitHub expressions;
    - `==`/`!=`;
    - `fromJSON` of a literal;
    - context lookups from a dict.
  - It asserts every row of the D3 evaluation table.
  - It asserts that every routed job's `runs-on` equals the canonical string after whitespace
    normalization.
  - It asserts that the labels inside `fromJSON(...)` equal `routing.self_hosted_labels`, that
    the `vars.<name>` reference equals `routing.repository_variable`, and that the
    `inputs.<name>` references equal `routing.dispatch_input` (mutating any one manifest field
    makes the test fail).

  **Spec scenarios**: ci-runner-infrastructure / "Unset variable keeps CI on hosted runners",
  "Variable opts same-repository events into the self-hosted lane", "Dispatch input overrides
  the variable in both directions", "Expression is tied to every manifest routing field",
  "Merge queue runs stay hosted", "Routed job drifts from the
  canonical expression", "Fork pull request routes to hosted even with the self-hosted lane
  enabled"
  **Contracts**: .github/runner-lanes.schema.json
  **Design decisions**: D3
  **Dependencies**: 1.2, 1.3
- [x] 2.2 Write `test_manifest_completeness.py` (S)
  - The set of job ids in each workflow equals the manifest's job set for that workflow, so
    unclassified and stale entries are both caught.
  - Every hosted job has `runs-on == "ubuntu-latest"` as a literal string.
  - Derived display names (D8 correlation contract: job id, or a literal `name:`) are unique
    within each workflow, and no job uses an expression in `name:`.

  **Spec scenarios**: ci-runner-infrastructure / "Unclassified job fails the suite", "Stale
  manifest entry fails the suite", "Hosted job uses a literal hosted label"
  **Design decisions**: D1, D2
  **Dependencies**: 1.2, 1.3
- [x] 2.3 Write `test_fork_guard.py` (S)
  - Every routed job's first step is the D4 guard: its `if` condition and its `exit 1`.
  - The guard's eligibility clause equals, after whitespace normalization, the negated
    event-eligibility clause of the canonical D3 expression (so `merge_group` and fork PRs are
    refused on a self-hosted runner).
  - Both workflows' triggers are a subset of `{push, pull_request, merge_group,
    workflow_dispatch}`.
  - Both workflows declare a `workflow_dispatch` `runner_lane` choice input with options
    `[auto, hosted, self-hosted]` and default `auto`.

  **Spec scenarios**: ci-runner-infrastructure / "Routed job lacks the in-job fork guard",
  "Privileged trigger is introduced", "Dispatch trigger and lane input are declared"
  **Design decisions**: D4
  **Dependencies**: 1.2, 1.3
- [x] 2.4 Write `test_tool_parity.py` (S)
  - A routed job must not declare `services:`.
  - A routed job's `run:` blocks must not invoke `docker`, `podman`, `sudo` or `apt-get` in
    command position (D10 matching rule), except for entries in the commented allowlist, which
    starts empty.
  - A path such as `scripts/check_docker_imports.py` is not an invocation (positive fixture).
  - A routed job that invokes `npm`/`npx`/`node`, `java` or `go` must have the matching
    `actions/setup-*` step.
  - Every routed job's `astral-sh/setup-uv` step passes
    `cache-local-path: /home/runner/.cache/uv` (D6; implemented by 2.8).

  **Spec scenarios**: ci-runner-infrastructure / "Container-engine job marked routed is
  rejected", "Command name inside a script path is not an invocation", "Routed job calls npm
  without setup-node"
  **Design decisions**: D2, D10
  **Dependencies**: 1.2, 1.3
- [ ] Checkpoint: run tests (expect 2.1–2.4 RED), review diff, verify scope
> **Same-file chain.** 2.5 → 2.6 → 2.7 → 2.8 all edit `ci.yml` and/or `security.yml` and run
> serially inside `wp-workflows`; they are never split across agents.

- [x] 2.5 Route the 20 routed `ci.yml` jobs (M)
  - Replace their `runs-on` with the canonical expression and insert the D4 guard as their
    first step.
  - Leave the 5 hosted jobs on a literal `ubuntu-latest`, each with a one-line comment that
    points to the manifest reason.
  - Do not change job ids, `needs`, `permissions`, `concurrency` or `timeout-minutes`.

  **Dependencies**: 2.1, 2.2, 2.3
- [x] 2.6 Route the 3 `security.yml` jobs (S)
  - Apply the canonical expression and the D4 guard, as in 2.5.

  **Dependencies**: 2.1, 2.2, 2.3, 2.5 (serial; same package)
- [x] 2.7 Add the `workflow_dispatch` trigger to both workflows (XS)
  - Add the trigger with the `runner_lane` choice input: `auto` | `hosted` | `self-hosted`,
    default `auto`.
  - Leave the existing triggers unchanged.

  **Dependencies**: 2.3, 2.6 (serial; edits both workflows after routing)
- [x] 2.8 Add explicit setup steps to routed jobs that rely on hosted-preinstalled tools (S)
  - `validate-specs` needs `npm` and gets `actions/setup-node` at the repository's pinned
    major version. Any other job that 2.4 flags gets the same treatment.
  - The setup step goes after the D4 guard, which must stay the first step.
  - Every routed job that uses `astral-sh/setup-uv` passes
    `cache-local-path: /home/runner/.cache/uv`, so an opted-in shared cache is actually used
    (D6); on the hosted lane the path is harmless because the hosted user is also `runner`.
    Test 2.4 asserts it for routed jobs.

  **Dependencies**: 2.4, 2.7 (serial; edits `ci.yml` after routing)
- [ ] 2.9 Run the existing tests that parse workflows and confirm they stay green (XS)
  - `skills/tests/ci_coverage/`
  - `skills/tests/validate-feature/test_ci_sweep_wiring.py`
  - `skills/tests/project-context-refresh/test_gate.py`
  - `skills/tests/project-context-refresh/test_remediation_policy.py`
  - `skills/tests/install_sh/test_consumer_portability.py`

  Fix only by adjusting this change's workflow edits, never by editing those tests' contracts.

  **Dependencies**: 2.5, 2.6, 2.7, 2.8
- [ ] Checkpoint: run tests (2.1–2.4 GREEN), review diff, verify scope

## Phase 3 — Runner kit (`deploy/gx10-runner/`), written and never installed

- [x] 3.1 Write `test_systemd_unit.py` (S)
  - Parse `systemd/gx10-runner@.service` with an INI parser that allows repeated keys.
  - `Restart=always` and `StartLimitIntervalSec=0` are set, and `WantedBy=default.target` is
    present.
  - `Restart=always` and `TimeoutStartSec` (> 90, and > the example env file's
    `GX10_MINT_MAX_ELAPSED`) are in `[Service]`; `StartLimitIntervalSec=0` is in `[Unit]`.
  - `ExecStartPre` invokes `mint-jitconfig.sh`, and `ExecStopPost` invokes `cleanup-runner.sh`.
  - `[Service]` has `EnvironmentFile=%h/.config/gx10-runner/env` and
    `LoadCredential=github-token:%h/.config/gx10-runner/token` (D7), and every `$VAR` that
    `ExecStartPre`/`ExecStart` reference is defined in `gx10-runner.env.example`.
  - `ExecStart` is `podman run` with each of these: `--rm`, `--replace`, `--pull=never`, `--env-file`,
    `--cap-drop ALL`, `--security-opt no-new-privileges`,
    `--network slirp4netns:allow_host_loopback=false`, `--pids-limit`, `--cpus`, `--memory`.
  - `ExecStart` contains none of these: `--privileged`, `--network host`/`--network=host`, any
    other `--network` value, a `*.sock` volume source, or `%h`/`$HOME` as a bind source.
  - Cache switch (D6/A10): `ExecStart` contains `$GX10_RUNNER_CACHE_ARGS` as a standalone,
    unbraced word and no literal cache `--volume`; the example env file sets it empty. Expanding
    `ExecStart` with systemd word-splitting semantics yields no `--volume` argument when the
    value is empty, and exactly `--volume gx10-runner-uv-cache:/home/runner/.cache/uv` (a named
    volume, never a bind path) when it holds the documented opt-in value.
  - If `systemd-analyze` is present, also run `systemd-analyze verify --user` on a copy whose
    `Exec*` paths are stubbed. Otherwise skip that check.

  **Spec scenarios**: ci-runner-infrastructure / "Unit runs a removable container with a
  single-use config", "Dangerous container options are absent", "Unit restart and install
  properties", "Unit wiring delivers configuration and credential", "Shared cache is off unless
  the operator opts in"
  **Design decisions**: D5, D6, D7
  **Dependencies**: 1.3
- [x] 3.2 Author `deploy/gx10-runner/systemd/gx10-runner@.service` and
      `deploy/gx10-runner/gx10-runner.env.example` (S)
  - The example env file sets: repo slug, instance CPU and memory limits, image reference,
    `GX10_RUNNER_CACHE_ARGS=` (empty: no shared cache, D6/A10), `GX10_MINT_MAX_ELAPSED`
    (default 600), and labels mirrored from the
    manifest. It does not set `GX10_RUNNER_TOKEN_FILE`: the unit delivers the credential
    through `LoadCredential=` (D7).

  **Dependencies**: 3.1
- [ ] 3.3 Write `test_jit_scripts.py` (M)
  - Run `mint-jitconfig.sh` and `cleanup-runner.sh` under `bash` with a stub `curl` on `PATH`.
    The stub records its arguments and returns fixture JSON, so the test never touches the
    network.
  - The mint script refuses a credential file whose mode is wider than 0600.
  - The mint script POSTs to `actions/runners/generate-jitconfig` with only the custom labels;
    the runner defaults (`self-hosted`, `Linux`, `ARM64`) ∪ the requested labels equal
    `routing.self_hosted_labels`, compared case-insensitively (D5).
  - The output env file has mode 0600 and contains only `ACTIONS_RUNNER_INPUT_JITCONFIG` and
    `GX10_RUNNER_ID`.
  - The mint script retries with backoff on HTTP 5xx and exits non-zero, writing no env file,
    once `GX10_MINT_MAX_ELAPSED` is spent. The test overrides the base delay and the budget so
    it stays fast.
  - The cleanup script issues a DELETE only for an offline runner id and always exits 0.
  - Before minting, the mint script DELETEs only **offline** runners whose name starts with
    `gx10-<hostname>-<instance>-`; an online runner, another instance's runner and another
    host's runner are left alone, a match on the second page is found, and a failing sweep does
    not stop the mint (D5).

  **Spec scenarios**: ci-runner-infrastructure / "Credential stays on the host", "Mint retries
  are bounded below the start timeout", "JIT labels match the routing labels", "Stale
  registrations of the instance are swept before minting"
  **Design decisions**: D5
  **Dependencies**: 1.2, 1.3
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.4 Author `deploy/gx10-runner/mint-jitconfig.sh` (S)
  - Use `set -euo pipefail`.
  - Read the credential from `$CREDENTIALS_DIRECTORY/github-token`, falling back to
    `GX10_RUNNER_TOKEN_FILE`.
  - Write with umask 077.
  - Sweep this instance's stale offline registrations before minting, across all pages up to
    a 10-page bound (D5).
  - Use exponential backoff with a per-attempt cap of 300 s, inside the total budget
    `GX10_MINT_MAX_ELAPSED` (default 600 s).

  **Dependencies**: 3.3
- [ ] 3.5 Author `deploy/gx10-runner/cleanup-runner.sh` (XS)
  - Delete the runner registration only if it is still registered and offline. Cleanup is
    best-effort and always exits 0.

  **Dependencies**: 3.3
- [ ] 3.6 Write `test_runner_image.py` (XS)
  - The `FROM` line of `Containerfile` names `ghcr.io/actions/actions-runner:<version>@sha256:<64 hex>`
    and does not use `latest`.
  - Every package in `toolchain.txt` is installed by the Containerfile.
  - The final `USER` is not root.
  - The image copies `job-started-hook.sh` and sets `ACTIONS_RUNNER_HOOK_JOB_STARTED` to it
    (D4).
  - `job-started-hook.sh`, run under `bash` with fixture event payloads, exits 0 only for
    `push` to `refs/heads/main`, `workflow_dispatch` and a same-repository `pull_request`, and
    non-zero for a fork `pull_request`, `merge_group`, `pull_request_target` and a `push` to
    another ref (D4).
  - The image sets `ENV UV_CACHE_DIR=/home/runner/.cache/uv` (D6).
  - No `sudoers` grant is added.

  **Spec scenarios**: ci-runner-infrastructure / "Base image is pinned", "Runner image installs
  the hook", "Runner hook refuses a fork PR that rewrote its workflow"
  **Design decisions**: D6
  **Dependencies**: 1.3
- [ ] 3.7 Author `deploy/gx10-runner/Containerfile`, `deploy/gx10-runner/toolchain.txt` and
      `deploy/gx10-runner/job-started-hook.sh` (S)
  - Pin the base image digest: read it from the registry manifest with `podman manifest
    inspect` or `skopeo inspect`. Reading is allowed; building or running an image is not.
  - Follow the D6 baseline toolchain.
  - Write the D4 job-started hook (`set -euo pipefail`, `jq` over `$GITHUB_EVENT_PATH`) and
    install it in the image with `ACTIONS_RUNNER_HOOK_JOB_STARTED`.

  **Dependencies**: 3.6
- [ ] 3.8 Write `test_install_units.py` (XS)
  - Run `install-units.sh --prefix <tmp>` with stub `systemctl`/`loginctl`/`podman` on `PATH`.
    Each stub fails the test if it is invoked.
  - Files land only beneath `<tmp>`.
  - The `loginctl enable-linger` and `systemctl --user enable --now gx10-runner@{1..N}`
    commands are printed but not executed.

  **Spec scenarios**: ci-runner-infrastructure / "Install script does not mutate the host
  during tests", "Scripts default to non-mutating behaviour"
  **Design decisions**: D7
  **Dependencies**: 1.3
- [ ] 3.9 Author `deploy/gx10-runner/install-units.sh` (XS)
  - Use the copy-and-print-only behaviour of D7.

  **Dependencies**: 3.8
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 4 — Measurement and run verification (`scripts/ci/ci_wallclock.py`)

- [ ] 4.1 Write `test_ci_wallclock.py` over JSON fixtures in `skills/tests/ci_runners/fixtures/` (S)
  - The median uses `success` runs only.
  - `compare` checks the 600/540/500 threshold cases and n<5 (insufficient sample).
  - `verify_run` flags each of these:
    - a misrouted routed job (both `expected_lane` values);
    - a hosted job on `gx10`;
    - a conclusion other than `success`/`skipped`, with jobs marked `continue-on-error`
      reported as warnings;
    - a `skipped` job that has no job-level `if:`;
    - a missing job;
    - a jobs-API entry that matches no manifest job (unknown job).
  - Correlation follows the D8 contract: display name = job id or literal `name:`, matrix
    expansions matched by `<display name> (` prefix and each checked (fixture with a matrix job).
  - `verify_run` does **not** flag `dependency-update-remediation` concluding `skipped` with no
    runner (it has a job-level `if:`).
  - The CLI's argument parsing, including `--head-sha`, `--event`, `--since`, `--until`,
    `--limit`, `--expect-lane` and `--workflow-file`, works with no network access. `gh` is
    stubbed.
  - With a recording `gh` stub that serves more matching runs than `--limit`, the issued
    requests are GETs carrying the workflow/event/`head_sha` filters, and paging stops once
    `--limit` runs are collected (no fetch-all-then-truncate).
  - `compare` excludes a run with mixed routed-job placement (or no assigned routed runner)
    from both samples and lists it in `excluded_runs`.
  - `verify-run` without `--workflow-file` fetches the definition at the run's `head_sha`
    (asserted on the recorded `gh api .../contents/...?ref=<sha>` call).

  **Spec scenarios**: ci-runner-infrastructure / "Median ignores cancelled and failed runs",
  "Comparison enforces threshold and sample size", "Run verification flags misrouted jobs",
  "Conditionally skipped job is not a violation", "Unconditional job skipped by an upstream
  failure is a violation", "Rollback check expects hosted placement", "Matrix expansions are
  correlated to their job id", "Failed continue-on-error job is a warning", "CLI fetches are
  filtered and bounded", "Runs with mixed placement are excluded from comparison"
  **Design decisions**: D8
  **Dependencies**: 1.2, 1.3
- [ ] 4.2 Implement the pure functions `median_wallclock`, `compare` and `verify_run` in
      `scripts/ci/ci_wallclock.py` (S)
  - Use the standard library plus PyYAML only.

  **Dependencies**: 4.1
- [ ] 4.3 Add the CLI subcommands `median`, `compare` and `verify-run` (S)
  - Each fetches through `gh api` read-only GETs, bounded by `--limit` (default 200).
  - `median` and `compare` select runs with `--workflow` (required), `--head-sha`, `--event`,
    `--since` and `--until` (D8).
  - `verify-run` takes `--expect-lane self-hosted|hosted` (default `self-hosted`) and exits
    non-zero on any violation; warnings (failed `continue-on-error` jobs) are printed and do
    not change the exit code.

  **Dependencies**: 4.2
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 5 — Operator runbook

- [ ] 5.1 Write `test_runbook.py` (XS)
  - `docs/guides/self-hosted-ci-runners.md` has headings `O1` through `O12`.
  - Each section contains at least one fenced `bash` verification block.
  - The runbook states the hard boundary.
  - The runbook names the rollback command (`gh variable set CI_RUNNER_LANE --body hosted`).

  **Spec scenarios**: ci-runner-infrastructure / "Runbook covers every operator step with a
  verification command"
  **Design decisions**: D9
  **Dependencies**: 1.3
- [ ] 5.2 Author `docs/guides/self-hosted-ci-runners.md` (S)
  - Write steps O1–O12 from § 7, each with its exact commands and verification.
  - Include the queued-run detection command for D9.
  - Include the GitHub App upgrade path for D5.
  - Include the cache opt-in for D6: it is off by default; enabling it sets
    `GX10_RUNNER_CACHE_ARGS=--volume gx10-runner-uv-cache:/home/runner/.cache/uv` only after the
    operator fills in a recorded risk-acceptance line (date, confirmation that every
    same-repository writer, including Dependabot and agent branches, is acceptable); disabling
    empties it and removes the volume; a move to team mode requires disabling it (A10).
  - Include the podman-5 note: keep the explicit `slirp4netns` network, or switch to
    `pasta:--no-map-gw` only through a reviewed unit change (A11).

  **Dependencies**: 5.1
- [ ] 5.3 Link the runbook from `docs/guides/documentation.md`, under setup and deployment (XS)

  **Dependencies**: 5.2
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 6 — Integration

- [ ] 6.1 Run the full skills suite and validators (S)
  - Run the full skills suite with `skills/.venv/bin/python -m pytest skills/tests -q`.
  - Run `openspec validate migrate-ci-to-self-hosted-gx10-runners --strict`.
  - If `actionlint` is available, run it over both workflows. Otherwise record it as skipped.
  - Confirm with `git diff origin/main --stat` that the diff touches only files inside the
    package scopes.
  - Cross-check the runbook against the kit: every `GX10_*` variable and every
    `deploy/gx10-runner/*` path that `docs/guides/self-hosted-ci-runners.md` names exists in
    `gx10-runner.env.example` or the kit, and every `ci_wallclock.py` flag it uses is accepted by
    the CLI's parser (wp-docs runs in parallel with the kit, so drift is caught here).

  **Dependencies**: 2.9, 3.2, 3.4, 3.5, 3.7, 3.9, 4.3, 5.3

## Phase 7 — OPERATOR-ONLY (post-merge; NOT implementation tasks)

> These steps need a human with host and repository-admin access. Autopilot phases MUST NOT
> perform them or mark them done. The validation report lists them as `pending_gate`. The
> runbook (§ 5) holds the full commands.
>
> **Order:** O1–O5 first, then O6 as the dry run, O7 to flip, O8–O11 to measure and verify, and
> O12 to roll back if needed.

- [ ] O1 Create the dedicated host user and enable linger *(outcome 4, host half)*
  - Run `sudo useradd --system --create-home --shell /usr/sbin/nologin ghrunner`, then give it
    a subordinate id range, which `useradd --system` does not allocate and rootless podman
    needs for the non-root `runner` user in the image. Pick a 65536-id range that overlaps no
    entry in `/etc/subuid` or `/etc/subgid` (start above the highest existing end), then
    `sudo usermod --add-subuids <start>-<start+65535> --add-subgids <start>-<start+65535> ghrunner`.
  - Run `sudo loginctl enable-linger ghrunner`.
  - Because the account has no login shell, run every later "as `ghrunner`" command as
    `sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) <command>` (or
    `systemctl --user --machine=ghrunner@ …` for unit operations).
  - **Verify**: `loginctl show-user ghrunner -p Linger` prints `Linger=yes`, and
    `grep ghrunner /etc/subuid /etc/subgid` shows one range in each file, and no two entries in
    either file overlap (`sort -t: -k2 -n /etc/subuid` shows each start above the previous
    entry's end).
- [ ] O2 Provision the registration credential
  - Create a fine-grained PAT for this repository only, with *Administration: read and write*
    and an expiry of 90 days or less.
  - Store it as `~ghrunner/.config/gx10-runner/token` with mode 0600; the unit's
    `LoadCredential=github-token:%h/.config/gx10-runner/token` reads it from there (D7).
  - Copy `deploy/gx10-runner/gx10-runner.env.example` to `~ghrunner/.config/gx10-runner/env`
    and fill in the repository slug and image reference (`EnvironmentFile=`, D7).
  - **Verify**: `stat -c %a ~ghrunner/.config/gx10-runner/token` prints `600`, and
    `GH_TOKEN=$(sudo cat …) gh api repos/{owner}/{repo}/actions/runners --jq .total_count`
    exits 0.
- [ ] O3 Build the runner image on the GX10 as `ghrunner`
  - Run `podman build -t localhost/gx10-runner:<sha> deploy/gx10-runner`.
  - **Verify**: `podman image inspect localhost/gx10-runner:<sha> --format '{{.Architecture}}'`
    prints `arm64`.
- [ ] O4 Install the host-service isolation control, then install and enable the units
  - First, as root, install the isolation control (D6). Preferred: a `table inet` `output`
    hook chain with, in order, `meta skuid ghrunner ip daddr 127.0.0.53 udp dport 53 accept`,
    the same rule for `tcp`, `meta skuid ghrunner fib daddr type local drop`, and drops for
    `ghrunner`-owned traffic to `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`,
    `100.64.0.0/10`, `169.254.0.0/16`, `fc00::/7`, `fe80::/10` and out of `tailscale0`.
    Persist it in `/etc/nftables.conf` and `sudo systemctl enable nftables`. Fallback: rebind
    every host service the runners must not reach to `127.0.0.1`.
  - Then run `deploy/gx10-runner/install-units.sh`, then `systemctl --user daemon-reload` and
    `systemctl --user enable --now gx10-runner@{1..8}` as `ghrunner`.
  - **Verify**:
    `gh api repos/{owner}/{repo}/actions/runners --jq '[.runners[]|select(any(.labels[];.name=="gx10"))|.status]'`
    lists 8 entries, all `online`.
  - **Also verify**: for each address in `10.0.2.2 $(hostname -I)` and each port in
    `54322 <coordinator-port>`,
    `podman exec gx10-runner-1 bash -c 'timeout 3 bash -c "exec 3<>/dev/tcp/<addr>/<port>" && echo reachable || echo unreachable'`
    prints `unreachable` (a transport-level connect; an HTTP `curl` probe is wrong here, because
    it fails after connecting to a non-HTTP service such as Postgres);
    the loop includes the host's IPv6 addresses;
    `podman exec gx10-runner-1 getent hosts api.github.com` resolves (the DNS exemption works;
    a host-side `getent` does not exercise it);
    `grep -c skuid /etc/nftables.conf` is non-zero (the rules are persistent);
    `sudo nft list ruleset | grep skuid` shows the rules (or `ss -ltnp` shows those ports bound
    to `127.0.0.1` only); and
    `podman inspect gx10-runner-1 --format '{{.HostConfig.NetworkMode}}'` shows `slirp4netns`.
    A probe of `10.0.2.2` alone is not sufficient (D6).
  - If the operator opts in to the shared uv cache (D6/A10), fill in the runbook's
    risk-acceptance line (date; confirmation that every same-repository writer, including
    Dependabot and agent branches, is acceptable) before setting `GX10_RUNNER_CACHE_ARGS`.
- [ ] O5 Set the fork-PR approval policy *(outcome 3, settings half)*
  - Run `gh api -X PUT repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval -f approval_policy=all_external_contributors`.
  - Confirm the runners are repository-scoped, not organization-scoped.
  - **Verify**:
    `gh api repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval --jq .approval_policy`
    prints `all_external_contributors`.
- [ ] O6 Self-hosted dry run before flipping *(outcome 1)*
  - Run `gh workflow run ci.yml --ref main -f runner_lane=self-hosted` and the same command for
    `security.yml`.
  - **Verify**: `python scripts/ci/ci_wallclock.py verify-run <run-id> --workflow ci.yml`, and
    the same for `security.yml`, report 0 violations.
  - If a routed job fails on arm64, open a PR that moves it to `hosted` with
    `reason_code: amd64-only`, then repeat O6.
- [ ] O7 Flip the lane
  - Run `gh variable set CI_RUNNER_LANE --body self-hosted`.
  - **Verify**: `gh variable get CI_RUNNER_LANE` prints `self-hosted`, and the next PR's
    `verify-run` reports 0 violations.
- [ ] O8 Measure wall-clock time *(outcome 2)*
  - Dispatch 5 or more paired runs per lane on the same commit (`runner_lane=hosted` versus
    `self-hosted`).
  - **Verify**: `python scripts/ci/ci_wallclock.py compare --baseline-lane hosted --candidate-lane self-hosted --workflow ci.yml --event workflow_dispatch --head-sha <sha>`
    passes, meaning the median ratio is 0.85 or less with n ≥ 5 on each side.
  - **Corroborate**: run `median` over 20 or more PR runs before and after the O7 date.
  - If the comparison fails, tune the instance count, or move the slowest routed jobs to
    `measured-slower`.
- [ ] O9 Check per-job ephemerality *(outcome 4)*
  - **Verify**: after 3 or more jobs have run on instance 1,
    `journalctl --user -u gx10-runner@1 | grep -c 'Listening for Jobs'` is 3 or more, and
    `gh api repos/{owner}/{repo}/actions/runs/<run-id>/jobs --jq '.jobs[].runner_name'` shows
    distinct names (JIT runners deregister after their job, so the runners list cannot show
    them).
  - **Also verify**: `podman ps -a --filter name=gx10-runner --filter status=exited` is empty.
- [ ] O10 Check reboot survival *(outcome 4)*
  - Run `sudo systemctl reboot`. Do not log in as `ghrunner`.
  - **Verify**: `sudo systemctl --user --machine=ghrunner@ is-active gx10-runner@1` prints
    `active`, and the runner shows `online` in the runners API within 2 minutes of boot.
  - **Also verify** that host isolation survived the reboot: `sudo nft list ruleset | grep skuid`
    lists the O4 rules (or `ss -ltnp` still shows loopback-only binding), and the O4
    TCP-connect probes and in-container DNS check give the same results as before.
- [ ] O11 Fork-PR end-to-end check *(outcome 3)*
  - Open a trivial PR from a fork account, and a second one that edits `ci.yml` to set one
    routed job's `runs-on` to the GX10 labels and delete its guard step.
  - **Verify**: `gh run list --branch <fork-branch> --json status,conclusion` shows the run
    awaiting approval (`action_required`).
  - After approval, `python scripts/ci/ci_wallclock.py verify-run <run-id> --workflow ci.yml --expect-lane hosted`
    reports 0 violations: every job ran on GitHub-hosted runners (without `--expect-lane hosted`
    the default `self-hosted` expectation would flag every routed job).
  - For the second PR, after approval, the rewritten job fails in its `Set up job` phase with
    the job-started hook's refusal message and no step of that job runs (D4).
- [ ] O12 Rollback drill
  - Run `gh variable set CI_RUNNER_LANE --body hosted`.
  - **Verify**: the next CI run's `verify-run --expect-lane hosted` shows every job on
    GitHub-hosted runners. Then restore with O7.
