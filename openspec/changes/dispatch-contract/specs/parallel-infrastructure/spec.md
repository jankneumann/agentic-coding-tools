## ADDED Requirements

### Requirement: Dispatchable Vendor Verification

`review_dispatcher.py --check-vendors` SHALL count a vendor lane as available for a mode only after a dry invocation for that mode succeeds: the adapter's declared no-op command (for a CLI lane, `<cli> --version`; for an SDK or API lane, the adapter's own authenticated no-op such as a model-list call) run with a 10-second timeout. Credentials MAY be read only inside the adapter's existing credential path, and the probe SHALL NOT print, log, or return any environment value or credential. With `--json` it SHALL print `{"modes": {<mode>: {"verified": [...], "unverified": [{"vendor", "reason"}]}}, "probe_command": "<argv>"}` and keep its existing exit codes (0 at quorum, 2 below quorum or on probe failure); when the roster cannot be resolved it SHALL print `{"error": "<reason>", "modes": {}}` and exit 2.

#### Scenario: A listed vendor without its CLI is unverified
- **WHEN** `agents.yaml` lists `codex` for mode `review` and no `codex` executable is on `PATH`
- **THEN** `--check-vendors --json` SHALL list `codex` under `unverified` with reason `cli_not_found`, and SHALL NOT count it toward `--min-vendors`

#### Scenario: A hanging dry invocation is unverified
- **WHEN** a lane's dry invocation does not exit within 10 seconds
- **THEN** the lane SHALL be `unverified` with reason `probe_timeout`

#### Scenario: The probe never discloses credentials
- **WHEN** the test sets `ANTHROPIC_API_KEY=sk-test-SENTINEL-1234567890` and `OPENAI_API_KEY=sk-test-SENTINEL-0987654321` and runs `--check-vendors --json`
- **THEN** neither sentinel value SHALL appear in stdout, stderr, or the JSON, and no `env` or `printenv` subprocess SHALL have been spawned
