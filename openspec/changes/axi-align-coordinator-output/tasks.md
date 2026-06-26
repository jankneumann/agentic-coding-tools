# Tasks: AXI-Align Coordinator Agent-Output Contract

## 1. CLI list-output envelope

- [x] 1.1 Add `_emit_list()` helper to `coordination_cli.py` emitting `{count, truncated, items, hint?, next_steps?}` with JSON and human-readable rendering
- [x] 1.2 Add `_probe_truncation()` helper implementing the `limit + 1` fetch-and-trim detection
- [x] 1.3 Apply envelope to unlimited list commands: `feature list`, `merge-queue status`, `lock status` (with `next_steps`)
- [x] 1.4 Apply envelope + accurate truncation to limited commands: `handoff read`, `memory query`, `audit query` (fetch `limit + 1`)

## 2. Tests

- [x] 2.1 Add `tests/test_coordination_cli_axi.py` covering envelope shape, empty state, `next_steps` presence/absence, truncation hint, and human-readable rendering
- [x] 2.2 Add truncation-probe unit tests (over-limit, exact-limit, under-limit)
- [x] 2.3 Confirm `mypy --strict`, `ruff`, and the existing `test_help_service.py` suite stay green

## 3. Spec

- [x] 3.1 ADD `Requirement: AXI-Aligned List Output Contract` to `specs/agent-coordinator/spec.md` delta
- [x] 3.2 MODIFY `Requirement: CLI Entry Point` so the feature-list scenario asserts the envelope object rather than a bare array

## 4. Follow-ups (deferred — not in this change)

- [ ] 4.1 Extend the envelope to `coordination_api.py` list endpoints (Pydantic models + OpenAPI consumers)
- [ ] 4.2 Pilot `--format=toon` behind a flag on the tabular list commands and A/B the token delta vs. JSON
- [ ] 4.3 Update any human-facing docs / skill prompts that show example `feature list` output to reflect the envelope
