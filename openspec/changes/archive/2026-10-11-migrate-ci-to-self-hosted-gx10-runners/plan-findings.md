# Plan Findings — migrate-ci-to-self-hosted-gx10-runners

## Iteration 1 (autopilot PLAN_ITERATE, archetype architect, non-interactive)

Baseline: `openspec validate --strict` green; work-packages VALID. Facts were checked against the
live `ci.yml` / `security.yml` (job-level `if:`, run-block commands, setup actions) and the host
(`podman version 4.9.3`).

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 1 | feasibility | high | `mint-jitconfig.sh` backs off up to 300 s inside `ExecStartPre`, but the unit set no `TimeoutStartSec` (default 90 s): systemd kills the script mid-backoff and restarts it every `RestartSec`, so the backoff never applies and the API is hammered. | D5/D7: total budget `GX10_MINT_MAX_ELAPSED` (600 s) < explicit `TimeoutStartSec=900`; new spec scenario "Mint retries are bounded below the start timeout"; tasks 3.1/3.2/3.3/3.4. |
| 2 | security | high | Host-loopback isolation relied on the podman default. Podman 5 defaults to `pasta`, which maps the gateway to host loopback, exposing the coordinator API / Postgres to PR code after a routine upgrade. | D6: explicit `--network slirp4netns:allow_host_loopback=false` and `--pull=never`, pinned by test; A11; O4 verification made concrete (`podman exec`, `podman inspect`). |
| 3 | correctness/testability | high | `verify_run` flagged every non-`success` job, but `dependency-update-remediation` has a job-level `if:` (Dependabot PRs only) and is `skipped` with no runner on every dispatch/push/PR run, so O6/O7/O11/O12 would always fail. | D8 + spec: `skipped` accepted (placement unchecked) for jobs with a job-level `if:`; unconditional skips remain violations; two new scenarios; task 4.1. |
| 4 | security/assumptions | high | D6 claimed `uv sync --locked` hash checks mitigate shared-cache poisoning. They do not: hashes are checked at download only, and many jobs run `uv sync` without `--locked`, `uv run --with`, `uv pip install`. | D6 rationale corrected; risk accepted explicitly as A10 (solo mode, same-repo writers already trusted); team-mode transition requires `GX10_RUNNER_UV_CACHE=off`; runbook task 5.2. |
| 5 | consistency | medium | Ephemerality scenario listed names via the runners API, but JIT runners deregister after their job, so names are gone. | Spec + O9 use the jobs API `runner_name`. |
| 6 | consistency | medium | `expected_lane` / `--expect-lane` (D8, O12) absent from the spec requirement and tasks 4.1/4.3. | Added to spec signature, a rollback scenario, and tasks. |
| 7 | completeness | medium | `compare` had no run selection, so A6's "paired runs on the same commit" was not reproducible; `--paginate` unbounded. | D8/spec/task 4.3: `--workflow`, `--head-sha`, `--event`, `--since`, `--until`, `--limit` (200); O8 command updated. |
| 8 | consistency | medium | Tool-parity requirement had no allowlist clause while its scenario did; the `check-docker-imports` allowlist rationale was wrong (only `check_docker_imports.py` appears). | D10: command-position matching, allowlist mechanism retained but empty; spec requirement + new scenario; documented limit (indirect script invocations) backstopped by O6. |
| 9 | clarity | medium | `StartLimitIntervalSec=0` "in [Service] or [Unit]" — systemd only honours it in `[Unit]`. | D7/spec/task 3.1 pin it to `[Unit]`. |
| 10 | parallelizability | medium | Tasks 2.5–2.8 all edit `ci.yml`/`security.yml` with no ordering between them. | Explicit serial chain 2.5 → 2.6 → 2.7 → 2.8 inside `wp-workflows`. |
| 11 | clarity | low | Routed-lane requirement omitted the fork exclusion in its main sentence. | Clause added. |

## Iteration 2 (re-review)

No findings at or above `medium`. Remaining low items, left for operator tuning:
- A9 default 8 × (2 CPU / 8 GiB) = 64 GiB on a host whose unified memory is shared with GPU
  workloads and the ri-08 daemon; tuned at O8.
- `secret-scan` (gitleaks-action binary) and `formal-coordination` (Java) arm64 parity remains
  an O6 dry-run outcome, by design (D2).

Termination: threshold met after iteration 1 fixes. Multi-vendor review not run here (no
`--vendor-review` flag; coordinator projection forbidden) — the autopilot PLAN_REVIEW phase
owns it.
