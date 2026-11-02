# Validation Report: add-local-agent-probe

Evidence recorded during IMPLEMENT (tasks 6.2 and 6.3). Full `/validate-feature` phases run later.

## Implementation Gates

**Status**: pass

| Gate | Command | Result |
|---|---|---|
| Contract tests | `skills/.venv/bin/python -m pytest skills/tests/parallel-infrastructure/test_vendor_probe_contracts.py` | 31 passed |
| Probe unit tests | `pytest skills/tests/parallel-infrastructure/test_vendor_probe{,_cache,_report}.py` | 47 passed |
| Dispatch + health | `pytest skills/tests/parallel-infrastructure` | 403 passed, 2 skipped |
| Watchdog loader | `agent-coordinator/.venv/bin/python -m pytest agent-coordinator/tests/test_watchdog_vendor.py agent-coordinator/tests/test_dockerfile_vendor_registry.py` | 15 passed |
| Config | `pytest agent-coordinator/tests/test_agents_config_probe.py test_agents_config.py` | 113 passed |
| Cross-source fingerprint | `pytest agent-coordinator/tests/test_probe_fingerprint_sources.py` | 3 passed |
| Install | `pytest skills/tests/install_sh` | 73 passed |
| Coordinator regression | `pytest agent-coordinator/tests -m 'not e2e and not integration'` | exit 0 |
| Skills regression | `pytest skills/tests -m 'not e2e and not integration' --continue-on-collection-errors --ignore=skills/tests/install_sh` | Pre-existing, not introduced by this change. With `AGENTIC_PROBE_CACHE` pointed at a scratch file, `origin/main` (`c2ed6982`) gives 12 failed, 7945 passed, 1 error, and the branch at `d833ce6a` gives 12 failed, 8062 passed, 1 error. The failing test IDs are identical (compared by name with `comm`): 10 in `multiplayer-simulation`, 2 in `roadmap-runtime`, and a collection error in `roadmap-runtime/test_cross_host_reconcile.py`. They fail on main, so they are not order-dependent. IMPLEMENT's earlier 13th failure, `autopilot/test_relayed_gate_answer.py`, did not reproduce. That run used the real `~/.cache` probe file, which was isolated in `7be0918a`. |
| OpenSpec | `openspec validate add-local-agent-probe --strict` | valid |
| Install check | `bash skills/install.sh --check` | exit 0 after syncing the gitignored runtime mirrors |
| Ruff | `ruff check` on agents_config, watchdog, vendor_probe, vendor_health, review_dispatcher | pass |
| Mypy | `mypy src/agents_config.py src/watchdog.py` (agent-coordinator) | pass |

## Real CLI Probe

**Status**: pass

`skills/.venv/bin/python skills/parallel-infrastructure/scripts/vendor_probe.py report` against the CLIs installed on this machine (2026-10-30):

```
Lane                   Version                    L0   L1                    L2
claude-local           2.1.314 (Claude Code)      ok   ok                    auth_ok
claude-remote          2.1.314 (Claude Code)      ok   review:missing_flags  auth_ok
codex-local            codex-cli 0.156.1          ok   ok                    auth_ok
antigravity-local      1.4.10                     ok   ok                    auth_unknown
grok-local             grok 1.0.52                ok   ok                    auth_ok
pi-local               0.85.1                     ok   ok                    auth_ok
ocr-local              Python 3.12.12             ok   ok                    auth_unknown
```

Finding: `claude-remote`'s `review` mode passes `--remote`, which `claude --help` (2.1.314) does not list. The probe correctly reports `missing_flags`; once that lane is probed it is excluded from dispatch. No `ignore_flags` entry was added because it would hide a real discrepancy. Resolved during VAL_REVIEW (2026-11-01): `--remote` is a hidden alias of `--cloud`, and `claude --print --remote ...` exits with "--cloud cannot be combined with --print". So `claude-remote`'s `review` mode cannot dispatch on 2.1.314 at all, and the probe is right to exclude it. That is a defect in the `claude-remote` config that predates this change and is out of scope here.

## Validate Phase (2026-11-01)

**Status**: pass

- Spec: `openspec validate add-local-agent-probe --strict` valid.
- Tests (post review fixes): parallel-infrastructure 420 passed, 2 skipped; coordinator probe/watchdog/config 131 passed.
- Lint: ruff clean on parallel-infrastructure scripts. Install check: exit 0.
- Deploy/smoke/e2e/security: skipped (no deployable service; CLI-tooling change). Real-CLI probe evidence recorded above.
- claude-remote `--remote`: resolved in VAL_REVIEW (alias of `--cloud`, which cannot be combined with `--print`; exclusion is correct).
- Degraded: IMPL_REVIEW recorded `converged` with a `review_skipped` degradation — 7 fixes (`9156a358`, `a9c671d3`, `42405489`) were adjudicated and test-verified but not re-reviewed by a vendor; only claude_code and grok counted (codex/pi/antigravity failed with `Errno 7` argv too long).

## Spec Compliance

**Status**: pass

- `openspec validate add-local-agent-probe --strict`: valid.
- Scenario coverage: all 70 WHEN/THEN scenarios across the 4 spec deltas map to a test task. parallel-infrastructure has 48, vendor-ux 9, agent-identity 8 and toolkit-distribution 5. 66 are named in `tasks.md`. The other 4 are agent-identity scenarios that task 4.1 covers as "every scenario of Declarative CLI Probe Block", and each has its own test in `agent-coordinator/tests/test_agents_config_probe.py`:
  - `test_help_override_must_contain_help_token`
  - the empty-list cases of `test_schema_rejects`
  - `test_login_status_accepted_bare_login_rejected`
  - `test_probe_round_trips_through_dispatch_configs`
- Suites at `f0e42c8e`, run by the orchestrator on 2026-11-02:
  - `skills/tests/parallel-infrastructure` plus `skills/parallel-infrastructure/tests`: 486 passed, 2 skipped.
  - Coordinator probe, config, watchdog, Dockerfile and fingerprint suites: 131 passed.
  - ruff: clean.

## Validation Review

**Status**: pass

**Disposition (operator, 2026-11-02):** recorded as converged with a `review_skipped` degradation. Under the convergence-loop result alone this would be fail (`max_iter`). The operator accepted it because every run ended with 0 blocking and 0 confirmed findings. The two findings that both lanes raised were fixed in `b37951ef` and re-verified. Every remaining item is parked with an adjudication note in the list below.

`convergence_loop.converge()` was run 3 times (review_type=implementation, fix_mode=targeted, base `origin/main`, min_quorum 2). VAL_FIX was wired as an operator-served fix_callback. None of the runs converged on its own: each stopped in round 1 at `adjudication_required` with 0 blocking and 0 confirmed findings.

- Counting lanes: `claude_code` and `grok`. `codex`, `pi` and `antigravity` failed every run with `[Errno 7] Argument list too long`, the same review-packet-as-argv defect seen in IMPL_REVIEW.
- Run 1 (29 findings) raised two high findings, each reported independently by both lanes. The synthesizer did not match the pairs because their anchors differed.
  - 67/85, the skills-side `probe_argv_unsafe` lacked the help-token rule: fixed in `b37951ef` (VAL_FIX), with tests (parallel-infrastructure 422 passed, 2 skipped).
  - 66/90, the `claude-remote` review lane is excluded: adjudicated as not a regression. `--remote` is an alias of `--cloud` and cannot be combined with `--print`.
- Run 2 (15 findings) raised one lone-grok high, 103: `_cli_probe_view` is a hand-maintained `*_flag` allowlist. Adjudicated as latent. The coordinator schema rejects any `*_flag` other than `model_flag` and `prompt_via_flag` (`thinking_flag` was checked and is rejected), and both are projected.
- Run 3 (13 findings) raised one lone-grok high, 101: the coordinator and the probe-side `login` check differ on case. Downgraded to low because the stricter rule is on the execute path, so it fails closed. Same issue as plan ledger [52].
- Follow-ups:
  - fix the vendor dispatch argv limit (pass the packet via stdin or a file)
  - fix the `claude-remote` review mode
  - derive `_cli_probe_view` from all `*_flag` keys
  - unify probe-argv case-folding
