# Design: add-local-agent-probe

## Context

Two probes exist today and disagree:

| Entry point | File | Checks |
|---|---|---|
| `/vendor-status`, watchdog, `setup-coordinator` | `skills/parallel-infrastructure/scripts/vendor_health.py:53` | `shutil.which`, API-key env |
| autopilot INIT quorum, `--check-vendors` | `review_dispatcher.py:3428` (`_dry_invoke`), `:3452` (`_probe_mode`) | `shutil.which`, `<cli> --version` |

Neither validates the flags a lane's `dispatch_modes` pass, neither checks login state, and
the dispatcher's runtime `auth_required` / `vendor_unavailable` classifications
(`review_dispatcher.py:1073`) are forgotten when the process exits.

## Decisions

### D1 — One probe module, two adapters

`skills/parallel-infrastructure/scripts/vendor_probe.py` owns every probe tier. It is
**stdlib-only** (no PyYAML, no coordinator imports) because `agent-coordinator/src/watchdog.py:439`
loads `vendor_health.py` by file path inside the coordinator container; the Dockerfile copy step
(`agent-coordinator/Dockerfile:86`) gains `vendor_probe.py` next to `vendor_health.py`, and
`vendor_health.py` imports it by sibling path. `vendor_health.check_vendor()` and
`review_dispatcher._probe_mode()` both become thin adapters that map a `LaneProbe` onto their
existing output shapes — existing fields keep their meaning, new tier fields are additive.

Input to the module is a plain `dict` lane config (the `cli:` block plus `agent_id`), so it is
agnostic of which of the three config sources (`AGENTS_YAML`, `/agents/dispatch-configs`, local
`agents.yaml`) produced it.

### D2 — Required flags are derived, not declared

For each dispatch mode, the probe splits `args` into a **subcommand path** (leading tokens up to
the first token starting with `-`) and the **flags** (tokens starting with `-`; `--flag=value`
normalizes to `--flag`; placeholder tokens such as `@review-findings-schema` and values are
skipped). The help command for that mode is `[command, *subcommand_path, "--help"]` unless
`probe.help_args` overrides it — e.g. codex's `exec -s read-only` checks `codex exec --help` for
`-s`. Flags named by `cli` keys ending in `_flag` (`model_flag`, `thinking_flag`, …) are added,
because the dispatcher injects them at runtime. `probe.ignore_flags` removes false positives.

A flag is present when it occurs in help output as a whole token
(`(?<![\w-])<flag>(?![\w-])`). L1 is therefore **per (lane, mode)**, which matches
`--check-vendors`' per-mode report.

Rejected: a hand-maintained `required_flags` list — it reproduces the stale-comment problem
this change exists to remove.

### D3 — Auth is exit-code-only, allowlist-shaped

L2 runs `probe.auth_status_args` with stdin/stdout/stderr bound to `DEVNULL`; only the exit code
is used (0 → `auth_ok`, non-zero → `auth_failed`, timeout → `probe_timeout`). Output is never
captured, so an auth command that prints an account email or a token cannot leak it.
`probe.credential_files` is checked with `Path.expanduser().exists()` only — never opened.

`AGENTS_SCHEMA` validation rejects an `auth_status_args` list when any token matches
`print-api-key|print-bearer-token|--credentials|--show-token|logout` (case-insensitive), or when
its **last** token is `login` — because several CLIs put credential-printing subcommands next to
their status commands (`pi auth print-api-key`), and a bare `grok login` would start an
interactive login. `login` elsewhere stays legal so `codex login status` is accepted. The
last-token rule is not expressible in JSON Schema, so it is enforced in `agents_config.validate`
alongside the schema check. With neither key declared, L2 is `auth_unknown`, which never excludes a lane.

Initial declarations (verified locally 2026-10-29 by `--help` only):

| Lane CLI | L2 declaration |
|---|---|
| `claude` | `auth_status_args: [auth, status]` |
| `codex` | `auth_status_args: [login, status]` |
| `pi` | `auth_status_args: [auth, check, --provider, <lane provider>, --no-refresh]` |
| `grok` | `credential_files: ["~/.grok/auth.json"]` (no status subcommand exists) |
| `agy` (antigravity) | none → `auth_unknown` (CLI not installed here to verify) |

### D4 — Per-user cache, fingerprinted

Path: `$AGENTIC_PROBE_CACHE` if set, else `$XDG_CACHE_HOME/agentic-coding-tools/vendor-probe.json`,
else `~/.cache/agentic-coding-tools/vendor-probe.json`. Schema:
`contracts/vendor-probe-cache.schema.json`.

Each entry is keyed by `agent_id` and stores `cli_realpath`, `cli_version`,
`config_fingerprint` (sha256 of the canonical-JSON `cli` block), `probed_at`, per-mode L1
results, L2 result, and optional `runtime_failure`. An entry is **fresh** when
`now - probed_at < ttl_seconds` **and** `cli_realpath` / `config_fingerprint` still match the
current environment; the version is re-read only on a re-probe. TTL defaults: 24 h for a probe
entry, 1 h for a `runtime_failure`. Writes are atomic (`tempfile` in the same dir +
`os.replace`) with mode `0600`; a cache that fails to parse or validate is treated as empty and
overwritten on the next write.

Rejected: repo-local `.agents/agents.local.json` (Approach 2) — needs a consumer `.gitignore`
mutation during install.

### D5 — Dispatch reads the cache, never probes

`discover_reviewers` (`review_dispatcher.py:2817`) consults the cache before the Tier 1
`can_dispatch` check and excludes a lane/mode when a **fresh** entry records `cli_not_found`,
`missing_flags` for that mode, `auth_failed`, or a fresh `runtime_failure`. Missing or stale
entries never exclude — dispatch adds no subprocesses, keeping warm-cache overhead ≤ 50 ms.
Probing (and cache writes) happen in `--check-vendors` (autopilot INIT), `vendor_health.py`,
and `install.sh --check`. `AGENTIC_PROBE_IGNORE_CACHE=1` disables the filter. Every exclusion
is logged at INFO with lane, mode, and reason so a run is never silently narrowed.

### D6 — Runtime failures write back

Where `classify_error` yields `ErrorClass.AUTH` or `ErrorClass.UNAVAILABLE`
(`review_dispatcher.py:1073–1097`), the dispatcher records
`runtime_failure = {error_class, observed_at, ttl_seconds: 3600}` for that lane. A later probe
whose L2 is `auth_ok` clears it. Capacity limits stay with `vendor_limit_reporter.py`;
nothing is duplicated.

### D7 — Reason codes

Existing codes keep their meaning: `cli_not_found`, `probe_timeout`, `probe_failed`,
`not_dispatchable`, `probe_unsupported`. New: `missing_flags`, `auth_failed`, `auth_unknown`
(informational), `runtime_auth_required`, `runtime_vendor_unavailable`. Lane ids are
`agents.yaml` agent ids, matching dg-01's registry so a follow-up can upload snapshots.

### D8 — install.sh report is informational

After the existing drift checks, `--check` runs
`python3 <skills>/parallel-infrastructure/scripts/vendor_probe.py report` with a 60 s overall
timeout. It prints a table (lane, version, L0/L1/L2, remediation hint) to stdout. Any failure —
no `python3`, no config resolvable, timeout — prints one `probe report unavailable: <reason>`
line. The probe's exit status is discarded; `--check`'s exit code is computed exactly as before.

### D9 — Backward compatibility

A `cli` block with no `probe:` key gets L0 plus a `--version` call (today's `--check-vendors`
behaviour), no flag check, and `auth_unknown`. `get_dispatch_configs()` serializes `probe` only
when present, so the endpoint payload is unchanged for configs without it.

### D10 — Concurrency and bounds

Lanes are probed in a `ThreadPoolExecutor` (≤ 8 workers); each subprocess has a 10 s timeout
(matching the existing `_dry_invoke` contract) and runs with `stdin=DEVNULL`.

## Risks

- **Help text formats vary** — a CLI listing flags only under `--help-all` would false-negative.
  Mitigation: `probe.help_args` override and `ignore_flags`; a `missing_flags` result reports
  the exact flags so the fix is obvious.
- **Merge conflicts in `AGENTS_SCHEMA`** with `add-model-usage-ledger`, `add-atomic-harness`,
  and `followup-add-prime-agent-harness` — textual only; the `probe` property is independent.
