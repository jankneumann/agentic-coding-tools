# Convergence synthesis recovery

Autopilot persists each review round under
`<artifacts-dir>/.review-cache/round-N/` before consensus synthesis. If
synthesis fails, read `checkpoint_dir` from the
`convergence.synthesis_failed_with_checkpoint` log record and replay the
co-installed consensus tool:

```bash
python3 "<skill-base-dir>/../parallel-infrastructure/scripts/consensus_synthesizer.py" \
  --review-type plan \
  --target <change-id> \
  --findings <checkpoint-dir>/findings-*-plan.json \
  --output consensus.json \
  --quorum 2
```

The replay accepts `line_range` as a mapping, a string such as `97-102`, or
`null`. Inspect the generated consensus before resuming the phase. Checkpoint
durability supports postmortem and manual recovery; it does not imply an
automatic subprocess fallback.

## Fail-closed review recovery

Treat `summary.convergence_blocking_count` as the authoritative convergence
gate. A medium-or-higher actionable finding remains blocking even when it is
unmatched, and the final review round does not relax it. At exhaustion, keep
the checkpoint and escalate an inconclusive outcome rather than declaring
convergence.

Malformed or failed vendor output is not quorum evidence. Inspect its bounded,
redacted attempt chain, then verify that any corrective redispatch, model
fallback, or replacement reached a schema-valid terminal result. A valid empty
finding list may count toward quorum; a malformed, unattributable, or failed
attempt may not.
