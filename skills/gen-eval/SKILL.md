---
name: gen-eval
description: Run generator-evaluator testing against live services
category: Git Workflow
tags: [testing, gen-eval, evaluation, scenarios, generator, evaluator]
triggers:
  - "gen eval"
  - "run gen eval"
  - "generator evaluator test"
  - "run gen-eval"
  - "gen-eval testing"
---

# Gen-Eval

Run the generator-evaluator testing framework against live or local services. Generates test scenarios from interface descriptors, executes them against running services, and evaluates results against expected behavior.

## Arguments

`$ARGUMENTS` - Required and optional flags:
- `--descriptor <path>` (required) — Path to interface descriptor YAML
- `--mode <mode>` (default: `template-only`) — Generator mode: `template-only`, `cli-augmented`, or `sdk-only`
- `--cli-command <cmd>` (default: `claude`) — CLI tool for cli-augmented mode (`claude` or `codex`)
- `--time-budget <minutes>` (default: `60`) — Time budget in minutes for CLI mode
- `--sdk-budget <usd>` — USD budget cap for SDK mode
- `--max-iterations <n>` (default: `1`) — Number of feedback loop iterations
- `--parallel <n>` (default: `5`) — Concurrent scenario execution count
- `--changed-features-ref <git-ref>` — Git ref for change detection (filters to changed features only)
- `--categories <cat1> [cat2 ...]` — Filter to specific scenario categories
- `--report-format <format>` (default: `both`) — Output format: `markdown`, `json`, or `both`
- `--output-dir <path>` (default: `.`) — Directory for report output
- `--change-id <id>` — OpenSpec change-id (for validate-feature integration)
- `--verbose` — Enable verbose output
- `--no-services` — Skip service startup/teardown (assume services already running)

## Prerequisites

- Python 3.11+ with the `agent-coordinator` package installed (`cd agent-coordinator && uv sync --all-extras`)
- Interface descriptor YAML file for the target project
- For `template-only` mode: no additional dependencies
- For `cli-augmented` mode: `claude` or `codex` CLI installed and configured
- For `sdk-only` mode: API key configured for the target SDK

## Usage Examples

### Basic template-only run

```bash
cd agent-coordinator
python -m evaluation.gen_eval \
  --descriptor evaluation/gen_eval/descriptors/coordinator-api.yaml \
  --mode template-only \
  --output-dir /tmp/gen-eval-reports
```

### CLI-augmented with change detection

```bash
python -m evaluation.gen_eval \
  --descriptor evaluation/gen_eval/descriptors/coordinator-api.yaml \
  --mode cli-augmented \
  --cli-command claude \
  --time-budget 30 \
  --changed-features-ref main \
  --verbose
```

### SDK-only with budget cap

```bash
python -m evaluation.gen_eval \
  --descriptor evaluation/gen_eval/descriptors/coordinator-api.yaml \
  --mode sdk-only \
  --sdk-budget 5.00 \
  --max-iterations 3 \
  --parallel 10
```

### Filter to specific categories

```bash
python -m evaluation.gen_eval \
  --descriptor evaluation/gen_eval/descriptors/coordinator-api.yaml \
  --categories auth crud error-handling \
  --report-format markdown
```

## How It Works

1. **Load descriptor** — Parses the interface descriptor YAML that defines features, transports, and scenario templates
2. **Create generator** — Based on `--mode`, selects template-based, CLI-augmented, or SDK-only scenario generation
3. **Generate scenarios** — Produces concrete test scenarios from descriptor feature definitions
4. **Execute scenarios** — Runs scenarios concurrently (up to `--parallel`) against live services
5. **Evaluate results** — Compares actual responses against expected behavior using evaluator rules
6. **Feedback loop** — If `--max-iterations > 1`, feeds failures back to the generator for refinement
7. **Write reports** — Produces markdown and/or JSON reports with pass rates, timing, and failure details

## Integration with validate-feature

Gen-eval runs as an optional `gen-eval` phase in `/validate-feature`. When a descriptor file exists for the project, validate-feature automatically invokes gen-eval in `template-only` mode between the smoke and e2e phases.

- **Phase name:** `gen-eval`
- **Criticality:** Non-critical (failure does not block validation)
- **Auto-detection:** Runs when `evaluation/gen_eval/descriptors/*.yaml` files exist
- **Default mode:** `template-only` (no CLI or SDK dependencies required)

To include gen-eval in a validation run:

```bash
/validate-feature <change-id> --phase smoke,gen-eval,e2e
```

Or it runs automatically when descriptors are detected during a full validation pass.

## Output

- Markdown report: `<output-dir>/gen-eval-report.md`
- JSON report: `<output-dir>/gen-eval-report.json`
- Exit code 0 if pass rate meets threshold, 1 otherwise
- When run via validate-feature, results appear in the validation report under the gen-eval phase
