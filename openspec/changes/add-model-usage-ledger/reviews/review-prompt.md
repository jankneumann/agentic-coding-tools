Review the OpenSpec plan artifacts in openspec/changes/add-model-usage-ledger/.

Read proposal.md, design.md, tasks.md, work-packages.yaml, all specs/*/spec.md, and everything
under contracts/ (openapi/v1.yaml, db/schema.sql, events/*.schema.json).

This plan adds an end-to-end model usage ledger: a dispatch record per autopilot phase, usage
records per vendor API call with token counts and cost, and /usage/* reporting routes that join
them on (session_id, agent_id).

A prior iteration already fixed the following. Do NOT re-report them. DO report anything they
missed, and especially any CONTRADICTION or INCOMPLETENESS the fixes themselves introduced —
a field required in one contract but absent from the one that would have to supply it is the
highest-value thing you can find here:
- all /usage/* routes now require the API key and are principal-scoped
- principal is server-derived from the API key, readOnly on ingest
- record_hash is recomputed server-side and mismatches rejected
- record_kind (dispatched|state_only) excludes state-only phases from mismatch accounting
- agent_id is patched on the adapter return path, not in build_phase_dispatch_kwargs
- non-Claude vendors store their own session id in agent_id
- orchestrator-session usage gets a session_overhead bucket
- phase enum equals agents_config.NON_TERMINAL_PHASES (GATEKEEPER in, REVIEW_PANEL out)
- DispatchRecordUpsert split into DispatchRecordCreate and DispatchRecordPatch
- priced rows require estimated IS TRUE
- limit/cursor on the aggregate routes
- migration renumbered to 037

Focus on: contract consistency across openapi/v1.yaml, db/schema.sql and events/*.schema.json;
whether every field one contract requires can actually be supplied by whatever produces it;
specification completeness; security; and work-package validity.

Output ONLY valid JSON conforming to review-findings.schema.json.
