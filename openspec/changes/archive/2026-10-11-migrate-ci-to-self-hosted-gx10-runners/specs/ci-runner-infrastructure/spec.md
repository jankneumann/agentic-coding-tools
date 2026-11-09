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

Every `routed` job SHALL use the single canonical `runs-on` expression defined in design D3. Under that expression a job SHALL resolve to `ubuntu-latest` unless the event is eligible — a `push`, a `workflow_dispatch`, or a same-repository `pull_request` (never a fork `pull_request`, never `merge_group`, never any other event) — and one of the following holds:
- a `workflow_dispatch` `runner_lane` input of `self-hosted` is supplied;
- the `CI_RUNNER_LANE` repository variable equals `self-hosted`, and no dispatch override of `hosted` is supplied.

The self-hosted label set inside the expression MUST equal the manifest's `routing.self_hosted_labels`.

Both `ci.yml` and `security.yml` SHALL declare a `workflow_dispatch` trigger with a `runner_lane` choice input whose options are exactly `auto`, `hosted` and `self-hosted`, with default `auto`.

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

#### Scenario: Expression is tied to every manifest routing field
- **WHEN** the routing test changes the manifest's `routing.self_hosted_labels`, `routing.repository_variable` or `routing.dispatch_input` without changing the workflows
- **THEN** the test fails, because the expression's `fromJSON` labels, its `vars.<name>` reference and its `inputs.<name>` reference must equal those three fields

#### Scenario: Merge queue runs stay hosted
- **WHEN** the reference evaluator resolves the expression for a `merge_group` event with `CI_RUNNER_LANE` set to `self-hosted`
- **THEN** the result is `ubuntu-latest`, because a merge-group commit can contain an approved fork pull request's code

#### Scenario: Any other event stays hosted
- **WHEN** the reference evaluator resolves the expression for an event outside `push`, `workflow_dispatch` and `pull_request` (for example `schedule`) with `CI_RUNNER_LANE` set to `self-hosted`
- **THEN** the result is `ubuntu-latest`

#### Scenario: Dispatch trigger and lane input are declared
- **WHEN** the fork guard test reads `ci.yml` and `security.yml`
- **THEN** each declares `workflow_dispatch` with a `runner_lane` choice input of options `auto`, `hosted`, `self-hosted` and default `auto`

#### Scenario: Routed job drifts from the canonical expression
- **WHEN** any `routed` job's `runs-on` differs from the canonical expression after whitespace normalization
- **THEN** the workflow routing test fails and names the job

### Requirement: Hosted-Pinned Jobs Are Explicit

Every `hosted` job SHALL declare a literal `runs-on: ubuntu-latest` and MUST NOT use the routing expression. A `routed` job MUST NOT declare `services:`, and its `run:` blocks MUST NOT invoke `docker`, `podman`, `sudo` or `apt-get` in command position, except for an entry in the tool-parity allowlist that names the workflow, job and command with a justifying comment (the allowlist starts empty). A `routed` job that invokes `npm`, `npx`, `node`, `java` or `go` in command position MUST include the matching setup action. A command name that appears only inside a path or identifier, such as `scripts/check_docker_imports.py`, is not an invocation. The scan covers `run:` text only; a command invoked indirectly from inside a script that a step calls is outside its reach and is caught by the operator's self-hosted dry run (O6), which moves such a job to `hosted` through the manifest.

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

A `pull_request` event whose head repository differs from the base repository, and every `merge_group` event (whose merge commit can contain approved fork code), SHALL resolve to `ubuntu-latest` regardless of the variable value. Every `routed` job's first step SHALL be a guard that fails the job when it is running on a self-hosted runner for any event outside the D3 eligibility allowlist, which includes every fork pull request and every `merge_group` run. Because a `pull_request` run uses the pull request's own workflow YAML, the runner image SHALL enforce this independently of the workflows: it SHALL install a job-started hook (`ACTIONS_RUNNER_HOOK_JOB_STARTED`) that fails the job before any step runs unless the GitHub-written event payload shows a `push` to `refs/heads/main`, a `workflow_dispatch`, or a `pull_request` whose head repository equals the base repository. Neither workflow SHALL declare the triggers `pull_request_target`, `workflow_run` or `issue_comment`. The repository's fork-PR contributor approval policy MUST be set to require approval for all external contributors; this is an operator-only step with a verification command.

#### Scenario: Fork pull request routes to hosted even with the self-hosted lane enabled
- **WHEN** the reference evaluator resolves the expression for a fork `pull_request` with `CI_RUNNER_LANE` set to `self-hosted`
- **THEN** the result is `ubuntu-latest`

#### Scenario: Routed job lacks the in-job fork guard
- **WHEN** a routed job's first step is not the canonical guard, with condition `runner.environment == 'self-hosted'` combined with the negation of the D3 event-eligibility clause
- **THEN** the fork guard test fails and names the job

#### Scenario: Runner hook refuses a fork PR that rewrote its workflow
- **WHEN** the hook test runs `job-started-hook.sh` with `GITHUB_EVENT_NAME=pull_request` and an event payload whose `pull_request.head.repo.full_name` differs from `GITHUB_REPOSITORY`
- **THEN** the hook exits non-zero
- **AND** it also exits non-zero for `merge_group`, for `pull_request_target`, and for `push` to a ref other than `refs/heads/main`
- **AND** it exits zero for `push` to `refs/heads/main`, for `workflow_dispatch`, and for a same-repository `pull_request`

#### Scenario: Runner image installs the hook
- **WHEN** the image test reads `deploy/gx10-runner/Containerfile`
- **THEN** it copies `job-started-hook.sh` into the image and sets `ACTIONS_RUNNER_HOOK_JOB_STARTED` to its path

#### Scenario: Privileged trigger is introduced
- **WHEN** `ci.yml` or `security.yml` declares `pull_request_target`, `workflow_run` or `issue_comment`
- **THEN** the trigger allowlist test fails

#### Scenario: Operator verifies the approval policy
- **WHEN** the operator runs `gh api repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval --jq .approval_policy`
- **THEN** the output is `all_external_contributors`

### Requirement: Runners Are Ephemeral Per Job

The runner kit under `deploy/gx10-runner/` SHALL meet all of the following:
- It SHALL register each runner with a single-use just-in-time configuration minted on the host before the container starts.
- It SHALL run the runner in a container started with `--rm`, so that one container serves exactly one job, and with `--replace`, so that a container left over from an unclean stop cannot wedge the restart loop.
- It SHALL delete the instance's own registration on stop (`ExecStopPost` runs `cleanup-runner.sh`) and, before minting, SHALL delete only the instance's own stale offline registrations, identified by the runner-name prefix `gx10-<hostname>-<instance>-`, searching every page of the runners list up to a bounded page count.
- It SHALL load its operator configuration through `EnvironmentFile=` and deliver the registration credential through `LoadCredential=`.
- It SHALL NOT pass the registration credential, a container engine socket, host networking or privileged mode into the container.
- It SHALL pin the container network explicitly to `slirp4netns:allow_host_loopback=false`, so that host loopback services stay unreachable regardless of the host's podman default.
- It SHALL start only the locally built image (`--pull=never`).
- It SHALL bound the mint script's total retry time below the unit's start timeout.
- It SHALL pin its base image by version and digest.
- It SHALL mount no shared cache volume by default; a shared uv cache volume is mounted only when the operator sets `GX10_RUNNER_CACHE_ARGS` to the documented named-volume value after recording a risk acceptance.
- Its runbook SHALL require an operator-installed control that keeps host services unreachable from runner containers on every host address, not only through the loopback mapping.

#### Scenario: Unit runs a removable container with a single-use config
- **WHEN** the unit test parses `gx10-runner@.service`
- **THEN** `ExecStartPre` invokes `mint-jitconfig.sh`
- **AND** `ExecStart` invokes `podman run` with `--rm`, `--replace`, `--pull=never`, `--env-file`, `--cap-drop ALL`, `--security-opt no-new-privileges` and `--network slirp4netns:allow_host_loopback=false`
- **AND** `ExecStopPost` invokes `cleanup-runner.sh`

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

#### Scenario: Unit wiring delivers configuration and credential
- **WHEN** the unit test parses `gx10-runner@.service` and `gx10-runner.env.example`
- **THEN** `[Service]` declares `EnvironmentFile=` for the operator env file and `LoadCredential=github-token:<path>`
- **AND** every variable referenced by `ExecStartPre` or `ExecStart` is defined in the example env file

#### Scenario: Stale registrations of the instance are swept before minting
- **WHEN** the stubbed runners API lists an offline runner `gx10-<host>-1-<epoch>`, an online runner with the same prefix, and an offline runner `gx10-<host>-2-<epoch>`, and `mint-jitconfig.sh 1` runs
- **THEN** it deletes only the offline instance-1 runner before requesting a new JIT config
- **AND** a matching offline runner served on the second page of the runners list is also deleted

#### Scenario: Shared cache is off unless the operator opts in
- **WHEN** the unit test expands `ExecStart` with the example env file's `GX10_RUNNER_CACHE_ARGS` (empty)
- **THEN** no `--volume` argument is present
- **AND** with the documented opt-in value the only added arguments are `--volume gx10-runner-uv-cache:/home/runner/.cache/uv`

#### Scenario: Operator verifies host services are unreachable on every host address
- **WHEN** the operator attempts a TCP connect (not an HTTP request) to `:54322` and the coordinator API port from inside a runner container at `10.0.2.2` and at every address printed by `hostname -I`
- **THEN** every connect is refused or times out
- **AND** either the persistent `table inet` nftables rules (a DNS exemption for the host stub resolver, then drops of `ghrunner`-owned traffic to local addresses and to private, CGNAT and link-local ranges) are listed and persisted by a dedicated boot-time unit that loads only that table (never through `nftables.service`, whose stock configuration flushes the whole ruleset), or `ss -ltnp` shows those ports bound to `127.0.0.1` only
- **AND** `api.github.com` resolves from inside the runner container
- **AND** after a host reboot the same rules are listed and the same probes still fail

#### Scenario: JIT labels match the routing labels
- **WHEN** the runner-kit test compares the labels requested by `mint-jitconfig.sh` with `routing.self_hosted_labels`
- **THEN** the request carries no runner default label (`self-hosted`, `Linux`, `ARM64`)
- **AND** the defaults together with the requested labels equal `routing.self_hosted_labels`, compared case-insensitively

#### Scenario: Base image is pinned
- **WHEN** the runner-kit test reads `deploy/gx10-runner/Containerfile`
- **THEN** its `FROM` line names a version tag and an `@sha256:` digest, and does not use `latest`

#### Scenario: Operator observes per-job ephemerality
- **WHEN** after three jobs have run on instance 1 the operator reads the runner names those jobs ran on with `gh api repos/{owner}/{repo}/actions/runs/<run-id>/jobs --jq '.jobs[].runner_name'` (JIT runners deregister after their job, so the runners list no longer shows them) and inspects `podman ps -a --filter name=gx10-runner --filter status=exited`
- **THEN** each executed job ran on a distinct runner name
- **AND** no exited runner container remains

### Requirement: Runners Survive Host Reboot Via systemd

The runner kit SHALL provide a systemd user template unit, `gx10-runner@.service`, with `Restart=always` and an explicit `TimeoutStartSec` in `[Service]`, `StartLimitIntervalSec=0` in `[Unit]`, and `WantedBy=default.target` in `[Install]`. The unit is intended to run under a dedicated lingering, unprivileged host user. Enabling linger and the units is an operator-only step. The kit's `install-units.sh` SHALL only copy files beneath its `--prefix` and print, never execute, the `loginctl` and `systemctl` commands that enable them.

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
- `median_wallclock(runs, *, conclusion="success")` SHALL compute the median wall-clock seconds over successful runs only.
- `compare(baseline, candidate, *, threshold=0.85, min_n=5)` SHALL pass only when the candidate median is at most `threshold` times the baseline median and both samples meet `min_n`.
- `verify_run(jobs, manifest, workflow, expected_lane="self-hosted")` SHALL report: every routed job that did not run on a `gx10`-labelled runner (or, with `expected_lane="hosted"`, every routed job that ran on a self-hosted runner); every hosted job that ran on a self-hosted runner; every job that concluded anything other than `success` or `skipped`, except that a job declared `continue-on-error: true` SHALL be reported as a warning rather than a violation; every `skipped` job whose definition has no job-level `if:`; and every manifest job missing from the run. A `skipped` job that has a job-level `if:` SHALL NOT be reported, and its runner placement SHALL NOT be checked. `verify_run` SHALL correlate manifest job ids with jobs-API entries through the display name derived from the workflow definition (the job id, or a literal `name:`; matrix expansions match `<display name> (` and are each checked), and SHALL report any jobs-API entry that matches no manifest job.

The CLI SHALL select runs only through explicit filters (`--workflow`, `--head-sha`, `--event`, `--since`, `--until`) and SHALL cap fetched runs with `--limit`.

#### Scenario: CLI fetches are filtered and bounded
- **WHEN** `ci_wallclock.py compare` runs under test with a stubbed `gh` that records its calls and serves more matching runs than `--limit 10`, with `--workflow ci.yml --event workflow_dispatch --head-sha <sha>`
- **THEN** the recorded `gh api` requests carry the workflow, event and `head_sha` filters, are all GET requests, and stop fetching pages once 10 runs are collected

#### Scenario: Runs with mixed placement are excluded from comparison
- **WHEN** `compare` receives a run whose routed jobs ran partly on `gx10` runners and partly on hosted runners
- **THEN** that run is excluded from both samples and listed in the result's `excluded_runs` with a reason

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

#### Scenario: Matrix expansions are correlated to their job id
- **WHEN** `verify_run` receives a workflow definition whose job `lint` has a two-entry `strategy.matrix`, and the jobs API returns `lint (a)` on a `gx10` runner and `lint (b)` on a hosted runner while the lane is self-hosted
- **THEN** it returns a violation for `lint (b)` and none for `lint (a)`
- **AND** a jobs-API entry whose name matches no manifest job is reported as an unknown job

#### Scenario: Manifest job missing from the run is a violation
- **WHEN** `verify_run` receives a jobs list that lacks a job the manifest names for that workflow
- **THEN** it returns a violation naming the missing job

#### Scenario: Unconditional job skipped by an upstream failure is a violation
- **WHEN** a job with no job-level `if:` concluded `skipped`
- **THEN** `verify_run` returns a violation naming that job

#### Scenario: Failed continue-on-error job is a warning
- **WHEN** a job declared `continue-on-error: true` concluded `failure` and every other job succeeded on its expected lane
- **THEN** `verify_run` returns zero violations and one warning naming that job
- **AND** the `verify-run` CLI exits zero, printing the warning (it exits non-zero only on violations)

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
