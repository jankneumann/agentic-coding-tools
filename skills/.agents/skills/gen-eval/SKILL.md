---
name: gen-eval
description: Run generator-evaluator testing against live services
category: Testing
tags: [testing, gen-eval, evaluation, scenarios, generator, evaluator]
triggers:
  - "gen eval"
  - "run gen eval"
  - "generator evaluator test"
  - "run gen-eval"
  - "gen-eval testing"
---

# Gen-Eval

Run the generator-evaluator testing framework against live or local services. Generates test scenarios from interface descriptors, executes them, and evaluates results against expected behavior.

## Arguments

`$ARGUMENTS` - Optional flags:
- `--descriptor <path>` — Path to interface descriptor YAML (auto-detected if omitted)
- `--mode <mode>` (default: `template-only`) — `template-only`, `cli-augmented`, or `sdk-only`
- `--cli-command <cmd>` (default: `claude`) — CLI tool for cli-augmented mode
- `--time-budget <minutes>` (default: `60`) — Time budget for CLI mode
- `--sdk-budget <usd>` — USD budget cap for SDK mode
- `--max-iterations <n>` (default: `1`) — Feedback loop iterations
- `--parallel <n>` (default: `5`) — Concurrent scenario execution
- `--changed-features-ref <git-ref>` — Git ref for change detection
- `--categories <cat1> [cat2 ...]` — Filter to specific categories
- `--report-format <format>` (default: `both`) — `markdown`, `json`, or `both`
- `--output-dir <path>` (default: `.`) — Report output directory
- `--no-services` — Skip service startup/teardown
- `--verbose` — Enable verbose output

## Steps

### 1. Auto-Detect Descriptor

If `--descriptor` is not provided, find the nearest descriptor YAML:

```bash
DESCRIPTOR=$(find . -path "*/evaluation/gen_eval/descriptors/*.yaml" -type f 2>/dev/null | head -1)

if [ -z "$DESCRIPTOR" ]; then
  echo "ERROR: No gen-eval descriptor found. Provide --descriptor <path> or create one with /gen-eval-scenario."
  exit 1
fi
echo "Auto-detected descriptor: $DESCRIPTOR"
```

### 2. Detect Project Root and Activate Venv

```bash
# Find the project root (directory containing the descriptor's evaluation/ parent)
PROJECT_ROOT=$(dirname "$(dirname "$(dirname "$(dirname "$DESCRIPTOR")")")")
echo "Project root: $PROJECT_ROOT"

# Activate the project venv
if [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
  PYTHON="$PROJECT_ROOT/.venv/bin/python"
else
  PYTHON="python3"
fi
```

### 3. Parse Mode and Build Command

Parse `$ARGUMENTS` for mode and flags. Build the CLI command:

```bash
# Defaults
MODE="${MODE:-template-only}"
PARALLEL="${PARALLEL:-5}"
MAX_ITER="${MAX_ITER:-1}"
REPORT_FORMAT="${REPORT_FORMAT:-both}"
OUTPUT_DIR="${OUTPUT_DIR:-.}"

CMD="$PYTHON -m evaluation.gen_eval --descriptor $DESCRIPTOR --mode $MODE --parallel $PARALLEL --max-iterations $MAX_ITER --report-format $REPORT_FORMAT --output-dir $OUTPUT_DIR"

# Append optional flags from arguments
if [ -n "$TIME_BUDGET" ]; then CMD="$CMD --time-budget $TIME_BUDGET"; fi
if [ -n "$SDK_BUDGET" ]; then CMD="$CMD --sdk-budget $SDK_BUDGET"; fi
if [ -n "$CLI_COMMAND" ]; then CMD="$CMD --cli-command $CLI_COMMAND"; fi
if [ -n "$CHANGED_REF" ]; then CMD="$CMD --changed-features-ref $CHANGED_REF"; fi
if [ -n "$CATEGORIES" ]; then CMD="$CMD --categories $CATEGORIES"; fi
if [ "$NO_SERVICES" = "true" ]; then CMD="$CMD --no-services"; fi
if [ "$VERBOSE" = "true" ]; then CMD="$CMD --verbose"; fi
```

### 4. Run Gen-Eval

Execute from the project root:

```bash
cd "$PROJECT_ROOT"
echo "Running: $CMD"
$CMD
EXIT_CODE=$?
```

### 5. Report Results

After execution, display a summary:

- If reports were generated, read and summarize the markdown report
- Show pass rate, coverage %, and any failures
- If `EXIT_CODE != 0`, highlight failing scenarios and suggest `/gen-eval-scenario` for authoring targeted scenarios

```bash
if [ -f "$OUTPUT_DIR/gen-eval-report.md" ]; then
  echo ""
  echo "=== Gen-Eval Report ==="
  cat "$OUTPUT_DIR/gen-eval-report.md"
fi
```

## Quick Start

The simplest invocation — auto-detects the descriptor and runs template-only:

```bash
/gen-eval
```

With CLI-augmented generation (subscription-covered):

```bash
/gen-eval --mode cli-augmented --time-budget 30
```

Against specific categories:

```bash
/gen-eval --categories lock-lifecycle auth-boundary
```

## Integration Points

- **`/validate-feature`**: Gen-eval runs as phase `4b` (between smoke and e2e). Auto-detected when descriptors exist.
- **`/explore-feature`**: Gen-eval report signals (failing interfaces, coverage gaps) feed into feature opportunity ranking.
- **`/gen-eval-scenario`**: Create new scenario YAML files interactively.
- **`make gen-eval`**: Makefile shorthand for the most common invocation.

## Output

- `gen-eval-report.md` — Markdown report with pass/fail summary
- `gen-eval-report.json` — Machine-readable results
- `gen-eval-metrics.json` — Per-scenario metrics for pipeline integration
- Exit code 0 if pass rate meets threshold (default 95%), 1 otherwise
