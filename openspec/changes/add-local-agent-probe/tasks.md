# Tasks: add-local-agent-probe

Sizes follow the plan-feature Task Sizing Reference. No task is XL; one is L (3.3, flagged).

## 1. Contracts (wp-contracts)

- [ ] 1.1 Write contract tests for the probe cache and probe-block schemas — accept/reject fixtures, including `["login","status"]` accepted, `["login"]` and `["auth","print-api-key"]` rejected, unknown probe key rejected **(S)**
  **Spec scenarios**: agent-identity — A credential-printing auth command is rejected at load; A status subcommand under login is accepted, a bare login is not; An unknown probe key is rejected
  **Contracts**: contracts/vendor-probe-cache.schema.json, contracts/cli-probe-block.schema.json
  **Design decisions**: D3, D4
  **Dependencies**: None

## 2. Probe core (wp-probe-core)

- [ ] 2.1 Write tests for flag derivation and L0/L1 tiers using fake CLI scripts on a temp `PATH` **(M)**
  **Spec scenarios**: parallel-infrastructure — A flag missing from help output fails L1 for that mode only; Subcommand flags are checked against subcommand help; Injected flags are required; A lane without a probe block keeps today's behaviour; vendor-ux — Health probes stay token-free
  **Design decisions**: D2, D9, D10
  **Dependencies**: 1.1
- [ ] 2.2 Implement `vendor_probe.py` flag derivation plus L0/L1 probing (stdlib-only, 10 s timeouts, `stdin=DEVNULL`, thread pool) **(M)**
  **Dependencies**: 2.1
- [ ] 2.3 Write tests for L2 auth — exit-code-only status command, credential-file existence on a `0000` file, sentinel never captured **(S)**
  **Spec scenarios**: parallel-infrastructure — Auth output is never captured; Credential files are checked for existence only
  **Design decisions**: D3
  **Dependencies**: 1.1
- [ ] 2.4 Implement L2 auth probing in `vendor_probe.py` **(S)**
  **Dependencies**: 2.3
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.5 Write tests for the probe cache — path resolution precedence, fingerprint/realpath invalidation, TTL, atomic `0600` write, corrupt-file recovery, runtime-failure record/clear **(M)**
  **Spec scenarios**: parallel-infrastructure — Changing the CLI invalidates its entry; Changing the lane config invalidates its entry; A corrupt cache does not break dispatch
  **Contracts**: contracts/vendor-probe-cache.schema.json
  **Design decisions**: D4, D6
  **Dependencies**: 1.1
- [ ] 2.6 Implement the probe cache read/write API in `vendor_probe.py` **(M)**
  **Dependencies**: 2.5
- [ ] 2.7 Write tests for the `vendor_probe.py report` CLI — table output, remediation hints, zero-vendor case, unresolvable config message **(S)**
  **Spec scenarios**: toolkit-distribution — No vendor CLIs installed; Unresolvable config is reported, not fatal
  **Design decisions**: D8
  **Dependencies**: 1.1
- [ ] 2.8 Implement the `report` subcommand **(S)**
  **Dependencies**: 2.7
- [ ] Checkpoint: run tests, review diff, verify scope

## 3. Dispatch integration (wp-dispatch)

- [ ] 3.1 Write tests for `vendor_health.py` delegation — preserved fields, new `cli_version`/`missing_flags`/`auth_status`, `healthy=false` on `auth_failed`, watchdog by-path load without PyYAML **(M)**
  **Spec scenarios**: vendor-ux — vendor-status and check-vendors agree; The watchdog loader still works
  **Design decisions**: D1
  **Dependencies**: 2.2, 2.4
- [ ] 3.2 Rewire `vendor_health.check_vendor` onto `vendor_probe`; add `vendor_probe.py` to the coordinator Dockerfile copy step **(S)**
  **Dependencies**: 3.1
- [ ] 3.3 Write tests for cache-filtered `discover_reviewers`, `--check-vendors` tier verdicts and runtime-failure write-back **(L — flagged: three entry points in one 3.7k-line file; kept as one test task because they share fixtures, implementation is split into 3.4–3.6)**
  **Spec scenarios**: parallel-infrastructure — A remembered auth failure skips the lane in the next run; Missing cache never narrows the roster; Ignore switch restores the full roster; Check-vendors rejects a lane whose login has expired; The probe never discloses credentials (existing)
  **Design decisions**: D5, D6, D7
  **Dependencies**: 2.6
- [ ] 3.4 Replace `_dry_invoke`/`_probe_mode` verdicts in `--check-vendors` with the tiered probe and write results to the cache **(M)**
  **Dependencies**: 3.3
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.5 Add the cache filter to `discover_reviewers` with per-exclusion INFO logging and `AGENTIC_PROBE_IGNORE_CACHE` **(S)**
  **Dependencies**: 3.3
- [ ] 3.6 Record `auth_required`/`vendor_unavailable` runtime failures into the cache at the `classify_error` sites **(S)**
  **Dependencies**: 3.3
- [ ] Checkpoint: run tests, review diff, verify scope

## 4. Coordinator config (wp-config)

- [ ] 4.1 Write tests for `cli.probe` in `AGENTS_SCHEMA`, `CliConfig`, last-token `login` rule, and `get_dispatch_configs()` round-trip (present-only) **(S)**
  **Spec scenarios**: agent-identity — all four scenarios of Declarative CLI Probe Block
  **Contracts**: contracts/cli-probe-block.schema.json
  **Design decisions**: D3, D9
  **Dependencies**: 1.1
- [ ] 4.2 Implement the `probe` schema property, `CliConfig.probe`, validation rule, and dispatch-configs serialization **(S)**
  **Dependencies**: 4.1
- [ ] 4.3 Add `probe:` blocks to `agents.yaml` per design D3's table and remove stale `# … verified <date>` comments **(XS)**
  **Dependencies**: 4.2
- [ ] Checkpoint: run tests, review diff, verify scope

## 5. Install report (wp-install)

- [ ] 5.1 Write tests that `install.sh --check` prints the probe report and that its exit code is unchanged across pass/drift × probe-pass/probe-fail/unavailable **(S)**
  **Spec scenarios**: toolkit-distribution — No vendor CLIs installed; Drift still fails regardless of the report; Unresolvable config is reported, not fatal
  **Design decisions**: D8
  **Dependencies**: 2.8
- [ ] 5.2 Wire the bounded, exit-code-neutral report into `install.sh --check`; document tiers and cache in `skills/vendor-status/SKILL.md` **(S)**
  **Dependencies**: 5.1

## 6. Integration (wp-integration)

- [ ] 6.1 Run the full gate set (pytest both venvs, ruff, mypy on touched coordinator modules, `openspec validate --strict`, `install.sh --check`) on the merged tree **(S)**
  **Dependencies**: 3.6, 4.3, 5.2
- [ ] 6.2 Verify the probe against the real local CLIs (claude, codex, grok, pi) and record the report in the validation evidence **(XS)**
  **Dependencies**: 6.1
