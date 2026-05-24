# Plan Findings: harness-engineering-features

## Iteration 1 (threshold: medium)

Merged from self-analysis + independent adversarial review.

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 1 | consistency | critical | D9 self-contradiction: design.md mandates LLM classifier "NOT regex/threshold", but wp-coordinator-extensions description + component diagram (design.md:151) still say "pattern matcher". | Rewrite wp description; fix diagram. |
| 2 | traceability | high | Task 2.6 files (`audit_triage.py`, `audit_triage_prompts/**`, `pyproject.toml`) absent from wp-coordinator-extensions `write_allow` → scope checker blocks implementer. | Add the three paths to write_allow + locks. |
| 3 | security | critical | Raw transcripts under `docs/transcripts/` are not git-ignored and sanitization only ordered before-LLM, not before-disk-write → unsanitized JSONL can be committed. | Add `docs/transcripts/` to .gitignore; require sanitize-before-disk in spec; add verification. |
| 4 | security | high | Sanitizer gaps for transcript payloads: bare secrets in tool_result blobs, missing `AIza`/`sk-proj`/`sk-svcacct`/JWT/`Authorization:` patterns. Task 6.8 vague ("add coverage"). | Enumerate required detectors + fixture-based recall test. |
| 5 | testability | high | No measurable recall criteria for the two LLM classifiers despite D9 declaring "recall is the controlling metric". "Single-shot struggle classification" undefined. | Define struggle-class enum; add labeled fixture corpus + recall floor to spec + wp verification. |
| 6 | traceability | medium | "Report-to-feature pipeline" scenario (spec) + Feature 4 "companion skill" have no implementing task. Orphan requirement. | Add task 5.7 building proposal-from-finding. |
| 7 | consistency | medium | `suggested_improvement` required in spec schema + report scenario but absent from D4 canonical schema and task 1.4. | Add to D4 + task 1.4. |
| 8 | clarity/feasibility | medium | Task 6.9 leaves "import agents_config OR call HTTP" unresolved. Existing skills (implement-feature, fix-scrub) use direct import. | Resolve to direct import matching precedent; HTTP fallback only. |
| 9 | consistency | medium | D11 claims transcript prompts emit `prompt_version:N` but D8 spec scenarios + tasks 6.9/6.10 don't require it. | Add prompt_version to transcript-mined findings (spec + tasks). |
| 10 | completeness | medium | D4 `source` tag: default behavior when a manual `remember` omits it is unspecified. | Spec: default `source:self-reported` when omitted. |
| 11 | consistency | low | Proposal says "seven features"; ships nine. | Update count. |
| 12 | consistency | low | D2 states CLAUDE.md "~130 lines"; actual 158. Hard gate is 120 (work-packages). | Correct baseline. |
| 13 | completeness | low | No edge-case scenario for transcript adapter schema-version drift (newer than pinned). | Add fail-soft-on-unsupported-version scenario. |
| 14 | assumptions | low | D9 ring buffer is in-memory → ephemeral on coordinator restart (un-drained entries lost). Unstated. | Add design trade-off note (acceptable for best-effort signal). |
| 15 | traceability | low (deferred) | `harness-engineering.N` scenario refs are positional/unstable and will rot. | Repo-wide convention — deferred; not changing unilaterally for one proposal. |

**Resolution:** Fix #1–#14 in iteration 1 (all medium+ plus cheap lows). #15 deferred (repo-wide convention; changing it here would create inconsistency with other proposals).
