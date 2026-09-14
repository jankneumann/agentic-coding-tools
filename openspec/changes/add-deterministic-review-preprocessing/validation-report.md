# Validation Report

<!-- Date: 2026-09-14
     Commit: a76db177 (tip at report time; wp-integration lands on top)
     Branch: claude/alibaba-code-review-cli-p1p48p -->

## Phase Results

| Phase | Result | Details |
|-------|--------|---------|
| Unit / integration tests | pass | 1115 passed, 0 failed — `skills/tests/parallel-infrastructure`, `skills/tests/autopilot`, `skills/parallel-infrastructure/scripts/tests` |
| Lint | pass | `ruff check .` — all checks passed (rule set `E4,E7,E9,F`) |
| Install-asset parity | pass | `skills/install.sh --check` — portability validation passed |
| OpenSpec validation | pass | `openspec validate add-deterministic-review-preprocessing --strict` — valid |
| Fact-check precision (fixture, recorded transcript) | pass | 0/5 labeled-true findings removed, 5/5 labeled-false findings removed — see `skills/tests/parallel-infrastructure/test_fact_check_fixture.py` |
| Line-resolution floor (fixture) | pass | 8/8 anchored findings resolved (100%, floor is 90%) — see `skills/tests/parallel-infrastructure/test_line_resolver_fixture.py` |
| Fact-check precision (live vendors) | DEGRADED | Not checked: this implementation session has no live vendor CLI/API access (no network egress to codex/grok/claude/pi model endpoints beyond the coding-agent's own harness). The fixture-driven figure above is the deterministic proxy the design (D8) exists to provide in its place. A live run is a follow-up step — see "Live Validation Follow-Up" below. |
| Round token spend delta (`fact_check` on vs off) | DEGRADED | Not checked: requires a live multi-round `converge()` run against real vendor CLIs to compare `fact_check_tokens` against the round baseline. Same blocker as above. |

## Spec Compliance

Full requirement traceability lives in the OpenSpec change's `specs/` deltas
(`specs/skill-workflow/spec.md`, `specs/review-convergence-safety/spec.md`);
this proposal predates the `change-context.md` traceability-matrix
convention, so no separate matrix file exists for it.

**Summary**: all 8 ADDED and 7 MODIFIED requirements in `skill-workflow`,
and the 1 MODIFIED requirement in `review-convergence-safety`, have at
least one passing automated test exercising their scenarios (selection,
rule groups, line resolution, coverage, fact-check, OCR vendor, packet
metadata v2, ledger snippet matching, manifest fields). 0 gaps, 0 deferred
at the requirement level — the two DEGRADED rows above are fitness-function
*measurements* the design itself deferred to a live-vendor validation
step (D8, and the Fitness Functions table's Performance row), not
unimplemented requirements.

## Log Analysis

Not applicable — this change ships library/script code and test fixtures,
not a deployed service; there is no running process to collect logs from
at validation time.

## Live Validation Follow-Up

The two DEGRADED rows need a session with live vendor CLI access
(at minimum two of: claude, codex, grok, pi, antigravity) to fill in:

1. **Fact-check precision, live**: run `converge()` with `fact_check=True`
   against a real multi-vendor round on a change with known findings (the
   fixture set's diffs are a reasonable starting point, replacing the
   recorded transcript with a live economy-tier call), and record the
   true/false removal counts the same way `test_fact_check_fixture.py`
   does, but against live model output instead of the transcript.
2. **Token delta**: run the same round twice, once with `fact_check=True`
   and once with `fact_check=False`, and diff the round manifest's
   `fact_check_tokens` against total round tokens. The design's target
   (Fitness Functions table) is a rise of at most 15%.

Until that run happens, `fact_check` stays enabled by default (D6) on the
strength of the fixture-driven precision figure and the resilience
guarantee (`fact_check.run()` never raises and removes nothing on any
caller/parse failure — `test_fact_check.py::test_error_removes_nothing`
and the like) rather than a measured token cost.

## Result

**DEGRADED** — Every phase this session can check (tests, lint, install
mirror, OpenSpec strict validation, fixture-driven fact-check precision,
fixture-driven line-resolution floor) is green. Two fitness-function
measurements that need live vendor access are not checked and are named
above with what's missing. This is not a blocker to merging the
implementation itself — the design (D8) always scoped the live figures to
a validation-phase step outside deterministic CI — but the live run
should happen before treating the token-spend NFR as verified.
