# Resolve the collect-transcripts --enable contract: implement or amend

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `resolve-collect-transcripts-enable-contract`
> Effort: L
> Priority: 2

## Summary

Implement the --enable flag, define analyze_session_llm behind the repo's vendor routing, and make the CLIs write structured findings to episodic memory when enabled, keeping dry-run as the default. If the LLM path is deliberately deferred, amend the spec and SKILL.md instead so documentation matches the heuristic-only behaviour; the item is complete only when code and spec agree.

## Dependencies

- None

## Acceptance Outcomes

- If the implement path is chosen: collect-transcripts --enable runs end to end on a fixture transcript and writes at least one episodic memory entry with a capability_gap:* tag and source:transcript-mined (verified against a fake coordinator).
- If the implement path is chosen: analyze_session_llm is defined, unit-tested with a stubbed model client, and discards any finding that lacks a verbatim quote.
- Without --enable both CLIs remain dry-run and write nothing; a test asserts zero memory writes.
- If the amend path is chosen: the spec and SKILL.md describe heuristic-only, print-only behaviour, the unused prompt files are removed, and the RI-12 scheduling assumption in docs/proposals/repo-improvement-roadmap.md is corrected.
- openspec/specs and skills/collect-transcripts/SKILL.md describe exactly the behaviour the code implements, and GitHub issue #495 is closed.

## Rationale

Section 6 defect 4, filed as GitHub issue #495. The pipeline never calls a model and never writes memory, so the transcript emitter of the capability-gap contract does not exist. Phase 3 distillation and Phase 4 memory emission both need a working model call and write path to sit behind.
