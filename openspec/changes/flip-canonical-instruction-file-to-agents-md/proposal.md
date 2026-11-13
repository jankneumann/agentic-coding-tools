# Flip canonical instruction file to AGENTS.md with CLAUDE.md import pointer

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `flip-canonical-instruction-file-to-agents-md`
> Effort: M
> Priority: 2

## Summary

Replace the AGENTS.md symlink with a self-contained canonical AGENTS.md and rewrite CLAUDE.md as a Claude-specific preamble (Sub-Agent Authorization block) ending in @AGENTS.md. Retarget test_claude_md_restructure.py, README.md line 7, the context-engineering skill, the skill-workflow spec text that says either file may exceed 300 lines, and the three skills that describe the two files as divergent.

## Dependencies

- None

## Acceptance Outcomes

- AGENTS.md is a regular file (git mode 100644) containing the full shared contract, and CLAUDE.md contains only Claude-specific content followed by a final @AGENTS.md line.
- skills/session-log/tests/test_claude_md_restructure.py asserts the line cap against AGENTS.md and passes.
- README.md, skills/context-engineering/SKILL.md, and openspec/specs/skill-workflow/spec.md no longer describe AGENTS.md as a symlink or as a second file that can diverge; grep for 'symlink' near AGENTS.md returns no stale hits in docs, specs, or skills.
- Codex-style consumers that ignore @ imports still receive the complete contract by reading AGENTS.md alone (verified by a test that AGENTS.md contains every section heading that the previous CLAUDE.md had, minus the Claude-specific block).

## Rationale

Section 3.3 of the proposal. A mode-120000 symlink degrades to a one-line text file under core.symlinks=false, Claude-specific text is currently read by Codex through the link, AGENTS.md is the cross-vendor convention matching the repo's harness-agnostic identity, and backpass recognises the pointer form as canonical. Also closes defect 6 in section 6 and overlaps repo-improvement stale-doc reconciliation.
