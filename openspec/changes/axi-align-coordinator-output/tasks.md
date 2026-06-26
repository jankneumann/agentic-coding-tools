# Tasks: AXI-Align Coordinator Agent-Output Contract

## 1. CLI list-output envelope

- [x] 1.1 Add `_emit_list()` helper to `coordination_cli.py` emitting `{count, truncated, items, hint?, next_steps?}` with JSON and human-readable rendering
- [x] 1.2 Add `_probe_truncation()` helper implementing the `limit + 1` fetch-and-trim detection
- [x] 1.3 Apply envelope to unlimited list commands: `feature list`, `merge-queue status`, `lock status` (with `next_steps`)
- [x] 1.4 Apply envelope + accurate truncation to limited commands: `handoff read`, `memory query`, `audit query` (fetch `limit + 1`)

## 2. Shared helpers + HTTP API

- [x] 2.1 Add `src/axi_output.py` with `probe_truncation()`, `truncation_hint()`, and `list_envelope()` (additive named-key envelope for HTTP)
- [x] 2.2 Refactor the CLI to consume the shared `probe_truncation` (keep `_probe_truncation` importable for tests)
- [x] 2.3 Apply additive envelope (`count` / `truncated` / `hint` / `next_steps`) to `GET /features/active`, `GET /merge-queue`, `GET /audit`, `POST /memory/query`, `POST /handoffs/read`
- [x] 2.4 Use `limit + 1` truncation detection on the limited endpoints (`/audit`, `/memory/query`, `/handoffs/read`); omit top-level `next_steps` on handoffs to avoid colliding with the per-row field
- [x] 2.5 (PR review) Push truncation detection into `HandoffService.read` via `detect_truncation` so the over-fetch never inflates the audit trail's `limit`/`count`; add `ReadHandoffResult.truncated`; add a regression test asserting audited limit/count are the trimmed values

## 3. Tests

- [x] 3.1 Add `tests/test_coordination_cli_axi.py` covering CLI envelope shape, empty state, `next_steps` presence/absence, truncation hint, and human-readable rendering
- [x] 3.2 Add `tests/test_axi_output.py` for the shared helpers (probe over/exact/under limit, envelope named-key preservation, hint, next_steps)
- [x] 3.3 Strengthen `tests/test_coordination_api.py` `/memory/query` and `/audit` cases to assert `count` / `truncated` and the `limit + 1` service call
- [x] 3.4 Confirm `mypy --strict`, `ruff`, and the existing `test_coordination_api.py` / `test_help_service.py` suites stay green

## 4. Spec

- [x] 4.1 ADD `Requirement: AXI-Aligned List Output Contract` (CLI) to `specs/agent-coordinator/spec.md` delta
- [x] 4.2 ADD `Requirement: AXI-Aligned HTTP List Output` (additive named-key envelope) to the delta
- [x] 4.3 MODIFY `Requirement: CLI Entry Point` so the feature-list scenario asserts the envelope object rather than a bare array

## 5. Follow-ups (deferred — not in this change)

- [ ] 5.1 Pilot `--format=toon` behind a flag on the tabular list commands and A/B the token delta vs. JSON
- [ ] 5.2 Update any human-facing docs / skill prompts that show example `feature list` output to reflect the envelope
