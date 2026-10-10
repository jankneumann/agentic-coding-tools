# Design: generate-coordinator-clients-from-contracts

## Context

Four coordinator surfaces are written by hand and kept in step by convention:

| Surface | File | Size | Transport |
|---|---|---|---|
| HTTP API | `agent-coordinator/src/coordination_api.py` | 89 routes, 0 with `response_model` | FastAPI |
| MCP server | `agent-coordinator/src/coordination_mcp.py` | 61 tools | stdio / `http_proxy.py` |
| CLI | `agent-coordinator/src/coordination_cli.py` | ~44 subcommands | in-process service calls, no HTTP |
| Bridge | `skills/coordination-bridge/scripts/coordination_bridge.py` | 2,202 lines, 15 importers | stdlib `urllib` |

The repository has already decided where the HTTP truth lives. 27 per-domain OpenAPI documents
under `openspec/contracts/agent-coordinator/openapi/` are authored from the specs, carry
`x-traceability`, and are verified against — never derived from — `app.openapi()`
(`derive-descriptors-from-contracts` D1; gen-eval "Contract As Descriptor Source Of Truth").

What is missing is the other half of the contract-first loop: nothing consumes those contracts to
produce client code, and nothing stops a contract edit from breaking existing clients.

The pilot domain, feature registry, currently has three latent defects (route shadowing on
`/features/active`, contract says bare array while the app returns the AXI envelope, and
description-only responses). See `proposal.md`.

### Prior-art finding: Cloudflare Forge

Investigated on 2026-10-08 from the repository and blog (not executed): `@cloudflare/forge`
v0.1.0, 6 commits on `main`, no releases; SDKs come from Fern generators
(`fernapi/fern-python-sdk`), Python is "planned"; CLI target is TypeScript; no MCP target and no
breaking-change linter in the code. Transformers are `(forge) => Promise<void>` with
`emit(path, content)`. Recorded as a re-evaluation candidate (D7), not adopted.

## Goals / Non-Goals

Goals:
- One promoted contract (`features.yaml`) generates the bridge's types and routing for its domain.
- Contract edits that break clients fail CI unless acknowledged in the diff.
- A conformance test proves the app's responses match the contract, for every operation.
- A written, evidence-based go/no-go for rolling the pattern out.

Non-Goals:
- Generating MCP tools. Agent-facing descriptions, session-derived identity, and composite tools
  stay curated.
- Changing the CLI's transport. It stays in-process; an HTTP CLI would add auth and policy checks
  it does not perform today.
- Adding `response_model` to FastAPI routes. The app is verified against the contract; it does
  not become the contract.
- Moving error bodies to RFC 7807. The contract describes the `{"detail": ...}` shape the app
  emits.
- Generating anything for the other 26 contract documents.

## Decisions

### D1 — The contract is the only generation input

Generators read `openspec/contracts/**/openapi/*.yaml` only. `app.openapi()` is used solely by
the conformance test (D5) and the existing gen-eval subset verifier. This keeps
`derive-descriptors-from-contracts` D1 intact: generation flows contract → code, verification
flows app → contract, and neither direction feeds the other.

*Rejected:* exporting `app.openapi()` as the canonical spec. With no `response_model` on any
route it would produce untyped responses, and it would make the contract a copy of the thing it
verifies.

### D2 — Two small generators, both standard-library at runtime

1. **Models:** `datamodel-codegen` with `--output-model-type typing.TypedDict
   --target-python-version 3.11 --disable-timestamp`. Spike on 2026-10-08 with v0.83.0 over this
   change's `contracts/openapi/v1.yaml`: 11 types; imports `__future__` and `typing` only;
   byte-identical across runs (`contracts/generated/models.py` is that output).
2. **Operations:** an in-repo emitter (`skills/coordination-bridge/scripts/generate_bindings.py`)
   that writes a literal `OPERATIONS: dict[str, Operation]` table, keyed by `operationId`, with
   `method`, `path`, `path_params`, `requires_api_key`, `request_model` and `response_model` names.
   It is a plain-Python literal with a `NamedTuple` — no parsing at import time.

*Rejected:* `openapi-python-client`. It emits a full httpx + attrs client, and skills invoke the
bridge with bare `python3`. That client remains a candidate for `http_proxy.py`, which already
runs inside the agent-coordinator venv with httpx, and is scored in `decision.md`.

### D3 — Models are type-only for the bridge

The generated models use `NotRequired`/`TypeAlias` from `typing`, which exist only on Python 3.11+.
A bare `python3` can be older (macOS ships 3.9). The bridge therefore imports the models under
`if TYPE_CHECKING:` only. The operations table is imported at runtime and uses only syntax valid
on 3.9. The import test in the bridge suite (spec "Bindings stay standard-library only") runs the
bridge under `python3 -I` with an empty `sys.path` extension to prove no third-party import is
reachable.

### D4 — Breaking-change gate: oasdiff, pinned Go module, acknowledgement files

- **Tool:** `oasdiff breaking -f json` (v1.33.0); ERR-level findings are breaking.
- **Pin (revised at implementation, 2026-10-09):** oasdiff is pinned as the Go module
  `github.com/oasdiff/oasdiff@v1.33.0` and installed by
  `scripts/contract_gate/fetch_oasdiff.py`, which (1) refuses to run when Go's
  checksum verification is disabled for the module (`GOSUMDB=off`, `-insecure` in
  `GOFLAGS`, or a matching `GONOSUMDB`/`GONOSUMCHECK`/`GOINSECURE`/`GOPRIVATE`
  pattern, read from the environment and `go env`); (2) runs
  `go mod download -json` and refuses unless `Sum` is present and `GoModSum`
  equals the value recorded in `scripts/contract_gate/oasdiff.sum`; (3) runs
  `go install`. Go verifies the module zip against the public checksum database,
  so content is pinned by a transparency log rather than a hand-recorded tarball
  hash. *Why not the planned release tarball + `sha256sum -c`:* the planning
  sandbox could not reach release-asset hosts to record the hash, and every
  oasdiff release from v1.24 on requires Go 1.26, so the recorded value had to be
  derivable from the tagged source. The fetch script is Python so its refusal
  paths are unit-tested without network.
- **Scope:** files under `openspec/contracts/**/openapi/*.yaml` that the PR changes,
  each compared with `git show <merge-base>:<path>`. New files are reported and
  pass; deleted files (and renames, detected as delete + add) fail unless
  acknowledged with rule `contract-document-deleted` and operation `*`.
- **Acknowledgement:** `openspec/changes/<id>/contracts/accepted-breaking-changes.yaml`, a list of
  `{document, operation, rule_id, rationale}`. The gate collects acknowledgement files from every
  change directory touched by the PR and suppresses only exact `(document, operation, rule_id)`
  matches. Unmatched acknowledgements are reported as warnings so stale ones are visible.
- **Wrapper:** `scripts/contract_gate/check_breaking.py` owns the git plumbing and matching
  (exit 0 pass, 1 unacknowledged break, 2 apparatus error), with oasdiff injected so its
  logic is tested with recorded oasdiff JSON and real temporary git repositories.
- **oasdiff JSON assumptions** (`id`, `text`, `level`, `operation`, `path`; integer or
  string level) are confirmed by the gate's first CI run against the real binary.

This change's own `features.yaml` typing is the first acknowledged change (task 2.2).

*Rejected:* writing a diff in Python (large, and the hard part is OpenAPI semantics); Forge's
lint (not present in the code).

### D5 — Response-conformance test validates against the contract, not the app

`agent-coordinator/tests/test_feature_registry_contract_conformance.py` loads `features.yaml`,
resolves `$ref`s, and for each operation calls `TestClient(create_coordination_api())` with the
feature registry service replaced by a fake (monkeypatching `get_feature_registry_service`, as
`test_code_search_surfaces.py` does for its runtime). Each response is validated with
`jsonschema.Draft202012Validator` against the schema for the returned status. The test fails if
the contract has an operation with no request driver, or a success response without a schema.

### D6 — Route order fix is the minimal code change

Move the `@app.get("/features/active")` block above `@app.get("/features/{feature_id}")`. No
`APIRouter` refactor. The conformance test's `listActiveFeatures` case is the regression guard;
the bridge fixture that mocks `/features/active` as 404
(`skills/coordination-bridge/scripts/tests/test_coordination_bridge.py:107`) is kept — it
simulates a deployment without the feature registry — and a separate test covers the 200 probe.

### D7 — Go/no-go is a scored record, not a judgement call

`decision.md` scores the pilot against the proposal's NFR table and these criteria:

| Criterion | Go threshold |
|---|---|
| Hand-written lines removed or replaced per domain in the bridge | > 0 net, with new helpers counted |
| Defects surfaced by conformance test in the pilot domain | Reported (3 known going in) |
| Generator drift between two CI runs | 0 bytes |
| Breaking-change gate false positives on the last 20 merged contract edits (replayed) | ≤ 1 |
| Time to add a typed operation (contract + regenerate + helper) | Recorded, no threshold |

Outcomes: **Go** opens follow-up changes per domain (bridge), and a separate one for
`http_proxy.py` via `openapi-python-client`. **No-go** keeps the gate and conformance test and
deletes the generators. Forge re-entry criteria: a released Python target and a standalone
breaking-change command.

## Risks / Trade-offs

- **Contract typing effort is per domain.** 26 documents are still description-only; rollout cost
  is dominated by authoring schemas, not by generation. Mitigation: the gate and conformance test
  are valuable on their own, so a no-go still leaves value.
- **oasdiff is a Go binary in a Python repo.** Pinned and checksummed; only CI needs it.
  Developers can run the wrapper locally with `--oasdiff <path>`.
- **Gate friction for in-flight changes.** Eight active changes ship change-local OpenAPI; none
  touch `features.yaml`. They meet the gate only when they promote. The acknowledgement file is
  the escape hatch.
- **`axi-align-coordinator-output` owns the envelope.** If it changes the envelope keys before
  this merges, `ActiveFeaturesEnvelope` must follow; the conformance test makes the mismatch loud.
- **Install mirrors.** `_generated/` lives under the bridge's `scripts/` and is copied by
  `install.sh` with the rest of the skill; `install.sh --check` covers it.

## Migration Plan

1. Promote the typed `features.yaml` and its acknowledgement (wp-contracts).
2. Land the route fix and conformance test (wp-api), the gate (wp-ci), and the generators and
   bridge helpers (wp-bridge) in parallel.
3. Integrate, replay the gate over recent history, write `decision.md` (wp-integration).

Rollback: revert the merge. No data, schema, or runtime-config changes are involved.

## Open Questions

- Should the gate eventually also cover `openspec/contracts/**/cli/*.yaml`? Out of scope here;
  noted for `decision.md`.
- Should the operations table be shared with `http_proxy.py` before a full client is considered?
  Deferred to the go/no-go.
