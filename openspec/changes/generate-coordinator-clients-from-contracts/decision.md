# Go / No-go: generate-coordinator-clients-from-contracts

**Verdict: GO, scoped.** Keep everything this change shipped, and roll the pattern out
**domain by domain, each rollout gated on first typing that domain's contract**. Do not
start the `http_proxy.py` regeneration or a Forge re-evaluation yet.

Recorded 2026-10-09, at the end of implementation, from the evidence below. Criteria come
from design D7 and the NFR table in `proposal.md`.

## What the pilot proved

The pilot set out to show whether generating from the hand-written contracts is worth it.
The strongest evidence is not the generator but **what the contract-first checks
found while it was built**:

| Defect | Found by | Status |
|---|---|---|
| `GET /features/active` shadowed by `GET /features/{feature_id}` (always 404) | Planning read; pinned by `test_feature_registry_http.py` and the shadowing check | Fixed |
| Contract said bare array; app returns the AXI envelope | Typing the contract | Fixed (contract) |
| All five feature responses were description-only, so nothing could check them | Typing the contract | Fixed (contract) |
| Register/deregister failure results return `null` `feature_id`/`action`; typed contract said `string` | Codex review of the typed contract | Fixed (contract) |
| `getFeature` contract omitted the API key the app enforces | Contract drift verification | Fixed (contract) |
| 26 further drift findings across 27 contracts (10 uncontracted routes, 3 unserved operations, 9 auth, 4 request-body) | Contract drift verification | Baselined with reasons |

Every one of these was latent and invisible to the hand-written parity tests.

## Scored criteria

| Criterion (D7 / NFR) | Target | Measured | Result |
|---|---|---|---|
| Existing bridge tests pass without expectation edits | 100% | 92/92 unchanged, 126 total with the 34 new | Met |
| Third-party imports reachable from the bridge at runtime | 0 | 0 (models under `TYPE_CHECKING`; operations table is stdlib; also imported under CPython 3.9.25) | Met |
| Generator determinism | byte-identical; `--check` exits 0 | Two consecutive `--check` runs exit 0; a test asserts byte identity | Met |
| Breaking-change job wall time on one contract | < 60 s | Gate step < 1 s; oasdiff install ~28 s (`go install`); dependency setup adds the rest | Met for the gate; the job's setup is the cost |
| `features.yaml` operations covered by response conformance | 5/5 | 5/5, 16 cases including failure shapes, 401, 404, 422 | Met |
| Operations with `x-traceability` after typing | 5/5 | 5/5; sweep exits 0 | Met |
| Gate false positives on 20 replayed contract edits | ≤ 1 | **Not measured** (see `deferred-tasks.md`); 1 real comparison: 0 false positives, 1 stale acknowledgement (a wrong guess of mine, which the gate correctly flagged) | Insufficient evidence |
| Hand-written lines removed per bridge domain | > 0 net, new helpers counted | Routing literals removed: 25. Bridge file: +152 / −25, because coverage grew from 2 to 5 operations. Per operation, method/path/auth/types are now generated | Mixed — see below |
| Time to add a typed operation | recorded | Not timed. The workflow is one contract edit, `generate_bindings.py`, and a thin helper (about 20 lines) | Recorded qualitatively |

### On the line-count criterion

As written ("> 0 net") it is not met: the bridge grew by 127 lines. That is the wrong
measure for this pilot, which deliberately *added* three helpers the bridge had never had.
The like-for-like number is the two pre-existing helpers, which each lost their hand-written
method, path, and capability literals (25 lines) and gained a typed payload. The real saving
appears only when a contract changes: today that is a regenerate and a `--check` in CI,
rather than a hand edit in up to four places that nothing verifies.

## What the follow-ups should be

1. **Per-domain rollout (GO).** For each bridge domain, in order of bridge usage
   (locks, work queue, handoffs, memory first): type its contract, regenerate, move its
   helpers onto `OPERATIONS`, add a conformance test, and delete its drift-baseline
   entries. One change per domain or small group. Contract typing is the dominant cost.
2. **Drift-baseline burn-down (GO).** Most of the 26 entries are contract-only edits,
   such as adding missing `security` to keyed reads. These are cheap, and each one
   shrinks the baseline the ratchet enforces.
3. **Gate replay (do first).** Complete deferred task 6.3 before the gate is relied on
   for promotions other than this change's.
4. **`http_proxy.py` via `openapi-python-client` (NOT YET).** It needs typed contracts
   for the domains it proxies; revisit after the rollout covers them.
5. **Forge (NOT YET).** Re-entry criteria unchanged: a released Python SDK target and a
   standalone breaking-change command. At v0.1.0 over Fern it adds a Node toolchain for
   output this pilot produces with two small Python generators.

## Known limitations carried forward

- `try_get_feature` on an unknown id returns `skipped` / `capability_unavailable`,
  because the bridge's shared response normalizer maps every 404 that way. The result is
  non-`ok` and never raises, as the spec requires, but the reason is misleading. Fixing
  it changes the shared normalizer for every helper and belongs to the rollout.
- datamodel-code-generator 0.83.0 warns that black and isort will become optional
  extras. They are pinned through `skills/uv.lock` today; a future bump must declare them.
- The gate's job installs oasdiff with `go install` on every run (~28 s). Caching the
  built binary keyed on `oasdiff.sum` is a cheap later optimisation.
