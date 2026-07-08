# Tasks: Add Trust Posture Contract File

> Change ID: `add-trust-posture-contract-file`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## 1. Design and spec

- [x] 1.1 Rewrite `proposal.md` (Why / What Changes / Out of Scope / Success Criteria)
- [x] 1.2 Write `design.md` (file-format choice, per-gate vs global, absent-file=block guarantee, ri-05 API surface, alternatives)
- [x] 1.3 Add `specs/trust-posture/spec.md` delta (new capability, ADDED requirements + scenarios)
- [x] 1.4 Justify new `trust-posture` capability vs extending `skill-workflow` (design D7)

## 2. Contract file and schema

- [x] 2.1 Author `TRUST_POSTURE.template.md` at repo root (all gates `block`, documented prose body, worked example)
- [x] 2.2 Represent all eight gates in the template
- [x] 2.3 Add `openspec/schemas/trust-posture.schema.json` (restricted gate keys, notify_with_timeout conditional)
- [x] 2.4 Confirm template front matter validates against the schema

## 3. Loader / validator library

- [x] 3.1 Implement `skills/shared/trust_posture.py` — `load_posture`, `TrustPosture.disposition_for`, `validate_posture_file`
- [x] 3.2 Define `Gate` (8), `Disposition` (3), `DefaultAction` (2), `GateDisposition`, `PostureValidationError`
- [x] 3.3 Guarantee absent-file → all `block` via a single shared `BLOCK` constant + fail-closed `dict.get`
- [x] 3.4 Enforce: unknown gate / unknown disposition raise; `notify_with_timeout` requires positive-int `timeout_seconds` + `default_action`; timeout/default rejected on `auto`/`block`
- [x] 3.5 Read fresh each call (hot-reloadable); no caching
- [x] 3.6 Provide `python -m shared.trust_posture validate|show` CLI
- [x] 3.7 Mirror the module into `.claude/skills/shared/` and `.agents/skills/shared/` (canonical source is `skills/shared/`)

## 4. Tests

- [x] 4.1 Valid contract loads
- [x] 4.2 All eight gates enumerated + representable (incl. template validates)
- [x] 4.3 Absent file → every gate blocks; omitted gate → block
- [x] 4.4 Each of the four disposition configurations round-trips
- [x] 4.5 Unknown gate fails; unknown disposition fails
- [x] 4.6 `notify_with_timeout` missing/malformed/bool/zero/negative timeout fails; missing/unknown default_action fails; timeout-on-block fails
- [x] 4.7 Structural failures (schema_version, front-matter fence) + one-pass multi-error collection
- [x] 4.8 `disposition_for` raises on unknown gate name; string/enum equivalence; explicit path override
- [x] 4.9 Cross-check JSON schema vs loader agree (template + negatives)

## 5. Validate

- [x] 5.1 `openspec validate add-trust-posture-contract-file --strict` passes
- [x] 5.2 `skills/.venv/bin/python -m pytest skills/shared/tests/test_trust_posture.py` green

## 6. Review and merge

- [ ] 6.1 Orchestrator review
- [ ] 6.2 Merge
