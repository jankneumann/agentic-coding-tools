# Self-Hosted CI Runners (GX10)

Operator runbook for `migrate-ci-to-self-hosted-gx10-runners` (roadmap item ri-20). CI jobs
route to ephemeral runners on the GX10 host when the repository variable `CI_RUNNER_LANE` is
`self-hosted`, and to GitHub-hosted `ubuntu-latest` otherwise. Everything below needs a human
with host and repository-admin access.

## Hard boundary

The implementation of this change wrote files on a branch only. It did **not** register
runners, mint registration or JIT tokens, call a mutating GitHub API, set repository or
organization settings or variables, run `systemctl`, `loginctl` or `podman run`/`podman build`
against the host, or touch `main`. Every step of that kind is **operator-only** and lives
here as O1-O12. Do the steps in this order: O1-O5 prepare the host and the repository, O6 is
the dry run, O7 flips the lane, O8-O11 measure and verify, O12 is the rollback drill.

Notation: `{owner}/{repo}` is filled in by `gh` from the current checkout. The account has
no login shell, so run "as `ghrunner`" commands as
`sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) <command>`, or use
`systemctl --user --machine=ghrunner@ ...` for unit operations. Every `sudo -u ghrunner`
command below carries that `XDG_RUNTIME_DIR`, so rootless podman always uses the same
runtime directory and storage as the units. Run the steps from a checkout `ghrunner` can
read (Ubuntu home directories are `0750`), for example a clone under `~ghrunner/src`.

Where things live:

| What | Path |
|---|---|
| Lane manifest and schema | `.github/runner-lanes.yaml`, `.github/runner-lanes.schema.json` |
| Runner kit | `deploy/gx10-runner/` (`Containerfile`, `toolchain.txt`, `job-started-hook.sh`, `mint-jitconfig.sh`, `cleanup-runner.sh`, `install-units.sh`, `gx10-runner.env.example`, `systemd/gx10-runner@.service`) |
| Measurement CLI | `scripts/ci/ci_wallclock.py` |

## O1 - Create the dedicated host user and enable linger

```bash
# Host prerequisites: the unit's ExecStartPre/ExecStopPost scripts run on the HOST and need
# curl and jq (the image's toolchain does not help them); podman and nft run the rest.
sudo apt-get install -y podman curl jq nftables
sudo useradd --system --create-home --shell /usr/sbin/nologin ghrunner
# useradd --system allocates no subordinate ids, which rootless podman needs for the
# non-root `runner` user in the image. Pick a 65536-id range that overlaps nothing in
# /etc/subuid or /etc/subgid (start above the highest existing end).
sort -t: -k2 -n /etc/subuid
sudo usermod --add-subuids <start>-<start+65535> --add-subgids <start>-<start+65535> ghrunner
sudo loginctl enable-linger ghrunner
# The unit passes --cpus/--memory/--pids-limit to rootless podman, which needs the cpu, io,
# memory and pids cgroup controllers delegated to the user manager. Stock Ubuntu delegates
# only some of them; without `cpu` every container start fails and the units restart-loop.
sudo mkdir -p /etc/systemd/system/user@.service.d
printf '[Service]\nDelegate=cpu cpuset io memory pids\n' |
  sudo tee /etc/systemd/system/user@.service.d/delegate.conf >/dev/null
sudo systemctl daemon-reload
```

Verify:

```bash
command -v podman curl jq nft                 # four paths: host prerequisites present
loginctl show-user ghrunner -p Linger        # Linger=yes
grep ghrunner /etc/subuid /etc/subgid        # one range in each file
sort -t: -k2 -n /etc/subuid                  # each start is above the previous entry's end
cat /sys/fs/cgroup/user.slice/user-$(id -u ghrunner).slice/user@$(id -u ghrunner).service/cgroup.controllers
                                             # lists cpu, io, memory and pids (after a reboot
                                             # or `sudo systemctl restart user@$(id -u ghrunner)`)
```

## O2 - Provision the registration credential

Create a fine-grained PAT for this repository only, with *Administration: read and write* and
an expiry of 90 days or less. Store it where the unit's `LoadCredential=` reads it, and copy
the example environment file.

```bash
sudo -u ghrunner install -d -m 700 ~ghrunner/.config/gx10-runner
sudo install -m 600 -o ghrunner -g ghrunner /dev/stdin ~ghrunner/.config/gx10-runner/token   # paste the PAT, Ctrl-D
sudo -u ghrunner cp deploy/gx10-runner/gx10-runner.env.example ~ghrunner/.config/gx10-runner/env
# edit GX10_RUNNER_REPO and GX10_RUNNER_IMAGE in that file
```

Verify:

```bash
sudo stat -c %a ~ghrunner/.config/gx10-runner/token                       # 600
GH_TOKEN=$(sudo cat ~ghrunner/.config/gx10-runner/token) \
  gh api repos/{owner}/{repo}/actions/runners --jq .total_count           # exits 0
```

Upgrade path: a **GitHub App** (short-lived installation tokens) replaces the PAT once the
host can sign JWTs. The mint script only needs a bearer token in
`$CREDENTIALS_DIRECTORY/github-token`, so an App is a change to how that file is produced,
not to the kit.

## O3 - Build the runner image on the GX10 as `ghrunner`

```bash
sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) podman build -t localhost/gx10-runner:<sha> deploy/gx10-runner
sudo -u ghrunner sed -i 's#^GX10_RUNNER_IMAGE=.*#GX10_RUNNER_IMAGE=localhost/gx10-runner:<sha>#' \
  ~ghrunner/.config/gx10-runner/env
```

Verify:

```bash
sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) podman image inspect localhost/gx10-runner:<sha> --format '{{.Architecture}}'   # arm64
```

The base image is pinned by version and digest in the `Containerfile`; bump both together.

## O4 - Install the host-service isolation control, then install and enable the units

Podman 4.9 uses `slirp4netns` and, with `allow_host_loopback=false`, makes host *loopback*
services unreachable. It does **not** stop PR code reaching a host service bound to `0.0.0.0`
or a LAN or Tailscale address: slirp4netns NATs through the host's network stack as
`ghrunner`. Isolation therefore rests on an operator-installed control that this step proves.

**Preferred: a persistent nftables egress rule for `ghrunner`**, in a `table inet` so IPv4 and
IPv6 are both filtered. Order matters: the DNS exemption for the host stub resolver comes
first, otherwise the mint script and container DNS cannot resolve `api.github.com` and no
instance ever comes online.

```bash
sudo mkdir -p /etc/nftables.d          # not shipped by Debian/Ubuntu
sudo tee /etc/nftables.d/gx10-runner.nft >/dev/null <<'NFT'
table inet gx10_runner_isolation
delete table inet gx10_runner_isolation
table inet gx10_runner_isolation {
  chain output {
    type filter hook output priority 0; policy accept;
    meta skuid ghrunner ip daddr 127.0.0.53 udp dport 53 accept
    meta skuid ghrunner ip daddr 127.0.0.53 tcp dport 53 accept
    meta skuid ghrunner fib daddr type local drop
    meta skuid ghrunner ip daddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 100.64.0.0/10, 169.254.0.0/16 } drop
    meta skuid ghrunner ip6 daddr { fc00::/7, fe80::/10 } drop
    meta skuid ghrunner oifname "tailscale0" drop
  }
}
NFT
# Persist it with a DEDICATED boot unit, not nftables.service: the stock /etc/nftables.conf
# starts with `flush ruleset`, so starting or restarting nftables.service (and every boot with
# it enabled) wipes ufw/firewalld/podman tables. The file above is idempotent (declare,
# delete, redefine) and touches only its own table, so loading it directly is safe.
sudo tee /etc/systemd/system/gx10-runner-isolation.service >/dev/null <<'UNIT'
[Unit]
Description=GX10 runner host-service isolation (nftables table inet gx10_runner_isolation)
DefaultDependencies=no
After=local-fs.target
Before=network-pre.target systemd-user-sessions.service
Wants=network-pre.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f /etc/nftables.d/gx10-runner.nft

[Install]
WantedBy=multi-user.target
UNIT
# Ordering alone (Before=) never stops a dependent unit when nft fails, and the lingering
# user manager does not wait for user sessions. Make ghrunner's user manager -- and so every
# runner unit -- REQUIRE the isolation unit: if the rules fail to load at boot, user@ fails
# and no runner starts; stopping the isolation unit stops the runners with it.
gx10_uid=$(id -u ghrunner)
sudo mkdir -p /etc/systemd/system/user@${gx10_uid}.service.d
sudo tee /etc/systemd/system/user@${gx10_uid}.service.d/gx10-runner-isolation.conf >/dev/null <<'DROPIN'
[Unit]
Requires=gx10-runner-isolation.service
After=gx10-runner-isolation.service
DROPIN
sudo nft -c -f /etc/nftables.d/gx10-runner.nft
sudo nft list ruleset | grep -c '^table'          # note the count: it must not drop below
sudo systemctl daemon-reload
sudo systemctl enable --now gx10-runner-isolation.service
sudo nft list ruleset | grep -c '^table'          # previous count, plus one on first install
sudo nft list table inet gx10_runner_isolation >/dev/null && echo loaded   # before any unit starts
```

**Fallback:** rebind every host service the runners must not reach to `127.0.0.1` (for example
publish compose ports as `127.0.0.1:54322:5432`) and check with `ss -ltnp`.

Then install and enable the units:

```bash
sudo -u ghrunner deploy/gx10-runner/install-units.sh          # copies files, prints the next commands
sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) systemctl --user daemon-reload
sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) systemctl --user enable --now gx10-runner@{1..8}
```

Verify:

```bash
gh api repos/{owner}/{repo}/actions/runners \
  --jq '[.runners[]|select(any(.labels[];.name=="gx10"))|.status]'    # 8 entries, all "online"

# Transport-level TCP connects (an HTTP curl probe is wrong: it fails AFTER connecting to a
# non-HTTP service such as Postgres). Every address, both ports, IPv6 included.
for addr in 10.0.2.2 $(hostname -I); do
  for port in 54322 <coordinator-port>; do
    echo -n "$addr:$port "
    sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) podman exec gx10-runner-1 bash -c \
      "timeout 3 bash -c 'exec 3<>/dev/tcp/$addr/$port' && echo reachable || echo unreachable"
  done
done                                                                # every line: unreachable

sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) podman exec gx10-runner-1 getent hosts api.github.com   # resolves (DNS exemption works)
# If it does not resolve: the container's upstream resolver (copied from the host's resolv.conf) is
# probably a LAN or Tailscale address the ruleset drops. Give it an explicit accept rule above the
# drops (`meta skuid ghrunner ip daddr <resolver> udp dport 53 accept`, same for tcp); never widen a drop.
systemctl is-enabled gx10-runner-isolation.service                       # enabled: loaded at every boot
systemctl show -p Requires -p After user@$(id -u ghrunner).service | grep -c gx10-runner-isolation   # 2: runners gated on the rules
grep -c skuid /etc/nftables.d/gx10-runner.nft                            # non-zero: the rules are in the loaded file
sudo nft list ruleset | grep skuid                                       # rules are loaded
sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) podman inspect gx10-runner-1 --format '{{.HostConfig.NetworkMode}}'   # slirp4netns
```

A probe of `10.0.2.2` alone is not sufficient evidence. A host-side `getent` does not exercise
the DNS exemption either, because glibc reaches systemd-resolved over its unix socket.

**Podman 5 note.** The unit passes `--network slirp4netns:allow_host_loopback=false`
explicitly because podman 5 defaults rootless networking to `pasta`, which maps the gateway to
the host. Keep the explicit `slirp4netns` option; moving to `pasta:--no-map-gw` is a reviewed
unit change, never a default.

### Optional: shared uv cache (off by default)

The cache is a cross-trust poisoning vector: a same-repository PR job can write files that a
later `main` job reads, and uv does not re-hash cached entries on reuse. Same-repository
branches are pushed by humans, **Dependabot** and agent PR sources (Jules, Codex), and by any
holder of a leaked collaborator credential. Enable the cache only as a recorded risk
acceptance. Fill in this line first, then set the variable:

```text
Risk acceptance: accepted by <name> on <YYYY-MM-DD>; every same-repository writer, including
Dependabot and agent branches, is acceptable as a cache writer.
```

```bash
# enable
sudo -u ghrunner sed -i 's#^GX10_RUNNER_CACHE_ARGS=.*#GX10_RUNNER_CACHE_ARGS=--volume gx10-runner-uv-cache:/home/runner/.cache/uv#' \
  ~ghrunner/.config/gx10-runner/env
# disable again
sudo -u ghrunner sed -i 's#^GX10_RUNNER_CACHE_ARGS=.*#GX10_RUNNER_CACHE_ARGS=#' ~ghrunner/.config/gx10-runner/env
sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) podman volume rm gx10-runner-uv-cache
```

A move to multiplayer team mode requires the cache to be disabled.

## O5 - Set the fork-PR approval policy

```bash
gh api -X PUT repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval \
  -f approval_policy=all_external_contributors
```

Confirm the runners are repository-scoped, not organization-scoped (O4 listed them under the
repository). Verify:

```bash
gh api repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval --jq .approval_policy
# all_external_contributors
```

Approval only lets a fork run start. Fork `pull_request` runs and every `merge_group` run
resolve to `ubuntu-latest`; the runner image's job-started hook refuses them even if a PR
rewrites its own workflow.

## O6 - Self-hosted dry run before flipping

```bash
gh workflow run ci.yml --ref main -f runner_lane=self-hosted
gh workflow run security.yml --ref main -f runner_lane=self-hosted
```

Verify (run ids from `gh run list --workflow ci.yml --limit 1 --json databaseId`):

```bash
python scripts/ci/ci_wallclock.py verify-run <run-id> --workflow ci.yml
python scripts/ci/ci_wallclock.py verify-run <run-id> --workflow security.yml
# both: 0 violation(s)
```

If a routed job fails on arm64 (for example `secret-scan` or `formal-coordination`), open a PR
that moves it to `hosted` in `.github/runner-lanes.yaml` with `reason_code: amd64-only` and
changes its `runs-on` to the literal `ubuntu-latest`, then repeat O6. Jobs that call a
container engine indirectly through a script are also caught here.

## O7 - Flip the lane

```bash
gh variable set CI_RUNNER_LANE --body self-hosted
```

Verify:

```bash
gh variable get CI_RUNNER_LANE                                    # self-hosted
python scripts/ci/ci_wallclock.py verify-run <next-pr-run-id> --workflow ci.yml   # 0 violations
```

**If the host goes down while the lane is `self-hosted`**, routed jobs queue (GitHub keeps them
24 hours; `timeout-minutes` does not cover queue time). Detect runs queued for more than ten
minutes:

```bash
gh run list --status queued --limit 100 --json databaseId,workflowName,createdAt \
  --jq '[.[] | select((now - (.createdAt | fromdateiso8601)) > 600)] | length'
```

A non-zero count means: set the variable to `hosted` (O12), cancel the queued runs, re-run
them. Automatic fallback is deferred (it needs a token that can list runners).

## O8 - Measure wall-clock time

Dispatch five or more paired runs per lane on the same commit (`runner_lane=hosted` versus
`runner_lane=self-hosted`).

```bash
for i in 1 2 3 4 5; do
  gh workflow run ci.yml --ref main -f runner_lane=hosted
  gh workflow run ci.yml --ref main -f runner_lane=self-hosted
done
```

Verify (the ratio must be 0.85 or less with n >= 5 on each side):

```bash
python scripts/ci/ci_wallclock.py compare --baseline-lane hosted --candidate-lane self-hosted \
  --workflow ci.yml --event workflow_dispatch --head-sha <sha>
```

Corroborate with the median over 20 or more PR runs before and after the O7 date:

```bash
python scripts/ci/ci_wallclock.py median --workflow ci.yml --event pull_request \
  --since 2026-01-01 --until <o7-date> --limit 200
python scripts/ci/ci_wallclock.py median --workflow ci.yml --event pull_request \
  --since <o7-date> --limit 200
```

If the comparison fails, tune the instance count (`systemctl --user enable --now
gx10-runner@{9..N}`), or move the slowest routed jobs to `hosted` with
`reason_code: measured-slower`.

## O9 - Check per-job ephemerality

Verify, after three or more jobs have run on instance 1:

```bash
sudo journalctl _UID=$(id -u ghrunner) --user-unit gx10-runner@1.service | grep -c 'Listening for Jobs'   # 3 or more
gh api repos/{owner}/{repo}/actions/runs/<run-id>/jobs --jq '.jobs[].runner_name'    # distinct names
sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) podman ps -a --filter name=gx10-runner --filter status=exited       # empty
```

JIT runners deregister after their job, so the runners list cannot show them; the runner names
recorded on the jobs are the evidence.

## O10 - Check reboot survival

```bash
sudo systemctl reboot        # do not log in as ghrunner afterwards
```

Verify:

```bash
sudo systemctl --user --machine=ghrunner@ is-active gx10-runner@1                 # active
gh api repos/{owner}/{repo}/actions/runners --jq '[.runners[].status]'            # online within 2 minutes
sudo nft list ruleset | grep skuid                                                # O4 rules survived
# Repeat the O4 TCP-connect probes and the in-container DNS check: same results as before.
```

## O11 - Fork-PR end-to-end check

Open a trivial PR from a fork account, and a second one that edits `ci.yml` to set one routed
job's `runs-on` to the GX10 labels and delete its guard step.

```bash
gh run list --branch <fork-branch> --json status,conclusion        # action_required: awaiting approval
```

After approval:

```bash
python scripts/ci/ci_wallclock.py verify-run <run-id> --workflow ci.yml --expect-lane hosted   # 0 violations
```

Without `--expect-lane hosted` the default `self-hosted` expectation would flag every routed
job. For the second PR, the rewritten job must fail in its `Set up job` phase with the
job-started hook's refusal message ("gx10 runner refused this job") and no step of that job
runs.

## O12 - Rollback drill

```bash
gh variable set CI_RUNNER_LANE --body hosted
```

Verify on the next CI run, then restore with O7:

```bash
python scripts/ci/ci_wallclock.py verify-run <run-id> --workflow ci.yml --expect-lane hosted   # all jobs on GitHub-hosted runners
gh variable delete CI_RUNNER_LANE      # alternative to setting it to "hosted"
```
