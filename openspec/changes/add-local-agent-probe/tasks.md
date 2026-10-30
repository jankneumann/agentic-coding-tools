# Tasks: add-local-agent-probe

Sizes follow the plan-feature Task Sizing Reference. No task is XL; one is L (3.3, flagged).

## 1. Contracts (wp-contracts)

- [x] 1.1 Write contract tests for the probe cache and probe-block schemas (schema layer only — the last-token `login` and help-token rules are not expressible in JSON Schema and are pinned in 4.1) — accept/reject fixtures, including `["login","status"]` accepted, `["auth","print-api-key"]` and `["auth","Print-API-Key"]` rejected in `auth_status_args`, `version_args`, and a `help_args` value, empty `version_args` / `help_args` value / `credential_files` rejected, unknown probe key rejected, every schema pattern compiles as ECMA-262 (no inline `(?i)`), an L0/L1 tier with reason `auth_failed` rejected, a cache with a top-level `runtime_failures` entry and no `lanes` entry for that lane accepted, a `runtime_failure` nested inside a `lanes` entry rejected **(S)**
  **Spec scenarios**: agent-identity — A credential-printing auth command is rejected at load; A credential-printing version command is rejected at load; An unknown probe key is rejected
  **Contracts**: contracts/vendor-probe-cache.schema.json, contracts/cli-probe-block.schema.json
  **Path rule**: tests locate both schemas with `change_dir("add-local-agent-probe") / "contracts"` from `openspec_paths` — never a literal `openspec/changes/<id>/` path (AGENTS.md *OpenSpec Path Stability in Tests*); the same applies to 2.5's schema validation
  **Also asserts**: empty `ignore_flags` and empty `help_args` map rejected; a cache `l2` without `method`, a failed tier without `reason`, and `method: none` with `auth_ok` rejected
  **Design decisions**: D3, D4
  **Dependencies**: None

## 2. Probe core (wp-probe-core)

- [x] 2.1 Write tests for flag derivation and L0/L1 tiers using fake CLI scripts on a temp `PATH` **(M)**
  **Spec scenarios**: parallel-infrastructure — A flag missing from help output fails L1 for that mode only; Subcommand flags are checked against subcommand help; Injected flags are required; A lane without a probe block keeps today's behaviour; A failing version command fails every mode; Modes sharing a help command run it once; The per-lane deadline bounds a slow lane; vendor-ux — Health probes stay token-free
  **Also asserts**: each subprocess timeout is capped at the remaining lane budget; parallel-infrastructure scenarios Value and placeholder tokens are not required flags; An undeclared model flag is still required; Ignored flags are not required; A partial help override leaves other modes on generated help; Version output is truncated before it is stored
  **Design decisions**: D2, D9, D10
  **Dependencies**: 1.1
- [x] 2.2 Implement `vendor_probe.py` flag derivation plus L0/L1 probing (stdlib-only, 10 s timeouts, `stdin=DEVNULL`, thread pool) **(M)**
  **Dependencies**: 2.1
- [x] 2.3 Write tests for L2 auth — exit-code-only status command, credential-file existence on a `0000` file, sentinel never captured, hanging status command killed at 10 s **(S)**
  **Spec scenarios**: parallel-infrastructure — Auth output is never captured; Credential files are checked for existence only; A hanging auth command times out without failing auth; A status command takes precedence over credential files; A missing credential file fails auth
  **Also asserts**: parallel-infrastructure scenario An auth command that cannot be launched is unknown
  **Design decisions**: D3
  **Dependencies**: 1.1
- [x] 2.4 Implement L2 auth probing in `vendor_probe.py` **(S)**
  **Dependencies**: 2.3
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 2.5 Write tests for the probe cache — path resolution precedence, normalized-projection fingerprint, realpath invalidation, TTL, locked read-modify-write with `0600` atomic replace, corrupt-file recovery, `runtime_failures` record (with and without a `lanes` entry) and per-class clearing, `probe_lanes(reuse_fresh=True)` starting no subprocesses **(M)**
  **Spec scenarios**: parallel-infrastructure — Cache path precedence; The cache file is private; Declaring an empty probe block invalidates a version-only entry; Changing the CLI invalidates its entry; Changing the lane config invalidates its entry; The same lane fingerprints identically across config sources (unit level, hand-built dicts); Editing a model list does not invalidate capability results; Concurrent writers do not lose updates; A corrupt cache does not break dispatch; A billing failure is not cleared by a passing auth probe; Credential-file evidence does not clear a runtime auth failure; A probe that started before the failure does not clear it; A defaulted version argv fingerprints like an absent one
  **Also asserts**: a `null` and an absent non-`model_flag` `*_flag` key fingerprint identically; parallel-infrastructure scenarios An expired entry is stale; An unwritable cache does not fail a probe
  **Contracts**: contracts/vendor-probe-cache.schema.json
  **Design decisions**: D4, D6, D11
  **Dependencies**: 1.1
- [x] 2.6 Implement the probe cache read/write API, `lane_fingerprint()`, and `probe_lanes(reuse_fresh=)` in `vendor_probe.py` **(M)**
  **Dependencies**: 2.5
- [x] 2.7 Write tests for the `vendor_probe.py report` CLI — table output, remediation hints, zero-vendor case, unresolvable config message **(S)**
  **Spec scenarios**: toolkit-distribution — No vendor CLIs installed; Unresolvable config is reported, not fatal
  **Also asserts**: config resolution happens only in the `report` entry point (importing the library functions does not import `review_dispatcher` or PyYAML)
  **Design decisions**: D1, D8
  **Dependencies**: 1.1
- [x] 2.8 Implement the `report` subcommand **(S)**
  **Dependencies**: 2.7
- [x] Checkpoint: run tests, review diff, verify scope

## 3. Dispatch integration (wp-dispatch)

- [x] 3.1 Write tests for `vendor_health.py` delegation — preserved fields, narrowed `dispatch_modes`, new `cli_version`/`missing_flags`/`auth_status`, `healthy=false` on `auth_failed`, watchdog by-path load without PyYAML (sibling load registered in `sys.modules`), CLI re-probes while `check_all_vendors()` reuses fresh entries, watchdog call runs via `asyncio.to_thread` **(M)**
  **Spec scenarios**: vendor-ux — vendor-status and check-vendors agree; An expired login makes a lane unhealthy; A remembered billing failure makes a lane unhealthy in both entry points; The health CLI re-probes; The watchdog probe runs off the event loop; The watchdog loader still works; The watchdog reuses fresh probe results; Health check verifies all dimensions (modified)
  **Design decisions**: D1, D11
  **Dependencies**: 2.2, 2.4, 2.6 (`reuse_fresh` and the cache API)
- [x] 3.2 Rewire `vendor_health.check_vendor` onto `vendor_probe` (by-path sibling load); add `vendor_probe.py` to the coordinator Dockerfile copy step; wrap the watchdog's vendor-health call in `asyncio.to_thread` **(S)**
  **Dependencies**: 3.1
- [x] 3.3 Write tests for cache-filtered `discover_reviewers`, `--check-vendors` tier verdicts and runtime-failure write-back **(L — flagged: three entry points in one 3.7k-line file; kept as one test task because they share fixtures, implementation is split into 3.4–3.6)**
  **Spec scenarios**: parallel-infrastructure — A remembered auth failure skips the lane in the next run; A remembered auth failure expires; A passing status command clears a remembered auth failure; Cache-driven exclusions appear in the dispatch manifest; A known-broken CLI is not dispatched; Check-vendors does not count a lane dispatch will skip; Existing JSON keys and exit codes are preserved; A listed vendor without its CLI is unverified (modified); A hanging dry invocation is unverified (modified); A billing failure is not cleared by a passing auth probe; A zero-exit review that mentions 402 is not remembered as unavailable; An unwritable cache does not fail the review; Missing cache never narrows the roster; Ignore switch restores the full roster; Check-vendors rejects a lane whose login has expired; The probe never discloses credentials (existing)
  **Also asserts**: a lane loaded through the dispatcher's own loader keeps its `probe` block on the mirror `CliConfig`; `discover_reviewers` starts no subprocesses
  **Design decisions**: D5, D6, D7
  **Dependencies**: 2.6
- [x] 3.4 Add `probe` to the dispatcher's mirror `CliConfig` and its loader; replace `_dry_invoke`/`_probe_mode` verdicts in `--check-vendors` with the tiered probe (`reuse_fresh=False`) and write results to the cache **(M)**
  **Dependencies**: 3.3
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 3.5 Add the cache filter to `discover_reviewers` with per-exclusion INFO logging, `ReviewOrchestrator.last_exclusions`, the additive `excluded_lanes` manifest key in `checkpoint_findings.write_manifest`, and `AGENTIC_PROBE_IGNORE_CACHE` **(S)**
  **Dependencies**: 3.4 (needs the mirror `CliConfig.probe` to fingerprint; same file)
- [x] 3.6 Record `auth_required`/`vendor_unavailable` runtime failures into `runtime_failures` at the non-zero-exit stderr `classify_error` sites only (`:1073`, `:1550`, `:1717`; never the zero-exit stdout sites `:1242`/`:1268`, design D6), best-effort (write errors logged, result unchanged) **(S)**
  **Dependencies**: 3.5 (same file — sequential to avoid conflicting hunks)
- [x] Checkpoint: run tests, review diff, verify scope

## 4. Coordinator config (wp-config)

- [x] 4.1 Write tests for `cli.probe` in `AGENTS_SCHEMA`, `CliConfig`, the semantic rules in `agents_config.validate` (last-token `login`; each `help_args` value contains a help token), and `get_dispatch_configs()` round-trip (present-only) **(S)**
  **Spec scenarios**: agent-identity — every scenario of Declarative CLI Probe Block, including An empty probe block survives the round-trip (including `["login"]` rejected, which only `validate` can enforce)
  **Contracts**: contracts/cli-probe-block.schema.json
  **Design decisions**: D3, D9
  **Dependencies**: 1.1
- [x] 4.2 Implement the `probe` schema property, `CliConfig.probe`, validation rule, and dispatch-configs serialization **(S)**
  **Dependencies**: 4.1
- [x] 4.3 Add `probe:` blocks to `agents.yaml` per design D3's table and remove stale `# … verified <date>` comments **(XS)**
  **Dependencies**: 4.2
- [x] Checkpoint: run tests, review diff, verify scope

## 5. Install report (wp-install)

- [ ] 5.1 Write tests that `install.sh --check` prints the probe report and that its exit code is unchanged across pass/drift × probe-pass/probe-fail/unavailable **(S)**
  **Spec scenarios**: toolkit-distribution — No vendor CLIs installed; Drift still fails regardless of the report; Unresolvable config is reported, not fatal; A bare interpreter without PyYAML is reported, not fatal; A hung probe is cut off at the overall timeout
  **Design decisions**: D8
  **Dependencies**: 2.8
- [ ] 5.2 Wire the bounded, exit-code-neutral report into `install.sh --check`; document tiers and cache in `skills/vendor-status/SKILL.md` **(S)**
  **Dependencies**: 5.1

## 6. Integration (wp-integration)

- [ ] 6.1 Write and pass a cross-source fingerprint test: every lane in the real `agent-coordinator/agents.yaml` produces the same fingerprint **and** the same required-flag set when loaded raw, when passed through `get_dispatch_configs()`, and when loaded through `review_dispatcher`'s own loader into its mirror `CliConfig` (the reader `discover_reviewers` fingerprints) **(S)**
  **Spec scenarios**: parallel-infrastructure — The same lane fingerprints identically across config sources (end-to-end)
  **Design decisions**: D4
  **Dependencies**: 3.6, 4.3
- [ ] 6.2 Run the full gate set (pytest both venvs, ruff, mypy on touched coordinator modules, `openspec validate --strict`, `install.sh --check`) on the merged tree **(S)**
  **Dependencies**: 6.1, 5.2
- [ ] 6.3 Verify the probe against the real local CLIs (claude, codex, grok, pi) and record the report in the validation evidence **(XS)**
  **Dependencies**: 6.2
