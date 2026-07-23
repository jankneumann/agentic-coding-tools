# Change: Add work-package context impact declarations

> Parent roadmap: `project-context-refresh-lifecycle`
> Roadmap item: `ri-08`
> Change ID: `add-work-package-context-impact-declarations`

## Why

Work packages declare file scope and contracts, but they do not say which durable
context surfaces a package is expected to change. A later branch checkpoint could
guess from changed files, yet guessing alone cannot distinguish a real omission
from a reviewed no-impact decision. Semantic retrieval also needs the package's
existing read and deny scope in a normalized, validated handoff.

## Selected approach

Add an optional `context_impact` object to each work package with six required
surface keys when present: capabilities, APIs, architecture, decisions,
documentation, and semantic code. Each declaration uses a disposition of
`refresh`, `no-impact`, or `unknown`, optional targets, and an optional reviewed
exception.

Extend `validate-packages` with deterministic inference rules over changed files,
declared contracts, and logical lock keys. An inferred impact is satisfied by
`refresh`; `unknown` remains an actionable validation failure in strict mode; and
`no-impact` is accepted only with a complete exception containing rationale,
reviewer, and review timestamp.

For compatibility, existing packages without `context_impact` validate with a
machine-readable `legacy-unclassified` warning in default mode. New templates
include the object, and `--require-context-impact` turns missing metadata into an
error. This creates an explicit migration path without breaking every active
change at once.

The package's existing `scope.read_allow` and `scope.deny` remain the source of
truth. The validator emits a normalized context handoff that copies those values
alongside declared impacts for branch refresh and semantic-query consumers.

## Approaches considered

### A. Authored declarations plus deterministic inference — selected

Place a fixed six-surface declaration in the reviewed work-package contract,
compare it with versioned path/contract/lock inference, and require review
provenance for conflicts. This preserves intent while making omissions detectable.

### B. Pure changed-file inference

This minimizes planning work, but cannot distinguish a true no-impact change from
an incomplete rule set. It also gives reviewers no early signal before code is
written.

### C. Separate context-impact manifest

This could evolve independently, but duplicates package identity and scope and can
drift from the execution contract. `work-packages.yaml` is already the reviewed
coordination boundary.

### D. LLM impact classification

This may add useful advisory hints later, but is nondeterministic and unsuitable
as a validation or merge gate. V1 uses inspectable rules and explicit exceptions.

## What changes

- Extend canonical and installed work-package schemas and templates.
- Add context-impact inference, validation, and normalized JSON output to
  `validate-packages`.
- Detect undeclared capability, API, architecture, decision, documentation, and
  semantic-code impacts from changed paths/contracts using versioned rules.
- Add a strict migration flag and clear legacy compatibility result.
- Make the normalized read/deny scope available to downstream refresh/index
  callers without introducing new authority.

## Dependencies

- None. This is a dependency root.
- `ri-09` consumes declarations for branch-local checkpoints.
- `ri-12` consumes normalized read/deny scope for semantic context injection.

## Out of scope

- Running any producer or semantic index.
- Deciding whether a work package is "large"; `ri-09` owns checkpoint policy.
- Expanding read permission beyond `scope.read_allow`.
- Inferring semantic meaning with an LLM; v1 rules are deterministic and
  reviewable.

## Acceptance outcomes

- Schemas/templates accept declarations for all six context surfaces.
- Validation catches deterministically implied but undeclared impacts.
- A no-impact exception requires review provenance and remains visible in output.
- Legacy files receive an explicit compatibility warning; strict mode fails them.
- Normalized output exposes read/deny scope exactly as declared, with deny taking
  precedence.

## Risks

- Broad path rules may over-report impacts. Reviewed exceptions preserve forward
  progress and provide evidence for tuning.
- Optional migration mode could linger. `ri-09` must use strict mode when it makes
  checkpointing operational.
- Targets can become stale after refactors. Validation treats targets as hints;
  declared disposition and inferred changed paths remain authoritative.
