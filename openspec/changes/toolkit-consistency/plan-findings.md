# Plan Findings

> Change ID: `toolkit-consistency`

## Iteration 1 — 2026-10-05T07:15Z

Baseline: `openspec validate toolkit-consistency --strict` passed on the roadmap scaffold, so no
validation failures seeded this iteration. Analysis ran sequentially (scaffold had 5
placeholder tasks and 1 spec delta, below the parallel-dispatch threshold).

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | testability | critical | All four scaffold scenarios were circular (`WHEN toolkit-consistency is implemented THEN <acceptance outcome>`); nothing was verifiable. | Replaced with 7 requirements and 25 concrete WHEN/THEN scenarios in `specs/toolkit-distribution/spec.md`, each with success and failure/edge paths. |
| 2 | completeness | critical | `proposal.md` lacked Why / What Changes / Impact; `tasks.md` had five generic placeholder tasks traceable to no requirement. | Rewrote `proposal.md` with the required sections and non-goals; rewrote `tasks.md` as 7 requirement-traced, single-commit tasks with file scopes and dependencies. |
| 3 | consistency | high | Spec delta sat under the placeholder capability `multiplayer-collaboration`, which has no spec; the real owner of install/portability requirements is `skill-workflow` (Cross-Repo Portability, Canonical Skill Distribution). | Decided D1: new capability `toolkit-distribution`; existing `skill-workflow` requirements referenced as constraints, not modified. Flagged for human approval in `proposal.md`. |
| 4 | clarity | high | Roadmap text says "add `install.sh --check`", but `--check` already exists (mirror parity vs source). The scaffold did not say what changes about it, which could be implemented as a parallel checker or a rewrite. | Proposal and Drift check requirement now say the existing check is kept unchanged and the stamp comparison is additive (D7), with distinct checkout-drift and runtime-drift messages. |
| 5 | assumptions | high | Where the "tracked file" lives and what it contains was undecided (per-agent dir vs `openspec/` vs root). Mirror dirs are often gitignored, so a per-agent stamp would not be tracked. | Decided D2/D3: `.agentic-toolkit/stamp.json` at the consumer root, the stamp *is* the pin. Could not use AskUserQuestion (non-interactive sub-agent); recorded as a decision needing approval in `proposal.md` and `design.md`. |
| 6 | assumptions | high | "Repository-scoped learnings" had no store, writer, format or consumer; the roadmap forbids a parallel learning store. | Decided D8/D9: one-way JSONL projection from episodic memory written by `improve-harness`, consumed by `analyze_failures.py`, never written back; explicit human-owned `config.json` opt-in. Flagged for approval. |
| 7 | completeness | high | No failure or edge scenarios: aborted install, invalid stamp, unpinned repo, self-install, disabled opt-in, transcript-mined entries, secrets in lessons. | Added a scenario for each under the corresponding requirement. |
| 8 | scope | medium | Acceptance outcome 4 (no private coordinator source in payloads) is already enforced by `validate_install_manifest.py` and `test_consumer_portability.py`; re-stating it would duplicate `skill-workflow` Cross-Repo Portability. | Treated as a regression constraint: portability scenarios under Payload hash and Exported learning privacy; T7 runs the existing gate. Noted in Impact. |
| 9 | feasibility | medium | "Payload hash" was unspecified; a non-deterministic or subset hash would give false drift or miss installed files. | D4 fixes the algorithm (installed file set, excludes, sorted `relpath\0sha256\n`, follows symlinks) and places the helper in `shared/` so it is portable. |
| 10 | scope | medium | No non-goals; the item could grow into auto-update, consumer CI enforcement or coordinator team memory. | Added Non-goals to `proposal.md`; coordinator-side sharing explicitly deferred to `closed-loop-learning`. |
| 11 | completeness | medium | Acceptance outcome 1 requires registration in `docs/guides/state-artifacts.md`; nothing planned it or defined writer/authority/missing-stale behaviour. | Added the State-artifact registration requirement, task T6 and a guard test; D6–D8 define the behaviours. |
| 12 | security | medium | Exported learnings could carry transcript excerpts (memory `details`), identities (`agent_id`, `session_id`) or secrets. | Exported learning privacy requirement: field allowlist, transcript-mined exclusion, session-log sanitizer, deterministic output. |
| 13 | parallelizability | medium | Placeholder tasks had no dependencies or file scopes; `install.sh` and `install-manifest.json` would be touched by several tasks. | Tasks now carry Files/Depends on; `install.sh` edits sequenced T2→T3; manifest edits owned solely by T7. |
| 14 | consistency | medium | Self-install (this repository, CI `install.sh --check` step) would churn a tracked stamp on every sync and could break CI. | D6: self-install writes no stamp and skips the stamp comparison; Impact notes CI is unaffected. |
| 15 | assumptions | low | Which version string is "the toolkit version" (`VERSION` 0.2.0 vs `skills/pyproject.toml` 0.2.0). | D5: `VERSION` + `source_commit`; informational only, hash decides drift. |
| 16 | clarity | low | Scaffold design.md open questions (capability, non-goals, decisions to record) were unanswered. | All three answered in `design.md` (D1, Non-goals, D1–D9). |

### Parallelizability assessment

- Independent tasks at start: 3 (T1, T4, T6)
- Sequential chains: T1→T2→T3; T4→T5; {T1, T4}→T7
- Max parallel width: 3
- File-overlap conflicts: `skills/install.sh` (T2, T3 — sequenced), `skills/install-manifest.json` (T7 only); none between independent tasks

### Deferred / out of scope

- Source-free installed checker, auto re-install, consumer CI wiring, coordinator team memory — recorded as non-goals; new proposals if wanted.

### Termination

Remaining findings after fixes: none at or above `medium`. Findings 15–16 (low) were fixed opportunistically. Iteration 2 not required; `openspec validate --strict` passes.
