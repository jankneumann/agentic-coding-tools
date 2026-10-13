# parallel-infrastructure Specification

## Purpose
TBD - created by archiving change judge-cross-vendor-finding-matching-in-consensus-synthesizer. Update Purpose after archive.
## Requirements
### Requirement: Judged Cross-Vendor Finding Matching

`ConsensusSynthesizer._match_all` MUST attempt a judged match, via
`system_one_decisions.decide()`, for candidate cross-vendor finding pairs
that share axis and file but are not resolved by the existing location or
snippet fast paths. Judged calls for all such pairs on one file MUST be
batched into a single `decide()` call carrying one `Noul` question per pair
over one shared per-file state. Pairs resolved by the location or snippet
fast paths MUST NOT trigger a `decide()` call.

When `system_one_decisions.decide()` is unavailable (not installed, or
returns `None`), matching for affected pairs MUST fall back to the existing
Jaccard token-similarity bands unchanged.

A match established only by the judged path MUST record `match_basis`
`"judged"`. A consensus finding whose match basis is `"judged"` MUST carry
`evidence_class` `"judgment"` regardless of its contributing findings' own
evidence classes, and MUST NOT be counted in `blocking_count`.

`MATCH_THRESHOLD` MUST be sourced from `review-rules.json`'s default layer
rather than a literal in the scoring path, for both `consensus_synthesizer.py`
and `review_ledger.py`.

#### Scenario: Fast-path pairs never call decide()

- **WHEN** two findings from different vendors match on the location+type or snippet fast path
- **THEN** `_match_all` resolves them without calling `system_one_decisions.decide()`

#### Scenario: Same-file, same-axis pairs are judged in one batched call

- **WHEN** a file has several candidate pairs unresolved by the fast paths, all sharing axis and file
- **THEN** exactly one `decide()` call is made for that file, carrying one Noul question per pair

#### Scenario: A judged match never raises blocking_count

- **WHEN** a judged-path match pairs two findings that are both deterministic evidence class
- **THEN** the resulting consensus finding's `evidence_class` is `"judgment"`
- **AND** it is not counted in `blocking_count`

#### Scenario: Decision helper unavailable falls back to Jaccard

- **WHEN** `system_one_decisions.decide()` returns `None` for a file's judgeable pairs
- **THEN** those pairs are scored by the existing Jaccard bands, unchanged

#### Scenario: MATCH_THRESHOLD has no literal in the scoring path

- **WHEN** `consensus_synthesizer.py` or `review_ledger.py` need the match threshold
- **THEN** the value is read from `review-rules.json`'s default layer, not a hardcoded float

### Requirement: OpenAI-Compatible Dispatcher Discovery

The review dispatcher SHALL construct an OpenAI-compatible adapter for configured `local` or
`openrouter` endpoints with a `base_url` after CLI and SDK discovery. A usable CLI SHALL retain
precedence over the endpoint adapter for the same agent.

#### Scenario: Endpoint-only agent is discoverable

- **WHEN** dispatch configuration contains a local/OpenRouter endpoint with no CLI or SDK block
- **THEN** review discovery SHALL return an OpenAI-compatible reviewer for that endpoint

#### Scenario: CLI retains precedence

- **WHEN** an agent has both a usable CLI and an OpenAI-compatible endpoint
- **THEN** review discovery SHALL select the CLI tier first

### Requirement: Dispatchable Vendor Verification

`review_dispatcher.py --check-vendors` SHALL count a vendor lane as available for a mode only after a dry invocation for that mode succeeds: the adapter's declared no-op command (for a CLI lane, `<cli> --version`; for an SDK or API lane, the adapter's own authenticated no-op such as a model-list call) run with a 10-second timeout. Credentials MAY be read only inside the adapter's existing credential path, and the probe SHALL NOT print, log, or return any environment value or credential. With `--json` it SHALL print `{"modes": {<mode>: {"verified": [...], "unverified": [{"vendor", "reason"}]}}, "probe_command": "<argv>"}` and keep its existing exit codes (0 at quorum, 2 below quorum or on probe failure); when the roster cannot be resolved it SHALL print `{"error": "<reason>", "modes": {}}` and exit 2.

#### Scenario: A listed vendor without its CLI is unverified
- **WHEN** `agents.yaml` lists `codex` for mode `review` and no `codex` executable is on `PATH`
- **THEN** `--check-vendors --json` SHALL list `codex` under `unverified` with reason `cli_not_found`, and SHALL NOT count it toward `--min-vendors`

#### Scenario: A hanging dry invocation is unverified
- **WHEN** a lane's dry invocation does not exit within 10 seconds
- **THEN** the lane SHALL be `unverified` with reason `probe_timeout`

#### Scenario: The probe never discloses credentials
- **WHEN** the test sets `ANTHROPIC_API_KEY=sk-test-SENTINEL-1234567890` and `OPENAI_API_KEY=sk-test-SENTINEL-0987654321` and runs `--check-vendors --json`
- **THEN** neither sentinel value SHALL appear in stdout, stderr, or the JSON, and no `env` or `printenv` subprocess SHALL have been spawned

