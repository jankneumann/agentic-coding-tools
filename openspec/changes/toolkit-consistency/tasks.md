# Tasks: Stamp and check team toolkit consistency

> Change ID: `toolkit-consistency`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## Tasks

Each task is single-commit sized, names the files it owns, and lists the tasks it depends
on. Tasks with no shared files and no `Depends on` can run in parallel worktrees.

- [x] **T1. Payload hash helper** — Add `skills/shared/payload_hash.py` (`hash_payload(root,
  skill_names, shared_libraries)` plus a `--root/--manifest` CLI printing the `sha256:` value)
  implementing D4, and tests proving source/mirror equality, content sensitivity and exclusion
  of `tests/`, `__pycache__/`, `node_modules/`.
  Requirements: Payload hash. Design: D4.
  Files: `skills/shared/payload_hash.py`, `skills/tests/install_sh/test_payload_hash.py`.
  Depends on: none.

- [x] **T2. Stamp writing in `install.sh`** — After all mirror, shared-library, manifest and
  asset steps succeed and only when `is_self_install()` is false, write
  `<target-root>/.agentic-toolkit/stamp.json` (schema_version, toolkit_version from `VERSION`,
  source_commit, payload_hash via T1, installed_at, agents, mode). `--check` must not write it.
  Tests cover consumer install, self-install skip, and an aborted install leaving the prior
  stamp untouched.
  Requirements: Install stamp. Design: D2, D3, D5, D6.
  Files: `skills/install.sh` (stamp section only), `skills/tests/install_sh/test_install_stamp.py`.
  Depends on: T1.

- [x] **T3. Drift check extension** — Extend `check_install_payload()` with the stamp
  comparison of D7 (checkout drift, runtime drift per agent, unpinned notice, invalid stamp
  error, self-install skip) and update the `usage()` text for `--check`. Existing parity output
  and exit codes are unchanged. Tests cover every scenario of the Drift check requirement.
  Requirements: Drift check. Design: D7.
  Files: `skills/install.sh` (`check_install_payload`, `usage`), `skills/tests/install_sh/test_install_check_drift.py`.
  Depends on: T2 (same file; sequential after T2).

- [x] **T4. Shared-learnings export** — Add
  `skills/improve-harness/scripts/export_shared_learnings.py`: read
  `.agentic-toolkit/config.json`, refuse with exit `2` when absent/disabled, query episodic
  memory through the existing `analyze_failures.query_memory()` path, apply the D8 allowlist,
  drop `details`/`agent_id`/`session_id`, keep only `tags` in the D4 namespaces
  (`failure_type:`, `capability_gap:`, `affected_skill:`, `severity:`, `source:`), exclude
  `source:transcript-mined`, sanitize via
  `<skill-base-dir>/../session-log/scripts/sanitize_session_log.py`, write deterministic
  `.agentic-toolkit/learnings.jsonl`. Tests use a stubbed memory response.
  Requirements: Shared learnings opt-in; Exported learning privacy. Design: D8, D9.
  Files: `skills/improve-harness/scripts/export_shared_learnings.py`, `skills/tests/improve-harness/test_export_shared_learnings.py`.
  Depends on: none.

- [x] **T5. Shared-learnings consumption** — Add `--shared-learnings <path>` to
  `analyze_failures.py` (default `<target-root>/.agentic-toolkit/learnings.jsonl`, read only
  when the config enables sharing), dedupe merged records against local and other shared
  findings on `(capability_gap, affected_skill, summary)` (exported records carry no
  `session_id`), tag them `origin:shared-repo`, and assert no write-back to memory. Document export and consumption
  in `skills/improve-harness/SKILL.md`.
  Requirements: One-way consumption of shared learnings. Design: D8.
  Files: `skills/improve-harness/scripts/analyze_failures.py`, `skills/improve-harness/SKILL.md`, `skills/tests/improve-harness/test_shared_learnings_merge.py`.
  Depends on: T4 (record format).

- [x] **T6. State-artifact registration and guides** — Add rows for
  `.agentic-toolkit/stamp.json`, `.agentic-toolkit/config.json` and
  `.agentic-toolkit/learnings.jsonl` to `docs/guides/state-artifacts.md` (writer, authority,
  consumers, missing/stale behaviour per D6–D8); document the stamp, extended `--check` and
  opt-in in `docs/guides/skills.md`; add a guard test asserting the three rows exist.
  Requirements: State-artifact registration. Design: D2, D3, D7, D8.
  Files: `docs/guides/state-artifacts.md`, `docs/guides/skills.md`, `skills/tests/install_sh/test_state_artifacts_registration.py`.
  Depends on: none (file names are fixed by design.md).

- [x] **T7. Manifest and portability gate** — Add `smoke_entrypoints` for
  `shared/payload_hash.py` and `improve-harness/scripts/export_shared_learnings.py`, add
  `session-log` to `improve-harness` in `cross_skill_dependencies`, then run
  `bash install.sh --mode copy --force ... && bash install.sh --check`,
  `validate_install_manifest.py` and `skills/tests/install_sh/test_consumer_portability.py`
  to prove the new files pass the Cross-Repo Portability gate unchanged.
  Requirements: Payload hash (portability scenario); Exported learning privacy (portability
  scenario). Design: D4, D9.
  Files: `skills/install-manifest.json`.
  Depends on: T1, T4.

## Dependency graph

```
T1 ─► T2 ─► T3
T1 ─┐
T4 ─┴► T7
T4 ─► T5
T6 (independent)
```

Independent at start: T1, T4, T6 (3). Sequential chains: T1→T2→T3, T4→T5, {T1,T4}→T7.
Max parallel width: 3. Shared-file conflicts: `skills/install.sh` (T2, T3 — sequenced);
`skills/install-manifest.json` (T7 only). No other task pair touches the same file.

## Verification

- `openspec validate toolkit-consistency --strict`
- `skills/.venv/bin/python -m pytest skills/tests/install_sh/ skills/tests/improve-harness/`
- `bash skills/install.sh --mode copy --force --deps none --openspec-assets none --openspec-cli none --python-tools none && bash skills/install.sh --check` (source-contribution-only commands run from this repository)
- `uv run ruff check skills/shared/payload_hash.py skills/improve-harness/scripts/`
