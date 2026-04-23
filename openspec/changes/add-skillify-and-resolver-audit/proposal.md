# Proposal — add-skillify-and-resolver-audit

## Why

The team's existing failure-postmortem habit (a Slack thread, a fix commit, sometimes a doc update) doesn't produce durable structural fixes. Two weeks later the same shape of failure recurs because nothing about the codebase prevents it. Garry Tan's "skillify" pattern (article: *"My agent screwed up twice this week. Neither failure can happen again."*) names the missing workflow: every reproducible failure becomes a SKILL.md + deterministic script + tests, registered in the resolver, audited for routing correctness.

Concurrently, at ~45 skills and growing, the cost of *not* auditing the resolver is rising. The article reports finding "15% of capabilities were dark" (skills shipped but unreachable from the resolver) at 40+ skills. We're at the threshold where this risk materializes naturally; adding the audit before it bites is much cheaper than discovering it in production.

This change introduces both pieces — a `/skillify` skill that promotes a failure into reviewable artifacts, and a resolver audit that detects dark skills, trigger overlaps, and broken script references.

Roadmap: `openspec/roadmaps/skillify-foundation/roadmap.yaml` item `ri-02`. Depends on `ri-01` (`add-update-skills`) because skillify-generated skills must reach `.claude/skills/` and `.agents/skills/` to be discoverable.

## What Changes

- **New skill** `skills/skillify/SKILL.md` accepting `--target-repo {coding-tools,content-analyzer,assistant}`. Default: infer from `git remote get-url origin` (matches by repo name). When run, the skill:
  1. Prompts for skill name (kebab-case), one-sentence description, category, initial trigger phrases.
  2. Scaffolds `skills/<name>/SKILL.md` (frontmatter + minimal body), `skills/<name>/scripts/.gitkeep`, `skills/tests/<name>/.gitkeep`.
  3. Creates a draft OpenSpec change at `openspec/changes/skillify-<name>/` with stub proposal.md referencing the failure being skillified.
  4. Prints next-step instructions: edit the scaffolded SKILL.md, run `/plan-feature skillify-<name>` to formalize, then `/implement-feature skillify-<name>`.
- **New skill** `skills/resolver-audit/SKILL.md` providing the `/audit-resolver` operator command and a library function callable from `/validate-feature`.
- **New script** `skills/resolver-audit/scripts/resolver_audit.py` walks every `skills/*/SKILL.md`, parses the YAML frontmatter, and reports three finding categories:
  1. **dark_skill**: skill has empty or missing `triggers:` list.
  2. **trigger_overlap**: two or more skills have triggers that match the same canonical intent (case-insensitive substring overlap with phrase normalization).
  3. **missing_script**: SKILL.md references a script path under `scripts/` that does not exist on disk.
- **Validate-feature integration**: extend `skills/validate-feature/` with a new `--phase resolver` selector that calls `resolver_audit.py --json --fail-on-findings`.
- **CI wiring**: add a CI job (or extend an existing one) that runs `/validate-feature --phase resolver` on every PR.

## Impact

- **Affected specs**: new capabilities `skillify-promotion` and `resolver-audit`. No modifications to existing specs.
- **Affected code**:
  - new: `skills/skillify/SKILL.md`, `skills/skillify/scripts/skillify.py`
  - new: `skills/resolver-audit/SKILL.md`, `skills/resolver-audit/scripts/resolver_audit.py`
  - new: `skills/tests/skillify/`, `skills/tests/resolver-audit/`
  - modified: `skills/validate-feature/SKILL.md` (add `resolver` phase), `skills/validate-feature/scripts/` (add phase dispatch)
  - modified: CI workflow file (TBD: depends on existing CI structure — confirm during implementation)
- **Operational risk**:
  - Resolver audit might initially produce findings against existing skills (the article's "15% dark" observation suggests this is expected). Triage these as a separate housekeeping change before turning the audit into a CI gate. Phase 5 task captures this.
  - `/skillify` creating an OpenSpec change for every failure could increase change throughput. Mitigation: the scaffolded change is a stub that requires user edit and `plan-feature` before it produces real artifacts; nothing auto-merges.

## Approaches Considered

### Approach 1 — Two skills (skillify, resolver-audit) + validate-feature phase (Recommended)

**Description**: `/skillify` and `/audit-resolver` are independent skills with their own SKILL.md, callable independently. Resolver audit logic also exposed as a library so `/validate-feature --phase resolver` can call it.

**Pros**:
- Each skill has a single responsibility.
- Resolver audit is callable directly (operator-friendly) and indirectly via validate-feature (CI-friendly).
- Skillify's scaffold is testable independently of the audit's correctness.

**Cons**:
- Two new skills (slight maintenance overhead).

**Effort**: M

### Approach 2 — One mega-skill `/skillify` that does everything (scaffold + audit + validation)

**Description**: A single `/skillify` skill that, in addition to scaffolding, runs the audit at the end and integrates with validate-feature internally.

**Pros**: Fewer top-level skills; one entry point for the whole "skill hygiene" concern.

**Cons**:
- Couples scaffold and audit, which have different invocation patterns (scaffold is interactive and operator-driven; audit is non-interactive and CI-driven).
- Hard to use the audit standalone, e.g. as a pre-merge check or a daily cron.
- Violates single-responsibility cleanly enough that it's worth the extra skill.

**Effort**: M (similar to Approach 1, but with worse modularity).

### Approach 3 — Resolver audit only, defer skillify

**Description**: Land the resolver audit now (it solves an immediate risk: dark skills at the 40+ threshold), defer `/skillify` to a separate change.

**Pros**: Smaller change; lower risk.

**Cons**:
- Splits roadmap item `ri-02` into two, which complicates the roadmap.
- Skillify is the user-facing operator command that drove the article and the team's interest; deferring it loses the momentum and the "one word makes the failure permanent" UX win.
- The audit alone doesn't deliver the workflow improvement; it only protects what's already there.

**Effort**: S, but rejected on scope.

## Selected Approach

**Approach 1** — both skills land together, with the resolver audit additionally exposed via `/validate-feature --phase resolver`. This delivers the operator UX (`/skillify`), the immediate-risk mitigation (audit), and the CI gate (validate-feature integration) in one coherent change while keeping each capability single-purpose.
