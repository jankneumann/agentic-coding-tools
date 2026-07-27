# Dogfooding gen-eval with gen-eval

gen-eval evaluating its own published CLI surface.

```bash
make -C packages/gen-eval dogfood
```

Runs at `--fail-threshold 1.0` — every scenario must pass. This is a contract
suite, not a sample.

## Why this exists

Everything under `tests/` imports `gen_eval` and drives Python objects. That
is the right shape for unit tests and the wrong shape for catching integration
defects, as UP-1 demonstrated: the console script was broken in *every*
release and a 551-test suite never noticed, because no test had ever executed
the installed executable.

This suite drives the descriptor loader, template generator, CLI transport,
evaluator, orchestrator lifecycle and report writer in one pass, against the
console script resolved from `PATH`. A break anywhere in that chain fails
here.

It is also gen-eval's only genuinely CLI-only descriptor, which makes it the
empirical case for UP-4.

## Layout

```
evaluation/
  descriptor.yaml              # GENERATED from the CLI contract — no startup block
  coverage-exclusions.yaml     # units this suite cannot exercise, each with a reason
  scenarios/
    cli-entrypoint.yaml        # UP-1: the console script and its exit codes
    contract-version.yaml      # UP-2: the published schema contract probe
    self-run.yaml              # UP-3 + UP-4: gen-eval driving gen-eval
    flag-surface.yaml          # D11: contracted flags with an assertable consequence
  fixtures/
    no-scenarios-descriptor.yaml    # inner descriptor for the self-run
    failing-startup-descriptor.yaml # startup that fails — the --no-services control
    empty/                          # deliberately empty scenario dir
  .reports/                    # run output (gitignored)
```

## What each scenario pins

| Scenario | Asserts | Regression it catches |
|---|---|---|
| `cli-help-exits-zero` | `--help` exits 0 and renders usage | UP-1: the console script raising `TypeError` on every invocation |
| `cli-missing-required-descriptor-exits-2` | exit 2 | `parse_args()` no longer reached |
| `cli-invalid-openspec-change-exits-64` | exit 64 | the `EX_USAGE` override lost; path traversal accepted |
| `cli-valid-openspec-change-is-not-a-usage-error` | exit ≠ 64 | negative control — a parser rejecting everything |
| `contract-version-probe-exits-zero` | exit 0 without `--descriptor` | the version probe stops short-circuiting the required flag |
| `contract-version-value-is-pinned` | version is exactly `2` | an unannounced contract bump |
| `self-run-without-startup-block` | runs with no `startup:` and no `--no-services` | UP-4 regression making the block mandatory again |
| `self-run-zero-scenarios-cannot-pass` | exit 1 at `--fail-threshold 0` | UP-3 vacuous-pass guard removed |
| `cli-verbose-announces-the-declared-surface` | "descriptor loaded — N services, M interfaces" | a regression to an empty declared surface |
| `cli-min-coverage-rejects-a-rate` | exit 2 on `0.8` | a rate read as a percent, i.e. a 0.8% floor every run clears |
| `cli-report-format-json-writes-only-json` | the markdown report line is **absent** | `--report-format` stops suppressing anything |
| `cli-mode-rejects-an-unknown-value` | exit 2 on an unknown mode | the enum silently falling back to the default |
| `cli-no-services-skips-startup` | reaches the run despite a failing startup command | `--no-services` stops skipping startup |

## The acceptance gate is completeness, not a percentage (D11)

`make dogfood` runs a second command after the evaluation:

```bash
uv run python scripts/check_coverage_completeness.py \
    --report evaluation/.reports/gen-eval-report.json \
    --exclusions evaluation/coverage-exclusions.yaml
```

Every contracted coverage unit must be exercised by a scenario **or** carry a
written reason in `coverage-exclusions.yaml`. The percentage is printed and is
not the gate: "58.8% covered" does not say whether the missing 41% is
`--verbose` or `--fail-threshold`, and an 80% floor on this surface would need
14 of 17 flags exercised — a gate that could never pass, which gets disabled
exactly as fast as one that could never fail.

### What "exercised" has to mean

Passing a flag and watching the process survive is not exercise. A flag that is
only parsed contributes a number to the percentage and no evidence, which is
the laundering D11 exists to stop.

The operational test: **remove the flag under test from the scenario's args and
the scenario must fail.** Three of the five `flag-surface.yaml` scenarios once
passed either way — they asserted output the default run produced too
(`mode=template-only` *is* the default; `gen-eval-report.json` is written under
`--report-format both` as well). Round 8 of the multi-vendor review caught it.

Two things came out of the fix and both are load-bearing:

- **`ExpectBlock.error_excludes`** — assert a substring is ABSENT. Flags whose
  effect is to *remove* output cannot be discriminated by a presence assertion,
  so the suite could not express the check it needed. Guarded by
  `tests/test_expect_error_excludes.py`.
- **`fixtures/failing-startup-descriptor.yaml`** — a startup command that always
  fails and a health check that always passes. `--no-services` was previously
  asserted against a descriptor with no startup block at all, where skipping
  startup and having nothing to skip are indistinguishable.

To re-run the discrimination check by hand, delete a flag from a scenario's
`args:` and run `make dogfood`. A green run means that scenario is not
exercising its flag, and the unit belongs in `coverage-exclusions.yaml` with an
honest reason instead.

## Findings this suite surfaced

Dogfooding is worth the effort only if it is allowed to report what it finds.
Three things turned up on the first run.

### 1. stderr was conflated with transport failure — fixed (UP-5)

`CliClient` assigned stderr to `StepResult.error`, and `Evaluator` short-circuits
to `status="error"` on any `result.error` *before* comparing expectations. Any
CLI that printed diagnostics to stderr was therefore an unconditional error
regardless of its exit code.

The consequence: `expect.exit_code` could not assert a non-zero exit, and
`expect.error_contains` was unreachable on the CLI transport — two fields that
exist specifically to assert failures. Three of the eight scenarios below
produced exactly the right exit codes (2, 64, 1) and were all reported as
errors.

Fixed: `error` is now reserved for the case where the command could not be run
at all. When the process ran, stderr is surfaced at `body.stderr`, which keeps
it assertable (`error_contains` already searches the body). Guarded by
`tests/test_cli_transport_stderr.py`.

### 2. Scalar stdout is JSON-parsed — recorded, not changed

`CliClient` runs `json.loads()` on stdout before falling back to
`{"raw": "<stdout>"}`. `"1"` is valid JSON, so `--print-contract-version`
yields `{"result": 1}` — an **int**, not the string `"1"`. A version like
`"v1"` or `"1.2.0-rc"` would land under `raw` instead, so the assertion key
changes with the *value*.

Not changed here: the parse-JSON-if-possible behaviour is load-bearing for
CLIs with a `--json` flag, which is the common case. But it is a sharp edge
for scalar output, and it means a consumer pinning the contract version from a
scenario must know which key to use. Worth raising upstream if the contract
version ever becomes non-numeric.

### 3. `--descriptor` pointing at a missing file crashes with a traceback

```
$ gen-eval --descriptor does-not-exist.yaml
Traceback (most recent call last):
  ...
FileNotFoundError: [Errno 2] No such file or directory: 'does-not-exist.yaml'
```

Exit code is 1, so `self-run` scenarios can assert it, but a raw traceback is
not an interface. A missing descriptor is the single most likely operator
error and deserves a clean message and a documented exit code.

Not fixed here — it is a CLI behaviour change beyond the scope of the upstream
handoff, and picking the right exit code (2? 66/`EX_NOINPUT`?) is a contract
decision. Recorded for a follow-up.

## `descriptor.yaml` is generated — do not edit it

It is derived from gen-eval's own CLI contract at
`openspec/contracts/gen-eval-framework/cli/gen-eval.yaml`:

```bash
uv run python scripts/generate_tool_descriptor.py           # write
uv run python scripts/generate_tool_descriptor.py --check   # CI gate
```

The contract is the declared surface (D1). Editing the artifact instead of the
contract does not change what the surface *is*; it makes the artifact disagree
with it, which is what `--check` fails on.

Deliberately absent from the generated file: a `startup:` block. There is
nothing to start — this is the empirical case for UP-4, which made startup
optional. Before that, this descriptor carried a no-op `command`, a no-op
`teardown` and a `health_check` URL that had to genuinely succeed: three lies
to satisfy a schema.

It also lives outside `src/` on purpose. Consumer evaluation data must not ship
inside the distributed package — see `tests/test_sdist_contents.py`.

## Resolved: flag-only CLIs are now nameable

**This limitation is closed.** Recorded here because the shape of the fix is
the reason the coverage numbers moved.

`Evaluator._extract_interfaces` used to derive a CLI identifier only from the
words in `step.command` *before the first flag* — the `cli:lock status` shape.
gen-eval's own CLI is one flat command with flags and no subcommands, so there
was nothing to name. `descriptor.yaml` declared `commands: []`,
`interfaces_tested` was empty on every verdict, `coverage_pct` was `0.0`, and
`unevaluated_interfaces` was `[]` **vacuously** — nothing had been declared.

That last point was the sharp end: a consumer asserting
`unevaluated_interfaces == []` as a coverage gate (which is what ri-06 does)
got a free pass on any flag-only project. Not a wrong assertion — a gap in the
interface *model* underneath it.

D3 closes it by making the **flag** the tool archetype's coverage unit, so a
flat CLI declares `cli:--descriptor`, `cli:--mode` and so on. gen-eval's own
surface is 17 such units rather than 0, and the drift guard refuses to treat an
empty declared surface as coverage at all.
