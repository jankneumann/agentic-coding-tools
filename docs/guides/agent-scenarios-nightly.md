# Agent scenarios: nightly cross-vendor parity runs

Runbook for `agent-scenarios nightly` (package: `packages/agent-scenarios/`). The run
executes the seed scenario suite across a vendor allowlist (default `claude` + `codex`),
appends results to a durable store, writes review findings, and emits capability gaps
(`source:scenario-parity`) that `/improve-harness` reads. It is **off by default** and ships
only as templates: nothing in the repository installs, enables or starts a schedule.

## Install (operator, once)

1. Create a **dedicated nightly user/HOME** on the host. It must have: no user-global skills
   (`~/.claude/skills`, `~/.agents/skills`), no coordinator MCP configuration, and no GitHub
   push credentials (SSH keys, credential helpers, `insteadOf` rewrites). Vendor CLIs keep
   their own auth under that HOME, so these are controlled operationally; the executor
   cannot replace HOME. Install the `claude` and `codex` CLIs and their keys for that user.
2. Copy `packages/agent-scenarios/deploy/nightly.example.yaml` to
   `~/.config/agent-scenarios/nightly.yaml`, fill `vendor_commands` and the paths, and keep
   `enabled: false`.
3. Review the plan: `agent-scenarios nightly --dry-run`. It prints the off-switch state, the
   effective vendors, the planned (scenario, vendor) pairs and the cap evaluation; it takes no
   lock, writes no record and starts no vendor (it works with `enabled: false`).
4. Render the unit and timer from `deploy/systemd/*.template` (replace `@UV@` and `@REPO@`),
   place them in `~/.config/systemd/user/`, run `systemctl --user daemon-reload`. Keep
   `TimeoutStartSec` at or above `max_wall_clock_minutes + per_pair_timeout_seconds + 10 min`
   (default 270 min): the budget is only checked between pairs.
5. Flip `enabled: true`, run the service once by hand, review results/findings/gaps, then
   `systemctl --user enable --now agent-scenarios-nightly.timer`.

## Disable (any one of)

- `systemctl --user disable --now agent-scenarios-nightly.timer`
- create the kill-file (`disable_file`, default `~/.config/agent-scenarios/DISABLED`)
- set `enabled: false`

A disabled run appends a `disabled` run record, constructs no executor and exits 0.

## Exit codes and triage

| Code | Meaning | First action |
|------|---------|--------------|
| 0 | `completed`, every pair passed (also `disabled` / `locked`) | none |
| 1 | one or more scenarios `fail` | `results query --status fail`; a capability gap was emitted per failing (scenario, vendor) |
| 2 | config or cap error (invalid config writes **no** record; `cap_exceeded`, `config_error` write one) | fix the config or raise the cap deliberately; nothing was launched |
| 3 | no `fail`, but one or more `error` results (a CLI missing, expired keys, timeouts, an unsupported `gh` call) **or** an incomplete matrix (`budget_exhausted`) | read the `error` text in `results query --status error`; no capability gap is emitted for infrastructure errors |

Precedence: 2 > 1 > 3 > 0. Systemd marks the unit failed for 1, 2 and 3 (`SuccessExitStatus=0`).
Error texts: `vendor CLI timed out after Ns` (raise `per_pair_timeout_seconds` or investigate
the scenario) is distinct from `vendor CLI unavailable` (binary missing);
`gh shim: unsupported call ...` means the agent used a `gh` subcommand the local shim does
not implement (widen the shim in a follow-up change; it is not a skill failure).

## Hermetic live runs

Each pair runs in `<workspaces_root>/<run_id>/<scenario>--<vendor>/` against a fixture-local
bare `origin` (`<workspace>.origin.git`). `gh` resolves to a local shim (`<workspace>.bin/gh`)
so no call reaches GitHub. The vendor subprocess never sees GitHub tokens, any coordinator
URL / API key / Cloudflare Access variable, or the variables named by `gaps.api_key_env` /
`gaps.coordinator_url_env`, and `COORDINATION_API_URL` is forced to `http://127.0.0.1:9`.
`env_scrub` can only add to that denylist and `env_set` may not name any scrubbed variable.
The whole `skills/` tree of the checkout under test is copied into the workspace's
`.claude/skills/` and `.agents/skills/` (excluded from git) and `skills_sha` (`+dirty` when
modified) is recorded on every result.

## Workspaces and retention

Workspaces of `pass` and `skipped_budget` pairs are deleted after scoring; `fail` and `error`
workspaces (and their `.origin.git`) are kept for diagnosis. At the start of each run, run
directories beyond the newest `retain_failed_runs` (default 7) are deleted.

## Results

```
agent-scenarios results query  --vendor codex --skill validate-feature --since 2026-10-01
agent-scenarios results query  --family merge --status fail --format table
agent-scenarios results trend  --group-by vendor,skill --bucket week
agent-scenarios results latest --skill implement-feature
```

Records are appended as each pair is scored, so a killed run keeps its completed pairs; a
`result` whose `run_id` has no `run` record is reported as `interrupted` (or `in_progress`
while the run lock is held). Trend pass rate is `pass / (pass + fail)`; `error` and
`skipped_budget` are counted separately.

## Capability gaps and /improve-harness

Each deterministic `fail` becomes one memory entry tagged `source:scenario-parity` (see
`docs/guides/memory-conventions.md`). Undeliverable entries are spooled to `gap-spool.jsonl`
and replayed at the start of the next run or by `agent-scenarios gaps flush`; delivery counts
only on HTTP 2xx with `success: true`, and an unset URL variable spools without any request.

- **Frequency unit**: `/improve-harness` counts raw memory entries, so a finding's frequency
  is the number of failing **(run, vendor) pairs**, not nights.
- **Two URL variables, one coordinator**: the gap emitter reads `COORDINATION_API_URL`
  (default; configurable via `gaps.coordinator_url_env`) and `COORDINATION_API_KEY`, whereas
  `/improve-harness` reads `COORDINATOR_URL`. Both must name the same coordinator or the
  emitted gaps are never read.

## Broken-skill drill (operator)

On a throwaway branch break one plan or validate skill, point a one-off config's `repo_root`
at it, run the nightly once, and confirm a `fail` result, a `source:scenario-parity` gap in
`/improve-harness`, and that restoring the skill goes green again.
