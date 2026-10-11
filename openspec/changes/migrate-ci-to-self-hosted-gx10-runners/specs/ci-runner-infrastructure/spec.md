## ADDED Requirements

### Requirement: Lane Manifest Classifies Every Workflow Job

The repository SHALL maintain a lane manifest at `.github/runner-lanes.yaml`, valid against `.github/runner-lanes.schema.json`. The manifest SHALL classify every job in `.github/workflows/ci.yml` and `.github/workflows/security.yml` as either `routed` or `hosted`. Every `hosted` job MUST carry a `reason_code` from the closed set `container-engine`, `amd64-only`, `privileged-token` and `measured-slower`, together with a non-empty written `reason`.

#### Scenario: Unclassified job fails the suite
- **WHEN** a job id exists in `ci.yml` or `security.yml` but not in the manifest
- **THEN** the lane manifest test fails and names the unclassified workflow and job id

#### Scenario: Stale manifest entry fails the suite
- **WHEN** the manifest names a job id that no longer exists in its workflow
- **THEN** the lane manifest test fails and names the stale entry

#### Scenario: Hosted job without justification is rejected
- **WHEN** a manifest entry has `lane: hosted` and lacks `reason_code` or has an empty `reason`
- **THEN** schema validation of the manifest fails

### Requirement: Routed Jobs Default To The Hosted Lane

Every `routed` job SHALL use the single canonical `runs-on` expression defined in design D3. Under that expression a job SHALL resolve to `ubuntu-latest` unless the event is not a fork pull request and one of the following holds:
- a `workflow_dispatch` `runner_lane` input of `self-hosted` is supplied;
- the `CI_RUNNER_LANE` repository variable equals `self-hosted`, and no dispatch override of `hosted` is supplied.

The self-hosted label set inside the expression MUST equal the manifest's `routing.self_hosted_labels`.

#### Scenario: Unset variable keeps CI on hosted runners
- **WHEN** the reference evaluator resolves the canonical expression for a same-repository `pull_request`, `push` or `merge_group` event with `CI_RUNNER_LANE` unset
- **THEN** the result is `ubuntu-latest`

#### Scenario: Variable opts same-repository events into the self-hosted lane
- **WHEN** the reference evaluator resolves the expression for a same-repository `pull_request` with `CI_RUNNER_LANE` set to `self-hosted`
- **THEN** the result is the manifest's self-hosted label set

#### Scenario: Dispatch input overrides the variable in both directions
- **WHEN** the expression is resolved for a `workflow_dispatch` event with `runner_lane` set to `hosted` while `CI_RUNNER_LANE` is `self-hosted`
- **THEN** the result is `ubuntu-latest`
- **AND** with `runner_lane` set to `self-hosted` while the variable is unset, the result is the self-hosted label set

#### Scenario: Routed job drifts from the canonical expression
- **WHEN** any `routed` job's `runs-on` differs from the canonical expression after whitespace normalization
- **THEN** the workflow routing test fails and names the job

### Requirement: Hosted-Pinned Jobs Are Explicit

Every `hosted` job SHALL declare a literal `runs-on: ubuntu-latest` and MUST NOT use the routing expression. A `routed` job MUST NOT declare `services:`, and its `run:` blocks MUST NOT invoke `docker`, `podman`, `sudo` or `apt-get` in command position, except for an entry in the tool-parity allowlist that names the workflow, job and command with a justifying comment (the allowlist starts empty). A `routed` job that invokes `npm`, `npx`, `node`, `java` or `go` in command position MUST include the matching setup action. A command name that appears only inside a path or identifier, such as `scripts/check_docker_imports.py`, is not an invocation.

#### Scenario: Container-engine job marked routed is rejected
- **WHEN** a job that declares `services:` or runs `docker`, `podman`, `sudo` or `apt-get` is classified `routed`
- **THEN** the tool-parity test fails, unless the job and command appear in the documented allowlist with a comment

#### Scenario: Hosted job uses a literal hosted label
- **WHEN** the routing test reads a manifest job with `lane: hosted`
- **THEN** that job's `runs-on` equals the string `ubuntu-latest`

#### Scenario: Command name inside a script path is not an invocation
- **WHEN** a routed job's `run:` block contains `uv run python scripts/check_docker_imports.py` and no other container command
- **THEN** the tool-parity test passes for that job without an allowlist entry

#### Scenario: Routed job calls npm without setup-node
- **WHEN** a routed job's `run:` block invokes `npm` and the job has no `actions/setup-node` step
- **THEN** the tool-parity test fails and names the job and command

### Requirement: Fork Pull Requests Never Execute On Self-Hosted Runners

A `pull_request` event whose head repository differs from the base repository SHALL resolve to `ubuntu-latest` regardless of the variable value. Every `routed` job's first step SHALL be a guard that fails the job when it is running on a self-hosted runner for a fork pull request. Neither workflow SHALL declare the triggers `pull_request_target`, `workflow_run` or `issue_comment`. The repository's fork-PR contributor approval policy MUST be set to require approval for all external contributors; this is an operator-only step with a verification command.

#### Scenario: Fork pull request routes to hosted even with the self-hosted lane enabled
- **WHEN** the reference evaluator resolves the expression for a fork `pull_request` with `CI_RUNNER_LANE` set to `self-hosted`
- **THEN** the result is `ubuntu-latest`

#### Scenario: Routed job lacks the in-job fork guard
- **WHEN** a routed job's first step is not the canonical fork guard, with condition `runner.environment == 'self-hosted'` combined with the fork test
- **THEN** the fork guard test fails and names the job

#### Scenario: Privileged trigger is introduced
- **WHEN** `ci.yml` or `security.yml` declares `pull_request_target`, `workflow_run` or `issue_comment`
- **THEN** the trigger allowlist test fails

#### Scenario: Operator verifies the approval policy
- **WHEN** the operator runs `gh api repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval --jq .approval_policy`
- **THEN** the output is `all_external_contributors`

### Requirement: Runners Are Ephemeral Per Job

The runner kit under `deploy/gx10-runner/` SHALL meet all of the following:
- It SHALL register each runner with a single-use just-in-time configuration minted on the host before the container starts.
- It SHALL run the runner in a container started with `--rm`, so that one container serves exactly one job.
- It SHALL NOT pass the registration credential, a container engine socket, host networking or privileged mode into the container.
- It SHALL pin the container network explicitly to `slirp4netns:allow_host_loopback=false`, so that host loopback services stay unreachable regardless of the host's podman default.
- It SHALL start only the locally built image (`--pull=never`).
- It SHALL bound the mint script's total retry time below the unit's start timeout.
- It SHALL pin its base image by version and digest.

#### Scenario: Unit runs a removable container with a single-use config
- **WHEN** the unit test parses `gx10-runner@.service`
- **THEN** `ExecStartPre` invokes `mint-jitconfig.sh`
- **AND** `ExecStart` invokes `podman run` with `--rm`, `--pull=never`, `--env-file`, `--cap-drop ALL`, `--security-opt no-new-privileges` and `--network slirp4netns:allow_host_loopback=false`

#### Scenario: Dangerous container options are absent
- **WHEN** the unit test scans `ExecStart`
- **THEN** none of `--privileged`, `--network host`, `--network=host`, a `--network` value other than `slirp4netns:allow_host_loopback=false`, or a volume whose source ends in `.sock` is present

#### Scenario: Credential stays on the host
- **WHEN** the runner-kit tests inspect `mint-jitconfig.sh` and the container env-file contract
- **THEN** the env file written for the container contains only the JIT config and the runner id
- **AND** the mint script refuses a credential file whose mode is wider than `0600`

#### Scenario: Mint retries are bounded below the start timeout
- **WHEN** the stubbed GitHub API returns HTTP 503 on every call and the test sets a short retry budget
- **THEN** `mint-jitconfig.sh` retries with growing delays, exits non-zero once the budget is spent, and writes no env file
- **AND** the unit's `TimeoutStartSec` is greater than the default `GX10_MINT_MAX_ELAPSED` in the example env file

#### Scenario: JIT labels match the routing labels
- **WHEN** the runner-kit test compares the labels requested by `mint-jitconfig.sh` with `routing.self_hosted_labels`
- **THEN** they are equal

#### Scenario: Base image is pinned
- **WHEN** the runner-kit test reads `deploy/gx10-runner/Containerfile`
- **THEN** its `FROM` line names a version tag and an `@sha256:` digest, and does not use `latest`

#### Scenario: Operator observes per-job ephemerality
- **WHEN** after three jobs have run on instance 1 the operator reads the runner names those jobs ran on with `gh api repos/{owner}/{repo}/actions/runs/<run-id>/jobs --jq '.jobs[].runner_name'` (JIT runners deregister after their job, so the runners list no longer shows them) and inspects `podman ps -a --filter name=gx10-runner --filter status=exited`
- **THEN** each executed job ran on a distinct runner name
- **AND** no exited runner container remains

### Requirement: Runners Survive Host Reboot Via systemd

The runner kit SHALL provide a systemd user template unit, `gx10-runner@.service`, with `Restart=always` and an explicit `TimeoutStartSec` in `[Service]`, `StartLimitIntervalSec=0` in `[Unit]`, and `WantedBy=default.target` in `[Install]`. The unit is intended to run under a dedicated lingering, unprivileged host user. Enabling linger and the units is an operator-only step.

#### Scenario: Unit restart and install properties
- **WHEN** the unit test parses `gx10-runner@.service`
- **THEN** `[Service]` has `Restart=always` and a `TimeoutStartSec` greater than 90
- **AND** `[Unit]` has `StartLimitIntervalSec=0`
- **AND** `[Install]` has `WantedBy=default.target`

#### Scenario: Install script does not mutate the host during tests
- **WHEN** the runner-kit test runs `install-units.sh --prefix <tmpdir>`
- **THEN** it writes only beneath that prefix
- **AND** it prints, without executing, the `loginctl enable-linger` and `systemctl --user enable --now` commands

#### Scenario: Operator verifies reboot survival
- **WHEN** the GX10 is rebooted and nobody logs in
- **THEN** `systemctl --user --machine=ghrunner@ is-active gx10-runner@1` reports `active`
- **AND** the runner appears `online` in `gh api repos/{owner}/{repo}/actions/runners`

### Requirement: CI Wall-Clock Measurement And Run Verification

The repository SHALL provide `scripts/ci/ci_wallclock.py` with three functions:
- `median_wallclock(runs)` SHALL compute the median wall-clock seconds over successful runs only.
- `compare(baseline, candidate, threshold=0.85, min_n=5)` SHALL pass only when the candidate median is at most `threshold` times the baseline median and both samples meet `min_n`.
- `verify_run(jobs, manifest, workflow, expected_lane="self-hosted")` SHALL report: every routed job that did not run on a `gx10`-labelled runner (or, with `expected_lane="hosted"`, every routed job that ran on a self-hosted runner); every hosted job that ran on a self-hosted runner; every job that concluded anything other than `success` or `skipped`; every `skipped` job whose definition has no job-level `if:`; and every manifest job missing from the run. A `skipped` job that has a job-level `if:` SHALL NOT be reported, and its runner placement SHALL NOT be checked.

The CLI SHALL select runs only through explicit filters (`--workflow`, `--head-sha`, `--event`, `--since`, `--until`) and SHALL cap fetched runs with `--limit`.

#### Scenario: Median ignores cancelled and failed runs
- **WHEN** `median_wallclock` receives runs whose conclusions include `cancelled` and `failure`
- **THEN** only `success` runs contribute to the median

#### Scenario: Comparison enforces threshold and sample size
- **WHEN** `compare` receives a baseline median of 600 s and a candidate median of 540 s, each with n=6
- **THEN** it fails, because 540 is greater than 0.85 × 600 = 510
- **AND** with a candidate median of 500 s it passes
- **AND** with n=4 on either side it fails for insufficient samples

#### Scenario: Run verification flags misrouted jobs
- **WHEN** `verify_run` receives a run in which a routed job ran on a `ubuntu-latest` runner while the lane was self-hosted, and a hosted job ran on a runner labelled `gx10`
- **THEN** it returns one violation for each job, naming the job and the expected lane

#### Scenario: Conditionally skipped job is not a violation
- **WHEN** `verify_run` receives a run in which `dependency-update-remediation`, which has a job-level `if:`, concluded `skipped` with no runner assigned, and every other job succeeded on its expected lane
- **THEN** it returns zero violations

#### Scenario: Unconditional job skipped by an upstream failure is a violation
- **WHEN** a job with no job-level `if:` concluded `skipped`
- **THEN** `verify_run` returns a violation naming that job

#### Scenario: Rollback check expects hosted placement
- **WHEN** `verify_run` is called with `expected_lane="hosted"` and a routed job ran on a runner labelled `gx10`
- **THEN** it returns a violation naming that job

#### Scenario: Operator confirms both workflows green on the self-hosted lane
- **WHEN** the operator dispatches `ci.yml` and `security.yml` with `runner_lane=self-hosted` and runs `python scripts/ci/ci_wallclock.py verify-run <run-id> --workflow <file>` for each run
- **THEN** both report zero violations

### Requirement: Implementation Does Not Mutate Hosts Or Repository Settings

The implementation of this capability MUST NOT perform any of the following actions:
- register runners;
- mint registration or JIT tokens;
- change repository or organization settings or variables;
- install, enable or start systemd units or containers;
- modify workflows on `main`.

Each of those actions SHALL be documented as an operator-only runbook step in `docs/guides/self-hosted-ci-runners.md`, and each step MUST carry a concrete verification command.

#### Scenario: Runbook covers every operator step with a verification command
- **WHEN** the runbook test parses `docs/guides/self-hosted-ci-runners.md`
- **THEN** each operator step O1 to O12 appears as a heading
- **AND** each step contains at least one fenced verification command block

#### Scenario: Scripts default to non-mutating behaviour
- **WHEN** `install-units.sh` runs, with any arguments, or `ci_wallclock.py` runs under test
- **THEN** no `systemctl`, `loginctl` or `podman` command and no mutating `gh api` call is executed
- **AND** the commands that would mutate the host are only printed
