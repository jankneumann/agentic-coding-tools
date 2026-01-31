# Advanced Coordination Patterns

These patterns extend the default worktree-based approach for special cases.

## Dependency Chains

For tasks with sequential dependencies, use bead blocking:

```bash
# Create dependency chain: A → B → C
A=$(bd add "Setup database schema")
B=$(bd add "Implement data models" --blocked-by $A)
C=$(bd add "Add API endpoints" --blocked-by $B)

# Only A is ready initially
# B becomes ready when A closes
# C becomes ready when B closes
```

## Fan-out / Fan-in

Multiple parallel tasks feeding into a final integration:

```bash
# Fan-out: parallel tasks
T1=$(bd add "Implement auth module")
T2=$(bd add "Implement user module")
T3=$(bd add "Implement settings module")

# Fan-in: integration depends on all
INTEGRATION=$(bd add "Integration tests" --blocked-by $T1 --blocked-by $T2 --blocked-by $T3)

# Spawn agents for ready beads (T1, T2, T3 get worktrees)
# INTEGRATION becomes ready only when all complete
```

## Shared Worktree Mode (Advanced)

For tightly coupled tasks where isolation isn't desired:

```bash
# Skip worktree creation - agents share working directory
# Use ONLY when tasks modify completely separate files
# Risk: race conditions, overwrites

bd ready --json | jq -r '.[] | .id' | while read bead_id; do
  TASK=$(bd show $bead_id --json | jq -r '.title')
  claude -p "Implement: $TASK (SHARED DIR - don't modify others' files)" &
done
wait

# Must manually review for conflicts
git diff
```

**⚠️ Not recommended** - use default worktree isolation instead.

## Progress Webhook

For long-running tasks, emit progress:

```bash
# Agent prompt includes progress reporting
claude -p "...
Report progress periodically:
curl -X POST http://localhost:8080/progress -d '{\"bead\":\"$bead_id\",\"status\":\"working\"}'
..."
```

## Timeout Handling

Prevent runaway agents:

```bash
TIMEOUT=900  # 15 minutes

bd ready --json | jq -r '.[] | .id' | while read bead_id; do
  TASK=$(bd show $bead_id --json | jq -r '.title')
  timeout $TIMEOUT claude -p "Implement: $TASK. Run: bd close $bead_id when done" || {
    echo "Agent timed out for bead $bead_id"
    bd add "RETRY: $TASK (previous attempt timed out)"
  } &
done
wait
```

## Conflict Detection

Check for conflicts before merging agent work:

```bash
# After agents complete, check for modified file overlap
MODIFIED_FILES=$(git diff --name-only HEAD)
CONFLICTS=$(echo "$MODIFIED_FILES" | sort | uniq -d)

if [ -n "$CONFLICTS" ]; then
  echo "Warning: Multiple agents modified these files:"
  echo "$CONFLICTS"
  echo "Manual conflict resolution required."
fi
```

## Resource Locking

For shared resources (databases, APIs), use lock files:

```bash
# In agent prompt:
"Before modifying shared config:
1. Check lock: [ -f /tmp/config.lock ] && sleep 5 && retry
2. Acquire lock: touch /tmp/config.lock
3. Make changes
4. Release lock: rm /tmp/config.lock"
```

## Batch Processing Large Task Lists

For many tasks, process in batches:

```bash
BATCH_SIZE=5
BATCH=0

bd ready --json | jq -r '.[] | .id' | while read bead_id; do
  if [ $((BATCH % BATCH_SIZE)) -eq 0 ] && [ $BATCH -gt 0 ]; then
    echo "Waiting for batch to complete..."
    wait
  fi
  
  TASK=$(bd show $bead_id --json | jq -r '.title')
  claude -p "Implement: $TASK" &
  BATCH=$((BATCH + 1))
done
wait
```
