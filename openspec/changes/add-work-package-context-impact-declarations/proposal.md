# Add work-package context impact declarations

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `add-work-package-context-impact-declarations`
> Effort: M
> Priority: 8

## Summary

Extend work-package schemas and templates with reviewable impacts for capabilities, APIs, architecture, decisions, documentation, and semantic code. Add changed-file and contract analysis that detects undeclared impacts while supporting an approved rationale.

## Dependencies

- None

## Acceptance Outcomes

- Work-package schemas and templates accept context-impact declarations for every surface named in the proposal.
- Validation fails when changed files or contracts imply an undeclared impact unless an approved rationale is present.
- Existing work packages without new metadata receive a clear migration or compatibility result.
- Declared read_allow and deny scopes are available to downstream indexing queries and context injection.

## Rationale

Planning metadata gives branch checkpoints a scoped starting point, but automated detection is required so omissions cannot silently leave context stale.
