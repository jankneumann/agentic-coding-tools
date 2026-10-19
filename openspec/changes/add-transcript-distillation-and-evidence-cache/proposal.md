# Add deterministic distillation and surface-hash evidence cache to collect-transcripts

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `add-transcript-distillation-and-evidence-cache`
> Effort: L
> Priority: 3

## Summary

Insert a deterministic reduction pass before any model call (user and assistant turns verbatim, each tool call collapsed to one line, output truncated, scaffolding dropped, secrets redacted) and cache per-transcript evidence keyed on transcript content, surface hash, and analysis-index version. Report the measured reduction percentage and cache hit rate in the dry-run output.

## Dependencies

- `ri-01`
- `ri-07`
- `ri-09`

## Acceptance Outcomes

- Dry-run output prints original and distilled token estimates per transcript and the reduction is at least 90 percent on the golden fixtures.
- Distilled output for a fixture containing a fake API key contains no substring of that key (redaction test).
- Running twice over the same transcripts with an unchanged surface hash makes zero model calls on the second run; changing one skill description invalidates only the cached entries whose analysis referenced it.

## Rationale

Adapt item 6 and adopt item 7 in section 4. backpass reaches 96-99 percent reduction before spending a model token; our pipeline passes the full event stream forward. The cache makes reruns after a description edit re-analyze only the transcripts whose evidence that edit could change.
