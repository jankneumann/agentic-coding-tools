# Extract shared review-findings schema

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `extract-shared-review-findings-schema`
> Effort: M
> Priority: 3

## Summary

Extract the review findings schema — today inlined as a JSON string in `agent-coordinator/agents.yaml` for grok's `--json-schema` arg while `review_dispatcher.py` and `consensus_synthesizer.py` carry parallel expectations — into one canonical schema file referenced by all three, with the adapter inlining it at dispatch time.

## Dependencies

- None

## Acceptance Outcomes

- One canonical schema file exists; agents.yaml references it and the adapter inlines it at dispatch time.
- review_dispatcher.py and consensus_synthesizer.py validate findings against the same schema file.
- A deliberately drifted finding fails validation loudly instead of merging silently into consensus, covered by a test.

## Rationale

Schema drift between a vendor adapter and the consensus layer reproduces the silent-false-consensus failure class already hit once (pi --no-tools); one canonical file eliminates the drift surface.
