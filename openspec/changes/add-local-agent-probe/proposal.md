# Change: add-local-agent-probe

## Why

When the skills are installed into a consumer repository, nothing establishes which agent
CLIs on *this machine* can actually be dispatched. Two partial probes exist and disagree:
`vendor_health.py` (behind `/vendor-status`) reports a vendor healthy after `shutil.which`
plus an API-key env check, while `review_dispatcher.py --check-vendors` additionally dry-runs
`<cli> --version`. Neither checks that the CLI supports the flags `dispatch_modes` actually
passes (`--json-schema`, `--remote`, `-s read-only`, …), and neither checks authentication.
`agents.yaml` compensates with hand-written comments such as
`# --json-schema verified 2026-09-12 (claude 2.1.268 --help)` that go stale silently. In a
consumer repo, `agents.yaml` resolution falls to `AGENTS_YAML` or the coordinator's
`/agents/dispatch-configs`, which describes the *coordinator host's* roster, not the local one.

The result is capability failures discovered mid-review: a vendor whose CLI rejects a flag,
or whose login has expired, is dispatched, fails with `auth_required` / `vendor_unavailable`,
and — because those error classes are not persisted — is dispatched again in the next run.
Configuration ("how to call a vendor") and capability ("can this machine call it right now")
are conflated. This change separates them: the coordinator remains the authority on policy,
a local probe becomes the authority on capability, and dispatch uses their intersection.

## What Changes

- New shared module `skills/parallel-infrastructure/scripts/vendor_probe.py` implementing
  tiered, token-free probes per CLI lane:
  - **L0 presence** — `shutil.which(command)`.
  - **L1 capability** — run the version command and the help command (bounded timeout), and
    check that every flag used in that lane's `dispatch_modes.*.args` appears in `--help`
    output. Reports the CLI version and any `missing_flags`.
  - **L2 auth** — run a declared non-inference auth-status command, or check that declared
    credential files *exist* (contents are never read, printed, or cached).
  - Every declared probe argv (version, help, auth) is screened against the same
    credential-printing token denylist, because version and help output are captured.
- `vendor_health.py` and `review_dispatcher.py --check-vendors` both delegate to
  `vendor_probe.py`, so `/vendor-status` and the autopilot quorum check can no longer
  disagree. Existing output fields are preserved; probe tiers are added fields.
- `agents.yaml` `cli:` blocks gain an optional declarative `probe:` section
  (`version_args`, `help_args`, `auth_status_args`, `credential_files`, `ignore_flags`).
  Required flags are *derived* from `dispatch_modes`, not hand-listed. The coordinator's
  `AGENTS_SCHEMA`, `CliConfig`, and `get_dispatch_configs()` carry the new key.
- A per-machine probe cache (user cache directory, outside any repository) records each
  lane's tier results with a timestamp and TTL, invalidated when the CLI's resolved path or
  the lane's normalized config fingerprint changes (the version is re-read on every re-probe;
  design D4). `review_dispatcher` excludes lanes whose cached probe failed before dispatch.
- Runtime `auth_required` and `vendor_unavailable` classifications observed during dispatch
  are written to a separate `runtime_failures` map in the same cache, so an account-scoped
  failure is remembered across runs until its TTL expires (or, for `auth_required`, a
  re-probe reports auth OK). Cache writes are locked read-modify-writes because lanes are
  dispatched concurrently.
- The coordinator watchdog's periodic vendor-health call reuses fresh probe results and runs
  off the event loop, so the new subprocess tiers never stall the coordinator.
- `install.sh --check` prints a probe report (lanes, tier status, remediation hints). The
  report is informational: it never changes the exit code, and zero dispatchable vendors is
  a valid state.
- The stale `# … verified <date>` comments in `agents.yaml` are removed; the probe replaces them.

Not changed (explicit non-goals): shipping a populated `agents.yaml` into consumer repos;
writing credentials or running login flows; inference ("smoke") probes — deferred to a
follow-up because they require amending the vendor-ux *Probe Cost* requirement; uploading
local probe results to the coordinator's vendor registry (dg-01) — the cache uses dg-01's
lane ids and reason codes so a later change can.

No **BREAKING** changes: the `probe:` key is optional, absent blocks fall back to L0 plus a
`--version` call (today's `--check-vendors` behaviour), and all existing JSON fields remain.
One field narrows in meaning: `vendor_health --json` `dispatch_modes` lists only modes that pass
L1 — identical to today for a lane without a `probe` block whose `--version` succeeds (vendor-ux
spec).

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Performance | Wall-clock of a cold full probe (all lanes, L0–L2) | Each subprocess timeout `min(10 s, remaining lane budget)`, 25 s hard per-lane deadline, ≤ 8 lanes concurrent → ≤ ~25 s for ≤ 8 lanes; the report's 60 s timeout caps larger rosters (design D10) | Unit tests with sleeping fake CLIs |
| Performance | Dispatch-time overhead with a warm cache | Zero subprocesses started by `discover_reviewers`; ≤ 50 ms added (generous bound, not a micro-benchmark) | Unit test patching `subprocess` to fail on call, plus a coarse timing check |
| Performance | Coordinator event loop | Watchdog vendor-health call runs in `asyncio.to_thread` and reuses fresh cache entries | `agent-coordinator/tests/test_watchdog_vendor.py` |
| Resilience | `install.sh --check` exit code when probes fail or no vendor is installed | Unchanged from pre-change behaviour (probe never contributes a failure) | `skills/tests/install_sh` tests |
| Security | Credential material in probe output, cache file, or logs | Zero occurrences (only paths + booleans recorded) | Unit test scanning cache/report for seeded secret values |
| Cost | Model tokens spent by any probe tier | 0 | Spec scenario + test asserting no dispatch-mode args are executed |
| Compatibility | Existing `vendor_health --json` / `--check-vendors --json` fields | All present with unchanged meaning | Existing test suites pass unmodified |

## Approaches Considered

### Approach 1: Shared probe module + per-user cache (Recommended)

`vendor_probe.py` is the single implementation; both entry points call it. Results are
cached in the user cache directory (`$XDG_CACHE_HOME/agentic-coding-tools/vendor-probe.json`,
falling back to `~/.cache/...`), keyed by lane id and validated against CLI realpath and a
config fingerprint (design D4).

- Pros: CLI availability is a property of the machine, not the repo, so one cache serves every
  consumer repo; no `.gitignore` edits in consumer repos; no risk of committing machine state;
  one probe implementation ends the vendor_health / --check-vendors disagreement.
- Cons: Cache is invisible from the repo; per-repo `agents.yaml` overrides with different
  probe declarations must be part of the cache key.
- Effort: M

### Approach 2: Shared probe module + repo-local gitignored cache

Same module, but the cache lives at `.agents/agents.local.json` inside each repo, and
`install.sh` appends the ignore rule to the consumer's `.gitignore`.

- Pros: Cache is discoverable next to the installed skills; trivially scoped to the repo's
  own `agents.yaml`.
- Cons: Mutating a consumer repo's `.gitignore` during install is a new side effect; a missing
  ignore rule commits machine state; every repo re-probes the same CLIs.
- Effort: M

### Approach 3: Live probing at dispatch, no cache

`CliVendorAdapter.can_dispatch()` runs L1/L2 itself on every discovery call.

- Pros: Never stale; no cache format or invalidation logic.
- Cons: Adds seconds of subprocess calls to every review round across 5+ lanes; cannot
  remember runtime `auth_required` failures across runs, which is half the problem.
- Effort: S

### Recommended

Approach 1. It satisfies the cross-run memory requirement that rules out Approach 3, and it
avoids Approach 2's new install-time side effect on consumer repositories. Checking a
normalized `cli`-block fingerprint on every read resolves its only real con: a per-repo override
makes the entry stale (re-probed), never wrongly applied (design D4, Risks).

### Selected Approach

Approach 1 (shared probe module + per-user cache), selected at Gate 1 on 2026-10-29 with no
modifications. Discovery answers that shape it: the probe lives in one shared module that
both `vendor_health.py` and `--check-vendors` call; inference/smoke probes are deferred to a
follow-up; the cache is a hard pre-dispatch filter that also persists runtime
`auth_required` / `vendor_unavailable`; results stay local (no coordinator upload).

Approaches 2 (repo-local cache — rejected for mutating consumer `.gitignore`) and 3 (live
probing — rejected for losing cross-run memory and adding per-round latency) are not pursued.

## Impact

Architecture layers: Execution (review dispatch), Coordination (agents.yaml schema and
dispatch-configs endpoint).

Affected specs (delta files under `specs/`):
- `parallel-infrastructure` — Dispatchable Vendor Verification (tiered probe, cache-driven exclusion)
- `vendor-ux` — Health Check Dimensions (capability and auth tiers; shared probe)
- `agent-identity` — Declarative Agent Configuration / Dispatch Principal Wire Contract (`cli.probe`)
- `toolkit-distribution` — Drift check (informational probe report)

Affected code:
- `skills/parallel-infrastructure/scripts/vendor_probe.py` (new)
- `skills/parallel-infrastructure/scripts/vendor_health.py`
- `skills/parallel-infrastructure/scripts/review_dispatcher.py` (`_dry_invoke`/`_probe_mode`, `discover_reviewers`, error-class persistence, the mirror `CliConfig` and its loader gaining `probe`)
- `agent-coordinator/src/watchdog.py` (`asyncio.to_thread` around the vendor-health call)
- `agent-coordinator/Dockerfile` (copy `vendor_probe.py` beside `vendor_health.py`)
- `agent-coordinator/src/agents_config.py` (`AGENTS_SCHEMA`, `CliConfig`, `get_dispatch_configs`)
- `agent-coordinator/agents.yaml` (`probe:` blocks; stale verification comments removed)
- `skills/install.sh` (`--check` report)
- `skills/vendor-status/SKILL.md`

Coordination with in-flight changes: `add-live-vendor-capability-and-cost-registry` (lane ids
and reason codes shared, no overlap in writes); `add-model-usage-ledger`, `add-atomic-harness`,
`followup-add-prime-agent-harness` extend the same `cli:` schema — expect textual merge
conflicts in `AGENTS_SCHEMA` only.
