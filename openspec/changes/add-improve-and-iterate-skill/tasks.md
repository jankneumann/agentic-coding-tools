## 1. Create the skill

- [ ] 1.1 Create `skills/improve-and-iterate/SKILL.md` with proper YAML frontmatter (name, description, category, tags, triggers)
- [ ] 1.2 Write the skill steps: argument parsing, iteration loop, analysis, implementation, commit, documentation update, termination check
- [ ] 1.3 Define the structured improvement analysis format (type, criticality, description, proposed fix)
- [ ] 1.4 Define iteration commit message format referencing change-id and iteration number
- [ ] 1.5 Define early termination logic (criticality threshold and max iterations)
- [ ] 1.6 Define OpenSpec document update step (proposal.md, design.md, spec deltas when findings reveal spec drift)

## 2. Update project documentation

- [ ] 2.1 Update CLAUDE.md workflow section to show the 4-skill workflow including `/improve-and-iterate`
- [ ] 2.2 Add lessons learned entry about iterative refinement patterns

## 3. Validate

- [ ] 3.1 Verify skill frontmatter follows existing conventions (matches plan-feature, implement-feature, cleanup-feature patterns)
- [ ] 3.2 Verify skill is self-contained with no code dependencies (pure SKILL.md instruction file)
- [ ] 3.3 Run `openspec validate add-improve-and-iterate-skill --strict`
