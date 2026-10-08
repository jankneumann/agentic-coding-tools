# Change: generate-coordinator-clients-from-contracts

## Why

The coordinator exposes one set of capabilities through four hand-maintained surfaces: the
FastAPI app (`agent-coordinator/src/coordination_api.py`, 89 routes), the MCP server
(`coordination_mcp.py`, 61 tools), the in-process CLI (`coordination_cli.py`, ~44 subcommands),
and the stdlib HTTP bridge used by cloud agents and skills
(`skills/coordination-bridge/scripts/coordination_bridge.py`, 2,202 lines, 15 importers). The
repository already has the right source of truth for the HTTP surface — 27 hand-authored,
requirement-traced OpenAPI documents under `openspec/contracts/agent-coordinator/openapi/`
(D1 of `derive-descriptors-from-contracts`: *the contract is the source; introspection is the
verifier*) — but nothing is generated from those contracts and nothing checks that a contract
edit is backward compatible. Clients are written by hand against the running app, so drift is
only caught when a parity test happens to exist for that domain.

The feature-registry domain shows what this costs today. Three defects coexist undetected:

1. **Route shadowing.** `GET /features/{feature_id}` (`coordination_api.py:2280`) is registered
   before `GET /features/active` (`:2304`), so `/features/active` is captured by the
   parameterised route and returns `404 Feature not found`. The bridge's capability probe
   (`coordination_bridge.py:63`, `_probe_capability`) reads that 404 as "unavailable", which
   should make `try_register_feature` / `try_deregister_feature` report
   `skipped/capability_unavailable` against a live coordinator (inferred from probe logic; the
   bridge test fixture even mocks the 404 at `tests/test_coordination_bridge.py:107`).
2. **Contract/implementation shape drift.** `features.yaml` says `/features/active` returns
   "a JSON array"; the app returns the AXI `list_envelope` object.
3. **Untyped contract responses.** Every `200` in `features.yaml` has a description and no
   schema, and the conflicts request body is a bare `object`, so neither a generator nor a
   conformance test has anything to check against.

A client generated from a typed contract, exercised in a contract test, fails on all three.

The original prompt for this change was Cloudflare Forge
(<https://blog.cloudflare.com/forge-open-source-generation-pipeline/>). Research during planning
found Forge at v0.1.0 (6 commits, no releases) as a resolver/overlay layer over Fern's
generators, with Python listed as "planned", a TypeScript-only CLI target, and no MCP target or
breaking-change linter present in the repository yet. The *pattern* — one contract, generated
artifacts, breaking-change lint in CI, handwritten extensions on top — is what this change
adopts; the tool is recorded as a re-evaluation candidate.

## What Changes

- **Breaking-change gate for promoted contracts.** New CI job runs `oasdiff breaking` over every
  `openspec/contracts/**/openapi/*.yaml` changed in a PR, comparing PR head against the merge
  base. A breaking difference fails the job unless the PR carries an explicit, reviewable
  acknowledgement (design D4). In-flight change-local contracts under `openspec/changes/*/contracts/`
  are out of the gate's scope; they are gated when promoted.
- **Type the feature-registry contract.** `features.yaml` gains response schemas for all five
  operations, a typed `analyzeFeatureConflicts` request body, the AXI list envelope for
  `listActiveFeatures`, and RFC 7807 error responses — authored from the spec and the AXI
  envelope requirement, not from `app.openapi()` (D1 preserved).
- **Generate stdlib-only bindings from the contract.** A deterministic generator produces, from
  `features.yaml`, `TypedDict` request/response models (via `datamodel-code-generator`) and an
  operation table (`operationId → method, path, auth, path params`) into a checked-in
  `_generated/` module. Generated code imports only the standard library, because skills invoke
  the bridge with bare `python3`. A `--check` mode fails CI when the generated output is stale.
- **Bridge feature helpers delegate to the generated bindings.** `try_register_feature` and
  `try_deregister_feature` resolve method/path from the operation table and are typed by the
  generated models; new `try_get_feature`, `try_list_active_features`, and
  `try_analyze_feature_conflicts` fill the bridge's missing feature coverage. The bridge's
  uniform `ok`/`skipped`/`error` envelope, URL allowlist, and capability probing are unchanged.
- **Fix the route shadowing.** Register `GET /features/active` before `GET /features/{feature_id}`.
  Update the bridge test fixture that encoded the 404.
- **Response-conformance contract test.** A test drives every `features.yaml` operation through
  `TestClient(create_coordination_api())` with a faked service and validates each response body
  against the contract's response schema. This is the check that would have caught all three
  defects above.
- **Go/no-go decision record.** A `decision.md` in the change scores the pilot against the
  NFRs below and states whether a follow-up change should (a) roll generated bindings out to the
  remaining bridge domains, (b) regenerate `http_proxy.py` from a full `openapi-python-client`
  client inside the agent-coordinator venv, and (c) re-evaluate Forge. No rollout happens in
  this change.
- **Not changed.** The MCP tool surface stays hand-curated (agent-facing docstrings,
  session-derived identity, composite tools). The CLI stays in-process against the service layer;
  a generated HTTP CLI would change its auth and policy semantics and is out of scope.

No **BREAKING** changes to runtime behaviour. The `/features/active` fix changes a `404` to a
`200` on a route that was unreachable; the contract-typing edit to `features.yaml` would itself
be flagged by the new gate as a response-shape change and is acknowledged in this PR.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Compatibility | Existing bridge tests (`skills/coordination-bridge/scripts/tests/`) passing without expectation edits, except the `/features/active` 404 fixture | 100% | CI `test-infra-skills` |
| Compatibility | Third-party imports reachable from `coordination_bridge.py` at runtime | 0 | Static import test in bridge suite |
| Determinism | Regenerating bindings twice on a clean tree | Byte-identical output; `--check` exits 0 | CI generated-bindings drift step |
| Operability | Wall time of the breaking-change job on a PR touching one contract | < 60 s | CI job timing |
| Correctness | `features.yaml` operations covered by the response-conformance test | 5 / 5 | CI `test` job |
| Traceability | Operations in `features.yaml` with an `x-traceability` block after typing | 5 / 5 (unchanged) | CI `requirement-traceability-sweep` |

## Approaches Considered

### Approach 1: Contract-first, Python-native generation with an oasdiff gate (Recommended)

Generate stdlib `TypedDict` models and an operation table from the hand-authored contracts with
`datamodel-code-generator` plus a small in-repo emitter; gate contract edits with `oasdiff`;
pilot on the feature registry behind the existing bridge envelope.

- **Pros:** Keeps D1 intact — the contract stays authored, generation reads it, `app.openapi()`
  stays a verifier. Fits the bridge's stdlib-only runtime. Python toolchain only, except the
  single pinned `oasdiff` binary in CI. Small, reversible pilot with a measurable outcome.
- **Cons:** Two generators (models + operation table) instead of one full SDK. Contracts must be
  typed domain by domain before they can generate anything useful. `oasdiff` is a Go binary to
  pin and verify in CI.
- **Effort:** M

### Approach 2: Cloudflare Forge (Fern) as the generation pipeline

Run Forge's resolver and Fern's Python SDK generator over the contracts; chain a CLI target off
the generated SDK.

- **Pros:** Matches the original prompt. One tool spanning SDK, docs, and (eventually) CLI and
  MCP. Overlays and transformers give a clean extension story.
- **Cons:** v0.1.0 with no releases, Python "planned"; CLI target is TypeScript and cannot replace
  the in-process Python CLI; no MCP target or breaking-change linter in the repository today.
  Adds a Node 22 + pnpm toolchain to CI. Fern's Python output depends on httpx and Pydantic, which
  the bridge cannot import under bare `python3`.
- **Effort:** L

### Approach 3: Code-first — export `app.openapi()` as the canonical spec

Commit a deterministic export of the running app's OpenAPI document and generate clients from it.

- **Pros:** No contract authoring; always matches the implementation; FastAPI already serves it.
- **Cons:** Directly contradicts D1 of `derive-descriptors-from-contracts` and the gen-eval
  requirement "Contract As Descriptor Source Of Truth" — the app would verify a copy of itself.
  All 89 routes return `dict[str, Any]` with no `response_model`, so the export has untyped
  responses everywhere and generated clients would be no better than today's.
- **Effort:** M (plus a superseding decision)

### Recommended

Approach 1. It is the only option that respects the repository's contract-as-source decision,
works inside the bridge's stdlib-only runtime, and produces a falsifiable result on one domain
before committing to a rollout. Forge (Approach 2) stays on record as a re-evaluation target in
`decision.md`, with explicit re-entry criteria (released Python target, standalone
breaking-change lint).

### Selected Approach

**Approach 1**, selected at discovery: contracts are the generation source, the generator choice
is Python-native and generator-neutral, the pilot domain is the feature registry, and the scope
is the pilot plus the breaking-change gate. Bridge-wide rollout, `http_proxy.py` regeneration,
and any CLI change are deferred to follow-up changes gated on `decision.md`.

## Impact

- **Architecture layers:** Coordination (bridge, HTTP API route order, contracts); Governance
  (new CI gate on contract compatibility).
- **Affected specs:**
  - `agent-coordinator` — ADDED "Contract Breaking-Change Gate", ADDED "Feature Registry Response
    Conformance"; MODIFIED "Feature Registry HTTP Endpoints" (route precedence for
    `/features/active`). Delta: `specs/agent-coordinator/spec.md`.
  - `coordination-bridge` — ADDED "Contract-Generated Bindings", ADDED "Feature Registry Bridge
    Helpers". Delta: `specs/coordination-bridge/spec.md`.
- **Affected code:** `openspec/contracts/agent-coordinator/openapi/features.yaml`,
  `agent-coordinator/src/coordination_api.py` (route order only),
  `skills/coordination-bridge/scripts/coordination_bridge.py` (feature helpers),
  new `skills/coordination-bridge/scripts/_generated/`, new generator script and
  `.github/workflows/ci.yml` jobs, new tests in `agent-coordinator/tests/` and
  `skills/coordination-bridge/scripts/tests/`.
- **Coordination with in-flight changes:** `axi-align-coordinator-output` owns the list envelope
  this change types into the contract (read, not modified). Eight active changes edit
  `coordination_api.py` and ship change-local OpenAPI; the gate applies to them only when they
  promote into `openspec/contracts/`. `gate-drift-with-mirrors-hooks-and-blocking-ci` and
  `assert-generated-artifacts-validate-in-ci` also edit `ci.yml`; the new jobs are additive.
- **Rollback:** Revert the PR. The bridge helpers fall back to their prior hand-written paths;
  the gate and drift jobs are independent CI steps with no runtime footprint.
