---
name: validate-feature
description: Deploy locally, run behavioral tests, check CI/CD, and verify OpenSpec spec compliance
category: Git Workflow
tags: [openspec, validation, deployment, e2e, playwright]
triggers:
  - "validate feature"
  - "validate deployment"
  - "test deployment"
  - "verify feature"
  - "run validation"
---

# Validate Feature

Deploy the feature locally with DEBUG logging, run behavioral tests against live services, check CI/CD status, and verify OpenSpec spec compliance. Produces a structured validation report and posts it to the PR.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (required), optionally followed by flags:
- `--skip-e2e` or `--skip-playwright` — skip the Playwright E2E phase
- `--skip-ci` — skip the CI/CD status check
- `--phase <name>[,<name>]` — run only specified phases (e.g., `--phase smoke,e2e`)

Valid phase names: `deploy`, `smoke`, `e2e`, `spec`, `logs`, `ci`

## Prerequisites

- Feature branch `openspec/<change-id>` exists with implementation commits
- Docker/docker-compose installed and running (for Deploy phase)
- Approved OpenSpec proposal exists at `openspec/changes/<change-id>/`
- Run `/implement-feature` first if no implementation exists

## Steps

### 1. Determine Change ID and Configuration

```bash
# Parse change-id from argument or current branch
BRANCH=$(git branch --show-current)
CHANGE_ID=${ARGUMENTS%% --*}  # Everything before first flag
CHANGE_ID=${CHANGE_ID:-$(echo $BRANCH | sed 's/^openspec\///')}

# Detect if running in a worktree and resolve OpenSpec path
GIT_COMMON=$(git rev-parse --git-common-dir)
if [[ "$GIT_COMMON" == ".git" ]]; then
  OPENSPEC_PATH="openspec"
  PROJECT_ROOT=$(git rev-parse --show-toplevel)
else
  MAIN_REPO="${GIT_COMMON%%/.git*}"
  OPENSPEC_PATH="$MAIN_REPO/openspec"
  PROJECT_ROOT="$MAIN_REPO"
fi
```

Parse flags from `$ARGUMENTS`:
- `--skip-e2e` or `--skip-playwright` → set SKIP_E2E=true
- `--skip-ci` → set SKIP_CI=true
- `--phase <names>` → set PHASES to comma-separated list; only run those phases

If `--phase` is provided, only the listed phases execute. If `--phase` includes phases other than `deploy`, assume services are already running (skip deploy and teardown).

### 2. Verify Prerequisites

```bash
# Verify on feature branch
git branch --show-current  # Should be openspec/<change-id>

# Verify proposal exists
openspec show $CHANGE_ID

# Verify implementation commits exist
COMMIT_COUNT=$(git log --oneline main..HEAD | wc -l)
if [ "$COMMIT_COUNT" -eq 0 ]; then
  echo "ERROR: No implementation commits found on this branch."
  echo "Run /implement-feature $CHANGE_ID first."
  exit 1
fi

# Check Docker availability (only if Deploy phase will run)
if docker info > /dev/null 2>&1; then
  echo "Docker is available"
else
  echo "ERROR: Docker is not available. Install Docker Desktop or start the Docker daemon."
  echo "  macOS: brew install --cask docker"
  echo "  Linux: sudo systemctl start docker"
  exit 1
fi
```

If not on the feature branch, check out `openspec/<change-id>`. If no implementation commits exist, abort with guidance.

### 3. Deploy Phase

**Phase name:** `deploy`
**Criticality:** Critical (stops validation on failure)

```bash
# Find docker-compose file
COMPOSE_FILE=$(find "$PROJECT_ROOT" -maxdepth 2 -name "docker-compose.yml" | head -1)

if [ -z "$COMPOSE_FILE" ]; then
  echo "SKIP: No docker-compose.yml found. Skipping Deploy phase."
  echo "  Smoke tests will run against already-running services."
  DEPLOY_SKIPPED=true
else
  COMPOSE_DIR=$(dirname "$COMPOSE_FILE")
  LOG_FILE="/tmp/validate-feature-${CHANGE_ID}-$(date +%s).log"

  echo "Starting services with DEBUG logging..."
  echo "  Compose file: $COMPOSE_FILE"
  echo "  Log file: $LOG_FILE"

  # Start services with DEBUG logging, redirect output to log file
  LOG_LEVEL=DEBUG docker-compose -f "$COMPOSE_FILE" up -d 2>&1 | tee "$LOG_FILE"

  # Wait for health checks
  echo "Waiting for services to be healthy..."
  docker-compose -f "$COMPOSE_FILE" ps

  # Wait for PostgreSQL health check (up to 30 seconds)
  for i in $(seq 1 30); do
    if docker-compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
      echo "PostgreSQL is ready"
      break
    fi
    sleep 1
  done

  # Wait for REST API (up to 15 seconds)
  for i in $(seq 1 15); do
    if curl -s http://localhost:3000/ > /dev/null 2>&1; then
      echo "REST API is ready"
      break
    fi
    sleep 1
  done

  # Collect running container logs in background
  docker-compose -f "$COMPOSE_FILE" logs -f >> "$LOG_FILE" 2>&1 &
  LOG_PID=$!

  DEPLOY_RESULT="pass"
fi
```

If Deploy fails, report the failure with Docker logs and skip to Teardown.

### 4. Smoke Phase

**Phase name:** `smoke`
**Criticality:** Critical (stops validation on failure)

Run the reusable pytest smoke test suite against the live services. The suite is configurable via environment variables so it works with any deployed HTTP API.

```bash
# Configure for the target API (adjust per project)
export API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
export API_HEALTH_ENDPOINT="${API_HEALTH_ENDPOINT:-/health}"
export API_READY_ENDPOINT="${API_READY_ENDPOINT:-/ready}"
export API_AUTH_HEADER="${API_AUTH_HEADER:-X-Admin-Key}"
export API_AUTH_VALUE="${API_AUTH_VALUE:-$ADMIN_API_KEY}"
export API_PROTECTED_ENDPOINT="${API_PROTECTED_ENDPOINT:-/api/v1/settings/prompts}"
export API_CORS_ORIGIN="${API_CORS_ORIGIN:-http://localhost:5173}"

# Run smoke tests
SKILL_DIR="$(git rev-parse --show-toplevel)/skills/validate-feature"
pytest "$SKILL_DIR/scripts/smoke_tests/" -v --tb=short 2>&1
SMOKE_EXIT=$?

if [ $SMOKE_EXIT -eq 0 ]; then
  SMOKE_RESULT="pass"
elif [ $SMOKE_EXIT -eq 5 ]; then
  # Exit code 5 = no tests collected (services not running, all skipped)
  SMOKE_RESULT="skip"
  echo "SKIP: Services not running — smoke tests auto-skipped"
else
  SMOKE_RESULT="fail"
  SMOKE_FAILED=true
fi
```

The smoke tests cover:
- **Health**: Health and readiness endpoints respond with 2xx
- **Auth enforcement**: No credentials → 401/403, valid credentials → 2xx, garbage credentials rejected
- **CORS**: Preflight returns correct Access-Control-* headers (skipped if CORS not configured)
- **Error sanitization**: Error responses don't leak filesystem paths, stack traces, internal IPs, or credentials
- **Security headers**: Content-Type set correctly, Server header not overly detailed, no X-Powered-By

If Smoke fails (SMOKE_EXIT != 0 and != 5), stop validation and skip to Teardown.

### 5. E2E Phase

**Phase name:** `e2e`
**Criticality:** Non-critical (continues on failure)

```bash
# Skip if --skip-e2e flag was provided
if [ "$SKIP_E2E" = true ]; then
  echo "SKIP: E2E phase skipped (--skip-e2e flag)"
else
  # Check if pytest-playwright is installed
  if python -c "import playwright" 2>/dev/null; then
    PLAYWRIGHT_AVAILABLE=true
  else
    PLAYWRIGHT_AVAILABLE=false
  fi

  # Check if E2E tests exist
  E2E_DIR=$(find "$PROJECT_ROOT" -path "*/tests/e2e" -type d | head -1)

  if [ -z "$E2E_DIR" ]; then
    echo "SKIP: No tests/e2e/ directory found. Skipping E2E phase."
  elif [ "$PLAYWRIGHT_AVAILABLE" = false ]; then
    echo "SKIP: pytest-playwright not installed. To install:"
    echo "  pip install pytest-playwright"
    echo "  playwright install chromium"
  else
    echo "Running E2E tests from $E2E_DIR..."
    pytest "$E2E_DIR" -v --tb=short 2>&1
    E2E_EXIT=$?

    if [ $E2E_EXIT -eq 0 ]; then
      E2E_RESULT="pass"
    else
      E2E_RESULT="fail"
    fi
  fi
fi
```

### 5b. Architecture Diagnostics Phase

**Phase name:** `architecture`
**Criticality:** Non-critical (continues on failure)

Run architecture flow validation against the changed files:

```bash
# Get changed files relative to main
CHANGED_FILES=$(git diff --name-only main...HEAD | tr '\n' ',')

if [ -f "scripts/validate_flows.py" ] && [ -f "docs/architecture-analysis/architecture.graph.json" ]; then
  echo "Running architecture validation on changed files..."
  python scripts/validate_flows.py \
    --graph docs/architecture-analysis/architecture.graph.json \
    --output docs/architecture-analysis/architecture.diagnostics.json \
    --files "$CHANGED_FILES" 2>&1
  ARCH_EXIT=$?

  if [ $ARCH_EXIT -eq 0 ]; then
    ARCH_RESULT="pass"
    ARCH_ERRORS=$(python -c "import json; d=json.load(open('docs/architecture-analysis/architecture.diagnostics.json')); print(d['summary']['errors'])" 2>/dev/null || echo 0)
    ARCH_WARNINGS=$(python -c "import json; d=json.load(open('docs/architecture-analysis/architecture.diagnostics.json')); print(d['summary']['warnings'])" 2>/dev/null || echo 0)
    if [ "$ARCH_ERRORS" -gt 0 ]; then
      ARCH_RESULT="fail"
    elif [ "$ARCH_WARNINGS" -gt 0 ]; then
      ARCH_RESULT="warn"
    fi
  else
    ARCH_RESULT="fail"
  fi
else
  echo "SKIP: Architecture validation not available (missing scripts or artifacts)"
  echo "  Run 'make architecture' to generate architecture artifacts"
  ARCH_RESULT="skip"
fi
```

Report architecture diagnostics including broken flows, missing test coverage, orphaned code, and disconnected endpoints.

### 6. Spec Compliance Phase

**Phase name:** `spec`
**Criticality:** Non-critical (continues on failure)

Read OpenSpec spec deltas for the change and verify each scenario against the live system:

1. Read `$OPENSPEC_PATH/changes/<change-id>/specs/` to find all spec delta files
2. For each delta file, extract `#### Scenario:` blocks
3. For each scenario, interpret the WHEN/THEN/AND clauses and verify against the live system:
   - **API scenarios**: Make HTTP requests to the running service and verify responses
   - **MCP tool scenarios**: Invoke MCP tools via the Python module and check results
   - **Database scenarios**: Query PostgreSQL directly and verify state
   - **Configuration scenarios**: Check file existence, content, or environment variables
4. Record pass/fail per scenario with details on any mismatches

**Example verification pattern:**

```python
# For a scenario like:
# WHEN agent calls discover_agents(capability?, status?)
# THEN system returns array of {agent_id, agent_type, capabilities, status, ...}

import httpx
response = httpx.get("http://localhost:3000/agent_sessions?status=eq.active")
assert response.status_code == 200
data = response.json()
# Verify response shape matches scenario expectations
```

Report results in a structured table:

```
Spec Compliance Results:
  ✓ Session Continuity > Agent writes handoff document
  ✓ Session Continuity > Agent reads previous handoff
  ✗ Agent Discovery > No matching agents: Expected empty array, got 500
  ✓ Heartbeat > Agent heartbeat updates timestamp
```

### 7. Log Analysis Phase

**Phase name:** `logs`
**Criticality:** Non-critical (continues on failure)

Scan the collected log file for warning signs:

```bash
if [ -f "$LOG_FILE" ]; then
  echo "Analyzing logs: $LOG_FILE"
  echo "Log file size: $(wc -l < "$LOG_FILE") lines"

  # Count by severity
  WARNINGS=$(grep -c -i "WARNING" "$LOG_FILE" 2>/dev/null || echo 0)
  ERRORS=$(grep -c -i "ERROR" "$LOG_FILE" 2>/dev/null || echo 0)
  CRITICALS=$(grep -c -i "CRITICAL" "$LOG_FILE" 2>/dev/null || echo 0)

  # Check for specific patterns
  DEPRECATIONS=$(grep -c -i "deprecat" "$LOG_FILE" 2>/dev/null || echo 0)
  STACK_TRACES=$(grep -c "Traceback" "$LOG_FILE" 2>/dev/null || echo 0)
  UNHANDLED=$(grep -c "unhandled\|uncaught" "$LOG_FILE" 2>/dev/null || echo 0)

  echo "  Warnings: $WARNINGS"
  echo "  Errors: $ERRORS"
  echo "  Critical: $CRITICALS"
  echo "  Deprecations: $DEPRECATIONS"
  echo "  Stack traces: $STACK_TRACES"
  echo "  Unhandled exceptions: $UNHANDLED"

  # Show context for errors and critical entries
  if [ "$ERRORS" -gt 0 ] || [ "$CRITICALS" -gt 0 ]; then
    echo ""
    echo "Error/Critical entries with context:"
    grep -n -i -B2 -A2 "ERROR\|CRITICAL" "$LOG_FILE" | head -50
  fi

  # Show deprecation warnings
  if [ "$DEPRECATIONS" -gt 0 ]; then
    echo ""
    echo "Deprecation notices:"
    grep -n -i "deprecat" "$LOG_FILE" | head -20
  fi
else
  echo "SKIP: No log file available (Deploy phase was skipped or no services started)"
fi
```

Categorize findings by severity:
- **Critical**: CRITICAL log entries, unhandled exceptions, stack traces
- **Warning**: WARNING entries, deprecation notices
- **Info**: Unusual patterns, high log volume from specific components

### 8. CI/CD Status Phase

**Phase name:** `ci`
**Criticality:** Non-critical (continues on failure)

```bash
# Skip if --skip-ci flag was provided
if [ "$SKIP_CI" = true ]; then
  echo "SKIP: CI/CD check skipped (--skip-ci flag)"
else
  # Check if GitHub remote is configured
  if git remote get-url origin > /dev/null 2>&1; then
    # Check if PR exists for this branch
    PR_URL=$(gh pr view "openspec/$CHANGE_ID" --json url --jq '.url' 2>/dev/null)

    if [ -n "$PR_URL" ]; then
      echo "PR found: $PR_URL"
      echo ""
      echo "CI/CD Check Status:"
      gh pr checks "openspec/$CHANGE_ID" 2>/dev/null || echo "  No CI checks configured yet"
    else
      echo "No PR found for openspec/$CHANGE_ID"
      echo "Checking latest workflow runs..."
      gh run list --branch "openspec/$CHANGE_ID" --limit 3 2>/dev/null || echo "  No workflow runs found"
    fi
  else
    echo "SKIP: No GitHub remote configured"
  fi
fi
```

### 9. Teardown

Stop services and clean up:

```bash
# Only teardown if we started services (Deploy phase ran)
if [ "$DEPLOY_SKIPPED" != true ] && [ -n "$COMPOSE_FILE" ]; then
  echo "Stopping services..."

  # Stop background log collection
  if [ -n "$LOG_PID" ]; then
    kill $LOG_PID 2>/dev/null
  fi

  # Stop docker-compose services
  docker-compose -f "$COMPOSE_FILE" down

  echo "Services stopped"
fi

# Handle log file
if [ -f "$LOG_FILE" ]; then
  if [ "$ALL_PHASES_PASSED" = true ]; then
    rm "$LOG_FILE"
    echo "Log file removed (all phases passed)"
  else
    echo "Log file preserved for inspection: $LOG_FILE"
  fi
fi
```

### 10. Validation Report

Produce a structured summary of all phases:

```
## Validation Report: <change-id>

**Date**: YYYY-MM-DD HH:MM:SS
**Commit**: <short SHA>
**Branch**: openspec/<change-id>

### Phase Results

✓ Deploy: Services started (N containers, DEBUG logging enabled)
✓ Smoke: All health checks passed (API, MCP, database)
✗ E2E: 3/5 tests passed, 2 failures
  - test_login_flow: TimeoutError on /api/auth
  - test_dashboard_load: Element not found: #stats-panel
✓ Architecture: No broken flows (2 warnings: orphaned functions)
✓ Spec Compliance: 8/8 scenarios verified
⚠ Log Analysis: 3 warnings found
  - [WARNING] Deprecated function call: old_api_handler (line 142)
✓ CI/CD: All checks passing

### Result

**PASS** — Ready for `/cleanup-feature <change-id>`

_or_

**FAIL** — Address findings, then re-run `/validate-feature` or `/iterate-on-implementation`
```

Use these symbols:
- ✓ — Phase passed
- ✗ — Phase failed
- ⚠ — Phase passed with warnings
- ○ — Phase skipped

### 11. Persist Report

Write the validation report to the OpenSpec change directory:

```bash
REPORT_FILE="$OPENSPEC_PATH/changes/$CHANGE_ID/validation-report.md"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
COMMIT_SHA=$(git rev-parse --short HEAD)

# Write report (overwrites previous)
cat > "$REPORT_FILE" << EOF
# Validation Report: $CHANGE_ID

**Date**: $TIMESTAMP
**Commit**: $COMMIT_SHA
**Branch**: openspec/$CHANGE_ID

## Phase Results

<phase results from Step 10>

## Result

<PASS or FAIL with guidance>
EOF

echo "Report written to: $REPORT_FILE"
```

### 12. PR Comment

Post the validation report as a PR comment:

```bash
PR_NUMBER=$(gh pr view "openspec/$CHANGE_ID" --json number --jq '.number' 2>/dev/null)

if [ -n "$PR_NUMBER" ]; then
  gh pr comment "$PR_NUMBER" --body "$(cat <<EOF
## 🔍 Automated Validation Report

<contents of validation report from Step 10>

---
_Generated by \`/validate-feature $CHANGE_ID\` at $TIMESTAMP_
EOF
)"
  echo "Report posted to PR #$PR_NUMBER"
else
  echo "SKIP: No PR found for openspec/$CHANGE_ID — report not posted"
  echo "  Create a PR first, then re-run to post the report"
fi
```

---

## After Validation

**If all phases PASS:**
```
Ready for cleanup:
/cleanup-feature <change-id>
```

**If phases FAIL:**
```
Option 1: Fix findings and re-validate:
/iterate-on-implementation <change-id>
/validate-feature <change-id>

Option 2: Re-run specific failing phases:
/validate-feature <change-id> --phase smoke,spec

Option 3: Skip non-critical failures and proceed:
/cleanup-feature <change-id>
```

Present the validation report and let the user decide the next step.

## Output

- Validation report printed to console
- Report persisted to `openspec/changes/<change-id>/validation-report.md`
- Report posted as PR comment (if PR exists)
- Services cleaned up (if Deploy phase ran)
- Log file preserved (if failures occurred) or removed (if all passed)

## Next Step

After validation passes:
```
/cleanup-feature <change-id>
```
