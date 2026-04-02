# Proposal: Expand Review Evaluation Criteria

**Change ID**: `review-evaluation-criteria`
**Status**: Draft
**Created**: 2026-04-02

## Why

The four review skills (iterate-on-plan, iterate-on-implementation, parallel-review-plan, parallel-review-implementation) evolved independently, resulting in three separate type taxonomies with no formal mapping between them. This creates blind spots:

- **iterate-on-plan** has no security or performance dimensions — an unauthenticated endpoint or unbounded query in the design passes undetected until implementation review
- **iterate-on-implementation** lumps security under "bug" rather than evaluating it systematically, and lacks observability and resilience dimensions
- **parallel-review-plan** has `performance` as a finding type in the schema but no corresponding checklist guidance
- Neither layer evaluates observability (logging, metrics, tracing) or backward compatibility
- The iterate-* skills (markdown) and parallel-review-* skills (JSON schema) have no documented mapping, so findings can't be reliably matched when crossing the dispatch/consensus boundary

Catching security, performance, and operational concerns at the plan stage is significantly cheaper than reworking after implementation.

## What Changes

### 1. Expand Shared Schema (review-findings.schema.json + consensus-report.schema.json)

Add 3 new finding types to the `type` enum:
- `observability` — Missing logging, metrics, tracing, or health checks
- `compatibility` — Breaking changes to existing APIs, migration safety, backward compatibility
- `resilience` — Missing retry logic, timeout handling, idempotency, graceful degradation

Both schemas must stay in sync: `review-findings.schema.json:type` and `consensus-report.schema.json:agreed_type`.

### 2. iterate-on-plan — Add security, performance dimensions + plan smells

Add two new type categories:
- **security**: Missing authentication/authorization for new endpoints, secrets in configuration, unvalidated inputs at system boundaries, OWASP top-10 considerations, missing threat model for new attack surface
- **performance**: Unbounded queries or loops in design, missing pagination for list operations, synchronous processing where async is needed, missing caching strategy for hot paths

Add new plan smells:
- `unprotected-endpoint` — New API endpoint without auth requirement stated
- `secret-in-config` — Credentials or keys referenced without secret management
- `missing-input-validation` — System boundary input without validation requirement
- `missing-pagination` — List operation without pagination or size limits
- `missing-observability` — New service/endpoint without monitoring requirements

Add a **Schema Type Mapping** section documenting how each plan dimension maps to one or more schema finding types.

### 3. iterate-on-implementation — Promote security, add observability + resilience

- Promote **security** from a sub-concern of "bug" to its own dimension: Security vulnerabilities, authentication/authorization issues, input validation gaps, secrets exposure
- Add **observability**: Missing structured logging for key operations, no error context in catch blocks, missing health/readiness endpoints, no metrics for SLI-relevant paths
- Add **resilience**: Missing retry with backoff for external calls, no timeout configuration, non-idempotent operations that should be idempotent, missing circuit breakers for external dependencies

Add a **Schema Type Mapping** section documenting how each implementation dimension maps to schema finding types.

### 4. parallel-review-plan — Add checklist sections for new types + performance

Add evaluation checklist sections:
- **Performance Review**: Unbounded queries, missing pagination, synchronous operations that should be async, missing caching requirements
- **Observability Review**: Monitoring requirements for new services/endpoints, alerting criteria, structured logging requirements
- **Compatibility Review**: Breaking changes to existing APIs, data migration rollback plan, consumer impact analysis
- **Resilience Review**: Retry/timeout/fallback requirements for external dependencies, failure mode analysis

Update the Finding Types documentation to include the 3 new types.

### 5. parallel-review-implementation — Add checklist items for new types

Add items to Code Quality Review checklist:
- Observability: Structured logging for key operations, error context, health endpoints
- Compatibility: API versioning, migration reversibility, deprecation notices
- Resilience: Timeout configuration, retry with backoff, idempotent operations

Update the Finding Types documentation to include the 3 new types.

### 6. vendor_review.py — Sync hardcoded type enum

Update the hardcoded finding type enum in the PR review prompt to include the 3 new types.

## Impact

### Affected Specs
- `skill-workflow` — Spec delta updates the Structured Improvement Analysis requirement (type enum: bug, edge-case, workflow, performance, UX → bug, security, edge-case, workflow, performance, UX, observability, resilience) and adds Schema Type Mapping and Expanded Review Finding Types requirements

### Affected Skills
- `iterate-on-plan/SKILL.md` — New dimensions, smells, mapping
- `iterate-on-implementation/SKILL.md` — Promoted + new dimensions, mapping
- `parallel-review-plan/SKILL.md` — New checklist sections, updated finding types
- `parallel-review-implementation/SKILL.md` — New checklist items, updated finding types
- `merge-pull-requests/scripts/vendor_review.py` — Updated type enum in prompt

### Affected Schemas
- `openspec/schemas/review-findings.schema.json` — 3 new type enum values
- `openspec/schemas/consensus-report.schema.json` — 3 new agreed_type enum values

### Affected Tests
- `skills/parallel-infrastructure/scripts/tests/test_consensus_synthesizer.py` — Add test fixtures for new finding types
- `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py` — Add test data for new finding types

### Non-goals
- Changing the consensus synthesizer algorithm (it already handles arbitrary type values)
- Changing the output format of iterate-* skills (remains markdown)
- Changing the output format of parallel-review-* skills (remains schema-validated JSON)
- Adding new criticality levels or disposition values

## Approaches Considered

### Approach A: Shared Core + Stage-Specific Extensions (Recommended)

Expand the schema to 10 finding types. Each iterate-* skill keeps its domain-specific dimensions but adds a documented mapping table showing how each dimension translates to schema types. The adapter pattern: each skill keeps its own vocabulary, but findings pass through a mapping layer at the dispatch/consensus boundary.

**Pros:**
- Maximum evaluative precision per skill (plan dimensions stay plan-specific)
- Schema becomes the lingua franca for cross-vendor consensus
- No disruption to existing iterate-* markdown output format
- Mapping enables accurate finding deduplication across layers

**Cons:**
- Mapping tables add documentation maintenance burden
- Two-level taxonomy is more complex to understand than a flat list

**Effort:** M

### Approach B: Full Unification to Schema Types

Replace iterate-* custom dimensions entirely with the 10 schema finding types. All skills use the same flat vocabulary.

**Pros:**
- Simplest mental model — one vocabulary everywhere
- No mapping needed

**Cons:**
- Loses evaluative nuance (e.g., `completeness`, `clarity`, `testability` all become `spec_gap`)
- Plan-specific concepts like `parallelizability` and `assumptions` don't map cleanly to any schema type
- Forces schema types to be generic enough for both plans and code, reducing their descriptive power

**Effort:** M

### Approach C: Expand Schema Only, No Iterate-* Changes

Add the 3 new types to the schema and parallel-review skills only. Leave iterate-* skills unchanged.

**Pros:**
- Minimal change scope
- No mapping complexity

**Cons:**
- iterate-on-plan still lacks security and performance dimensions
- iterate-on-implementation still lumps security under "bug"
- No mapping documentation — the boundary translation gap persists

**Effort:** S

### Selected Approach

**Approach A: Shared Core + Stage-Specific Extensions** — selected per user discussion. Provides the right balance between evaluative precision (each skill retains domain vocabulary) and cross-layer consistency (shared schema types as lingua franca). The mapping tables formalize the implicit relationship that already exists.
