# Session Log — add-skillify-and-resolver-audit

---

## Phase: Plan (2026-04-23)

**Agent**: claude_code | **Session**: skillify-pattern

### Decisions

1. **Two skills (`/skillify` and `/audit-resolver`), not one.** Kept scaffold and audit as separate single-responsibility skills. The audit is also exposed as a library. The validate-feature phase calls it. This gives operators a direct command. CI gets a programmatic entry point.

2. **`/skillify` produces an OpenSpec change, not a finished skill.** The scaffold is intentionally a stub. The user runs `/plan-feature skillify-<name>` next. This preserves the existing review discipline. No skill ships without going through the existing gates.

3. **Audit lands first, then skillify, then CI gate.** Phase 1 is independent of Phase 3 and could land first. The CI gate (Phase 4) only enables after Phase 5 triage. This keeps existing dark skills from blocking the change itself. The sequence is: ship the tool, fix the findings, then enforce.

4. **JSON contract for resolver findings.** Declared resolver-finding.schema.json. Future consumers bind to the schema, not to the script implementation. Single-file contract. No type-gen stubs in v1.

5. **`--target-repo` accepts three values; v1 requires running from inside target.** Explicit override is enabled. Cross-repo cd-into-target is deferred. This keeps the scope tight. It avoids the where-do-I-clone question.

6. **Sequential tier; same rationale as Change A.** Small, tightly-coupled work. Coordinated tier offers no benefit despite coordinator availability.

### Alternatives Considered

- Approach 2 (mega-skill `/skillify` includes audit): rejected. Scaffold and audit have different invocation patterns. Coupling them prevents standalone audit use.
- Approach 3 (resolver audit only, defer skillify): rejected. Skillify is the user-facing UX win. Deferring loses momentum. It also bundles the wrong things.
- Auto-fixing dark skills as part of the audit: rejected. The audit reports. The human or a separate skillify follow-up fixes. Auto-modifying SKILL.md from a CI tool is too risky.

### Trade-offs

- Accepted two new skills over one mega-skill. Reason: cleaner single-responsibility and independent testability.
- Accepted stub OpenSpec change requiring user follow-up over directly producing finished SKILL.md plus tests. Reason: the latter would bypass plan-feature review gates.
- Accepted deferring CI gate enable over gating at PR-merge time. Reason: existing dark skills would block this PR. Better to land tool, run audit as housekeeping, then enable gate.

### Open Questions

- [ ] CI workflow file location. Task 4.1 audits this. Likely `.github/workflows/openspec.yml`. Defer to implementation.
- [ ] Should the audit detect non-string trigger values in YAML frontmatter? The spec assumes strings. Consider adding a malformed_triggers finding type if the audit encounters this in practice.
- [ ] Whether `/skillify` should register the change-id in the coordinator feature registry. Defer. This is an integration concern, not a skillify concern.

### Context

This change converts the existing failure-postmortem habit into a structured workflow. The output is durable tested skills, not ephemeral fixes. The skillify article supplies the pattern. This change adapts it to the existing OpenSpec multi-agent gates. It also addresses an emerging risk: at ~45 skills the dark-skill threshold is near. The audit lands before the risk materializes. Both pieces ship together because they reinforce each other.
