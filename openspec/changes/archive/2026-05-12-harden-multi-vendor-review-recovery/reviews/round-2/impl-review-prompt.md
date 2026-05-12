# IMPL_REVIEW — harden-multi-vendor-review-recovery (Round 2)

You are reviewing **round 2** of the implementation review. Round 1 found
7 consensus findings; the conductor applied 5 targeted fix commits.
Your job in round 2 is to:

1. **Verify** the round-1 findings are actually resolved (not just
   superficially patched).
2. **Find new issues** introduced BY the fixes themselves (regressions,
   new edge cases, semantics changes).
3. **Report only what's new or unresolved** — do not re-raise round-1
   findings unless you believe the fix is incomplete or wrong.

## Working tree

- cwd: repo root of `agentic-coding-tools`
  (worktree `.git-worktrees/harden-multi-vendor-review-recovery/`)
- branch: `openspec/harden-multi-vendor-review-recovery`
- HEAD: latest (8 commits ahead of round-1 dispatch)
- diff range you should examine for round 2: `21acdf3..HEAD`
  (6 fix commits + the loop-state update)

## Round-1 findings and the fixes applied

| ID | Round-1 issue | Fix commit | Verify |
|----|---------------|------------|--------|
| **C1** | `read_manifest`/`read_vendor_findings` did not validate `schema_version` despite contract MUST. | `1f97a60` | Read raises `ValueError` on `version != MANIFEST_SCHEMA_VERSION`. Tests at `skills/tests/parallel-infrastructure/test_checkpoint_findings.py` cover v0/v2/missing/v999. |
| **C2** | Spec says checkpoint path is `<artifacts_dir>/.review-cache/` but code wrote to `<artifacts_dir>/reviews/round-N/`. | `84cbdbb` | `convergence_loop.py:264` now uses `.review-cache/round-{N}/`. Docstring + `docs/parallel-agentic-development.md` updated. Tests updated to match. |
| **C3** | `ReviewOrchestrator.write_manifest()` shim silently ignored `output_path.name`. | `0b2f666` | Now raises `ValueError` if `output_path.name != "review-manifest.json"`. New test `test_write_manifest_rejects_non_canonical_filename`. |
| **C4** | `checkpoint_findings.write_manifest` only validated `vendors[].name`, not `findings_path` / `finding_count`. | `0b2f666` | Both now validated at write time mirroring read-side. New tests cover separator, traversal, non-string, non-int finding_count. |
| **C5** | `convergence_loop.py` omitted `quorum_requested` and `quorum_received` kwargs to `cf_write_manifest`, so a 3-of-3 dispatch with 1 failure recorded `quorum_requested=2` instead of 3. | `e637007` | Now passes `quorum_requested=len(results)` and `quorum_received=sum(... if r.success)` explicitly. New test exercises 3-vendor dispatch with 1 failed vendor. |
| **C6** | `_atomic_write_json` parent-dir `os.fsync(dirfd)` is POSIX-only; would crash on Windows or some macOS filesystems. | `1468358` | Both `os.open(parent)` and `os.fsync(fd)` wrapped in `try/except OSError` that downgrades to no-op. The file-level fsync remains load-bearing. New tests simulate dir-fsync EINVAL and dir-open failure. |
| **C7** | `<path>.tmp` residue leaked when json.dump/flush/file-fsync raised mid-write. | `1468358` | Inner write wrapped in `try/except (OSError, ValueError)` that calls `tmp.unlink(missing_ok=True)` before re-raising. New test exercises mid-write failure cleanup. |

## Files to read before reporting

The 5 fix commits touched these files:
- `skills/parallel-infrastructure/scripts/checkpoint_findings.py`
- `skills/parallel-infrastructure/scripts/review_dispatcher.py`
- `skills/autopilot/scripts/convergence_loop.py`
- `skills/tests/parallel-infrastructure/test_checkpoint_findings.py`
- `skills/tests/parallel-infrastructure/test_review_dispatcher_migration.py`
- `skills/tests/autopilot/test_convergence_checkpoint.py`
- `skills/tests/autopilot/test_convergence_durability_integration.py`
- `docs/parallel-agentic-development.md` (paragraph at line 558-560)

To inspect: `git show 1f97a60`, `git show 84cbdbb`, `git show 0b2f666`,
`git show e637007`, `git show 1468358`.

## What to look for

For each round-1 finding above:
- Is the fix complete? Or does it patch the symptom but leave a gap?
- Are the new tests strong (real failure modes) or vacuous (always pass)?
- Did the fix introduce a new edge case that wasn't there before?

For potential **regressions** introduced by the fixes:
- The path change `reviews/round-{N}/` → `.review-cache/round-{N}/` —
  any tooling, glob, or doc still pointing at the old path?
- The `output_path.name` guard in `write_manifest` — does any caller
  in the wider codebase still pass a custom filename and now break?
- The `tmp.unlink(missing_ok=True)` in `_atomic_write_json` — does
  Python 3.10+ guarantee `missing_ok=True` semantics across all
  filesystems? Could the unlink itself raise unexpectedly?
- The schema_version reject — what happens if a manifest was written
  by an older version of `review_dispatcher.py` (pre-proposal)? Is
  there a migration path, or does the system just refuse forever?

Look for **incomplete fixes** — a common review failure mode is
"patched the test but not the bug" or vice versa.

## Output format

Return STRICT JSON:

```json
{
  "findings": [
    {
      "id": "F1",
      "type": "security|correctness|robustness|spec_gap|style|test_gap|regression",
      "criticality": "low|medium|high|critical",
      "description": "Concrete; cite file:line and the round-1 finding ID being verified (or 'new' for novel issues).",
      "disposition": "fix|accept|escalate|regenerate",
      "file_path": "path/to/file.py",
      "line_range": "12-34",
      "verifies_round_1": "C1|C2|C3|C4|C5|C6|C7|new"
    }
  ]
}
```

If round-1 fixes are correct AND no new issues exist, return
`{"findings": []}`. **Do not pad with low-criticality re-statements of
round-1 findings.** A clean return signals convergence.
