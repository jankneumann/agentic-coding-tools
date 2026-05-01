---
name: documentation-and-adrs
description: |
  Write durable documentation that captures *why* a system is the way it is. Use when making a
  significant architectural decision, adding or changing a public API, shipping user-facing
  behavior, onboarding new humans or agents, or any time you find yourself explaining the same
  thing twice. Covers the ADR template (Status / Context / Decision / Consequences), ADR
  lifecycle (PROPOSED → ACCEPTED → SUPERSEDED → DEPRECATED), sequential numbering, the
  "comment intent not mechanics" rule, and a README skeleton (quick-start / commands /
  architecture). Localized to this repo's `docs/decisions/` capability-timeline format and
  OpenSpec workflow.
category: Documentation
tags:
  - documentation
  - adr
  - architectural-decision-record
  - readme
  - comments
  - openspec
  - onboarding
triggers:
  - "write an ADR"
  - "architectural decision record"
  - "document this decision"
  - "should we write an ADR"
  - "update the readme"
  - "document the api"
  - "add a comment"
  - "where do we record decisions"
user_invocable: true
related:
  - update-specs
  - plan-feature
---

# Documentation and ADRs

Adapted from [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills) under its upstream license; localized to this repo's `docs/decisions/` capability-timeline format and OpenSpec workflow.

## Overview

Document decisions, not just code. The most valuable documentation captures the *why* — the context, the constraints, the alternatives that were rejected and the reasons they were rejected. Code shows *what* was built; documentation explains *why it was built this way*. That context is what future humans and agents need to extend the system without re-litigating its foundations.

## When to Use

- Making a significant architectural decision
- Choosing between competing approaches with no obvious winner
- Adding or changing a public API
- Shipping a feature that changes user-visible behavior
- Onboarding new team members or agents to the project
- Any time you find yourself explaining the same thing repeatedly

**When NOT to use:** Don't document obvious code. Don't write comments that restate what the code already says. Don't write docs for throwaway prototypes. Don't write an ADR for a decision that doesn't outlive the change that introduced it.

## ADRs vs OpenSpec Changes

The two artifacts answer different questions and live at different timescales — keep them separate so they reinforce each other instead of drifting:

- **ADRs are timeless decision records.** They capture an architectural commitment future contributors should understand: "We chose X over Y because of Z." Once accepted, an ADR is read-only history; it is only ever superseded, never edited away.
- **OpenSpec changes are time-bounded delivery vehicles.** They describe a unit of work — proposal, tasks, spec deltas — and they archive when the work lands.

An OpenSpec proposal MAY produce an ADR, but not every proposal needs one. Write an ADR only when the change locks in an architectural commitment that constrains future work. Routine engineering choices (rename a function, swap a config default, add a CI step) should not generate ADRs — they clutter the index without adding archaeological value.

Rule of thumb: if the next contributor would benefit from reading the rationale before making *their* design choices, it is an ADR. If the rationale only matters until this change archives, it belongs in the OpenSpec proposal and nowhere else.

## Architecture Decision Records (ADRs)

ADRs capture the reasoning behind significant technical decisions. They are the highest-value documentation you can write.

### When to Write an ADR

- Choosing a framework, library, or major dependency
- Designing a data model or database schema
- Selecting an authentication strategy
- Deciding on an API architecture (REST vs GraphQL vs tRPC)
- Choosing build tools, hosting platforms, or core infrastructure
- Any decision that would be expensive to reverse

### ADR Template

The classic per-decision template — use it as the starting point even when you commit to this repo's capability-timeline format (see *This repo's ADR format* below).

```markdown
# ADR-001: Use PostgreSQL for primary database

## Status
PROPOSED | ACCEPTED | SUPERSEDED by ADR-XXX | DEPRECATED

## Date
2025-01-15

## Context
We need a primary database for the task management application. Key requirements:
- Relational data model (users, tasks, teams with relationships)
- ACID transactions for task state changes
- Support for full-text search on task content
- Managed hosting available (small team, limited ops capacity)

## Decision
Use PostgreSQL with Prisma ORM.

## Alternatives Considered

### MongoDB
- Pros: Flexible schema, easy to start with
- Cons: Our data is inherently relational; would need to manage joins manually
- Rejected: Relational data in a document store leads to ad-hoc joins or duplication

### SQLite
- Pros: Zero config, embedded, fast for reads
- Cons: Limited concurrent writes; no managed hosting story
- Rejected: Not suitable for multi-user web app in production

### MySQL
- Pros: Mature, widely supported
- Cons: PostgreSQL has better JSON support, full-text search, and ecosystem tooling
- Rejected: PostgreSQL is the better fit for the feature requirements

## Consequences
- Prisma provides type-safe access and migration management
- Full-text search needs no extra service (use PostgreSQL FTS)
- Team needs PostgreSQL knowledge (standard skill, low risk)
- Hosting via managed service (Supabase, Neon, or RDS)
```

### ADR Lifecycle

```
PROPOSED → ACCEPTED → (SUPERSEDED or DEPRECATED)
```

- **PROPOSED** — drafted, under review, not yet binding.
- **ACCEPTED** — the decision is in force; new code must comply.
- **SUPERSEDED** — a later ADR replaces it. Add a `Superseded by ADR-NNN` link at the top.
- **DEPRECATED** — no longer in force, but no replacement either (rare; usually only for retired capabilities).

**Do not delete old ADRs.** They capture historical context. When a decision changes, write a *new* ADR that supersedes the old one and add bidirectional links.

### Sequential Numbering Convention

Use `ADR-NNN` with zero-padded three-digit numbers (`ADR-001`, `ADR-002`, …). Numbering is monotonic and never reused — even after an ADR is superseded, its number stays retired so back-references remain stable. The next ADR you write takes the next free number.

### This Repo's ADR Format: `docs/decisions/`

This repository keeps decisions in `docs/decisions/`, but with a twist: instead of one file per ADR, the directory holds **capability timelines**. Each `<capability>.md` is reverse-chronological; every entry has a status (`active` or `superseded`) and back-references to the originating session-log phase entry.

Existing capability timelines (read these to see the on-disk style before adding to them):

- [`docs/decisions/agent-coordinator.md`](../../docs/decisions/agent-coordinator.md)
- [`docs/decisions/configuration.md`](../../docs/decisions/configuration.md)
- [`docs/decisions/merge-pull-requests.md`](../../docs/decisions/merge-pull-requests.md)
- [`docs/decisions/skill-workflow.md`](../../docs/decisions/skill-workflow.md)
- [`docs/decisions/software-factory-tooling.md`](../../docs/decisions/software-factory-tooling.md)

The index at [`docs/decisions/README.md`](../../docs/decisions/README.md) is **generated** by `make decisions` from `architectural:`-tagged Decision bullets in session-log Phase Entries. Do not hand-edit the generated index.

**Numbering still applies, but at the entry level.** Inside each capability timeline, individual entries inherit ADR-style numbering relative to that capability. When you tag a session-log Decision bullet with `` `architectural: <capability>` ``, the next `make decisions` run produces a new entry at the top of the timeline. The first new ADR-style entry you add to a capability follows the existing entry numbering for that file (read the file to see the highest current number and continue from there).

If you need a *standalone* per-decision ADR — a one-off architectural choice that doesn't fit any existing capability — start a new capability file. Pick a kebab-case filename (`<capability>.md`) and let `make decisions` index it.

### Linking ADRs to OpenSpec

When an OpenSpec change produces an ADR-worthy decision:

1. In the change's `proposal.md`, add a line `Decision: <one-sentence summary>  ` `architectural: <capability>` ``.
2. After implementation, the next `make decisions` run picks up the tag and writes the entry into `docs/decisions/<capability>.md`.
3. Reference the capability page from the OpenSpec proposal so future readers can trace from work-package to commitment.
4. Run `/update-specs` during cleanup so `openspec/specs/` reflects the new commitment.

The OpenSpec change archives; the capability timeline persists. That asymmetry is the point.

## Inline Documentation

### Comment Intent, Not Mechanics

Comment the *why*, not the *what*. The code already shows the *what*; the *why* is what disappears from memory.

```python
# BAD: Restates the code
# Increment counter by 1
counter += 1

# GOOD: Explains non-obvious intent
# Sliding window rate limit: reset on window boundary, not on a fixed
# schedule, so attackers can't burst at the edge of two windows.
if now - window_start > WINDOW_SIZE_MS:
    counter = 0
    window_start = now
```

### When NOT to Comment

```python
# Don't comment self-explanatory code:
def calculate_total(items: list[CartItem]) -> Decimal:
    return sum((item.price * item.quantity for item in items), Decimal(0))

# Don't leave TODO breadcrumbs for things you should just do now:
# TODO: add error handling   <-- just add it

# Don't keep commented-out code:
# old_implementation = ...   <-- delete it; git remembers
```

### Document Known Gotchas

```python
def initialize_theme(theme: Theme) -> None:
    """Apply the user's theme.

    IMPORTANT: must be called before the first render. If invoked after
    hydration, it causes a flash of unstyled content because the theme
    context is not available during SSR.

    See docs/decisions/skill-workflow.md (theme-init entry) for the
    full design rationale.
    """
    ...
```

The TypeScript/JSDoc form from the upstream skill applies equally — the principle is language-agnostic. Pick the idiom that matches your file's language; preserve the *intent-not-mechanics* rule either way.

## API Documentation

For public APIs (HTTP, GraphQL, library surfaces), let the type system carry as much weight as it can; document only what types cannot express.

### Inline with Types

```python
def create_task(input: CreateTaskInput) -> Task:
    """Create a new task.

    Args:
        input: Task creation data. ``title`` is required (1-200 chars);
            ``description`` is optional.

    Returns:
        The created Task with a server-generated id and timestamps.

    Raises:
        ValidationError: If ``title`` is empty or exceeds 200 characters.
        AuthenticationError: If the caller is not authenticated.

    Example:
        >>> task = create_task(CreateTaskInput(title="Buy groceries"))
        >>> task.id
        'task_abc123'
    """
```

### OpenAPI for HTTP APIs

```yaml
paths:
  /api/tasks:
    post:
      summary: Create a task
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateTaskInput'
      responses:
        '201':
          description: Task created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Task'
        '422':
          description: Validation error
```

## README Structure

Every project — and every meaningful sub-package — should have a README that covers:

```markdown
# Project Name

One-paragraph description of what this project does and who it's for.

## Quick Start
1. Clone the repo
2. Install dependencies: `uv sync`
3. Set up environment: `cp .env.example .env`
4. Run the dev server: `uv run python -m project`

## Commands
| Command            | Description                |
|--------------------|----------------------------|
| `uv run pytest`    | Run tests                  |
| `uv run ruff check`| Run linter                 |
| `uv run mypy .`    | Run type checker           |
| `make decisions`   | Regenerate ADR index       |

## Architecture
Brief overview of the project structure and key design decisions.
Link to ADRs in `docs/decisions/` for the full rationale.

## Contributing
How to contribute, coding standards, PR process. Reference OpenSpec
workflow for any change that touches a spec.
```

The three load-bearing sections — *Quick Start*, *Commands*, *Architecture* — are the minimum viable README. Add more (Deployment, Troubleshooting, FAQ) when the audience justifies it.

## Changelog Maintenance

For shipped features, keep a `CHANGELOG.md` in the [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
# Changelog

## [1.2.0] - 2025-01-20
### Added
- Task sharing: users can share tasks with team members (#123)
- Email notifications for task assignments (#124)

### Fixed
- Duplicate tasks appearing when rapidly clicking create button (#125)

### Changed
- Task list now loads 50 items per page (was 20) for better UX (#126)
```

This repo automates much of this through the `changelog-version` skill — invoke it during cleanup so the changelog and version bump land in the same merge.

## Documentation for Agents

Special-case audience: AI agents need explicit, durable, machine-readable context.

- **`CLAUDE.md` / `AGENTS.md` / rules files** — document project conventions so agents follow them automatically. Treat them as living specs, not historical artifacts.
- **OpenSpec specs (`openspec/specs/`)** — keep them current via `/update-specs` so agents build the right thing.
- **ADRs / capability timelines** — give agents the *why* so they don't re-decide settled questions.
- **Inline gotchas** — prevent agents from falling into known traps the type system cannot encode.

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "The code is self-documenting." | Code shows *what*. It does not show *why*, which alternatives were rejected, or which constraints applied. Self-documenting code is necessary, not sufficient. |
| "We'll write docs when the API stabilizes." | APIs stabilize *because* they are documented — the doc is the first review of the design. Stable-then-document is the same loop as test-after-merge. |
| "Nobody reads docs." | Agents read docs. New hires read docs. Your three-months-later self reads docs. The "nobody" is whoever wrote the code yesterday. |
| "ADRs are overhead." | A 10-minute ADR prevents a 2-hour debate six months later. The cost of *not* writing it is paid by every future contributor in unrecoverable time. |
| "Comments get outdated." | Comments on *why* age slowly; comments on *what* age fast — that is exactly the rule. The fix is to stop writing the second kind, not to stop writing the first. |
| "The OpenSpec proposal already covers this." | Proposals archive; ADRs persist. If the rationale should outlive the change, copy it into a capability timeline before archiving. |
| "I'll add the README later." | Later never comes; the next contributor will git-blame you in a Slack channel you cannot read. |

## Red Flags

- Architectural choices with no written rationale anywhere reachable from the repo root.
- Public APIs with no docstrings, no type hints, and no OpenAPI schema.
- README that does not show how to install, run, or test the project.
- Commented-out code instead of deletion.
- TODO comments older than a sprint that nobody is tracking.
- Significant decisions made in chat or in PR descriptions with no migration to `docs/decisions/`.
- Documentation that restates the code instead of explaining intent.
- An ADR that has been "PROPOSED" for more than two weeks (decisions decay; ship them or kill them).
- Two ADRs on the same capability with no `Supersedes` link between them — the timeline is broken.
- Rules files (`CLAUDE.md`, `AGENTS.md`) that contradict the code or each other.

## Verification

1. Every significant architectural decision is reachable from `docs/decisions/` (capability timeline) or an OpenSpec proposal — and "significant" was defined up front, not retrofitted.
2. The README's Quick Start, Commands, and Architecture sections are accurate today (run them to confirm — `uv sync && uv run pytest` should not fail because the README lied).
3. Public API surfaces have docstrings *or* an OpenAPI schema covering parameters, return types, and at least one error case.
4. Inline comments document intent, not mechanics — spot-check ten comments at random; none should restate the next line of code.
5. No commented-out code remains in changed files; the linter or pre-commit hook enforces this.
6. ADR lifecycle is honored: PROPOSED entries either move to ACCEPTED or are explicitly killed; SUPERSEDED entries link to their replacement; numbers are never reused.
7. Rules files (`CLAUDE.md`, `AGENTS.md`) reflect the current workflow — diff them against the last sprint's PRs and reconcile any drift before claiming done.
8. `make decisions` runs clean (no `git diff docs/decisions/`) — the index is fresh.
