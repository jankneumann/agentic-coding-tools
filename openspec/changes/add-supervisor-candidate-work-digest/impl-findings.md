# Implementation Findings

## Iteration 1

<!-- Date: 2026-09-11 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | bug | critical | A persisted digest journal could target arbitrary repo-relative files and recovery validated operations while mutating. | Added an operation-specific allowlist, complete preflight validation, checksum verification, and byte/operation bounds before mutation. |
| 2 | bug | high | Dry-run fresh stubs were not persisted and therefore disappeared before prepare-batch. | Added a validated in-memory stubs overlay to prepare-batch and wired the dry-run host command to pass it. |
| 3 | workflow | high | The host rank command omitted fresh-key arguments, classifying all fresh work as retained. | Threaded validated store fresh_keys into rank as a Bash argv array and pinned the workflow contract. |
| 4 | bug | high | Terminal pruning removed approved/rejected entries from durable digested-stub history. | Merge terminal history into every published mirror while excluding it from the active store and ranked digest. |
| 5 | edge-case | high | Lifecycle rebuild accepted caches with a mismatched fingerprint or singleton stub key. | Require prior-digest fingerprint, generated_at, singleton count, and exact stub key identity. |
| 6 | bug | high | The 64-KiB check measured compact JSON while stdout emitted larger default JSON; ready-set context was injected separately without the same bound. | Measure exact stdout bytes and embed ready-set data inside the one bounded manifest. |
| 7 | bug | high | Canonical change-prefixed dependencies did not resolve through the all-status index. | Normalize validated change references before change-id lookup. |
| 8 | edge-case | high | Dry-run store and stub-to-request could derive candidate output while a recovery journal was pending. | Refuse all read-only or dry-run candidate output until recovery completes. |
| 9 | performance | medium | Evidence slicing loaded the full artifact before taking the 2-KiB prefix. | Read only MAX_EVIDENCE_BYTES + 1 from a binary file handle. |
| 10 | bug | medium | A refreshed same-key candidate was silently ignored and kept its stale score cache. | Transactionally replace changed same-key payloads, invalidate their singleton cache, and report them as fresh. |

### Quality Checks

- pytest: pass   330 supervise tests
- mypy: unavailable in skills/.venv; install.sh reports the same missing optional tool
- ruff: pass
- openspec validate: pass (strict)
- work packages, DAG, overlap, context-impact, mirrors, and diff integrity: pass
- configured default skills testpaths: pass — 3,802 passed, 13 optional skips
- isolated CI topology: all feature-relevant suites pass; two Autopilot smoke tests fail only when inherited coordinator credentials violate their coordinator-unavailable precondition, and both pass with COORDINATION_API_KEY/URL unset

### Spec Drift

Updated design, supervise spec delta, tasks, prompt contract, and canonical workflow to make the dry-run overlay, bounded embedded ready set, journal authority, and fresh-key handoff explicit.

---

## Summary

- Total iterations: 1
- Total findings addressed: 10
- Remaining findings: none at or above medium
- Termination reason: threshold met
