# Change Context: phase-record-compaction

<!-- 3-phase incremental artifact. Phase 1 written 2026-04-25 (pre-implementation). -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | Phase Record Data Model — Round-trip equality through markdown | PhaseRecord.render_markdown() then parse_markdown() round-trips equal | contracts/schemas/phase-record.schema.json | D1, D10 | --- | test_phase_record_markdown.py | --- |
| skill-workflow.2 | Phase Record Data Model — Round-trip equality through handoff payload | PhaseRecord.to_handoff_payload() then from_handoff_payload() round-trips equal | contracts/schemas/phase-record.schema.json | D1 | --- | test_phase_record_handoff.py | --- |
| skill-workflow.3 | Phase Record Data Model — Empty optional sections render compactly | Markdown rendering omits empty alternatives/trade_offs/open_questions/completed_work/relevant_files | contracts/schemas/phase-record.schema.json | D1 | --- | test_phase_record_markdown.py | --- |
| skill-workflow.4 | Phase Record Persistence Pipeline — All three steps succeed | write_both happy path: append → sanitize → coordinator success | --- | D2, D4 | --- | test_phase_record_write_both.py | --- |
| skill-workflow.5 | Phase Record Persistence Pipeline — Coordinator unavailable triggers local-file fallback | write_both falls back to JSON file when coordinator returns success=False | contracts/schemas/handoff-local-fallback.schema.json | D2, D3 | --- | test_phase_record_write_both.py | --- |
| skill-workflow.6 | Phase Record Persistence Pipeline — Sanitizer failure does not block coordinator write | write_both proceeds with unsanitized payload if sanitizer exits non-zero | --- | D2 | --- | test_phase_record_write_both.py | --- |
| skill-workflow.7 | Phase Record Persistence Pipeline — Markdown append failure does not block coordinator write | write_both still attempts coordinator write if markdown append fails | --- | D2 | --- | test_phase_record_write_both.py | --- |
| skill-workflow.8 | Phase-Boundary Skill PhaseRecord Adoption — A skill produces matching session-log and coordinator content | All 6 phase-boundary skills produce equivalent content in both session-log.md and handoff_documents | --- | D5 | --- | test_skills_integration.py | --- |
| skill-workflow.9 | Phase-Boundary Skill PhaseRecord Adoption — Legacy append_phase_entry callers continue working | Shim emits DeprecationWarning and writes through write_both | --- | D5 | --- | test_extract_session_log.py | --- |
| skill-workflow.10 | Coordinator Handoff Population at Autopilot Phase Boundaries — Handoff is populated on each defined boundary | _maybe_handoff calls handoff_fn with PhaseRecord (not string); handoff_id appended to state.handoff_ids | --- | D6 | --- | test_autopilot_handoff_dispatch.py | --- |
| skill-workflow.11 | Coordinator Handoff Population at Autopilot Phase Boundaries — Existing autopilot snapshots load without migration | Existing LoopState JSON snapshots load with last_handoff_id=None | --- | --- | --- | test_loopstate_schema.py | --- |
| skill-workflow.12 | Autopilot Phase Sub-Agent Isolation — Sub-agent return surfaces only outcome and handoff_id | Driver LoopState delta after Layer 2 phase return is bounded; transcript not consumed | --- | D6 | --- | test_phase_agent.py, test_loopstate_opacity.py | --- |
| skill-workflow.13 | Autopilot Phase Sub-Agent Isolation — IMPLEMENT runs in worktree isolation | run_phase_subagent("IMPLEMENT", ...) calls Agent with isolation="worktree" | --- | D7 | --- | test_phase_agent.py | --- |
| skill-workflow.14 | Autopilot Phase Sub-Agent Isolation — IMPL_REVIEW and VALIDATE run in shared checkout | run_phase_subagent for IMPL_REVIEW/VALIDATE does NOT use worktree isolation | --- | D7 | --- | test_phase_agent.py | --- |
| skill-workflow.15 | Phase Sub-Agent Crash Recovery — First attempt succeeds, no retry | Successful first attempt does not trigger retry | --- | D8 | --- | test_phase_agent_recovery.py | --- |
| skill-workflow.16 | Phase Sub-Agent Crash Recovery — Retry on malformed output | Driver retries up to 2 more times with same incoming PhaseRecord | --- | D8 | --- | test_phase_agent_recovery.py | --- |
| skill-workflow.17 | Phase Sub-Agent Crash Recovery — Escalation writes phase-failed handoff | After 3 attempts: write phase-failed PhaseRecord and raise PhaseEscalationError | --- | D8 | --- | test_phase_agent_recovery.py | --- |
| skill-workflow.18 | Context Window Token Instrumentation — Meter uses SDK when available | measure_context calls anthropic.messages.count_tokens when SDK importable + ANTHROPIC_API_KEY set | --- | D9 | --- | test_phase_token_meter.py | --- |
| skill-workflow.19 | Context Window Token Instrumentation — Meter falls back to proxy when SDK unavailable | Proxy formula: sum(len(json.dumps(msg)) for msg in messages) // 4 | --- | D9 | --- | test_phase_token_meter.py | --- |
| skill-workflow.20 | Context Window Token Instrumentation — Meter is disabled when env flag set | AUTOPILOT_TOKEN_PROBE=disabled returns -1, skips SDK + proxy | --- | D9 | --- | test_phase_token_meter.py | --- |
| skill-workflow.21 | PhaseRecord Markdown Round-Trip — Decision index regenerator output is unchanged | make decisions before/after byte-identical (modulo timestamps) | --- | D10 | --- | check_decisions_roundtrip.py | --- |
| skill-workflow.22 | PhaseRecord Markdown Round-Trip — Capability tag survives round-trip | Decision.capability="..." round-trips through markdown via `architectural: <capability>` span | contracts/schemas/phase-record.schema.json | D10 | --- | test_phase_record_markdown.py | --- |
| skill-workflow.23 | PhaseRecord Markdown Round-Trip — Supersedes tag survives round-trip | Decision.supersedes="<change-id>#D<n>" round-trips via `supersedes: <ref>` span | contracts/schemas/phase-record.schema.json | D10 | --- | test_phase_record_markdown.py | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | PhaseRecord lives inside the session-log skill | --- | Co-located with template + sanitizer; one module instead of three |
| D2 | write_both() best-effort, each step independent | --- | Matches existing sanitizer log-and-continue convention; avoids coupling phase boundary to coordinator availability |
| D3 | Local-file fallback at openspec/changes/<id>/handoffs/<phase>-<N>.json | --- | Matches local-first persistence pattern (proposal.md, validation reports); git-tracked |
| D4 | Three-step pipeline: markdown → sanitize → coordinator | --- | Sanitization must precede coordinator write so secrets stay local; matches SKILL.md:122-139 |
| D5 | append_phase_entry stays as deprecation-warned shim | --- | Other callers exist (merge-pull-requests, ad-hoc scripts); hard removal would break silently |
| D6 | Sub-agent return contract: (outcome: str, handoff_id: str) | --- | Driver LoopState delta is bounded; transcript discarded — core compaction mechanism |
| D7 | Worktree isolation only for IMPLEMENT | --- | Setup cost only pays off when phase mutates files; IMPL_REVIEW/VALIDATE are read-mostly |
| D8 | Crash recovery: 3 retries with same incoming handoff | --- | Phase artifacts written incrementally; re-run sees prior state. Simplest model preserving work |
| D9 | Token meter: anthropic SDK primary, proxy fallback, env-disable | --- | SDK authoritative but needs network; proxy gives offline estimate; env flag for opt-out |
| D10 | Markdown rendering preserves architectural: + supersedes: spans | --- | make decisions regenerator parses these spans unchanged; round-trip preservation maintains compatibility |

## Coverage Summary

- **Requirements traced**: 23/23 (Phase 1 complete; all spec scenarios mapped to test files)
- **Tests mapped**: 23 requirements have at least one test planned
- **Evidence collected**: 0/23 requirements have pass/fail evidence (filled during Phase 3 validation)
- **Gaps identified**: ---
- **Deferred items**: ---
