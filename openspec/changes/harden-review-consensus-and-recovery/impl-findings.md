# Implementation refinement findings

## Iteration 1

| # | Type | Criticality | Description | Proposed Fix | Status |
|---|---|---|---|---|---|
| 1 | resilience | high | SDK review dispatch could return success after silently dropping a requested thinking setting because the SDK transport has no portable thinking parameter. | Fail closed with a configuration attempt before the SDK call. | fixed |
| 2 | correctness | high | Convergence checkpointing counted `ReviewResult.success` directly and discarded logical attempt chains, allowing an ineligible malformed result to satisfy quorum. | Preserve attempt-chain evidence and use the shared eligibility predicate when available. | fixed |

No remaining findings at or above the medium threshold were identified in this iteration.

## Iteration 2

| # | Type | Criticality | Description | Proposed Fix | Status |
|---|---|---|---|---|---|
| 1 | compatibility | critical | Copied skill installs resolved the review findings schema through the wrong parent and imported coordinator internals directly. | Discover repository schema portably and resolve routing through the public coordinator bridge with static fallback. | fixed |
| 2 | resilience | critical | Review attempts could retain raw provider diagnostics, accept invalid chains, and allow a synchronous invoke to run past its logical deadline. | Sanitize all diagnostics, validate the frozen chain schema and automaton, and isolate invokes behind the remaining monotonic deadline. | fixed |
| 3 | observability | critical | CLI dispatch waited for all vendors before persisting terminal evidence. | Checkpoint each terminal slot atomically before dispatching the next reviewer. | fixed |
| 4 | correctness | critical | Convergence admitted success-only results and consensus matching/identity/producer validation were incomplete. | Require valid logical eligibility, enforce all revision-2 aliases, support structured cross-family location matches, stabilize fingerprints, and validate before atomic writes. | fixed |
