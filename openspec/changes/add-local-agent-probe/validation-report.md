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
| Skills regression | `pytest skills/tests -m 'not e2e and not integration' --continue-on-collection-errors --ignore=skills/tests/install_sh` | 8068 passed, 13 failed, 1 collection error; all failures are in `multiplayer-simulation`, `roadmap-runtime`, `autopilot/test_relayed_gate_answer.py` and pass (285) when those directories run on their own, so they come from cross-directory module collisions in a single-process run, not from this change |
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

Finding: `claude-remote`'s `review` mode passes `--remote`, which `claude --help` (2.1.314) does not list. The probe correctly reports `missing_flags`; once that lane is probed it is excluded from dispatch. No `ignore_flags` entry was added because it would hide a real discrepancy; whether `--remote` is a hidden flag is an open question for the owner.
