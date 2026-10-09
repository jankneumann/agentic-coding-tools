# Stamp and check team toolkit consistency

> Parent roadmap: `multiplayer-collaboration` (item `ri-20`)
> Change ID: `toolkit-consistency`
> Effort: M
> Priority: 5

## Why

This toolkit is dogfooded by one developer and installed into team repositories with
`skills/install.sh`. Nothing records *which* toolkit payload a consumer repository was
installed from. `install.sh --check` already exists, but it only compares the installed
mirrors (`.claude/skills/`, `.agents/skills/`) against whatever source checkout the person
who runs it happens to have: two teammates on different toolkit commits both pass `--check`
while their agents run different skills. Team behaviour then diverges silently, and the
divergence is discovered as "it works on my machine" rather than as a reported drift.

Learning has the same shape. `improve-harness` reads capability-gap signals from the
coordinator's episodic memory, which is scoped to the developer's own agents and coordinator
principal. A lesson one developer's sessions learn never reaches a teammate's agents unless
it is hand-copied. Roadmap principle P9 (every action traceable, every intervention a signal)
needs a pinned, checkable install so improvements reach every teammate, and an opt-in way to
share learnings without sharing private session transcripts.

## What Changes

1. **Install stamp.** After a successful sync into a consumer repository, `install.sh`
   writes `.agentic-toolkit/stamp.json` under the target root: toolkit version (`VERSION`),
   source commit, deterministic payload hash, timestamp, agents and mode. The stamp is the
   pin: committing it declares the toolkit payload the repository expects. A self-install
   (target root is this repository) does not write a stamp; `--check` never writes one.
2. **Deterministic payload hash.** A dependency-free helper, `skills/shared/payload_hash.py`,
   hashes the installed file set (every portable skill directory, every shared library,
   `install-manifest.json`; `tests/`, `__pycache__/`, `node_modules/` excluded) so the same
   value is produced from the source tree and from a freshly synced mirror. It ships inside
   `shared/`, so it is available in consumer layouts and must pass the existing
   Cross-Repo Portability gate.
3. **Drift check.** `install.sh --check` keeps its current mirror-parity check and adds a
   stamp comparison when a stamp is present: pinned hash vs the source checkout (checkout
   drift: "your toolkit checkout is not the pinned version") and pinned hash vs each
   installed mirror (runtime drift: "your installed copies are not the pinned payload").
   Each drift kind has its own message and exits `1`. An absent stamp is reported as
   "unpinned" and does not fail; an unreadable or schema-invalid stamp fails loud.
4. **Opt-in repository-scoped learnings.** A human-owned config file,
   `.agentic-toolkit/config.json`, carries `shared_learnings.enabled`. When enabled,
   `improve-harness` gains `export_shared_learnings.py`, which projects capability-gap
   entries from episodic memory into a tracked `.agentic-toolkit/learnings.jsonl` using an
   allowlist of fields (`event_type`, `summary`, `outcome`, `lessons`, `tags`, `created_at`),
   drops `details`, `agent_id` and `session_id`, keeps only the gap-schema tags
   (`failure_type:`, `capability_gap:`, `affected_skill:`, `severity:`, `source:`), excludes
   every entry tagged `source:transcript-mined`, and passes exported text through the
   session-log secret sanitizer. `analyze_failures.py` merges the shared file into its
   analysis, deduplicating on `(capability_gap, affected_skill, summary)`, tagging merged
   entries `origin:shared-repo`, and never writes them back into episodic memory. The file is
   a one-way projection of the existing learning store, not a second store.
5. **State-artifact registration.** `docs/guides/state-artifacts.md` gains rows for the
   stamp, the config and the learnings projection with canonical writer, authority, consumers
   and missing/stale behaviour. `docs/guides/skills.md` documents the stamp, the extended
   `--check` and the opt-in.

### Non-goals

- A source-free checker: `--check` keeps running from the toolkit checkout's `install.sh`,
  as today. Shipping an installed checker is a follow-up if teams ask for it.
- Automatic re-install or auto-update when drift is reported; `--check` reports, humans act.
- Enforcing the drift check in consumer CI. The exit code makes that possible; wiring it is
  the consumer's decision.
- Sharing learnings through the coordinator (team-scoped episodic memory, new memory layers,
  new endpoints). The `closed-loop-learning` roadmap owns recall and earned-delegation.
- Any change to the roadmap learnings loop (`openspec/roadmaps/<id>/learnings/`), which is
  already repository-scoped and tracked.
- Pinning Python tool versions, OpenSpec CLI versions or per-skill dependency hooks.

## Impact

- **Specs**: new capability `toolkit-distribution` (ADDED requirements: install stamp,
  payload hash, drift check, shared-learnings opt-in, exported-learning privacy, one-way
  consumption, state-artifact registration). No existing requirement is modified;
  `skill-workflow` / Cross-Repo Portability and Canonical Skill Distribution act as
  constraints every new file must satisfy.
- **Code**: `skills/install.sh` (stamp writing, `--check` extension, usage text);
  `skills/shared/payload_hash.py` (new); `skills/improve-harness/scripts/export_shared_learnings.py`
  (new); `skills/improve-harness/scripts/analyze_failures.py` (merge shared learnings);
  `skills/improve-harness/SKILL.md`; `skills/install-manifest.json` (smoke entrypoints for
  the two new scripts, `session-log` added to `improve-harness` cross-skill dependencies).
- **Docs**: `docs/guides/state-artifacts.md`, `docs/guides/skills.md`.
- **Tests**: `skills/tests/install_sh/test_payload_hash.py`, `test_install_stamp.py`,
  `test_install_check_drift.py`; `skills/tests/improve-harness/test_export_shared_learnings.py`,
  `test_shared_learnings_merge.py`; a guard test that the three new artifacts are registered
  in `docs/guides/state-artifacts.md`.
- **Consumers**: repositories that commit `.agentic-toolkit/stamp.json` get a working drift
  check; repositories that never run the new installer see no change (`--check` reports
  "unpinned" and keeps its existing behaviour). CI in this repository is unaffected: the
  self-install path writes no stamp and the existing `--check` step keeps passing.
- **Roadmap acceptance outcome 4** ("installed payloads contain no references to private
  coordinator source") is already enforced by `skills/shared/validate_install_manifest.py`
  and `skills/tests/install_sh/test_consumer_portability.py`; this change adds no new
  requirement for it and instead requires its new files to pass that existing gate.

## Decisions needing approval

Surfaced here because this iteration ran non-interactively (see `design.md` for the
alternatives considered on each):

- D1: new capability `toolkit-distribution` rather than appending to `skill-workflow`.
- D2: stamp, config and learnings live under a tracked `.agentic-toolkit/` directory at the
  consumer root, independent of the agent mirror directories.
- D8: exported learnings are JSONL and exclude `source:transcript-mined` entries outright,
  rather than including their summaries behind a flag.
