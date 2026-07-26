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
  descriptor.yaml              # gen-eval's descriptor for gen-eval — no startup block
  scenarios/
    cli-entrypoint.yaml        # UP-1: the console script and its exit codes
    contract-version.yaml      # UP-2: the published schema contract probe
    self-run.yaml              # UP-3 + UP-4: gen-eval driving gen-eval
  fixtures/
    no-scenarios-descriptor.yaml   # inner descriptor for the self-run
    empty/                         # deliberately empty scenario dir
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

## Known limitation: flag-only CLIs have no nameable interfaces

`Evaluator._extract_interfaces` derives a CLI interface identifier from the
words in `step.command` *before the first flag* — the `cli:lock status` shape.
gen-eval's own CLI is a single flat command with flags and no subcommands, so
there is nothing to name.

Consequences for any flag-only project:

- `descriptor.yaml` declares `commands: []`
- `interfaces_tested` is empty on every verdict
- `per_interface` is `{}` and `coverage_pct` is `0.0`
- `unevaluated_interfaces` is `[]` — **vacuously**, because nothing was declared

That last point matters: a consumer asserting `unevaluated_interfaces == []`
as a coverage gate (which is what ri-06 does) gets a free pass on a flag-only
project. The assertion is sound for projects whose interfaces are nameable;
this is a gap in the interface *model*, not in the assertion.

Scenario-level pass/fail is unaffected, which is why this suite is still
meaningful. Left as-is rather than stretching the model mid-handoff.
