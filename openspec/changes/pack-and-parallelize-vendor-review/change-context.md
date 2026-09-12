# Change Context: pack-and-parallelize-vendor-review

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md — Review Packet As Default Input | Packet contains schema contract, diff or empty-diff marker, spec excerpts, optional ledger | contracts/review-packet.schema.json | D1 | skills/parallel-infrastructure/scripts/review_packet.py, skills/autopilot/scripts/convergence_loop.py | test_review_packet.py, test_review_packet_schema.py | --- |
| skill-workflow.2 | specs/skill-workflow/spec.md — Missing ledger still builds a packet | Absent `.review-ledger/` still builds from diff+specs+schema | contracts/review-packet.schema.json | D1 | skills/parallel-infrastructure/scripts/review_packet.py | test_review_packet.py, test_review_packet_dispatch.py | --- |
| skill-workflow.3 | specs/skill-workflow/spec.md — Over-budget packet sets tools overflow | Over 320k chars sets tools_overflow and allows Read/Grep | contracts/review-packet.schema.json | D1 | skills/parallel-infrastructure/scripts/review_packet.py | test_review_packet.py | --- |
| skill-workflow.4 | specs/skill-workflow/spec.md — Parallel Review Dispatch | Concurrent subprocesses; wall clock is max not sum | --- | D2, D4 | skills/parallel-infrastructure/scripts/review_dispatcher.py | test_review_dispatcher.py -k concurrent | --- |
| skill-workflow.5 | specs/skill-workflow/spec.md — Sequential dispatch is a bug | Two 2s stubs finish under 3s | --- | D4 | skills/parallel-infrastructure/scripts/review_dispatcher.py | test_concurrent_stub_vendors_overlap_under_three_seconds | --- |
| skill-workflow.6 | specs/skill-workflow/spec.md — Verify-Then-Wire Structured Output | Wire JSON-schema flags only for verified probe rows | contracts/vendor-structured-output.md | D3 | agent-coordinator/agents.yaml, contracts/vendor-structured-output.md | existing grok schema tests | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 Packet contents and budget | Timeouts are a repo-walk symptom | review_packet.py + converge() writes packet before dispatch | Explicit artifacts, no semantic-context flag |
| D2 Concurrent dispatch, read-only cwd | Spec already SHALL parallel | Thread pool in dispatch_and_wait; async submit-then-poll | Shared cwd; snapshot fallback on git-lock |
| D3 Verify-then-wire | Do not guess CLI flags | Probe table; wire claude/agy `--json-schema`; leave Codex/pi | Empirical help+parse, not Grok flag copy |
| D4 Fake-CLI overlap test | Live p50 is not CI | Two 2s stubs <3s | D4 fitness function |
| D5 No new result-path regex | Keep ReviewResult | Concurrent collect still uses ReviewResult | dg-02 owns async poll regex |

## Coverage Summary

- Packet schema + builder tests, converge packet prompt, concurrent overlap, async submit-then-poll, git-lock snapshot retry, packet-plus-concurrency fixture
- Live 4-vendor p50 is deferred to validation evidence (D4)
