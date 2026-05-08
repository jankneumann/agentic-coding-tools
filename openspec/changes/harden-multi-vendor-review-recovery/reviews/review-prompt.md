# Plan Review — harden-multi-vendor-review-recovery (ROUND 2)

This is the SECOND round of multi-vendor review. The proposal was substantially revised after round 1.

## What round 1 caught

Round 1 (claude + codex + gemini) converged on a fundamental architectural flaw: the original Approach 1 was "auto-fallback to CLI subprocess on synthesis failure." All three vendors identified that the in-process synthesizer AND the CLI subprocess BOTH call `Finding.from_dict()`, so deterministic parser bugs (like the `consensus_synthesizer.py:59` `line_range` shape mismatch) cause both paths to fail identically. The fallback would log audit events about a recovery that didn't actually happen.

Plus several high-criticality compatibility issues:
- Per-vendor finding files are wrapper objects `{review_type, target, reviewer_vendor, findings: [...]}`, NOT raw arrays as the original `finding.schema.json` defined.
- The original manifest schema would have replaced rather than supersetted the existing dispatcher format.
- The original location for `checkpoint_findings.py` (under `skills/autopilot/`) created a bidirectional dependency cycle with `parallel-infrastructure`.
- Routing CLI per-vendor writes into `.review-cache/` would have silently broken existing globs in other code.

Round 1 raw findings are preserved in `reviews/round-1/`.

## What iteration 2 changed

The user chose to re-frame the proposal as "durable checkpoint + manual recovery" rather than "automatic recovery." Major changes:

- **Dropped R3** (CLI subprocess fallback) entirely. Synthesis failures now propagate to the caller; the checkpoint exists for manual recovery only.
- **Dropped --findings-dir CLI extension** — no subprocess fallback to consume it.
- **Dropped secret sanitization** — no diagnostics to sanitize.
- **Dropped relocation** of CLI per-vendor writes into `.review-cache/`. Files stay where the dispatcher writes them today.
- **Moved `checkpoint_findings.py`** to `skills/parallel-infrastructure/scripts/` to fix dependency direction.
- **Fixed `finding.schema.json`** to be a wrapper object, matching the actual wire format.
- **Compressed**: spec went from 6 requirements / 24 scenarios to 5 / 17. LOC estimate dropped from 1190 to 780.

## Your job in round 2

You are an independent reviewer evaluating the REVISED proposal. Round 1's central concerns should be ADDRESSED — verify that. Look especially for:

1. **Architecture verification** — Does dropping automatic recovery actually fix the problem round 1 caught? Or did the rewrite introduce a new architectural issue?
2. **New issues from the rewrite** — Edits at the scope of "drop a requirement and 7 scenarios" can introduce inconsistencies. Are there spec scenarios referencing dropped concepts? Tasks pointing at non-existent requirements? Stale text in proposal.md or design.md?
3. **Wire-format correctness** — Does `contracts/finding.schema.json` actually match what `review_dispatcher.py` writes today and what `consensus_synthesizer.py` reads? Round 1 caught the original raw-array shape was wrong; verify the wrapper-object shape is right.
4. **Manifest superset correctness** — Does the new schema accept what the dispatcher will write after migration AND what existing CLI consumers will read? Look for required-field mismatches.
5. **Path safety completeness** — R5 covers vendor names and artifacts_dir. Anything else?
6. **Testability** — Every SHALL/MUST should map to a task. Find scenarios that don't.
7. **Honesty of framing** — The proposal claims "durable checkpoint for manual recovery, NOT automatic recovery." Does any text still imply automatic recovery? Are the post-merge action descriptions clear about what THIS proposal does and doesn't deliver?

## Read these artifacts

- `proposal.md` — Re-written with new framing. Look for stale language.
- `design.md` — Re-written. Decision Log D1-D6 reflects the new architecture.
- `tasks.md` — Re-written. 6 phases now (was 8); Phase 5 dropped (was CLI fallback).
- `specs/skill-workflow/spec.md` — 5 requirements, 17 scenarios.
- `contracts/README.md`, `contracts/review-cache-layout.schema.json`, `contracts/finding.schema.json`
- `work-packages.yaml` — 5 packages now (wp-cli-refactor renamed wp-cli-migrate; wp-converge-recovery renamed wp-converge-checkpoint).

ALSO read these existing files:
- `skills/autopilot/scripts/convergence_loop.py` — `converge()` function being modified.
- `skills/parallel-infrastructure/scripts/consensus_synthesizer.py` — UNCHANGED in this proposal (round 1's `--findings-dir` extension was dropped). Verify the proposal doesn't accidentally still reference modifying it.
- `skills/parallel-infrastructure/scripts/review_dispatcher.py` — manifest write logic (lines ~1180-1208).

## Output format

Output ONLY valid JSON conforming to the wire format used by `consensus_synthesizer.py`. Each file is a wrapper object:

```json
{
  "review_type": "plan",
  "target": "harden-multi-vendor-review-recovery",
  "reviewer_vendor": "<your vendor>",
  "findings": [
    {
      "id": <integer or string>,
      "type": "architecture | security | spec_gap | correctness | contract_mismatch | testability | observability | performance | resilience | compatibility | style",
      "criticality": "low | medium | high | blocking",
      "description": "1-2 sentences, specific, with file:line where applicable",
      "disposition": "fix | regenerate | accept | escalate",
      "resolution": "1 sentence proposed fix",
      "file_path": "<optional>",
      "line_range": {"start": N, "end": M},
      "vendor": "<your vendor>"
    }
  ]
}
```

If you find NO issues — emit `"findings": []`. Don't fabricate findings to fill space.
