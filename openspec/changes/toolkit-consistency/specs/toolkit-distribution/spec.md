## ADDED Requirements

### Requirement: Install stamp

`skills/install.sh` SHALL write `<target-root>/.agentic-toolkit/stamp.json` after every
successful sync into a target root that is not the toolkit repository itself. The stamp
SHALL be a JSON object with `schema_version` (integer, `1`), `toolkit_version` (contents of
the repository-root `VERSION` file), `source_commit` (the source checkout's `HEAD` SHA, or
`null` when the source is not a git checkout), `payload_hash` (per the Payload hash
requirement), `installed_at` (ISO-8601 UTC), `agents` (sorted list of agent names
installed) and `mode` (`symlink`, `rsync` or `copy`). The stamp SHALL be written only after
every mirror, shared-library, manifest and OpenSpec-asset step has succeeded, and SHALL NOT
be written by `--check` or by a self-install.

#### Scenario: Consumer install writes the stamp

- **WHEN** `install.sh --target <consumer>` completes successfully for agents `claude,agents`
- **THEN** `<consumer>/.agentic-toolkit/stamp.json` SHALL exist and parse as JSON
- **AND** its `payload_hash` SHALL equal the Payload hash of the source tree
- **AND** its `agents` SHALL be `["agents", "claude"]` and `schema_version` SHALL be `1`

#### Scenario: Self-install writes no stamp

- **WHEN** `install.sh` runs with the toolkit repository root as the target root
- **THEN** no `.agentic-toolkit/stamp.json` SHALL be created or modified

#### Scenario: Aborted install leaves the previous stamp intact

- **WHEN** a stamp exists from a prior install
- **AND** `install.sh` exits non-zero before completing its sync steps
- **THEN** the stamp's contents SHALL be byte-identical to the prior stamp

#### Scenario: Check mode does not stamp

- **WHEN** `install.sh --check` runs against a target without a stamp
- **THEN** no `.agentic-toolkit/stamp.json` SHALL be created

### Requirement: Payload hash

The toolkit SHALL provide a dependency-free helper, `skills/shared/payload_hash.py`, that
computes `sha256:<hex>` over the installed file set: every file under each portable skill
directory and each declared shared library directory, plus `install-manifest.json`, skipping
any path containing a `tests`, `__pycache__` or `node_modules` directory component, ordered
by POSIX relative path, hashing `relpath\0sha256(content)\n` per file, and following
symlinks. The helper SHALL produce the same value for a source `skills/` root and for an
agent mirror root synced from it, and SHALL be installable in the consumer layout.

#### Scenario: Source and mirror hash identically

- **WHEN** `install.sh` syncs the payload into a fresh target in `rsync` or `copy` mode
- **THEN** the hash of the source root SHALL equal the hash of each agent mirror root

#### Scenario: Content change changes the hash

- **WHEN** one byte of one installed file under a portable skill changes
- **THEN** the hash SHALL differ from the previous value

#### Scenario: Excluded directories do not affect the hash

- **WHEN** a file is added or changed under `tests/`, `__pycache__/` or `node_modules/`
- **THEN** the hash SHALL be unchanged

#### Scenario: Helper passes the portability gate

- **WHEN** `validate_install_manifest.py` and the consumer-portability test run after the
  helper is added
- **THEN** they SHALL pass and the helper SHALL be listed in `smoke_entrypoints`

### Requirement: Drift check

`install.sh --check` SHALL keep its existing mirror-parity validation and exit codes, and
SHALL additionally compare the stamp when `<target-root>/.agentic-toolkit/stamp.json`
exists and the run is not a self-install. It SHALL report *checkout drift* when the stamp's
`payload_hash` differs from the source root's hash, *runtime drift* for each agent whose
mirror hash differs from the stamp's `payload_hash`, each with a distinct message naming
the pinned `toolkit_version` and `source_commit`, and SHALL exit `1` on either. It SHALL
report an absent stamp as unpinned without changing the exit code, and SHALL exit `1` with an
error for a stamp that is not valid JSON, not an object, or whose `schema_version` is not `1`.

#### Scenario: Pinned payload matches

- **WHEN** the stamp's `payload_hash` equals the source hash and every mirror hash
- **THEN** `--check` SHALL print that the pinned toolkit matches, naming the version and
  hash prefix, and exit `0`

#### Scenario: Checkout drift

- **WHEN** the stamp was written from toolkit commit A and `--check` runs from a checkout at
  commit B whose payload hash differs
- **THEN** `--check` SHALL print a checkout-drift message naming the pinned version and
  commit A and exit `1`

#### Scenario: Runtime drift

- **WHEN** the stamp's `payload_hash` equals the source hash but an agent mirror was synced
  from a different payload
- **THEN** `--check` SHALL print a runtime-drift message naming that agent and exit `1`

#### Scenario: Unpinned repository

- **WHEN** no `.agentic-toolkit/stamp.json` exists under the target root
- **THEN** `--check` SHALL print that the repository is unpinned and how to stamp it
- **AND** the exit code SHALL be determined solely by the existing mirror-parity check

#### Scenario: Invalid stamp fails loud

- **WHEN** `.agentic-toolkit/stamp.json` is not valid JSON or has `schema_version` other than `1`
- **THEN** `--check` SHALL print an error naming the file and exit `1`
- **AND** SHALL NOT rewrite or delete the file

#### Scenario: Self-install skips the stamp comparison

- **WHEN** `--check` runs with the toolkit repository root as the target root
- **THEN** it SHALL perform only the existing mirror-parity validation and say the source tree is the pin

### Requirement: Shared learnings opt-in

Repository-scoped learning export SHALL be enabled only by a human-owned file,
`<target-root>/.agentic-toolkit/config.json`, containing `{"schema_version": 1,
"shared_learnings": {"enabled": true}}`. `<target-root>` is the same consumer repository
root the Install stamp requirement names: the installer's target and the repository the
exporter and `analyze_failures.py` run in. `install.sh` SHALL NOT create or modify this file.
`export_shared_learnings.py` SHALL exit `2` and write nothing when the file is absent,
unreadable, or has `shared_learnings.enabled` other than `true`.

#### Scenario: Export refused without opt-in

- **WHEN** `export_shared_learnings.py` runs and `.agentic-toolkit/config.json` is absent or
  `enabled` is `false`
- **THEN** it SHALL exit `2`, print why, and `.agentic-toolkit/learnings.jsonl` SHALL NOT be
  created or modified

#### Scenario: Export with opt-in

- **WHEN** `enabled` is `true` and episodic memory returns capability-gap entries
- **THEN** `.agentic-toolkit/learnings.jsonl` SHALL be written with one JSON object per line

#### Scenario: Installer never touches the config

- **WHEN** `install.sh` runs against a target with or without `.agentic-toolkit/config.json`
- **THEN** the file SHALL be unchanged, and SHALL NOT be created when absent

### Requirement: Exported learning privacy

Each exported record SHALL contain only `event_type`, `summary`, `outcome`, `lessons`,
`tags` and `created_at`. The exporter SHALL drop `details`, `agent_id` and `session_id`.
`tags` SHALL be filtered to the D4 gap namespaces `failure_type:`, `capability_gap:`,
`affected_skill:`, `severity:` and `source:` (`docs/guides/memory-conventions.md`); every
other tag, in particular identity- or context-bearing ones such as `agent:`, `session:`,
`change:`, `vendor:` and `model:`, SHALL be dropped. The exporter SHALL exclude every entry
tagged `source:transcript-mined`, SHALL pass every exported string through the `session-log`
sanitizer's `sanitize()`, and SHALL write records sorted by `created_at` then `summary`,
deduplicated on `(capability_gap, affected_skill, summary)`, where `capability_gap` and
`affected_skill` are the values of the retained `capability_gap:` and `affected_skill:` tags
(the same tags `analyze_failures.py` reads today; an entry lacking either tag SHALL use
`unknown` for that key, as `analyze_failures.py` does). The exporter SHALL pass the Cross-Repo
Portability gate.

#### Scenario: Transcript-mined entries are excluded

- **WHEN** memory returns an entry tagged `source:transcript-mined`
- **THEN** no record derived from it SHALL appear in `learnings.jsonl`

#### Scenario: Private fields are dropped

- **WHEN** memory returns an entry with `details`, `agent_id` and `session_id`
- **THEN** the exported record SHALL contain none of those keys

#### Scenario: Identity-bearing tags are dropped

- **WHEN** memory returns an entry tagged `agent:<id>`, `session:<id>`, `change:<id>` and
  `capability_gap:<text>`
- **THEN** the exported record's `tags` SHALL contain the `capability_gap:` tag and none of
  the `agent:`, `session:` or `change:` tags

#### Scenario: Secrets are redacted

- **WHEN** an entry's `summary` or `lessons` contains a string matching a `SECRET_PATTERNS`
  rule of the session-log sanitizer
- **THEN** the exported text SHALL contain the sanitizer's redaction marker instead

#### Scenario: Deterministic output

- **WHEN** the exporter runs twice against the same memory response
- **THEN** both `learnings.jsonl` files SHALL be byte-identical

#### Scenario: Exporter passes the portability gate

- **WHEN** `validate_install_manifest.py` and the consumer-portability test run after
  `export_shared_learnings.py` is added
- **THEN** they SHALL pass and the exporter SHALL be listed in `smoke_entrypoints`

### Requirement: One-way consumption of shared learnings

`analyze_failures.py` SHALL accept `--shared-learnings <path>` (default
`<target-root>/.agentic-toolkit/learnings.jsonl`) and SHALL read it only when
`<target-root>/.agentic-toolkit/config.json` enables sharing. Merged records SHALL carry the
tag `origin:shared-repo`, SHALL be deduplicated against local and other shared findings on
`(capability_gap, affected_skill, summary)` — the exporter's key, because exported records
carry no `session_id` and the local `(capability_gap, affected_skill, session_id)` key cannot
apply to them — and SHALL NOT be written back into episodic memory.

#### Scenario: Shared records merged and attributed

- **WHEN** sharing is enabled and `learnings.jsonl` holds a record not present in the
  developer's own memory
- **THEN** the analysis SHALL include it tagged `origin:shared-repo`

#### Scenario: Duplicate shared record appears once

- **WHEN** `analyze_failures.py --shared-learnings <custom path>` runs with sharing enabled
  and the file holds a record whose `(capability_gap, affected_skill, summary)` equals a
  local finding's
- **THEN** the analysis SHALL read the file from `<custom path>` and SHALL contain that
  finding once, with `origin:shared-repo` listed among its sources

#### Scenario: Disabled sharing ignores the file

- **WHEN** `learnings.jsonl` exists but the config is absent or `enabled` is `false`
- **THEN** the analysis SHALL contain no `origin:shared-repo` records

#### Scenario: No write-back

- **WHEN** `analyze_failures.py` completes with shared records merged
- **THEN** no `remember` / `POST /memory/store` call SHALL have been made for them

### Requirement: State-artifact registration

`docs/guides/state-artifacts.md` SHALL register `.agentic-toolkit/stamp.json`,
`.agentic-toolkit/config.json` and `.agentic-toolkit/learnings.jsonl`, each with its
canonical writer (`install.sh`, the repository's humans, `export_shared_learnings.py`), its
authority (the stamp pins the expected payload; the config is the sole opt-in switch; the
learnings file is an advisory one-way projection), its consumers and its missing/stale
behaviour (absent stamp = unpinned, invalid stamp = fail loud; absent config = disabled;
absent or stale learnings = reduced context, never execution state).

#### Scenario: Registration rows present

- **WHEN** the guard test reads `docs/guides/state-artifacts.md`
- **THEN** it SHALL find a table row for each of the three paths naming a writer and a
  missing/stale behaviour

#### Scenario: Projection never feeds canonical state

- **WHEN** any skill reads `.agentic-toolkit/learnings.jsonl`
- **THEN** it SHALL treat the contents as advisory context and SHALL NOT derive loop state,
  checkpoint state or trust posture from them
