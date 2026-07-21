# Change: enforce-skill-install-portability

## Why

Skills installed by `skills/install.sh` are intended to run from consumer repositories without access to the `agentic-coding-tools` source checkout. The current payload violates that boundary: confirmed entry points import coordinator internals or deleted repo-root modules, while other scripts and instructions assume canonical `skills/`, `agent-coordinator/`, Makefile, and documentation layouts that consumers do not receive.

This change makes the install payload a tested runtime boundary. Every synced skill, shared library, reference library, hook, and installed OpenSpec asset must either run using files in that payload and explicitly declared external prerequisites, or be excluded from consumer installation with a documented reason.

## What Changes

- Add a clean-consumer regression harness that installs skills into an isolated repository with no coordinator source tree or canonical `skills/` directory.
- Move PR classification and other reusable runtime behavior into the shipped skill boundary.
- Repair broken cross-skill imports and installed-layout path resolution.
- Replace direct `src.*` coordinator access with public coordination interfaces or shipped helpers.
- Make validation, Langfuse, worktree, session-log, review-artifact, Bao, vendor, architecture, and coordinator setup flows portable or explicitly non-distributable.
- Normalize commands and documentation so paths resolve from the installed skill directory.
- Expand dependency-direction linting and CI validation to reject static, dynamic, subprocess, shell, hook, and documentation references outside the declared install payload.
- Keep generated `.claude/skills/` and `.agents/skills/` copies untouched as sources; canonical fixes land under `skills/` and are propagated only through `skills/install.sh`.

## Approaches Considered

### Approach 1: Explicit portable runtime boundary

Define the complete install payload, place reusable helpers in `skills/shared/`, resolve sibling paths from each installed skill, and test the rsynced output as a standalone consumer distribution.

**Pros**

- Preserves shared behavior without depending on coordinator internals.
- Tests the same paths consumers execute.
- Gives future changes an enforceable architectural boundary.
- Works for both `.claude/skills/` and `.agents/skills/` destinations.

**Cons**

- Requires coordinated changes across several existing skills.
- Some source-repository-specific behavior needs an explicit portable fallback or distribution classification.

**Effort:** L

### Approach 2: Duplicate dependencies into each affected skill

Copy every required helper into the skill that uses it and avoid all cross-skill imports.

**Pros**

- Each skill directory is self-contained in isolation.
- Path resolution is simple.

**Cons**

- Reintroduces duplicated classifiers, configuration logic, and drift.
- Makes security and behavior fixes harder to propagate consistently.
- Does not address non-portable instructions or installer policy.

**Effort:** M

### Approach 3: Exclude coupled skills from consumer installs

Add an installer allowlist or per-skill distribution flag and stop shipping every skill that assumes this repository's coordinator, Makefile, docs, or source layout.

**Pros**

- Smallest immediate runtime surface.
- Avoids pretending repo-maintenance skills are generic.

**Cons**

- Removes useful capabilities from consumers.
- Does not solve shared path conventions for the remaining skills.
- Risks silently changing the current install catalogue.

**Effort:** M

### Recommended

Use Approach 1, with a narrow element of Approach 3 only when a skill is intentionally source-repository-only and cannot truthfully offer consumer behavior. This retains useful skills, establishes one shared runtime boundary, and prevents regression through tests rather than relying on review discipline.

### Selected Approach

Approach 1 is selected. The user's explicit request to create this proposal and immediately implement the complete P0–P3 audit is treated as direction and plan approval. Any intentionally non-distributable skill must be declared and omitted by the installer rather than shipped in a broken state.

## Impact

- **Execution layer:** installed skill entry points, hooks, path discovery, dependency loading, and consumer-layout smoke tests.
- **Coordination layer:** coordinator interactions move from private imports to public bridge/API boundaries.
- **Governance layer:** installation manifests, dependency-direction policy, CI enforcement, and documentation accuracy.
- **Affected specs:** `skill-workflow`, `merge-pull-requests`, `coordinator-kanban-viz`, and `worktree`.
- **Primary code:** `skills/install.sh`, `skills/shared/`, affected skill scripts and `SKILL.md` files, `skills/validate-feature/scripts/linters/`, and `skills/tests/`.
- **Rollback:** revert the feature commits; no persisted data or external interface migration is involved.
