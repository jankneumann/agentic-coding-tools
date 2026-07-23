# Superseded: Add update-documentation skill

> **Status: SUPERSEDED — DO NOT IMPLEMENT**
> Superseded by: `add-deterministic-context-producer-checks` (ri-05)
> Parent roadmap: `project-context-refresh-lifecycle`

## Supersession Decision

This change is no longer an executable proposal.

The useful behavior has moved to ri-05's registered
`documentation.inventory` producer:

- filesystem-derived skill, spec, and documentation inventories;
- generated marker regions;
- preservation of hand-authored prose;
- deterministic generation and side-effect-free checking;
- cross-link validation and precise affected-path reporting.

The following lifecycle behavior is rejected and MUST NOT be implemented from
this change:

- an independent `.githooks/pre-commit` documentation writer/gate;
- an independent `.githooks/post-merge` writer or auto-commit;
- direct `cleanup-feature` merge integration;
- a separate `validate-feature --phase docs` lifecycle;
- any main-writing path outside the shared project-context convergence flow.

ri-10 owns deterministic drift gates. ri-11 owns merge convergence. ri-05 owns
the independently runnable documentation producer.

## Historical Motivation

The original proposal correctly identified that skill, spec, and documentation
inventories drift when maintained manually. Its marker-preserving renderer and
filesystem-source-of-truth decisions remain useful and are retained in
`design.md` as historical rationale.

## Execution Status

- No tasks remain.
- No work package may be dispatched.
- The only normative spec delta is a supersession guard; no implementation
  behavior remains.
- Implementations must use
  `add-deterministic-context-producer-checks` instead.
