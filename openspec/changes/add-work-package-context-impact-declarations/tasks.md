# Tasks: Add work-package context impact declarations

Tests precede implementation. Checkpoint after each numbered phase.

## 1. Extend contracts and templates

- [ ] 1.1 (S) Write failing JSON Schema tests for the six required surface keys,
  allowed dispositions, unique targets, complete exceptions, unknown properties,
  and backward-compatible absence.
  - **Scenarios:** Complete context declaration validates; Planning uncertainty is explicit
  - **Design:** D1, D2, D4
  - **Contracts:** `contracts/README.md`, `contracts/context-impact-handoff.schema.json`
  - **Depends on:** none
- [ ] 1.2 (S) Extend canonical and installed
  `work-packages.schema.json` with `ContextImpact`, `ImpactDeclaration`, and
  `ReviewedException` definitions.
  - **Scenarios:** Complete context declaration validates
  - **Design:** D1, D2, D4
  - **Contracts:** canonical and installed `work-packages.schema.json`
  - **Depends on:** 1.1
- [ ] 1.3 (S) Update canonical and plan-feature-installed templates plus
  `plan-feature` guidance with a complete declaration example and the default
  rule: use `unknown` rather than silently claiming no impact.
  - **Scenarios:** Planning uncertainty is explicit
  - **Design:** D1, D2, D4
  - **Contracts:** canonical and plan-feature-installed templates
  - **Depends on:** 1.2

## 2. Add deterministic impact inference

- [ ] 2.1 (M) Write table-driven tests for versioned path/contract/lock rules
  covering all six surfaces, multi-surface paths, sorted output, and no-match
  behavior.
  - **Scenarios:** Contract change implies API impact; One path implies multiple surfaces
  - **Design:** D3
  - **Contract:** normalized `inferred` entries
  - **Depends on:** 1.2
- [ ] 2.2 (M) Implement the inference module under
  `skills/validate-packages/scripts/`, keeping the rule table data-driven and
  returning evidence for every inferred surface.
  - **Scenarios:** Contract change implies API impact; One path implies multiple surfaces
  - **Design:** D3
  - **Contract:** `contracts/context-impact-handoff.schema.json`
  - **Depends on:** 2.1
- [ ] 2.3 (S) Add changed-file inputs (`--changed-file` repeatable and
  `--changed-files-from`) without invoking Git implicitly, so callers control the
  comparison boundary.
  - **Scenario:** Contract change implies API impact
  - **Design:** D3
  - **Contract:** validate-packages CLI
  - **Depends on:** 2.2

## 3. Validate declarations and reviewed exceptions

- [ ] 3.1 (M) Write failing tests for refresh satisfaction, unknown failures,
  undeclared inferred impacts, incomplete exceptions, approved no-impact
  exceptions, and deny-precedence scope normalization.
  - **Scenarios:** Reviewed exception permits deliberate no-impact; Unreviewed rationale fails; Deny scope remains authoritative
  - **Design:** D2, D5
  - **Contracts:** `ReviewedException`, normalized `read_scope`
  - **Depends on:** 1.2, 2.1
- [ ] 3.2 (M) Implement declaration validation and stable diagnostic codes:
  `CONTEXT_IMPACT_MISSING`, `CONTEXT_IMPACT_UNKNOWN`,
  `CONTEXT_IMPACT_UNDECLARED`, and `CONTEXT_IMPACT_EXCEPTION_INVALID`.
  - **Scenarios:** Planning uncertainty is explicit; Contract change implies API impact; Unreviewed rationale fails
  - **Design:** D2, D3
  - **Contract:** validate-packages diagnostics
  - **Depends on:** 2.2, 3.1
- [ ] 3.3 (S) Add `--require-context-impact`; default mode emits
  `legacy-unclassified` warnings for packages without metadata while strict mode
  fails them.
  - **Scenarios:** Legacy plan in compatibility mode; Strict consumer rejects missing declarations
  - **Design:** D4
  - **Contract:** validate-packages CLI
  - **Depends on:** 3.2

## 4. Emit the downstream handoff

- [ ] 4.1 (S) Write failing golden/schema tests for normalized JSON containing
  package ID, declarations, inference evidence, exceptions, read allow, and deny.
  - **Scenarios:** Reviewed exception permits deliberate no-impact; Deny scope remains authoritative
  - **Design:** D3, D5
  - **Contract:** `contracts/context-impact-handoff.schema.json`
  - **Depends on:** 2.1, 3.1
- [ ] 4.2 (S) Add `--context-impact-output <path>` with deterministic key/list
  ordering, schema validation, and fail-before-write behavior.
  - **Scenarios:** One path implies multiple surfaces; Deny scope remains authoritative
  - **Design:** D3, D5
  - **Contract:** `contracts/context-impact-handoff.schema.json`
  - **Depends on:** 3.2, 4.1
- [ ] 4.3 (S) Prove output never broadens scope: deny entries are preserved and
  downstream effective scope is described as read-allow minus deny.
  - **Scenario:** Deny scope remains authoritative
  - **Design:** D5
  - **Contract:** normalized `read_scope`
  - **Depends on:** 4.2

## 5. Integrate and verify

- [ ] 5.1 (S) Update canonical/install-asset parity tests and
  validate-packages/plan-feature documentation.
  - **Scenarios:** Complete context declaration validates; Legacy plan in compatibility mode
  - **Design:** D1, D4
  - **Contracts:** all schema/template copies
  - **Depends on:** 1.3, 3.3
- [ ] 5.2 (S) Add migration fixtures for a legacy v1 file, a fully declared file,
  and a reviewed no-impact exception.
  - **Scenarios:** Legacy plan in compatibility mode; Strict consumer rejects missing declarations; Reviewed exception permits deliberate no-impact
  - **Design:** D2, D4
  - **Contracts:** work-package and handoff schemas
  - **Depends on:** 3.3, 4.2
- [ ] 5.3 (XS) Run strict OpenSpec validation, work-package schema/overlap checks,
  focused validate-packages and plan-feature pytest, install mirror checks, and
  `git diff --check`.
  - **Scenarios:** all
  - **Design:** D1-D5
  - **Contracts:** all
  - **Depends on:** 4.3, 5.1, 5.2
