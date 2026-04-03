---
name: gen-eval-scenario
description: Create gen-eval scenario YAML files interactively
category: Testing
tags: [testing, gen-eval, scenarios, authoring, yaml]
triggers:
  - "gen eval scenario"
  - "create gen eval scenario"
  - "new gen eval scenario"
  - "write gen eval scenario"
  - "gen-eval scenario"
  - "add scenario"
  - "create scenario"
---

# Gen-Eval Scenario

Interactively create gen-eval scenario YAML files. Reads the project's interface descriptor, suggests categories and interfaces, and produces validated scenario YAML.

## Arguments

`$ARGUMENTS` - Optional:
- `--descriptor <path>` — Path to interface descriptor YAML (auto-detected if omitted)
- `--category <name>` — Target category (e.g., `lock-lifecycle`, `auth-boundary`)
- `--interfaces <list>` — Transports to exercise (e.g., `http,mcp,db`)
- `--type success|failure|cross-interface` — Scenario type
- `--output <path>` — Output file path (auto-generated if omitted)

## Steps

### 1. Auto-Detect Descriptor

```bash
DESCRIPTOR=$(find . -path "*/evaluation/gen_eval/descriptors/*.yaml" -type f 2>/dev/null | head -1)

if [ -z "$DESCRIPTOR" ]; then
  echo "ERROR: No gen-eval descriptor found."
  echo "Create a descriptor first, or provide --descriptor <path>."
  # Show descriptor format reference and exit
fi
```

Read the descriptor to understand available services, endpoints, and transports.

### 2. Analyze Existing Scenarios

```bash
SCENARIO_DIR=$(dirname "$DESCRIPTOR")/../scenarios
```

Scan existing scenarios to understand:
- Which categories have scenarios and how many
- Which interfaces are under-tested (appear in descriptor but few scenarios exercise them)
- Common patterns used (cleanup steps, variable capture, cross-interface verification)

Present a coverage summary to the user:

```
Category            Scenarios  Coverage
lock-lifecycle      11         85%
auth-boundary       10         71%
cross-interface     17         65%
work-queue          12         80%
...
```

### 3. Gather Scenario Intent

If `--category` and `--type` were not provided, ask the user:

1. **What are you testing?** — Map to a category. Suggest under-tested categories from step 2.
2. **Success or failure path?** — Success scenarios verify happy paths. Failure scenarios verify error handling, edge cases, and security boundaries.
3. **Which transports?** — Suggest transports based on the category. Cross-interface scenarios should use 2+ transports.
4. **What specific behavior?** — A one-line description of the scenario's goal.

### 4. Select Relevant Endpoints

Based on the category and transports chosen, read the descriptor and list the relevant endpoints/tools/commands:

```
Available HTTP endpoints for 'locks':
  POST /locks/acquire    — Acquire an exclusive file lock
  POST /locks/release    — Release an existing file lock
  GET  /locks/status/{path} — Check lock status

Available MCP tools for 'locks':
  acquire_lock  — Acquire a file lock
  release_lock  — Release a file lock
  check_locks   — Check lock status

Available CLI commands for 'locks':
  lock status   — Show lock status
  lock release  — Release a lock
```

Let the user pick which endpoints to include in the scenario steps.

### 5. Generate Scenario YAML

Build the scenario YAML following the `Scenario` model schema. Key rules:

**Schema reference** (from `evaluation/gen_eval/models.py`):

```yaml
# Required fields
id: "<category>-<descriptive-slug>"        # unique, kebab-case
name: "<Human-readable scenario name>"
description: "<What this scenario tests and why>"
category: "<category-name>"                # must match a scenarios/ subdirectory
priority: 1|2|3                            # 1=critical, 2=important, 3=coverage
interfaces: ["http", "mcp", "cli", "db"]   # transports exercised

# Steps (ordered sequence)
steps:
  - id: <step_id>                          # unique within scenario
    transport: http|mcp|cli|db|wait
    # HTTP-specific
    method: GET|POST|PUT|DELETE
    endpoint: /path
    body: { key: value }
    headers: { X-Custom: value }
    # MCP-specific
    tool: tool_name
    params: { key: value }
    # CLI-specific
    command: "subcommand --flag value"
    # DB-specific (SELECT only, for state verification)
    sql: "SELECT ... FROM ..."
    # Wait-specific
    seconds: 1.0
    # Expectations (at least one per step)
    expect:
      status: 200                          # HTTP status code
      exit_code: 0                         # CLI exit code
      body: { key: expected_value }        # JSONPath assertions on response
      rows: 1                              # DB row count
      row: { column: value }               # DB row assertions
      error_contains: "message"            # Error substring match
      not_empty: true                      # Response must not be empty
    # Variable capture (for use in later steps)
    capture:
      var_name: "$.json.path"              # JSONPath → variable

# Cleanup (optional, always runs even on failure)
cleanup:
  - id: cleanup_step
    transport: http
    # ... same fields as steps

# Tags (for filtering)
tags: ["locks", "success", "basic"]
```

**Best practices for scenario authoring:**

1. **Always include cleanup steps** for scenarios that create state (locks, tasks, memories). Cleanup failures are warnings, not errors.
2. **Use variable capture** when a step produces an ID needed by later steps (e.g., `capture: { task_id: "$.task_id" }` then `body: { task_id: "{{ task_id }}" }`).
3. **Verify state in DB** after mutations — don't trust the API response alone.
4. **Cross-interface scenarios** should perform an action via one transport and verify via another (e.g., acquire lock via HTTP, check via MCP, verify in DB).
5. **Failure scenarios** should assert error conditions: `status: 4xx`, `error_contains: "..."`, `body: { success: false }`.
6. **Keep scenarios focused** — test one behavior per scenario. A scenario with 10+ steps may be doing too much.
7. **Use priority wisely**: 1 = critical paths (auth, locks, data integrity), 2 = important features, 3 = coverage/edge cases.

### 6. Validate the Scenario

Before writing, validate the generated YAML against the Pydantic model:

```bash
cd <project-root>
.venv/bin/python -c "
import yaml
from evaluation.gen_eval.models import Scenario

with open('/dev/stdin') as f:
    data = yaml.safe_load(f)
scenario = Scenario(**data)
print(f'Valid scenario: {scenario.id} ({len(scenario.steps)} steps, {len(scenario.interfaces)} transports)')
" <<< "$SCENARIO_YAML"
```

If validation fails, show the error and fix the YAML before writing.

### 7. Write and Confirm

Write the validated YAML to the appropriate location:

```
<scenarios-dir>/<category>/<scenario-id>.yaml
```

After writing:
1. Show the full YAML for review
2. Run a dry validation to confirm it loads
3. Suggest running `/gen-eval --categories <category>` to test the new scenario

## Example Session

```
User: /gen-eval-scenario --category auth-boundary --type failure

Agent: Reading descriptor... 10 auth-related endpoints found.
       Existing auth-boundary scenarios: 10 (71% coverage).
       Under-tested: policy denial with Cedar, trust level escalation.

       I'll create a failure scenario for trust level escalation.

       Generated: auth-boundary/trust-level-escalation.yaml
       - 5 steps across http and db transports
       - Tests: low-trust agent attempts high-trust operation → blocked
       - Cleanup: removes test agent profile

       Run it: /gen-eval --categories auth-boundary
```

## Output

- New scenario YAML file at `<scenarios-dir>/<category>/<id>.yaml`
- Validation confirmation
- Suggested next command to run the scenario
