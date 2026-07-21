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
