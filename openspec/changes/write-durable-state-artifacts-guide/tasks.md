# Tasks: Write a Durable State-Artifacts Guide

## Phase 1 — RED documentation contracts

- [ ] 1.1 Add failing structural tests for the five-class inventory, required ownership fields, canonical bootstrap/verification order, relevant skill links, supervise alignment, and changed-skill mirror parity. **Size**: S. **Spec scenarios**: Canonical durable state-artifact inventory / All durable classes are discoverable; Deterministic fresh-session rehydration / Fresh supervisor session resumes active work; Skill documentation links to the canonical guide / Relevant skill documentation is audited, Runtime skill mirrors are installed. **Design decisions**: D1–D4. **Dependencies**: None.
- [ ] 1.2 Run the focused test on the roadmap parent commit and record the expected RED failures for the missing guide and links. **Size**: XS. **Spec scenarios**: all. **Design decisions**: D4. **Dependencies**: 1.1.

- [ ] Checkpoint: preserve RED output, review the test diff, and verify writes remain inside the declared package scope.

## Phase 2 — GREEN canonical documentation

- [ ] 2.1 Write `docs/guides/state-artifacts.md` with the exact inventory, question-scoped authority, bootstrap locator rule, canonical verification sequence, conflict handling, and missing/stale behavior. **Size**: S. **Spec scenarios**: Canonical durable state-artifact inventory / All durable classes are discoverable, Advisory state conflicts with authoritative state; Deterministic fresh-session rehydration / Fresh supervisor session resumes active work, Canonical state is missing. **Design decisions**: D1–D3. **Dependencies**: 1.2.
- [ ] 2.2 Link the documentation index and relevant canonical skill sources to the guide while retaining phase-specific commands and gate semantics. **Size**: S. **Spec scenarios**: Skill documentation links to the canonical guide / Relevant skill documentation is audited. **Design decisions**: D1, D4. **Dependencies**: 2.1.
- [ ] 2.3 Align the supervise rehydration section with the bootstrap and canonical verification order. **Size**: S. **Spec scenarios**: Deterministic fresh-session rehydration / Fresh supervisor session resumes active work, Canonical state is missing. **Design decisions**: D2–D4. **Dependencies**: 2.1.

- [ ] Checkpoint: run focused GREEN tests, inspect link targets, and confirm the guide has not changed runtime behavior.

## Phase 3 — Mirrors and validation

- [ ] 3.1 Install changed skill sources into `.agents` and `.claude`, then verify byte identity. **Size**: S. **Spec scenarios**: Skill documentation links to the canonical guide / Runtime skill mirrors are installed. **Design decisions**: D4. **Dependencies**: 2.2, 2.3.
- [ ] 3.2 Run focused and affected skill tests, strict OpenSpec, work-package validation, context-drift, link checks, scope checks, and diff checks. **Size**: S. **Spec scenarios**: all. **Design decisions**: D4. **Dependencies**: 3.1.

- [ ] Checkpoint: review the complete branch diff, reconcile task checkboxes with commit reality, and preserve validation evidence.

