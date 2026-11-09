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
`vendor_health.py` imports it by sibling path: it loads
`Path(__file__).with_name("vendor_probe.py")` through `importlib.util.spec_from_file_location`
and registers the module in `sys.modules["vendor_probe"]` **before** `exec_module` (the #643
lesson: `@dataclass` resolves postponed annotations through `sys.modules`). A plain
`import vendor_probe` is not used because the watchdog's by-path load does not put the scripts
directory on `sys.path`. `review_dispatcher.py` uses the same sibling-path loader (one shared
helper, registered under the same `sys.modules["vendor_probe"]` key, so a process that loads both
gets one module instance and one cache lock). `vendor_health.check_vendor()` and
`review_dispatcher._probe_mode()` both become thin adapters that map a `LaneProbe` onto their
existing output shapes — existing fields keep their meaning, new tier fields are additive.

Input to the module is a plain `dict` lane config (the `cli:` block plus `agent_id`), so it is
agnostic of which of the three config sources (`AGENTS_YAML`, `/agents/dispatch-configs`, local
`agents.yaml`) produced it. `review_dispatcher` keeps a *mirror* `CliConfig` dataclass
(`review_dispatcher.py:558`) that today drops every key it does not name; it gains a
`probe: dict | None` field and the loader (`review_dispatcher.py:~2571`) populates it, otherwise
the dispatcher would fingerprint and filter on a config that has silently lost its probe block.

### D2 — Required flags are derived, not declared

For each dispatch mode, the probe splits `args` into a **subcommand path** (leading tokens up to
the first token starting with `-`) and the **flags** (tokens starting with `-`; `--flag=value`
normalizes to `--flag`; placeholder tokens such as `@review-findings-schema` and values are
skipped). The help command for that mode is `[command, *subcommand_path, "--help"]` unless
`probe.help_args[<mode>]` overrides it (lookup is per mode: a partial map leaves unlisted modes on
the generated command) — e.g. codex's `exec -s read-only` checks `codex exec --help` for
`-s`. Flags named by `cli` keys ending in `_flag` (`model_flag`, `thinking_flag`, …) are added,
because the dispatcher injects them at runtime. They are read from the **same normalized
projection the fingerprint uses (D4)** — `model_flag` defaults to `"-m"` (the dispatcher's own
`CliConfig` default, so it is injected whether or not a raw `agents.yaml` names it) and `null`
keys are dropped — so a lane yields the same required-flag set from every config source. `probe.ignore_flags` removes false positives.

`probe.help_args` is constrained because it replaces a generated help command with an
arbitrary argv: each value must contain `--help`, `-h`, or `help` (enforced in
`agents_config.validate`), so an override cannot run a real subcommand such as
`exec -s read-only`, and it passes the same denied-token check as every other probe argv (D3).

A flag is present when it occurs in help output as a whole token
(`(?<![\w-])<flag>(?![\w-])`). L1 is therefore **per (lane, mode)**, which matches
`--check-vendors`' per-mode report.

Rejected: a hand-maintained `required_flags` list — it reproduces the stale-comment problem
this change exists to remove.

### D3 — Auth is exit-code-only; every probe argv is denylist-screened

**Every probe argv is denylisted, not only the auth one.** The version command's stdout *is*
captured (it becomes `cli_version` in the cache and the report), and help output is captured for
the flag check, so a mis-declared `version_args: [auth, print-api-key]` would otherwise persist a
credential. The denied-token rule below therefore applies to `version_args`, every `help_args`
value, and `auth_status_args` alike, and every declared argv list must be non-empty. As defence in
depth, only the first line of version output, truncated to 200 characters, is stored.

L2 runs `probe.auth_status_args` with stdin/stdout/stderr bound to `DEVNULL`; only the exit code
is used (0 → `auth_ok`, non-zero → `auth_failed`, timeout → `probe_timeout`). Output is never
captured, so an auth command that prints an account email or a token cannot leak it.
`probe.credential_files` is checked with `Path.expanduser().exists()` only — never opened.

`AGENTS_SCHEMA` validation rejects any probe argv list (`version_args`, a `help_args` value, or
`auth_status_args`) when any token matches
`print-api-key|print-bearer-token|--credentials|--show-token|logout` (case-insensitive, written
as explicit character classes because JSON Schema patterns are ECMA-262 and do not accept an
inline `(?i)` flag), and rejects an `auth_status_args` list whose **last** token is `login` — because several CLIs put credential-printing subcommands next to
their status commands (`pi auth print-api-key`), and a bare `grok login` would start an
interactive login. `login` elsewhere stays legal so `codex login status` is accepted. The
last-token rule is not expressible in JSON Schema, so it is enforced in `agents_config.validate`
alongside the schema check. **Precedence.** Exactly one L2 method runs, recorded as `l2.method`: when `auth_status_args` is
declared it is used and `credential_files` is ignored (`status_command`); otherwise, when
`credential_files` is declared, L2 is `auth_ok` if every listed path exists and `auth_failed` if
any is missing (`credential_files`); with neither key declared, L2 is `auth_unknown` (`none`),
which never excludes a lane. A status command that cannot be launched (`FileNotFoundError` /
`PermissionError`) yields `auth_unknown`, not `auth_failed`. `credential_files` evidence is
weaker than a status command — a stale token file still exists — so it never clears a runtime
`auth_required` failure (D6).

Initial declarations (verified locally 2026-10-29 by `--help` only):

| Lane CLI | L2 declaration |
|---|---|
| `claude` | `auth_status_args: [auth, status]` |
| `codex` | `auth_status_args: [login, status]` |
| `pi` | `auth_status_args: [auth, check, --provider, openrouter, --no-refresh]` (literal; `openrouter` is the provider `pi-local`'s dispatch args pass — the probe block does no templating) |
| `grok` | `credential_files: ["~/.grok/auth.json"]` (no status subcommand exists) |
| `agy` (antigravity) | none → `auth_unknown` (CLI not installed here to verify) |

### D4 — Per-user cache, fingerprinted

Path: `$AGENTIC_PROBE_CACHE` if set, else `$XDG_CACHE_HOME/agentic-coding-tools/vendor-probe.json`,
else `~/.cache/agentic-coding-tools/vendor-probe.json`. Schema:
`contracts/vendor-probe-cache.schema.json`.

The document has two independent maps, both keyed by `agent_id`:

- `lanes` — probe entries: `cli_realpath`, `cli_version`, `config_fingerprint`, `probed_at`,
  per-mode L1 results, L2 result. An entry is **fresh** when `now - probed_at < ttl_seconds`
  **and** `cli_realpath` / `config_fingerprint` still match the current environment; the version
  is re-read only on a re-probe. TTL default 24 h.
- `runtime_failures` — `{error_class, observed_at, ttl_seconds}` written by the dispatcher (D6).
  Kept separate because a runtime failure is **account-scoped**, not config-scoped: it must be
  recordable when no probe entry exists yet (the schema's `lanes` entry requires L0/L1/L2 data
  the dispatcher does not have), and it must survive a `config_fingerprint` change. Fresh while
  `now - observed_at < ttl_seconds` (default 1 h); nothing else invalidates it.

**Fingerprint is over a normalized projection, not raw JSON.** The three config sources do not
serialize a `cli` block identically: local `agents.yaml` is raw (defaults absent), while
`get_dispatch_configs()` emits the `CliConfig` dataclass with defaults filled in (`model_flag:
"-m"`, `prompt_via_stdin: false`, …). A raw-JSON hash would make the same lane fingerprint
differently depending on which source the writer (`install.sh --check`) and the reader
(`discover_reviewers`) used, so every entry would look stale and the filter would never fire.
`vendor_probe.lane_fingerprint(cli)` therefore hashes the canonical JSON (sorted keys, no
whitespace) of exactly the probe-relevant fields with defaults applied: `command`,
`{mode: args}` for every dispatch mode, every key ending in `_flag` (with `model_flag`
defaulting to `"-m"`; for every other `_flag` key, `null` and absent are the same and the key is
dropped from the projection), and `probe` (absent → `null`, kept distinct from a declared `{}`
because D9 gives the two different L1 behaviour — adding `probe: {}` to turn flag checking on
must invalidate a cached version-only result). Inside a declared `probe`, keys equal to their
default are dropped (`version_args: ["--version"]` ≡ absent), so a source that materializes schema
defaults and one that does not fingerprint the same. Every carrier of the block — the
coordinator `CliConfig`, `get_dispatch_configs()`, and the dispatcher's mirror loader — tests
presence with `is not None`, never truthiness, so a declared `{}` survives the round-trip. Fields that do not change probe outcome
(`model`, `model_fallbacks`, `api_key_env`, …) are excluded so editing a model list does not
discard capability results.

**Writes are read-modify-write under a lock.** The dispatcher dispatches lanes concurrently
(`ThreadPoolExecutor`, `review_dispatcher.py:3181`) and several reviews can run at once, so two
runtime-failure writes can race; `os.replace` prevents a torn file but not a lost update. Every
write takes a module-level `threading.Lock` and an exclusive `fcntl.flock` on a sibling
`vendor-probe.json.lock`, re-reads the current document, merges, writes a `tempfile` in the same
directory with mode `0600`, and `os.replace`s it. Where `fcntl` is unavailable the flock is
skipped (best-effort; a lost update only delays one exclusion). Readers take no lock. A cache that
fails to parse or validate is treated as empty and overwritten on the next write. **Every write is
best-effort for every caller**: an `OSError` (read-only or absent `~/.cache`, as in the
coordinator container) is logged at WARNING and `probe_lanes()` still returns what it computed, so
the watchdog, `vendor_health`, `--check-vendors`, and `report` never fail on cache I/O.

Rejected: repo-local `.agents/agents.local.json` (Approach 2) — needs a consumer `.gitignore`
mutation during install.

### D5 — Dispatch reads the cache, never probes

`discover_reviewers` (`review_dispatcher.py:2817`) consults the cache before the Tier 1
`can_dispatch` check and excludes a lane/mode when a **fresh** entry records `cli_not_found`,
`missing_flags` or `probe_failed` (a version or help command that exited non-zero) for that mode,
`auth_failed`, or a fresh `runtime_failures` record. `probe_timeout` never excludes — a slow
machine is not a broken CLI. This is the same predicate `--check-vendors` uses to mark a lane/mode
unverified, so the INIT quorum check and dispatch agree on which lanes exist. Missing or stale
entries never exclude — dispatch adds no subprocesses, keeping warm-cache overhead ≤ 50 ms.
Probing (and cache writes) happen in `--check-vendors` (autopilot INIT), `vendor_health.py`,
and `install.sh --check`. `AGENTIC_PROBE_IGNORE_CACHE=1` disables the filter. Every exclusion
is logged at INFO with lane, mode, and reason, and is also kept on the orchestrator
(`ReviewOrchestrator.last_exclusions`) so the review manifest writer
(`checkpoint_findings.write_manifest`) records it as an additive `excluded_lanes:
[{vendor, mode, reason, since}]` list — INFO logs are rarely surfaced in CLI-reviewer runs, the
manifest is what operators read. The `report` remediation hint for `auth_failed` and
`runtime_auth_required` names the refresh command (`/vendor-status`, which re-probes), because a
stale `auth_failed` can otherwise linger for the 24 h TTL after a re-login. The same predicate
(fresh `cli_not_found` / `missing_flags` / `probe_failed` / `auth_failed` / runtime failure) is
used by `--check-vendors` (unverified) and `vendor_health` (`healthy: false`, new
`runtime_failure` field), so all three entry points agree.

### D6 — Runtime failures write back

Where `classify_error` yields `ErrorClass.AUTH` or `ErrorClass.UNAVAILABLE` **on the stderr of a
non-zero-exit invocation** (`review_dispatcher.py:1073`, `:1550`, `:1717`), the dispatcher records
`runtime_failures[agent_id] = {error_class, observed_at, ttl_seconds: 3600}`. The write is
best-effort: an `OSError` is logged at WARNING and never changes the `ReviewResult`.

Clearing differs by class, because the probe can only observe what it can observe token-free:

- `auth_required` is cleared by a later probe whose L2 is `auth_ok` **with method
  `status_command`**, and only when that auth subprocess *started* after the failure's
  `observed_at` (the clear is decided inside the locked read-modify-write, against the record
  re-read there), so a probe that began before a concurrent dispatch observed the failure cannot
  erase it. An `auth_ok` from `credential_files` (existence only) does not clear it,
  because an expired token file still exists; such a failure clears only when its TTL expires.
- `vendor_unavailable` is the **billing/credits** class (`_UNAVAILABLE_PATTERNS`, HTTP 402); no
  token-free probe can show credits were restored, so it clears only when its TTL expires.

Classifications made on **zero-exit stdout** (`review_dispatcher.py:1242`, `:1268`) are never
written back. That path runs `classify_error` over the whole unparseable output, and PLAN_REVIEW
observed it misclassifying a working codex review as `vendor_unavailable` because the review
text discussed HTTP 402. Persisting that would exclude a healthy lane for an hour; the per-run
`error_class` on the `ReviewResult` is unchanged. Narrowing `classify_error` itself is a
separate follow-up (decided at the IMPLEMENT entry, 2026-10-30).

Capacity limits stay with `vendor_limit_reporter.py`; nothing is duplicated.

### D7 — Reason codes

Existing codes keep their meaning: `cli_not_found`, `probe_timeout`, `probe_failed`,
`not_dispatchable`, `probe_unsupported`. New: `missing_flags`, `auth_failed`, `auth_unknown`
(informational), `runtime_auth_required`, `runtime_vendor_unavailable`. Lane ids are
`agents.yaml` agent ids, matching dg-01's registry so a follow-up can upload snapshots.

### D8 — install.sh report is informational

After the existing drift checks, `--check` runs
`<py> <skills>/parallel-infrastructure/scripts/vendor_probe.py report` with a 60 s overall
timeout, where `<py>` is `<source-root>/skills/.venv/bin/python` when it exists and `python3`
otherwise. In a consumer repo with only a bare `python3` (no PyYAML), the lazy resolver import
below fails and the report prints `probe report unavailable: config resolver needs PyYAML
(run skills/.venv)` — an expected, non-fatal outcome that the install tests cover. Config resolution is the one non-stdlib step and lives only in the `report` entry
point: it lazily imports `review_dispatcher`'s existing resolver (`AGENTS_YAML` →
`COORDINATION_API_URL` `/agents/dispatch-configs` → local `agent-coordinator/agents.yaml`) and
passes the resulting plain dicts to the stdlib-only library functions. If that import fails
(e.g. no PyYAML) or no source resolves, the report prints `probe report unavailable: <reason>`.
The library path used by `vendor_health.py` and the watchdog never performs this import (D1). It prints a table (lane, version, L0/L1/L2, remediation hint) to stdout. Any failure —
no `python3`, no config resolvable, timeout — prints one `probe report unavailable: <reason>`
line. `report` itself exits 0 whenever it prints a table (zero dispatchable lanes included) and 2 when it prints the `unavailable` line. The probe's exit status is discarded by `--check`; `--check`'s exit code is computed exactly as before.

### D9 — Backward compatibility

A `cli` block with no `probe:` key gets L0 plus a `--version` call (today's `--check-vendors`
behaviour), no flag check, and `auth_unknown`. `get_dispatch_configs()` serializes `probe` only
when present, so the endpoint payload is unchanged for configs without it.

### D10 — Concurrency and bounds

Lanes are probed in a `ThreadPoolExecutor` (≤ 8 workers); each subprocess has a 10 s timeout
(matching the existing `_dry_invoke` contract) and runs with `stdin=DEVNULL`. Within a lane the
subprocesses run sequentially (version, then each **distinct** help argv — modes sharing a help
command run it once — then auth), under a **25 s per-lane deadline**: each subprocess's timeout
is `min(10 s, remaining lane budget)`, and a subprocess with no budget left is not run and its
tier is recorded `probe_timeout`. A lane therefore never exceeds 25 s (plus kill latency). With
≤ 8 lanes the pool runs one wave, so a cold full probe is bounded by ~25 s; with more lanes the
bound is `ceil(lanes / 8) × 25 s`, which the report's 60 s timeout (D8) still caps — lanes not
finished when it fires are reported as `probe_timeout`.

### D11 — Who re-probes, who reuses

`vendor_probe.probe_lanes(configs, reuse_fresh: bool, max_age_seconds: int | None = None)`
returns fresh cache entries without running subprocesses when `reuse_fresh=True`;
`max_age_seconds` tightens freshness below the entry TTL for that caller only.

| Caller | `reuse_fresh` | Why |
|---|---|---|
| `review_dispatcher.py --check-vendors` (autopilot INIT) | `False` | Authoritative refresh point before a run |
| `vendor_probe.py report` (`install.sh --check`) | `False` | Operator asked for a live check |
| `vendor_health.py` CLI `main()` (`/vendor-status`) | `False` | Operator asked for a live check |
| `vendor_health.check_all_vendors()` default (watchdog) | `True`, `max_age_seconds=3600` | Runs every 5 min; must not spawn auth commands each cycle. L0 (`shutil.which` + realpath, no subprocess) is evaluated live every cycle; L1/L2 entries older than 1 h are re-probed, so `vendor.unavailable` lags an expired login or a flag regression by at most ~1 h instead of the 24 h TTL |
| `discover_reviewers` | never probes (D5) | Dispatch-time overhead budget |

The watchdog calls `check_all_vendors()` synchronously inside an `async` method
(`watchdog.py:472–480`). A cold probe would block the coordinator's event loop for up to the D10
bound, so the call moves to `await asyncio.to_thread(self._load_vendor_health_report)`.

## Risks

- **Cross-repo thrash** — two consumer repos with differently-configured lanes under the same
  `agent_id` alternately overwrite one `lanes` entry; each sees a stale entry after the other
  probes, so the filter does not fire (never a wrong exclusion). Accepted: keying by
  `(agent_id, fingerprint)` would grow the cache without bound for a rare case.

- **Runtime failures are keyed by `agent_id` only** — the cache is per user, so the same
  `agent_id` in two repositories on one machine normally runs under the same login and account;
  the record is deliberately not fingerprinted so it survives config edits (D4). Where two repos
  drive one `agent_id` with different credentials (e.g. a per-repo API-key env), one repo's
  failure can exclude the lane in the other for at most the 1 h TTL. Mitigation:
  `AGENTIC_PROBE_IGNORE_CACHE=1`, and every exclusion is logged with its reason (D5). Accepted.
- **In-place CLI upgrades** — an upgrade that keeps the same realpath keeps a fresh entry for up
  to the 24 h TTL; the version is only re-read on a re-probe. Autopilot INIT re-probes
  (`reuse_fresh=False`, D11), so a run never starts on a stale verdict; only between-run
  discovery can lag. Accepted.
- **Help text formats vary** — a CLI listing flags only under `--help-all` would false-negative.
  Mitigation: `probe.help_args` override and `ignore_flags`; a `missing_flags` result reports
  the exact flags so the fix is obvious.
- **Merge conflicts in `AGENTS_SCHEMA`** with `add-model-usage-ledger`, `add-atomic-harness`,
  and `followup-add-prime-agent-harness` — textual only; the `probe` property is independent.
