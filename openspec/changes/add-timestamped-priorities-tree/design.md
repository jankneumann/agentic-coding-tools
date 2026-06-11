# Design — add-timestamped-priorities-tree

## Context

The `/prioritize-proposals` skill currently writes a single overwriting report at `openspec/changes/prioritized-proposals.md` (and a matching `.json` on `--format json`). The location is semantically wrong (the path is under `openspec/changes/` but the file is not a change), and the single-overwriting-file pattern erases the evolution of priorities across runs. See `proposal.md` for the full motivation and the three approaches considered (dated dirs + flat latest **[selected]**, append-only JSONL, status quo).

## Key Decisions

### D1: Directory layout mirrors `openspec/changes/archive/`

`openspec/priorities/<YYYY-MM-DD>-HHMMSS-<short-git-sha>/` — per-run subdirectory, multi-file. **Why:** matches the existing OpenSpec archive idiom (operators already understand "dated directory per artifact"), naturally accommodates multiple files per run (md + json + future siblings), and makes side-by-side comparison a `diff <dir-A>/report.md <dir-B>/report.md`.

**Rejected alternative**: Codeviz's `<artifact-dir>/<YYYY-MM-DD>/<run-id>.json` pattern (date as folder, run-id as filename). Optimized for single-file events; doesn't fit multi-file output without either nesting (`<date>/<run-id>/`) or filename suffixes (`<run-id>.report.md` + `<run-id>.report.json`). The user's brief and the openspec archive convention both favor a per-run directory.

### D2: Run-id format is `HHMMSS-<short-git-sha>`

Example: `143052-a93fe59`. **Why:** sortable lexically within a day (so `ls openspec/priorities/` is chronological), ties each run to the commit it analyzed (so a reviewer can reproduce the priority calculation by checking out `a93fe59`), human-recognizable, and collision-resistant in practice (two runs would need to start in the same second AND analyze the same commit).

**Rejected alternatives**:
- 8-char UUID suffix — opaque, no commit-context tie-in.
- Sequential counter per day — requires a coordinated counter (stat the dir or call coordinator), race-y under parallel invocation.
- Just `HHMMSS` — loses the commit-context tie-in, and a hook-driven double-fire in the same second would collide.

### D3: `latest.md` / `latest.json` are rewritten flat files, not symlinks

**Why:** cross-platform (Windows, archive tarballs, GitHub web-UI downloads, CI runners that fight symlinks), clean `git diff` shows what changed since last run, no symlink-resolution gotchas, no `git config core.symlinks` foot-gun. The duplication cost (~5 KB per run for the flat copy) is negligible against the bound of one copy at all times.

**Rejected**: symlinks (Posix-only, surprising in archives, sometimes filtered by CI checkout actions). Hybrid (symlink + fallback file) would create two ways to be wrong.

### D4: Mandatory artifact header on `report.json` matches the codeviz event-artifact schema

```json
{
  "_header": {
    "schema_version": 1,
    "generated_at": "2026-06-10T14:30:52Z",
    "git_sha": "a93fe59a8b1c2d3e4f5...",
    "generator": "prioritize-proposals@1.0",
    "run_id": "2026-06-10-143052-a93fe59",
    "event_kind": "priorities-report"
  },
  "report": { ... existing report body ... }
}
```

**Why:** forward-compatible with the codeviz `skills/shared/artifact_header.py` helper (roadmap-planned). When that helper lands, this skill migrates without an on-disk schema change. The `event_kind` value `"priorities-report"` slots cleanly into the codeviz event-artifact registry. `git_sha` carries the full 40-char hash for cryptographic stability; the short SHA used in the directory name is purely for human readability.

**Why inline now** (not waiting for the codeviz helper): the helper is in a roadmap, not a current change. Inlining is ~10 LOC; migrating later is trivial because the on-disk schema is identical.

### D5: Retention scans run after each successful write, archive (not delete)

Per-run flow: write dated artifact directory → write `latest.{md,json}` → enumerate `openspec/priorities/*/` (excluding `archive/`, `latest.md`, `latest.json`) → if count > N, move oldest to `openspec/priorities/archive/`. **Why archive vs. delete:** the user's selection at Gate 1 (A2). Archived runs preserve the audit trail and let future analyses ("what was the priority during the Q1 push?") still work. Sustained growth is ~5 KB × 365 ≈ 2 MB/year — negligible.

**Threshold default 30**: chosen because it's roughly one month of one-run-per-day cadence. Configurable via `--retain N` flag.

### D6: Legacy file migration is a one-time task with a header allowance

`openspec/changes/prioritized-proposals.md` (dated 2026-05-04) is moved to `openspec/priorities/2026-05-04-legacy/report.md` as the first historical entry. The directory name uses the literal suffix `-legacy` (no `HHMMSS-<short-git-sha>` because the original write time isn't recoverable). The accompanying `report.json` (if it exists) does NOT get the new mandatory header retrofitted — instead, the spec carves out a pre-migration allowance that whitelists the literal directory name `2026-05-04-legacy` in any future header-presence check.

**Why this carve-out**: retrofitting a header to a legacy artifact would either (a) lie about `generated_at` (we'd put the migration date, not the original) or (b) require historical recovery that isn't worth the effort. The whitelist is 1 line of code and ages out naturally (the legacy entry rolls into archive once 30 newer runs accumulate).

## Component Interactions

```
/prioritize-proposals
        │
        │ 1. compute analysis (unchanged)
        │ 2. compute run_id = f"{utc_now:%Y-%m-%d-%H%M%S}-{head_sha[:7]}"
        │ 3. dated_dir = openspec/priorities/{run_id}/
        │ 4. write dated_dir/report.md
        │ 5. if --format json: write dated_dir/report.json with _header block
        │ 6. write openspec/priorities/latest.md (copy of report.md)
        │ 7. if --format json: write openspec/priorities/latest.json (copy of report.json)
        │ 8. retention scan: list openspec/priorities/{date}-*/ entries
        │    - if count > N (default 30): move oldest to openspec/priorities/archive/
        ▼
git tracks both: dated dirs (accumulating audit trail) + latest files (rewritten each run)
```

## Open Questions

None at planning stage. Two were resolved at Gate 1 (retention behavior → A2; legacy migration → B2); the rest were specified in the brief or have obvious defaults.

## Task-title "and" audit

The plan-feature skill's "and splitting heuristic" flags task titles containing the word "and." After audit, the following task-line "and"s in `tasks.md` are **intentional non-splits**:

| Task | "and" usage | Why not split |
|---|---|---|
| 2.4 | "the live spec, and the delta in this change folder will be applied to it" | Prose comma-substitute inside a single sentence describing one outcome (spec sync verification). |
| 2.5 | "verify the migration target file exists and the source is gone" | Checkpoint task; both checks verify a single migration outcome (success = target present, source absent). |
| 2.5 | Same pattern | Same. |
| 3.1 | "verify ... and matches" | Three smoke verifications of one outcome (dated-artifact write correctness). Splitting would force three end-to-end runs to cover one feature behavior. |
| 3.2 | "verify ... and is byte-identical" | Single-run verification of `--format json` write behavior. |
| 3.3 | "verify exactly 30 remain and one was moved to archive" | Single-run verification of one retention behavior; pre/post-conditions of one operation. |
| 3.4 | "regenerate `.claude/skills/...` and `.agents/skills/...`" | One `install.sh` invocation regenerates both mirrors as side effects of one command. |

Task 1.2 ("run-id and path construction") was the only borderline case and was split into 1.2a / 1.2b.
