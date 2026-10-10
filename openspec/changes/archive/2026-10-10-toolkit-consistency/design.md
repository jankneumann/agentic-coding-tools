# Design: Stamp and check team toolkit consistency

## Context

`skills/install.sh` mirrors the portable payload (every `install-manifest.json` skill with
`"distribution": "portable"`, the `shared/` and `references/` libraries, and the manifest
itself) into `.claude/skills/` and `.agents/skills/` under a target root. It already has
`--check`, which diffs each mirror against the source tree and fails on any difference, and
`is_self_install()`, which detects that the target root is this repository. Validation of the
payload's portability (no `agent-coordinator/` or repo-root `skills/` references) is done by
`skills/shared/validate_install_manifest.py` before anything is copied.

Learning signals live in the coordinator's episodic memory (`POST /memory/store` /
`/memory/query`, bridge `try_remember` / `try_recall`), tagged per
`docs/guides/memory-conventions.md`. `improve-harness` queries them with
`analyze_failures.query_memory()` and deduplicates on
`(capability_gap, affected_skill, session_id)`. Working and procedural memory layers were
removed (ri-15); roadmap learnings use tracked `learnings/<item-id>.md` files.

Everything below extends those mechanisms; nothing introduces a second distribution path,
a second learning store, or a coordinator schema change.

## Decisions

### D1: New capability `toolkit-distribution`

The delta is written under `openspec/specs/toolkit-distribution/` (replacing the
`multiplayer-collaboration` placeholder the roadmap scaffold used).

- *Alternative: append to `skill-workflow`.* That spec already holds Canonical Skill
  Distribution and Cross-Repo Portability, but it is a 7,000-line accretion spec. Stamp,
  drift and shared-learnings requirements form a coherent "how the toolkit reaches a consumer
  repository" surface and are easier to review and own separately. The two existing
  requirements are left untouched and referenced as constraints.
- *Alternative: keep `multiplayer-collaboration`.* No such spec exists; the scaffold marks it
  as a placeholder. The roadmap is an epic, not a capability.

### D2: One tracked directory, `.agentic-toolkit/`, at the consumer root

`stamp.json` (installer-owned), `config.json` (human-owned), `learnings.jsonl`
(exporter-owned) live under `<target-root>/.agentic-toolkit/`.

- *Alternative: a stamp per agent directory (`.claude/toolkit-stamp.json`).* Mirror
  directories are frequently gitignored in consumer repositories (this repository rebuilds
  them in `setup-cloud.sh`), so the pin would not be tracked; it would also exist twice.
- *Alternative: under `openspec/`.* Only present when `--openspec-assets sync` ran; the
  stamp must exist for every install.
- *Alternative: a flat root dotfile.* Three files with three writers belong in one directory
  so ownership stays visible and `.gitignore` rules stay simple.

### D3: The stamp is the pin

There is no separate pin file. Committing the stamp written by the last successful install
declares the expected payload. Updating the pin is "run `install.sh` from the new toolkit
checkout and commit the stamp".

- *Alternative: separate `pin.json` edited by hand.* A hand-maintained version string drifts
  from the payload actually installed and cannot carry a hash anyone computed.

### D4: Payload hash over the installed file set

`skills/shared/payload_hash.py` walks each portable skill directory, each shared library
directory and `install-manifest.json`; skips `tests/`, `__pycache__/`, `node_modules/`
components; sorts entries by POSIX relative path; emits `relpath\0sha256(content)\n` per file;
and returns `sha256:` + the SHA-256 of that stream. Run against a source `skills/` root or an
agent mirror root it yields the same value when they are in sync. It follows symlinks so
`--mode symlink` mirrors hash identically.

- *Alternative: hash only `runtime_globs` matches.* The mirror contains the whole skill
  directory minus the excludes; hashing a subset would miss files that are installed.
- *Alternative: `git rev-parse HEAD:skills`.* Not available in a mirror and not equal to what
  was installed when the checkout is dirty.
- The helper is dependency-free and uses `install.sh`'s existing python3 requirement; it must
  pass `validate_install_manifest.py` and gets a `smoke_entrypoints` entry.

### D5: Version = `VERSION` file + source commit

`toolkit_version` is the contents of the repository-root `VERSION` file (`0.2.0` today);
`source_commit` is `git -C "$SCRIPT_DIR" rev-parse HEAD` or `null` when not a git checkout.
Both are informational; drift is decided by `payload_hash`.

- *Alternative: `skills/pyproject.toml` version.* Same value today, but it names the
  `skill-scripts` package, not the toolkit.

### D6: Self-install writes no stamp

When `is_self_install()` is true, the source tree *is* the pin; writing a stamp would churn a
tracked file on every skill edit and CI run. `--check` on a self-install skips the stamp
comparison and reports "self-install: source tree is the pin".

### D7: `--check` is additive; unpinned is advisory, invalid is loud

Existing mirror-parity behaviour and exit codes are unchanged. With a readable stamp:
checkout drift (`payload_hash` ≠ source hash) and runtime drift (`payload_hash` ≠ mirror
hash, per agent) each print one distinct message and set exit `1`. Absent stamp: one
notice, exit code unaffected. Unreadable, non-object or `schema_version` ≠ 1 stamp: error,
exit `1` — a tracked artifact is never silently repaired (`docs/guides/state-artifacts.md`).
Stamping happens after every mirror, shared library, manifest and asset step has
succeeded, so an aborted install leaves the previous stamp in place (writer ordering).

- *Alternative: fail when unpinned.* Would break every consumer that upgrades the toolkit
  before running the new installer once; the roadmap's constraint is that advisory signals
  fail open.

### D8: Shared learnings are an opt-in, one-way, allowlisted JSONL projection

`config.json` `{"schema_version": 1, "shared_learnings": {"enabled": true}}` is the only
switch; `install.sh` never creates or edits it. `export_shared_learnings.py` refuses (exit
`2`, writes nothing) when the file is absent or disabled. Records carry only `event_type`,
`summary`, `outcome`, `lessons`, `tags`, `created_at`; `details`, `agent_id`, `session_id`
are dropped; `tags` are filtered to the D4 gap namespaces (`failure_type:`, `capability_gap:`,
`affected_skill:`, `severity:`, `source:`) so `agent:`, `session:`, `change:`, vendor and
model tags never leave the repository; entries tagged `source:transcript-mined` are excluded;
remaining text is run
through `sanitize_session_log.sanitize()` from the co-installed `session-log` skill. Output is
deterministic (sorted by `created_at`, then `summary`; deduplicated on
`(capability_gap, affected_skill, summary)`), so re-exports produce reviewable diffs.
`analyze_failures.py` reads the file when enabled, dedupes merged records against local and
other shared findings on `(capability_gap, affected_skill, summary)` (its local key uses
`session_id`, which exported records do not carry; `capability_gap` and `affected_skill` are
the retained tag values, `unknown` when absent, as today), tags merged entries
`origin:shared-repo`, and never calls `remember` with them.

- *Alternative: embed the opt-in in the stamp.* The stamp is overwritten on every install;
  a human choice must not live in an installer-owned file.
- *Alternative: Markdown export.* Reads better for humans, but the consumer is
  `analyze_failures.py` and the dedupe/merge needs structured records; PR review of JSONL
  line diffs is adequate.
- *Alternative: include transcript-mined summaries behind `--include-transcript-mined`.*
  Turns "never include private transcript content" into a conditional; excluded until a
  per-principal consent model exists (`principal-credential-architecture`).
- *Alternative: coordinator-side team memory.* Out of scope; owned by `closed-loop-learning`
  and would require new endpoints and a trust model.

### D9: No new skill

Export and merge live in `improve-harness`, which already owns the memory → report pipeline.
`improve-harness` gains a declared cross-skill dependency on `session-log` for the sanitizer.

## Risks and trade-offs

- `--check` becomes slower: one hash walk of the source plus one per agent mirror. The payload
  is small (tens of MB); acceptable, and the walk reuses the parity loop's exclusions.
- Stamp churn: every toolkit upgrade changes a tracked file. Intended — it is the pin.
- Hash mismatch from platform differences (CRLF checkouts, symlink-less filesystems) would
  report false drift. Mitigation: hash file bytes as copied by `mirror_tree`, document the
  limitation, and keep the message actionable (re-run install from the pinned commit).
- Sanitizer coverage is pattern-based; the allowlist and the transcript-mined exclusion are
  the primary privacy controls, the sanitizer is defence in depth.
- Adding `session-log` as a dependency of `improve-harness` increases the installed closure
  for consumers who only want reports; both skills are already portable.

## Open questions

- Should a future `install.sh --stamp-only` refresh the stamp without re-syncing, for teams
  that install via a different mechanism? Deferred; not needed for the acceptance outcomes.
- Should consumer CI templates (`session-bootstrap`) call `--check`? Deferred to the
  non-goals above; revisit after one team adopts the stamp.
